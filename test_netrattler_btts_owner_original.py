"""BTTS original-owner card contract; synthetic values, never Telegram posts."""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

import netrattler_premium_telegram_adapter as premium
from netrattler_btts_owner_original import REFERENCE, W, H


def sample_crest(shade):
    icon=Image.new("RGBA",(125,125),(0,0,0,0))
    d=ImageDraw.Draw(icon)
    d.ellipse((10,10,115,115),fill=shade,outline="#FFFFFF",width=5)
    out=io.BytesIO()
    icon.save(out,"PNG")
    return out.getvalue()


def sample():
    return {"match":"Example United vs Sample City",
            "league":"Example League",
            "time_local":"20:00",
            "bookmaker":"TEST_SOURCE_ONLY",
            "probability":64.3,
            "btts_l10":"7/10",
            "btts_home":70,
            "btts_away":59,
            "oddsYes":1.92,
            "tip":"YES"}


class OwnerBttsImageTests(unittest.TestCase):
    def draw(self,**changes):
        entry=sample()
        entry.update(changes)
        with patch("netrattler_premium_telegram_adapter.render_verified_png",
                   side_effect=AssertionError("technical SVG MUST NOT be used")):
            return premium.render([("btts",entry)],"2026-11-20",
                crest_provider=lambda team: sample_crest(
                  "#45ABF2" if team.startswith("Example") else "#F2A243"))

    def test_btts_direct_renderer_refuses_opaque_pasted_on_club_logo(self):
        from netrattler_btts_owner_original import _crest
        canvas=Image.new("RGBA",(W,H),(4,17,29,255))
        before=canvas.copy()
        for mode in ("RGB","RGBA"):
            with self.subTest(mode=mode):
                tile=Image.new(mode,(125,125),
                               (250,250,250) if mode=="RGB" else (250,250,250,255))
                ImageDraw.Draw(tile).ellipse((14,14,110,110),fill=(60,129,218))
                with self.assertRaisesRegex(ValueError,"Opaque BTTS badge tile"):
                    _crest(canvas,tile,281)
                self.assertIsNone(ImageChops.difference(canvas,before).getbbox())

    def test_user_original_header_and_footer_unchanged(self):
        raw=self.draw()
        with Image.open(io.BytesIO(raw)) as rendered, Image.open(REFERENCE) as src:
            self.assertEqual(rendered.size,(W,H))
            source=src.convert("RGB").resize((W,H),Image.Resampling.LANCZOS)
            for label, box in (("metallic header",(0,0,W,280)),
                               ("@prophunter footer",(0,1276,W,H))):
                self.assertIsNone(ImageChops.difference(rendered.crop(box),
                    source.crop(box)).getbbox(),label)
            # The example Barcelona and Alaves crests and fixed price inside
            # the original must have been replaced, never overprinted.
            self.assertIsNotNone(ImageChops.difference(
                rendered.crop((100,330,1010,1030)),
                source.crop((100,330,1010,1030))).getbbox())

    def test_premium_ai_shows_real_model_probability_in_clean_slot(self):
        import netrattler_btts_owner_original as original
        observed=[]
        drawing=original._text
        def capture(draw,label,*args,**kwargs):
            observed.append(str(label))
            return drawing(draw,label,*args,**kwargs)
        with patch.object(original,"_text",side_effect=capture):
            self.draw()
        self.assertIn("KI-MODELL",observed)
        self.assertIn("64.3%",observed)
        self.assertIn("EV",observed)
        self.assertIn("7/10",observed)
        self.assertNotIn("BEISPIELQUOTE",observed)

    def test_fractional_model_probability_matches_percent_and_ev(self):
        import netrattler_btts_owner_original as original
        self.assertEqual(original._percent(0.643), "64.3%")
        self.assertEqual(original._percent("64.3%"), "64.3%")
        # Explicit percentages must not be silently multiplied by 100.
        self.assertEqual(original._percent("0.643%"), "0.6%")
        seen=[]
        real_text=original._text
        def inspect_text(draw, value, *args, **kwargs):
            seen.append(str(value))
            return real_text(draw, value, *args, **kwargs)
        with patch.object(original, "_text", side_effect=inspect_text):
            self.draw(probability=0.643)
        self.assertIn("64.3%", seen)
        self.assertIn("+23.5%", seen)
        self.assertNotIn("0.6%", seen)

    def test_real_selection_changes_original_image(self):
        first=self.draw()
        second=self.draw(oddsYes=2.15,probability=59.8,btts_l10="5/10")
        self.assertNotEqual(first,second)

    def test_bad_sources_missing_crest_probability_and_no_are_blocked(self):
        for bad in ({"probability":None},{"probability":float("nan")},
                    {"oddsYes":float("nan")},{"tip":"NO"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.draw(**bad)
        with self.assertRaises(ValueError):
            premium.render([("btts",sample())],"2026-11-20",
                crest_provider=lambda team: b"not a genuine crest")

    def test_winning_settlement_is_inside_original_picture(self):
        entry=sample()
        creds=lambda name: sample_crest("#45ABF2")
        original=premium.render([("btts",entry)],"2026-11-20",
                              crest_provider=creds)
        closed=premium.render([("btts",entry)],"2026-11-20",
                              crest_provider=creds,
                              result={"marks":{"0":"win"},"ft":"2-1"})
        self.assertNotEqual(original,closed)
        with Image.open(io.BytesIO(closed)) as im:
            self.assertEqual(im.size,(W,H))


if __name__=="__main__":
    unittest.main()
