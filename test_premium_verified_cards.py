"""Smoke-test all 16 verified-data card categories without publishing picks."""
import io
import unittest
from xml.etree import ElementTree as ET
from PIL import Image
from netrattler_premium_verified_cards import CATEGORIES, render_verified_svg, render_verified_png

LEG = {"match": "Home FC vs Away FC", "market": "Over 2.5 Goals",
       "bookmaker_odds": 2.15, "bookmaker": "verified_fixture",
       "estimated": False}


class VerifiedCardTests(unittest.TestCase):
    def test_every_category_renders(self):
        for category in CATEGORIES:
            with self.subTest(category=category):
                n = 3 if category in ("combo", "builder") else 1
                svg = render_verified_svg(category, [LEG.copy() for _ in range(n)])
                root = ET.fromstring(svg)
                labels = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
                self.assertEqual(labels.count("Home FC vs Away FC"), n)
                self.assertEqual(labels.count("@ 2.15"), n)
                self.assertIn("@prophunter", labels)
                raw = render_verified_png(category, [LEG.copy() for _ in range(n)])
                with Image.open(io.BytesIO(raw)) as image:
                    image.verify()

    def test_combo_and_builder_dynamic_limits(self):
        for category, maximum in (("combo", 10), ("builder", 6)):
            for n in range(3, maximum + 1):
                with self.subTest(category=category, count=n):
                    svg = render_verified_svg(category, [LEG.copy() for _ in range(n)])
                    root = ET.fromstring(svg)
                    texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
                    self.assertEqual(texts.count("@ 2.15"), n)

    def test_pngs_have_correct_dimensions_and_no_baked_in_example(self):
        for category in CATEGORIES:
            n = 3 if category in ("combo", "builder") else 1
            raw = render_verified_png(category, [LEG.copy() for _ in range(n)])
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.width, 1122)
                self.assertGreater(image.height, 400)
                self.assertEqual(image.format, "PNG")
            svg = render_verified_svg(category, [LEG.copy() for _ in range(n)])
            self.assertNotIn(b"@netrattler", svg.lower())
            self.assertNotIn(b"BEISPIEL SPIELER", svg.upper())

    def test_reject_missing_or_fabricated_odds(self):
        for replacement in ({"bookmaker_odds": None}, {"estimated": True},
                            {"synthetic": True}, {"model_odds": 2.2},
                            {"bookmaker": ""}, {"bookmaker_odds": float("nan")},
                            {"market": ""}):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):
                    render_verified_svg("btts", [{**LEG, **replacement}])


if __name__ == "__main__":
    unittest.main()
