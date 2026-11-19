"""Offline regression: API-Football recovery must prove exact real match identity."""
import copy
import datetime as dt
import os
import unittest
from unittest.mock import patch

import netrattler_lmg_api_fallback as api
from test_netrattler_lmg_fotmob import daily
from netrattler_lmg_fotmob import fixtures_from_fotmob


def live_row():
    return {"fixture":{"id":998877,"date":"2026-11-18T11:30:00+00:00",
                       "status":{"short":"2H","elapsed":68}},
            "teams":{"home":{"id":111,"name":"Tampines Rovers FC"},
                     "away":{"id":222,"name":"Ratchaburi FC"}},
            "goals":{"home":1,"away":1}}


def live_stats():
    return [
        {"team":{"id":111},"statistics":[
            {"type":"Total Shots","value":12},
            {"type":"Shots on Goal","value":5},
            {"type":"Corner Kicks","value":4}]},
        {"team":{"id":222},"statistics":[
            {"type":"Total Shots","value":10},
            {"type":"Shots on Goal","value":4},
            {"type":"Corner Kicks","value":5}]},
    ]


class VerifiedApiFallbackTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures_from_fotmob(daily())[0]

    def test_only_unique_matching_event_keeps_original_fotmob_id(self):
        result=api.unique_live_match(self.fx,[live_row()])
        self.assertEqual(result["fixture_id"],998877)
        self.assertEqual(self.fx["fixture_id"],1000014437)
        self.assertEqual(result["home_id"],111)

    def test_reject_wrong_game_conditions(self):
        for change in (
            lambda x: x["teams"]["away"].update(name="Unrelated FC"),
            lambda x: x["goals"].update(away=2),
            lambda x: x["fixture"]["status"].update(elapsed=80),
            lambda x: x["fixture"]["status"].update(short="1H"),
            lambda x: x["fixture"].update(date="2026-11-18T15:30:00Z"),
            lambda x: x["teams"]["home"].update(id=None),
        ):
            sample=copy.deepcopy(live_row())
            change(sample)
            self.assertIsNone(api.unique_live_match(self.fx,[sample]))
        second=copy.deepcopy(live_row())
        second["fixture"]["id"]=999999
        self.assertIsNone(api.unique_live_match(self.fx,[live_row(),second]))

    def test_stats_only_exact_provider_team_ids_and_real_counts(self):
        identity=api.unique_live_match(self.fx,[live_row()])
        m=api.verified_stats(live_stats(),identity)
        self.assertEqual((m["shots"],m["sot"],m["corners"]),(22,9,9))
        self.assertEqual(m["teams"]["home"]["shots"],12)
        self.assertEqual(m["teams"]["away"]["sot"],4)
        self.assertNotIn("xg",m["teams"]["home"])
        for modifier in (
            lambda r: r[1]["team"].update(id=8888),
            lambda r: r[1]["statistics"].pop(0),
            lambda r: r[0]["statistics"][1].update(value=19),
        ):
            bad=copy.deepcopy(live_stats())
            modifier(bad)
            self.assertIsNone(api.verified_stats(bad,identity))

    def test_absent_key_and_cooldown_never_use_network(self):
        with patch.dict(os.environ,{"API_FOOTBALL_KEYS":"","API_FOOTBALL_KEY":""}), \
             patch.object(api,"reserve_source_calls",side_effect=AssertionError("budget")), \
             patch.object(api,"_query",side_effect=AssertionError("network")):
            self.assertIsNone(api.recover(self.fx))
        with patch.dict(os.environ,{"API_FOOTBALL_KEYS":"test-key"}), \
             patch.object(api,"reserve_source_calls",return_value=False), \
             patch.object(api,"_query",side_effect=AssertionError("network")):
            self.assertIsNone(api.recover(self.fx))

    def test_verified_recovery_never_guesses_quota(self):
        with patch.dict(os.environ,{"API_FOOTBALL_KEYS":"test-key"}), \
             patch.object(api,"reserve_source_calls",return_value=True) as reserve, \
             patch.object(api,"_query",side_effect=[
                 ([live_row()],80),(live_stats(),78)]) as query:
            result=api.recover(self.fx)
        self.assertEqual(result["shots"],22)
        self.assertEqual(query.call_count,2)
        self.assertEqual(reserve.call_args.kwargs["max_per_day"],24)
        self.assertEqual(reserve.call_args.kwargs["cooldown_seconds"],3600)

    def test_quota_remaining_safeguard_skips_stats_request(self):
        with patch.dict(os.environ,{"API_FOOTBALL_KEYS":"test-key"}), \
             patch.object(api,"reserve_source_calls",return_value=True), \
             patch.object(api,"_query",return_value=([live_row()],19)) as query:
            self.assertIsNone(api.recover(self.fx))
        query.assert_called_once()

    def test_unavailable_api_returns_none_without_fabricating_metrics(self):
        import requests
        with patch.dict(os.environ,{"API_FOOTBALL_KEYS":"test-key"}), \
             patch.object(api,"reserve_source_calls",return_value=True), \
             patch.object(api,"_query",side_effect=requests.Timeout()):
            self.assertIsNone(api.recover(self.fx))


if __name__ == "__main__":
    unittest.main()
