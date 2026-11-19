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

    def test_per_team_stats_and_optional_decimal_xg(self):
        fixture=bot.fixtures_from_fotmob(daily())[0]
        payload=detail()
        payload["content"]["stats"]["Periods"]["All"]["stats"].append({
            "key":"expected_goals","title":"Expected goals","stats":["1.25","0.87"]})
        m=bot.metrics_from_fotmob(payload,fixture)
        self.assertEqual(m["teams"]["home"],{"shots":12,"sot":5,"corners":2,"xg":1.25})
        self.assertEqual(m["teams"]["away"],{"shots":10,"sot":4,"corners":5,"xg":0.87})
        text=bot.common.format_tip(fixture,m)
        self.assertIn("Tampines Rovers FC: Schüsse 12",text)
        self.assertIn("Ratchaburi FC: Schüsse 10",text)
        self.assertIn("xG 1.25",text)
        self.assertIn("xG 0.87",text)
        self.assertNotIn("Quote",text)

    def test_missing_xg_is_omitted_not_invented(self):
        fixture=bot.fixtures_from_fotmob(daily())[0]
        m=bot.metrics_from_fotmob(detail(),fixture)
        self.assertNotIn("xg",m["teams"]["home"])
        self.assertNotIn("xG",bot.common.format_tip(fixture,m))

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
        self.assertEqual(report["no_tip_reason"],"missing_verified_live_stats")
        send.assert_not_called()


    def test_repeated_fixture_is_explained_not_sent_twice(self):
        with patch.dict("os.environ",{"LMG_SEND":"true","LMG_SHADOW_ENABLED":"false"}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(bot.common,"_get",return_value=detail()), \
             patch.object(bot.common,"reserve_alert",return_value=None), \
             patch.object(bot.common,"send_alert") as send:
            report=bot.run()
        self.assertEqual(report["qualified"],1)
        self.assertEqual(report["already_alerted"],1)
        self.assertEqual(report["no_tip_reason"],"already_alerted")
        self.assertEqual(report["sent"],0)
        send.assert_not_called()

    def test_dry_run_is_explicit(self):
        with patch.dict("os.environ",{"LMG_SEND":"false","LMG_SHADOW_ENABLED":"false"}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(bot.common,"_get",return_value=detail()), \
             patch.object(bot.common,"send_alert") as send:
            report=bot.run()
        self.assertEqual(report["no_tip_reason"],"dry_run")
        send.assert_not_called()

    def test_recover_stats_only_for_same_live_game_with_fotmob_id(self):
        import netrattler_lmg_free as common
        fx=bot.fixtures_from_fotmob(daily())[0]
        scoreboard={"leagues":[{"name":"ASEAN Club Championship"}],"events":[{
            "id":"99123","date":"2026-11-18T11:30:00Z",
            "status":{"period":2,"displayClock":"68:00","type":{"state":"in"}},
            "competitions":[{"competitors":[
                {"homeAway":"home","score":"1",
                 "team":{"id":"10","displayName":"Tampines Rovers FC"}},
                {"homeAway":"away","score":"1",
                 "team":{"id":"20","displayName":"Ratchaburi FC"}}]}]}]}
        summary={"boxscore":{"teams":[
            {"team":{"id":"10"},"statistics":[
                {"name":"totalShots","value":11},{"name":"shotsOnTarget","value":5},
                {"name":"cornerKicks","value":3}]},
            {"team":{"id":"20"},"statistics":[
                {"name":"totalShots","value":12},{"name":"shotsOnTarget","value":4},
                {"name":"cornerKicks","value":5}]}]}}
        with patch.object(common,"_get",return_value=summary):
            metrics=bot.recover_espn_metrics(fx,scoreboard)
        self.assertEqual(metrics["shots"],23)
        self.assertEqual(metrics["sot"],9)
        self.assertEqual(metrics["teams"]["home"]["shots"],11)
        self.assertEqual(metrics["teams"]["away"]["corners"],5)
        self.assertNotIn("xg",metrics["teams"]["home"])
        self.assertEqual(fx["fixture_id"],1000014437)

        wrong=__import__("copy").deepcopy(scoreboard)
        wrong["events"][0]["competitions"][0]["competitors"][1]["team"]["displayName"]="Another Team"
        with patch.object(common,"_get") as get:
            self.assertIsNone(bot.recover_espn_metrics(fx,wrong))
        get.assert_not_called()

        wrong=__import__("copy").deepcopy(scoreboard)
        wrong["events"][0]["status"]["displayClock"]="80:00"
        with patch.object(common,"_get") as get:
            self.assertIsNone(bot.recover_espn_metrics(fx,wrong))
        get.assert_not_called()

        with patch.dict("os.environ",{"LMG_SEND":"true"}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(common,"_get",side_effect=[
                 {"content":{"stats":{"Periods":{"All":{"stats":[]}}}}},
                 scoreboard,summary]), \
             patch.object(common,"reserve_alert",return_value="1000014437"), \
             patch.object(common,"send_alert",return_value=301) as send, \
             patch.object(common,"mark_sent") as marked:
            report=bot.run()
        self.assertEqual(report["espn_recovered"],1)
        self.assertEqual(report["qualified"],1)
        self.assertEqual(report["sent"],1)
        self.assertEqual(send.call_args.args[0]["fixture_id"],1000014437)
        marked.assert_called_once_with("1000014437",301)

    def test_optional_verified_api_football_recovery_uses_original_fotmob_fixture(self):
        empty={"content":{"stats":{"Periods":{"All":{"stats":[]}}}}}
        verified=bot.metrics_from_fotmob(detail(),bot.fixtures_from_fotmob(daily())[0])
        with patch.dict("os.environ",{"LMG_SEND":"true","LMG_SHADOW_ENABLED":"false",
                                     "API_FOOTBALL_KEYS":"offline-test","API_FOOTBALL_KEY":""}), \
             patch.object(bot,"fetch_fotmob",return_value=daily()), \
             patch.object(bot.common,"_get",side_effect=[empty,{"events":[]}]), \
             patch("netrattler_lmg_api_fallback.recover",return_value=verified) as recovery, \
             patch.object(bot.common,"reserve_alert",return_value="1000014437"), \
             patch.object(bot.common,"send_alert",return_value=451) as send, \
             patch.object(bot.common,"mark_sent") as marked:
            report=bot.run()
        self.assertEqual(report["espn_recovered"],0)
        self.assertEqual(report["api_football_checked"],1)
        self.assertEqual(report["api_football_recovered"],1)
        self.assertEqual(report["sent"],1)
        recovery.assert_called_once()
        self.assertEqual(send.call_args.args[0]["fixture_id"],1000014437)
        marked.assert_called_once_with("1000014437",451)

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
