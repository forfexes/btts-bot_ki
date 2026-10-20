"""Offline regression checks for the NETRATTLER open-source source registry.

This suite is intentionally network-free and does not activate any provider.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parent


class OpenSourceRegistryTests(unittest.TestCase):
    def test_source_hub_parses(self):
        ast.parse((ROOT / "netrattler_source_hub.py").read_text(encoding="utf-8"))

    def test_identity_hub_parses(self):
        ast.parse((ROOT / "netrattler_identity_hub.py").read_text(encoding="utf-8"))

    def test_registry_contains_existing_open_source_candidates(self):
        content = (ROOT / "netrattler_source_hub.py").read_text(encoding="utf-8")
        for source in ("soccerdata", "reep_identity", "statsbomb_open_data",
                       "openfootball_football_json", "openfootball_south_america"):
            with self.subTest(source=source):
                self.assertIn('SourceAdapter("' + source + '"', content)

    def test_identity_mapping_mentions_reep(self):
        content = (ROOT / "netrattler_identity_hub.py").read_text(encoding="utf-8")
        self.assertIn("REEP", content.upper())


if __name__ == "__main__":
    unittest.main()
