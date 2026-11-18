"""Offline contract tests: never use live provider data as historical/settlement odds."""
import os
import unittest
from unittest.mock import patch

from netrattler_specialized_sources import (
    EXAMPLE_SEASON, SOURCES, _count, audit, coverage_report,
    fetch_footystats_history, normalize_footystats_match,
)

MATCH = {"status": "complete", "id": 124, "homeID": 18, "awayID": 25,
         "homeGoalCount": 2, "awayGoalCount": 1,
         "team_a_shots": 13, "team_b_shots": 7, "team_a_shotsOnTarget": 5,
         "team_b_shotsOnTarget": 3, "team_a_corners": -1,
         "team_b_corners": 4, "date_unix": 1540000000}

class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
        self.ok = 200 <= status < 300
    def json(self):
        return self.data

class SpecializedSourceTests(unittest.TestCase):
    def test_policy_never_claims_unlicensed_live(self):
        self.assertEqual(set(SOURCES), {"footystats", "sofascore", "overlyzer",
                                        "statisticsports", "besoccer"})
        self.assertTrue(all(source["live"] is False for source in SOURCES.values()))
        self.assertEqual(SOURCES["footystats"]["api"], "official_with_key")
    def test_sentinels_not_zeros(self):
        self.assertIsNone(_count(-1))
        self.assertIsNone(_count("-2"))
        self.assertEqual(_count(0), 0)
        self.assertIsNone(_count(True))
    def test_completed_only(self):
        row = normalize_footystats_match(MATCH, EXAMPLE_SEASON)
        self.assertEqual(row["home_goals"], 2)
        self.assertIsNone(row["home_corners"])
        self.assertFalse(row["live_eligible"])
        self.assertFalse(row["odds_eligible"])
        self.assertIsNone(normalize_footystats_match({**MATCH, "status": "incomplete"}, EXAMPLE_SEASON))
        self.assertIsNone(normalize_footystats_match({**MATCH, "awayID": 18}, EXAMPLE_SEASON))
    def test_bounded_history_and_dedup(self):
        calls = []
        def fake(url, **kwargs):
            calls.append((url, kwargs))
            return Reply({"success": True, "data": [MATCH, MATCH]})
        rows = fetch_footystats_history(api_key="example", season_id=EXAMPLE_SEASON, get=fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["params"]["key"], "example")
        self.assertEqual(coverage_report(rows)["with_corners_both"], 0)
    def test_refuse_bad_demo_id(self):
        with self.assertRaisesRegex(ValueError, "restricted"):
            fetch_footystats_history(api_key="example", season_id=1, get=lambda *a, **k: None)
    def test_bad_schema_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "schema_mismatch"):
            fetch_footystats_history(api_key="example", season_id=EXAMPLE_SEASON,
                                     get=lambda *a, **k: Reply({"success": True, "data": {}}))
    def test_inconsistent_duplicate_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "inconsistent_duplicate"):
            fetch_footystats_history(api_key="example", season_id=EXAMPLE_SEASON,
                get=lambda *a, **k: Reply({"success": True, "data": [MATCH, {**MATCH,"homeGoalCount": 7}]}))
    def test_no_secret_in_errors(self):
        class Boom(Exception):
            pass
        import requests
        def fail(*a, **k):
            raise requests.ConnectionError("https://provider/?key=MY_SECRET")
        with self.assertRaises(RuntimeError) as caught:
            fetch_footystats_history(api_key="MY_SECRET", season_id=EXAMPLE_SEASON, get=fail)
        self.assertNotIn("MY_SECRET", str(caught.exception))
    def test_missing_key_never_calls_network(self):
        with patch.dict(os.environ, {"FOOTYSTATS_API_KEY": ""}):
            report = audit()
        self.assertEqual(report["footystats_probe"]["status"], "skipped_missing_key")
        self.assertEqual(report["supabase_writes"], 0)
        self.assertFalse(report["live_signals_enabled"])

if __name__ == "__main__":
    unittest.main()
