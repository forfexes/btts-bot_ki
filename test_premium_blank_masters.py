"""Regression checks for the 16 empty NETRATTLER premium SVG masters."""
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent / "assets"
CATEGORIES = (
    "builder", "goal", "corner", "btts", "over", "btts_halftime",
    "over_halftime", "match_result", "combo", "player_props",
    "fouls_cards", "var", "last_minute_goal", "late_goals",
    "live_halftime", "cross_mix",
)
SVG = "{http://www.w3.org/2000/svg}"


class PremiumMasterTests(unittest.TestCase):
    def test_all_sixteen_exist(self):
        actual = {p.name for p in ROOT.glob("premium_*_blank.svg")}
        expected = {f"premium_{category}_blank.svg" for category in CATEGORIES}
        self.assertEqual(actual, expected)

    def test_empty_branded_masters(self):
        for category in CATEGORIES:
            with self.subTest(category=category):
                path = ROOT / f"premium_{category}_blank.svg"
                root = ET.parse(path).getroot()
                self.assertEqual(root.get("viewBox"), "0 0 1122 1402")
                texts = ["".join(t.itertext()).strip() for t in root.iter(SVG + "text")]
                self.assertEqual(texts[0], "NETRATTLER")
                self.assertEqual(texts[-1], "@prophunter")
                self.assertEqual(len(texts), 3, "Master must contain only fixed branding and category title")
                self.assertNotIn("@netrattler", path.read_text(encoding="utf-8").lower())

    def test_rows_do_not_overlap_footer(self):
        for category in CATEGORIES:
            with self.subTest(category=category):
                root = ET.parse(ROOT / f"premium_{category}_blank.svg").getroot()
                rows = []
                for rect in root.iter(SVG + "rect"):
                    if rect.get("x") == "42" and rect.get("width") == "1038":
                        y, height = float(rect.get("y")), float(rect.get("height"))
                        if y < 1185:
                            rows.append((y, y + height))
                self.assertTrue(rows)
                self.assertTrue(all(end <= 1185 for _, end in rows))
                self.assertTrue(all(rows[i][1] < rows[i+1][0] for i in range(len(rows)-1)))
                if category == "combo":
                    self.assertEqual(len(rows), 10)


if __name__ == "__main__":
    unittest.main()
