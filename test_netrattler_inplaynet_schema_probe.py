#!/usr/bin/env python3
"""Pure-logic regression for the InPlayNet schema sniffer target list."""
import unittest

import netrattler_inplaynet_schema_probe as sniffer


class InPlayNetSchemaProbeTests(unittest.TestCase):
    def test_targets_are_curated_inplaynet_brands(self):
        self.assertEqual(len(sniffer.TARGETS), 2)
        self.assertEqual({brand for _, brand, _ in sniffer.TARGETS}, {"rolletto", "cosmobet"})
        self.assertTrue(all(family == "inplaynet" for family, _, _ in sniffer.TARGETS))
        self.assertTrue(all(url.startswith("https://") for _, _, url in sniffer.TARGETS))

    def test_reuses_the_same_sniff_logic_as_altenar_probe(self):
        payload = {"events": [{"eventId": 1, "hometeam": "A", "awayteam": "B",
                                "markets": [{"name": "1X2", "price": 1.9}]}]}
        result = sniffer.sniff(payload)
        self.assertTrue(result["shapes"])


if __name__ == "__main__":
    unittest.main()
