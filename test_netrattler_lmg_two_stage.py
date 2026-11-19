"""Offline two-stage discovery/deep polling tests: never network or Telegram."""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch

import netrattler_lmg_two_stage as stage
import netrattler_lmg_fotmob as fotmob
from test_netrattler_lmg_fotmob import daily, detail


def fake_feed(minute="68’",score="1 - 1"):
    return daily(minute=minute,score=score)


class GoalHunterTwoStageTests(unittest.TestCase):
    def test_pre_watch_requires_zero_zero_and_second_half(self):
        zero=stage.discover(fake_feed("60’","0 - 0"))
        self.assertEqual(len(zero),1)
        self.assertEqual(zero[0]["minute"],60)
        self.assertEqual(stage.discover(fake_feed("60’","1 - 0")),[])
        self.assertEqual(stage.discover(fake_feed("59’","0 - 0")),[])
        self.assertEqual(stage.discover(fake_feed("86’","0 - 0")),[])
        payload=fake_feed()
        payload["leagues"][0]["matches"][0]["status"]["halfs"]={}
        payload["leagues"][0]["matches"][0]["status"]["liveTime"]["basePeriod"]=45
        self.assertEqual(stage.discover(payload),[])

    def test_league_filter_and_unique_event_ids(self):
        feed=fake_feed()
        feed["leagues"][0]["matches"].append(copy.deepcopy(feed["leagues"][0]["matches"][0]))
        self.assertEqual(len(stage.discover(feed)),1)
        self.assertEqual(len(stage.discover(feed,league_filter=("AFC Champions League Two",))),1)
        self.assertEqual(stage.discover(feed,league_filter=("English Premier League",)),[])

    def test_bounded_polling_and_no_send_in_dry_run(self):
        calls=[]
        waits=[]
        with patch.dict(os.environ,{"LMG_SEND":"false","LMG_SHADOW_ENABLED":"false",
                                     "LMG_TARGET_LEAGUES":""}), \
             patch.object(stage.common,"reserve_alert",side_effect=AssertionError("reserve not allowed")), \
             patch.object(stage.common,"send_alert",side_effect=AssertionError("Telegram not allowed")):
            r=stage.run(feed=fake_feed(),cycles=3,sleep=waits.append,
                        fetch=lambda url,params: calls.append(params["matchId"]) or detail())
        self.assertEqual(r["poll_cycles"],3)
        self.assertEqual(r["details"],3)
        self.assertEqual(waits,[75,75])
        self.assertEqual(len(calls),3)
        self.assertEqual(r["sent"],0)

    def test_no_unverified_early_tip_even_if_stats_available(self):
        fixtures=stage.discover(fake_feed("60’","0 - 0"))
        with patch.object(stage.common,"reserve_alert",side_effect=AssertionError("early send")), \
             patch.object(stage.common,"send_alert",side_effect=AssertionError("early telegram")):
            r=stage.poll_once(fixtures,first_pass=True,send=True,shadow=False,
                              fetch=lambda url,params:detail())
        self.assertEqual(r["sent"],0)

    def test_valid_tip_may_send_first_pass_only_not_with_stale_score(self):
        candidates=stage.discover(fake_feed("68’","1 - 1"))
        with patch.object(stage.common,"reserve_alert",return_value="event-1") as reserve, \
             patch.object(stage.common,"send_alert",return_value=123) as send, \
             patch.object(stage.common,"mark_sent") as marked:
            first=stage.poll_once(candidates,first_pass=True,send=True,shadow=False,
                                  fetch=lambda url,params:detail())
            next_poll=stage.poll_once(candidates,first_pass=False,send=True,shadow=False,
                                      fetch=lambda url,params:detail())
        self.assertEqual(first["sent"],1)
        self.assertEqual(next_poll["sent"],0)
        reserve.assert_called_once()
        send.assert_called_once()
        marked.assert_called_once_with("event-1",123)

    def test_errors_fail_closed_and_dont_emit_fake_stats(self):
        candidates=stage.discover(fake_feed())
        with patch.object(stage.common,"send_alert",side_effect=AssertionError("telegram")):
            r=stage.poll_once(candidates,first_pass=True,send=True,shadow=False,
                              fetch=lambda *a,**k:{})
        self.assertEqual(r["sent"],0)
        self.assertEqual(r["missing_stats"],1)

    def test_invalid_cycles_rejected(self):
        for cycles in (0,4,1.5,True):
            with self.subTest(cycles=cycles), self.assertRaises(ValueError):
                stage.run(feed=fake_feed(),cycles=cycles,sleep=lambda _:None,
                          fetch=lambda *a,**k:detail())


if __name__=="__main__":
    unittest.main()
