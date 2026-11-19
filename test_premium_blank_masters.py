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

    def test_dynamic_row_compaction(self):
        from netrattler_premium_compact import compact_master
        for category, counts in (("combo", range(3, 11)), ("builder", range(3, 7))):
            previous_height = 0
            for count in counts:
                with self.subTest(category=category, count=count):
                    root = ET.fromstring(compact_master(category, count))
                    height = int(root.get("height"))
                    self.assertGreater(height, previous_height)
                    previous_height = height
                    self.assertEqual(root.get("viewBox"), f"0 0 1122 {height}")
                    rows = [r for r in root.iter(SVG + "rect")
                            if r.get("x") == "42" and r.get("width") == "1038"
                            and float(r.get("height")) < 170]
                    self.assertEqual(len(rows), count)
                    footer = next(r for r in root.iter(SVG + "rect")
                                  if r.get("x") == "42" and r.get("height") == "170")
                    self.assertLess(float(rows[-1].get("y")) + float(rows[-1].get("height")),
                                    float(footer.get("y")))
                    brand = next(t for t in root.iter(SVG + "text")
                                 if "".join(t.itertext()).strip() == "@prophunter")
                    self.assertLess(float(brand.get("y")), height)

    def test_rasterized_compact_previews(self):
        import io
        from PIL import Image
        from netrattler_premium_compact import render_blank_preview
        for category, counts in (("combo", (3, 7, 10)), ("builder", (3, 4, 6))):
            for count in counts:
                with self.subTest(category=category, count=count):
                    payload = render_blank_preview(category, count)
                    with Image.open(io.BytesIO(payload)) as im:
                        im.verify()
                    with Image.open(io.BytesIO(payload)) as im:
                        self.assertEqual(im.width, 1122)
                        step = 73 if category == "combo" else 100
                        maximum = 10 if category == "combo" else 6
                        self.assertEqual(im.height, 1402 - (maximum - count) * step)

    def test_dynamic_invalid_counts(self):
        from netrattler_premium_compact import compact_master
        for category, count in (("combo", 2), ("combo", 11), ("builder", 7),
                                ("goal", 3), ("combo", True)):
            with self.assertRaises(ValueError):
                compact_master(category, count)

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
