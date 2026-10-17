"""Guard: training odds loader keeps working with the narrow column select."""
import unittest
from unittest import mock

import train_model as tm


class OddsLoadTests(unittest.TestCase):
    def test_narrow_select_still_builds_match_buckets(self):
        rows = [
            {"match_date": "2026-10-10", "home_team": "A", "away_team": "B", "market": "1x2",
             "bookmaker": "pinnacle", "selection": "home", "odds": 2.1, "captured_date": "2026-10-10",
             "source": "pinnacle"},
            {"match_date": "2026-10-10", "home_team": "A", "away_team": "B", "market": "1x2",
             "bookmaker": "kambi", "selection": "home", "odds": 2.0, "captured_date": "2026-10-10",
             "source": "kambi"},
        ]
        with mock.patch.object(tm, "_fetch_supabase_rows", return_value=rows) as fetch:
            by_key = tm._load_odds_history(limit_total=1000000)
        sel = fetch.call_args.kwargs["select"]
        for col in ("match_date", "home_team", "away_team", "market", "bookmaker", "selection", "odds"):
            self.assertIn(col, sel)
        self.assertNotIn("raw", sel)
        self.assertEqual(len(by_key), 1)
        self.assertEqual(len(next(iter(by_key.values()))), 2)


if __name__ == "__main__":
    unittest.main()
