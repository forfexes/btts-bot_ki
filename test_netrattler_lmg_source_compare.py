"""Offline regression tests: only proven cross-provider live matches are paired."""
import copy
import unittest
from unittest.mock import patch
import netrattler_lmg_source_compare as compare
import netrattler_lmg_fotmob as fotmob
from test_netrattler_lmg_fotmob import daily


def board():
    return {"events": [{
        "id": "99123", "date": "2026-11-18T11:30:00Z",
        "status": {"period": 2, "displayClock": "68:00", "type": {"state": "in"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "team": {"id": "10", "displayName": "Tampines Rovers FC"}},
            {"homeAway": "away", "score": "1", "team": {"id": "20", "displayName": "Ratchaburi FC"}},
        ]}]
    }]}


class PairedSourceTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = fotmob.fixtures_from_fotmob(daily())

    def test_exact_pair(self):
        found = compare.pair_coverage(self.fixtures, board())
        self.assertEqual(found["paired"], 1)
        self.assertEqual(found["unpaired_fotmob"], 0)
        self.assertEqual(found["telegram_messages"], 0)

    def test_wrong_opponent_rejected(self):
        bad = board()
        bad["events"][0]["competitions"][0]["competitors"][1]["team"]["displayName"] = "Wrong Team"
        self.assertEqual(compare.pair_coverage(self.fixtures, bad)["paired"], 0)

    def test_wrong_score_and_clock_rejected(self):
        for attr, value in [("displayClock", "78:00")]:
            bad = board()
            bad["events"][0]["status"][attr] = value
            self.assertEqual(compare.pair_coverage(self.fixtures, bad)["paired"], 0)
        bad = board()
        bad["events"][0]["competitions"][0]["competitors"][0]["score"] = "2"
        self.assertEqual(compare.pair_coverage(self.fixtures, bad)["paired"], 0)

    def test_ambiguous_duplicate_rejected(self):
        bad = board()
        bad["events"].append(copy.deepcopy(bad["events"][0]))
        bad["events"][1]["id"] = "99124"
        result = compare.pair_coverage(self.fixtures, bad)
        self.assertEqual(result["paired"], 0)
        self.assertEqual(result["ambiguous"], 1)

    def test_no_send_and_no_write(self):
        with patch.object(compare.common, "reserve_alert", side_effect=AssertionError("send")), \
             patch.object(compare.common, "send_alert", side_effect=AssertionError("send")):
            self.assertEqual(compare.pair_coverage(self.fixtures, board())["paired"], 1)


if __name__ == "__main__":
    unittest.main()
