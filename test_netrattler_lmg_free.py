"""Offline regression tests for no-odds 65'+ Goal Hunter signals."""
import datetime as dt
import unittest
from unittest.mock import patch

import netrattler_lmg_free as lmg

UTC = dt.timezone.utc


def fixture(minute=65, score=(0, 3)):
    return {"fixture_id": 1234, "minute": minute, "clock": str(minute) + "'",
            "home": "Lecce", "away": "Roma", "hg": score[0], "ag": score[1],
            "home_id": "10", "away_id": "20", "league": "Serie A",
            "kickoff": dt.datetime(2026, 11, 18, 12, tzinfo=UTC)}


def board(minute=65, score=(0, 3), period=2):
    return {"leagues": [{"name": "Serie A"}], "events": [{
        "id": "1234", "date": "2026-11-18T12:00:00Z",
        "status": {"period": period, "displayClock": f"{minute}:17", "type": {"state": "in"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": str(score[0]),
             "team": {"id": "10", "displayName": "Lecce"}},
            {"homeAway": "away", "score": str(score[1]),
             "team": {"id": "20", "displayName": "Roma"}}
        ]}]}]}


def stats():
    return {"boxscore": {"teams": [
        {"team": {"id": "10"}, "statistics": [
            {"name": "totalShots", "value": 10},
            {"name": "shotsOnTarget", "value": 4},
            {"name": "cornerKicks", "value": 3}]},
        {"team": {"id": "20"}, "statistics": [
            {"name": "totalShots", "value": 12},
            {"name": "shotsOnTarget", "value": 5},
            {"name": "cornerKicks", "value": 4}]}
    ]}}


class GoalHunterFreeTests(unittest.TestCase):
    def test_minute_64_no_alert_65_to_85_allowed_and_86_plus_blocked(self):
        self.assertEqual(lmg.fixtures_from_espn(board(64)), [])
        self.assertEqual(lmg.fixtures_from_espn(board(65))[0]["minute"], 65)
        self.assertEqual(lmg.fixtures_from_espn(board(85))[0]["minute"], 85)
        self.assertEqual(lmg.fixtures_from_espn(board(86)), [])
        self.assertEqual(lmg.fixtures_from_espn(board(90)), [])
        self.assertEqual(lmg.fixtures_from_espn(board(65, period=1)), [])

    def test_zero_zero_score_and_numeric_zero_are_valid(self):
        payload = board(65, (0, 0))
        payload["events"][0]["competitions"][0]["competitors"][0]["score"] = 0
        self.assertEqual(lmg.fixtures_from_espn(payload)[0]["hg"], 0)

    def test_missing_score_is_never_interpreted_as_zero(self):
        payload = board()
        payload["events"][0]["competitions"][0]["competitors"][0]["score"] = None
        self.assertEqual(lmg.fixtures_from_espn(payload), [])

    def test_real_espn_stats_and_no_missing_value_guess(self):
        metrics = lmg.metrics_from_espn(stats(), fixture())
        self.assertEqual(metrics["sot"], 9)
        self.assertEqual(metrics["tier"], "PREMIUM")
        broken = stats()
        broken["boxscore"]["teams"][1]["statistics"] = []
        self.assertIsNone(lmg.metrics_from_espn(broken, fixture()))

    def test_only_one_extra_goal_no_price_no_percent_no_two_goals(self):
        msg = lmg.format_tip(fixture(), lmg.metrics_from_espn(stats(), fixture()))
        self.assertIn("OVER 0.5 RESTSPIELZEIT", msg)
        self.assertIn("Noch mindestens 1 Tor", msg)
        self.assertNotIn("3.5", msg)
        self.assertNotIn("4.5", msg)
        self.assertNotIn(" @ ", msg)
        self.assertNotIn("%", msg)
        self.assertIn("0:3", msg)

    def test_real_pressure_signal_even_with_no_bookmaker_key(self):
        with patch.dict("os.environ", {"LMG_SEND": "false", "PULSESCORE_API_KEY": "",
                                    "API_FOOTBALL_KEYS": ""}), \
             patch.object(lmg, "_get", side_effect=[board(), stats()]) as request:
            result = lmg.main()
        self.assertEqual(result["qualified"], 1)
        self.assertEqual(result["odds_calls"], 0)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(request.call_count, 2)

    def test_signal_sent_exactly_once_and_without_odds(self):
        with patch.dict("os.environ", {"LMG_SEND": "true", "PULSESCORE_API_KEY": "",
                                    "API_FOOTBALL_KEYS": ""}), \
             patch.object(lmg, "_get", side_effect=[board(), stats()]), \
             patch.object(lmg, "reserve_alert", return_value="1234") as reserve, \
             patch.object(lmg, "send_alert", return_value=777) as send, \
             patch.object(lmg, "mark_sent") as settle:
            result = lmg.main()
        self.assertEqual(result["sent"], 1)
        reserve.assert_called_once()
        send.assert_called_once()
        settle.assert_called_once_with("1234", 777)

    def test_duplicate_signal_not_sent_again(self):
        with patch.dict("os.environ", {"LMG_SEND": "true"}), \
             patch.object(lmg, "_get", side_effect=[board(), stats()]), \
             patch.object(lmg, "reserve_alert", return_value=None), \
             patch.object(lmg, "send_alert") as send:
            result = lmg.main()
        self.assertEqual(result["sent"], 0)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
