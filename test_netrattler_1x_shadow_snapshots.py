#!/usr/bin/env python3
"""Fail-closed tests for raw 1xBet player-market evidence; never bet from G/T."""
import unittest
from unittest.mock import Mock

import netrattler_1x_shadow_snapshots as x1


class ShadowPlayerTests(unittest.TestCase):
    def test_real_player_identity_pl_and_market_code_are_preserved(self):
        payload = {"E": [
            {"G": 117, "T": 833, "C": 2.25, "P": 1.5,
             "PL": {"N": "Lasse Gunther", "I": 93516630, "T": 1}},
            {"G": 118, "T": 834, "C": 1.80,
             "PL": {"N": "Marius Wolf", "I": 4179153, "T": 2}},
        ]}
        rows = x1.extract_snapshots(payload, "Augsburg vs Elversberg", "Players' stats")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["g"], 117)
        self.assertEqual(rows[0]["t"], 833)
        self.assertEqual(rows[0]["line"], 1.5)
        self.assertEqual(rows[0]["player"], "Lasse Gunther")
        self.assertEqual(rows[0]["side"], 1)
        self.assertNotIn("stat", rows[0])
        self.assertNotIn("market", rows[0])
        self.assertNotIn("tip", rows[0])

    def test_no_identity_no_market_classification_and_invalid_prices(self):
        events = [
            {"G": 117, "T": 833, "C": 2.0, "PN": "Fake player"},
            {"G": 117, "T": 833, "C": 1.0, "PL": {"N": "Valid Player", "I": 1, "T": 1}},
            {"G": 117, "T": 833, "C": 2.0, "PL": {"N": "Valid Player", "I": 1, "T": 0}},
            {"G": 117, "T": 833, "C": 2.0, "P": "NaN",
             "PL": {"N": "Valid Player", "I": 1, "T": 1}},
        ]
        self.assertEqual(x1.extract_snapshots({"E": events}, "A vs B", "Players' stats"), [])
        self.assertEqual(x1.extract_snapshots({"E": events}, "A vs B", "Goalscorer"), [])

    def test_limits_and_deduplicates(self):
        record = {"G": 117, "T": 833, "C": 2.0,
                  "PL": {"N": "Valid Player", "I": 22, "T": 2}}
        self.assertEqual(len(x1.extract_snapshots({"E": [record] * 80},
                         "A vs B", "Players' stats", max_rows=5)), 1)

    def test_database_write_is_bounded_and_shadow_only(self):
        response = Mock()
        response.raise_for_status = Mock()
        client = Mock(post=Mock(return_value=response))
        rows = [{"match_name": "A vs B", "g": 117, "t": 833, "odds": 2.0}] * 405
        with self.subTest("batch"):
            n = x1.persist_snapshots(rows, "https://db.example", "test-token", client)
        self.assertEqual(n, 405)
        self.assertEqual(client.post.call_count, 3)
        self.assertTrue(all("x1_player_snapshots" in call.args[0] for call in client.post.call_args_list))
        self.assertTrue(all(len(call.kwargs["json"]) <= 200 for call in client.post.call_args_list))
        self.assertTrue(all("Authorization" in call.kwargs["headers"] for call in client.post.call_args_list))

    def test_write_errors_are_not_counted_as_success(self):
        client = Mock()
        client.post.return_value.raise_for_status.side_effect = RuntimeError("DB down")
        with self.assertRaises(RuntimeError):
            x1.persist_snapshots([{"match_name": "A vs B"}], "https://db.example", "test", client)


if __name__ == "__main__":
    unittest.main()
