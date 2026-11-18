"""Regression tests for the safe historic merge and live-only replay boundary."""
import unittest
from copy import deepcopy

from netrattler_specialized_merge_backtest import (
    merge_historical_sources, replay_late_goal_predictions,
)

A = {
    "source": "footystats", "data_kind": "historical_completed_match",
    "live_eligible": False, "odds_eligible": False, "event_id": "111",
    "home_id": "14", "away_id": "15", "kickoff_unix": 1540000000,
    "home_goals": 2, "away_goals": 1, "home_shots": 10, "away_shots": 6,
    "home_sot": 5, "away_sot": 2, "home_corners": 4, "away_corners": 3,
}
B = {
    **A, "source": "fotmob", "event_id": "882",
    "home_id": "777", "away_id": "888",
}
MAP = {
    "footystats:111": {
        "canonical_id": "match-1", "home_id": "14", "away_id": "15",
        "kickoff_unix": 1540000000,
    },
    "fotmob:882": {
        "canonical_id": "match-1", "home_id": "777", "away_id": "888",
        "kickoff_unix": 1540000000,
    },
}
LIVE = {
    "data_kind": "verified_live_prediction", "canonical_fixture_id": "match-1",
    "identity_verified": True, "source_timestamp_verified": True,
    "model_locked": True, "minute": 75,
    "locked_at": "2026-11-18T17:00:00Z",
    "stats_at": "2026-11-18T17:14:00Z",
    "tip_at": "2026-11-18T17:15:00Z",
    "final_at": "2026-11-18T17:35:00Z",
    "score_at_tip": [1, 1], "final_score": [2, 1],
    "baseline_send": True, "extra_sources_send": True,
}

class MergeAndReplayTests(unittest.TestCase):
    def test_dedupe_identical_history(self):
        report = merge_historical_sources([A, deepcopy(A)])
        self.assertEqual(report["unique_matches"], 1)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(report["quarantined"], [])
        self.assertFalse(report["live_signals_enabled"])

    def test_unlinked_different_provider_ids_do_not_merge(self):
        report = merge_historical_sources([A, B])
        self.assertEqual(report["unique_matches"], 2)
        self.assertEqual(report["rows"][0]["sources"], ["footystats"])

    def test_verified_crosswalk_merges_exact_sources(self):
        report = merge_historical_sources([A, B], MAP)
        self.assertEqual(report["unique_matches"], 1)
        self.assertEqual(report["rows"][0]["sources"], ["footystats", "fotmob"])

    def test_wrong_home_or_away_id_cannot_merge(self):
        with self.assertRaisesRegex(ValueError, "unverified_cross"):
            merge_historical_sources([A, {**B, "away_id": "999"}], MAP)

    def test_changed_kickoff_cannot_merge(self):
        with self.assertRaisesRegex(ValueError, "unverified_cross"):
            merge_historical_sources([A, {**B, "kickoff_unix": 1540000100}], MAP)

    def test_conflicting_stats_are_quarantined_not_overwritten(self):
        report = merge_historical_sources([A, {**B, "away_sot": 11}], MAP)
        self.assertEqual(report["unique_matches"], 0)
        self.assertIn("conflicting_away_sot", report["quarantined"][0]["reasons"])

    def test_inconsistent_same_provider_duplicate_is_quarantined(self):
        report = merge_historical_sources([A, {**A, "home_goals": 3}])
        self.assertEqual(report["unique_matches"], 0)
        self.assertIn("inconsistent_duplicate_provider_row",
                      report["quarantined"][0]["reasons"])

    def test_missing_stats_are_not_assumed_zero(self):
        report = merge_historical_sources([{**A, "home_sot": None}])
        self.assertIsNone(report["rows"][0]["home_sot"])
        report = merge_historical_sources([{**A, "home_sot": None}, B], MAP)
        self.assertEqual(report["rows"][0]["home_sot"], 5)

    def test_historical_cannot_be_marked_live_or_odds(self):
        for alteration in ({"live_eligible": True}, {"odds_eligible": True},
                           {"data_kind": "live"}):
            with self.assertRaisesRegex(ValueError, "non_historical"):
                merge_historical_sources([{**A, **alteration}])

    def test_no_live_rows_cannot_claim_uplift(self):
        report = replay_late_goal_predictions([])
        self.assertEqual(report["status"], "not_backtestable_no_live_snapshots")
        self.assertFalse(report["live_uplift_confirmed"])

    def test_historical_fulltime_cannot_replay_as_live(self):
        with self.assertRaisesRegex(ValueError, "historical_data_is_not_live"):
            replay_late_goal_predictions([A])

    def test_valid_single_live_tip_is_insufficient(self):
        result = replay_late_goal_predictions([LIVE])
        self.assertEqual(result["verified_matches"], 1)
        self.assertEqual(result["baseline"]["hit_rate"], 1.0)
        self.assertEqual(result["extra_sources"]["won"], 1)
        self.assertEqual(result["status"], "insufficient_for_uplift")
        self.assertFalse(result["live_uplift_confirmed"])

    def test_no_duplicate_game_is_scored(self):
        with self.assertRaisesRegex(ValueError, "duplicate_or_missing_fixture"):
            replay_late_goal_predictions([LIVE, LIVE])

    def test_no_future_or_stale_stats(self):
        for updated in ({"stats_at": "2026-11-18T17:16:00Z"},
                        {"stats_at": "2026-11-18T17:03:00Z"},
                        {"locked_at": "2026-11-18T17:17:00Z"},
                        {"final_at": "2026-11-18T17:14:00Z"}):
            with self.assertRaisesRegex(ValueError, "lookahead_or_stale|stale_inplay"):
                replay_late_goal_predictions([{**LIVE, **updated}])

    def test_no_fuzzy_unverified_identity(self):
        for field in ("identity_verified","source_timestamp_verified","model_locked"):
            with self.assertRaisesRegex(ValueError, "unverified_snapshot"):
                replay_late_goal_predictions([{**LIVE, field: False}])

    def test_outside_minute_or_bad_score_refused(self):
        with self.assertRaisesRegex(ValueError, "out_of_late"):
            replay_late_goal_predictions([{**LIVE, "minute": 89}])
        with self.assertRaisesRegex(ValueError, "inconsistent_score"):
            replay_late_goal_predictions([{**LIVE, "final_score": [0,1]}])

    def test_no_unbacked_predictions(self):
        with self.assertRaisesRegex(ValueError, "missing_locked_predictions"):
            replay_late_goal_predictions([{**LIVE, "baseline_send": None}])

if __name__ == "__main__":
    unittest.main()
