"""Offline goal hunter regression for FotMob live-fallback source."""
import unittest
from unittest.mock import patch

import netrattler_lmg_fotmob as bot


def match(minute="68’", score="1 - 1", period=True):
    return {"id":1000014437,
            "home":{"name":"Tampines Rovers FC"}, "away":{"name":"Ratchaburi FC"},
            "status":{"ongoing":True,"started":True,"finished":False,
                      "cancelled":False,"utcTime":"2026-11-18T11:30:00Z",
                      "halfs":{"secondHalfStarted":"18.11.2026 13:33:53"} if period else {},
                      "scoreStr":score,
                      "liveTime":{"short":minute,"basePeriod":90 if period else 45}}}


def daily(minute="68’", score="1 - 1", period=True):
    return {"leagues":[{"name":"AFC Champions League Two",
                        "matches":[match(minute,score,period)]}]}


def detail():
    return {"content":{"stats":{"Periods":{"All":{"stats":[
        {"key":"top_stats","stats":[
            {"key":"total_shots","title":"Total shots","stats":[12,10]},
            {"key":"ShotsOnTarget","title":"Shots on target","stats":[5,4]},
            {"key":"corners","title":"Corners","stats":[2,5]}
        ]},
        {"key":"shots","stats":[
            {"key":"ShotsOnTarget","title":"Shots on target","stats":[5,4]},
            {"key":"total_shots","title":"Total shots","stats":[12,10]}
        ]}
    ]}}}}}


class FotmobTest(unittest.TestCase):
    def test_64_no_signal_65_signal(self):
        self.assertEqual(bot.fixtures_from_fotmob(daily("64’")),[])
        got=bot.fixtures_from_fotmob(daily("65’"))
        self.assertEqual((got[0]["minute"],got[0]["hg"],got[0]["ag"]),(65,1,1))

    def test_no_first_half_false_live_or_missing_score(self):
        self.assertEqual(bot.fixtures_from_fotmob(daily("65’",period=False)),[])
        self.assertEqual(bot.fixtures_from_fotmob(daily("65’",score="bad")),[])
        wrong=daily()
        wrong["leagues"][0]["matches"][0]["status"]["ongoing"]=False
        self.assertEqual(bot.fixtures_from_fotmob(wrong),[])

    def test_strict_actual_full_match_stats(self):
        fixture=bot.fixtures_from_fotmob(daily())[0]
        metrics=bot.metrics_from_fotmob(detail(),fixture)
        self.assertEqual((metrics["shots"],metrics["sot"],metrics["corners"]),(22,9,7))
        self.assertEqual(metrics["tier"],"PREMIUM")
        wrong=detail()
        wrong["content"]["stats"]["Periods"]={"FirstHalf":{"stats":[]}}
        self.assertIsNone(bot.metrics_from_fotmob(wrong,fixture))

    def test_send_without_any_bookmaker_or_api_football(self):
        with patch.dict("os.environ",{"LMG_SEND":"true","API_FOOTBALL_KEYS":"",
                                     "PULSESCORE_API_KEY":""}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(bot.common,"_get",return_value=detail()) as get, \
             patch.object(bot.common,"reserve_alert",return_value="match-key") as reserve, \
             patch.object(bot.common,"send_alert",return_value=9001) as send, \
             patch.object(bot.common,"mark_sent") as sent:
            report=bot.run()
        self.assertEqual(report["qualified"],1)
        self.assertEqual(report["sent"],1)
        self.assertEqual(report["odds_calls"],0)
        reserve.assert_called_once()
        send.assert_called_once()
        sent.assert_called_once_with("match-key",9001)
        self.assertEqual(get.call_count,1)

    def test_missing_shots_no_send(self):
        bad={"content":{"stats":{"Periods":{"All":{"stats":[]}}}}}
        with patch.dict("os.environ",{"LMG_SEND":"true"}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(bot.common,"_get",return_value=bad), \
             patch.object(bot.common,"send_alert") as send:
            report=bot.run()
        self.assertEqual(report["sent"],0)
        self.assertEqual(report["missing_stats"],1)
        send.assert_not_called()


    def test_80_standard_81_to_85_premium_only_and_86_blocked(self):
        for minute in (80, 81, 85):
            fixture=bot.fixtures_from_fotmob(daily(str(minute)+"’"))[0]
            observed=bot.metrics_from_fotmob(detail(),fixture)
            tier=bot.common.select_goal_tier(fixture,observed)
            self.assertEqual(tier,"PREMIUM")
            weaker=dict(observed,shots=12,sot=6)
            self.assertEqual(bot.common.select_goal_tier(fixture,weaker),
                             "STANDARD" if minute==80 else None)
        self.assertEqual(bot.fixtures_from_fotmob(daily("86’")),[])
        self.assertEqual(bot.fixtures_from_fotmob(daily("90’")),[])

    def test_late_tips_need_real_corners_when_provided(self):
        fixture=bot.fixtures_from_fotmob(daily("83’"))[0]
        m=dict(bot.metrics_from_fotmob(detail(),fixture),shots=22,sot=9,corners=3)
        self.assertIsNone(bot.common.select_goal_tier(fixture,m))
        m["corners"]=None
        self.assertEqual(bot.common.select_goal_tier(fixture,m),"PREMIUM")

    def test_espn_backup_when_no_fotmob_late_match(self):
        with patch.dict("os.environ",{"LMG_SEND":"false"}), \
             patch.object(bot,"fetch_fotmob",return_value=daily("60’")), \
             patch.object(bot.common,"main",return_value={"sent":0,"qualified":0}) as backup:
            r=bot.run()
        self.assertEqual(r["sent"],0)
        backup.assert_called_once()



if __name__=="__main__":
    unittest.main()
