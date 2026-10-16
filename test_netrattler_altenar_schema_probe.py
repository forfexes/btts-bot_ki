#!/usr/bin/env python3
"""Pure-logic regression for the bounded Altenar schema sniffer.

No Playwright/browser is exercised here; only the JSON-walking and value
truncation logic, against synthetic payloads shaped like the publicly
observed Altenar event/marketGroup wrapper.
"""
import unittest

import netrattler_altenar_schema_probe as sniffer


class AltenarSchemaSniffTests(unittest.TestCase):
    def test_sniffs_event_market_selection_price_shape(self):
        payload = {
            "events": [
                {
                    "eventId": 123456,
                    "homeTeam": "FC Example",
                    "awayTeam": "AC Sample",
                    "startDate": "2026-10-20T18:00:00Z",
                    "marketGroups": [
                        {
                            "marketName": "1X2",
                            "selections": [
                                {"name": "1", "price": 1.85},
                                {"name": "X", "price": 3.40},
                                {"name": "2", "price": 4.20},
                            ],
                        }
                    ],
                }
            ]
        }
        result = sniffer.sniff(payload)
        self.assertTrue(result["shapes"])
        self.assertGreaterEqual(len(result["samples"]), 1)
        sample_keys = {k.lower() for s in result["samples"] for k in s["keys"]}
        self.assertIn("name", sample_keys)
        self.assertIn("price", sample_keys)

    def test_truncate_never_returns_full_long_strings_or_deep_objects(self):
        long_value = "x" * 5000
        out = sniffer._truncate(long_value)
        self.assertLessEqual(len(out), 80)
        nested = {"a": {"b": {"c": {"d": "too deep"}}}}
        out2 = sniffer._truncate(nested)
        self.assertIsInstance(out2, dict)

    def test_truncate_rounds_numeric_price_values(self):
        self.assertEqual(sniffer._truncate(1.845001234), 1.845)

    def test_no_shapes_for_unrelated_payload(self):
        result = sniffer.sniff({"css": "body{color:red}", "meta": {"lang": "en"}})
        self.assertEqual(result["shapes"], {})
        self.assertEqual(result["samples"], [])

    def test_describe_top_level_arrays_keeps_real_join_keys(self):
        payload = {
            "sports": [{"id": 1, "name": "Football"}],
            "events": [{"id": 999, "sportId": 1, "champId": 5,
                        "competitors": [{"id": 10, "name": "FC Example"},
                                        {"id": 11, "name": "AC Sample"}],
                        "startDate": "2026-10-20T18:00:00Z"}],
            "markets": [{"id": 77, "eventId": 999, "name": "1X2"}],
            "odds": [{"id": 1, "marketId": 77, "name": "1", "price": 1.85, "typeId": 1}],
        }
        described = sniffer.describe_top_level_arrays(payload)
        self.assertIn("events", described)
        self.assertIn("markets", described)
        self.assertEqual(described["events"][0]["id"], 999)
        self.assertEqual(described["markets"][0]["eventId"], 999)
        # nested competitor list inside the event sample must survive (not "…")
        self.assertIsInstance(described["events"][0]["competitors"], list)
        self.assertEqual(described["events"][0]["competitors"][0]["name"], "FC Example")

    def test_describe_top_level_arrays_ignores_non_dict_payload(self):
        self.assertEqual(sniffer.describe_top_level_arrays(["not", "a", "dict"]), {})

    def test_bounded_sample_count(self):
        many_markets = {"events": [
            {"eventId": i, "hometeam": "A", "awayteam": "B", "markets": [
                {"name": "Over", "price": 1.9 + i * 0.01}
            ]}
            for i in range(50)
        ]}
        result = sniffer.sniff(many_markets)
        self.assertLessEqual(len(result["samples"]), sniffer.MAX_SAMPLES)


if __name__ == "__main__":
    unittest.main()
