"""Real 7/9-tip owner COMBO source PNG: no sample bookmaker data or crests."""
import io
import math
import unittest
from unittest.mock import patch
from PIL import Image, ImageChops, ImageDraw

from netrattler_combo_owner_original import W,H,ROOT,render_original_combo


def crest(name):
    im=Image.new("RGBA",(100,100),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.ellipse((8,8,92,92),fill="#249CD6",outline="#FFFFFF",width=6)
    buf=io.BytesIO()
    im.save(buf,"PNG")
    return buf.getvalue()


def sample(n):
    return [{"home":f"HOME {i+1}","away":f"AWAY {i+1}",
             "market":"OVER 2.5" if i%2 else "BTTS JA",
             "odds":round(1.60+i*.08,2)}
            for i in range(n)]


def render(n,**changes):
    attrs=dict(combined_odds=14.25 if n==7 else 39.70,
        probability=22.5 if n==7 else 8.3,ev=3.1,confidence="HIGH",
        stake=1.0,combined_odds_observed=True,
        combined_quote_id="SYNTHETIC_TEST_TICKET",
        bookmaker="TEST_BOOKMAKER",crest_provider=crest,status="OFFEN")
    attrs.update(changes)
    # Historical owner screenshot reconstruction is synthetic QA ONLY.
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"}):
        return render_original_combo(sample(n),**attrs)


class VerifiedOriginalComboTests(unittest.TestCase):
    def test_real_combo_club_crest_must_have_transparent_shape_not_white_tile(self):
        from netrattler_combo_owner_original import _photo_crest
        opaque=Image.new("RGB",(100,100),(250,250,250))
        ImageDraw.Draw(opaque).ellipse((8,8,92,92),fill=(36,156,214))
        buf=io.BytesIO();opaque.save(buf,"PNG")
        with self.assertRaisesRegex(ValueError,"Opaque Combo club crest sticker"):
            _photo_crest(buf.getvalue())
        # The correctly transparent provider asset remains supported.
        good=_photo_crest(crest("VERIFIED TEAM"))
        self.assertEqual(good.mode,"RGBA")
        self.assertLess(max(good.size),100)

    def test_both_owner_originals_preserve_crown_and_real_footer(self):
        for n in (7,9):
            with self.subTest(n=n):
                image=render(n)
                with Image.open(io.BytesIO(image)) as output, Image.open(
                    ROOT/f"NETRATTLER_COMBO_{n}_originalkarte.png") as raw:
                    ref=raw.convert("RGB").resize((W,H),Image.Resampling.LANCZOS)
                    self.assertEqual(output.size,(W,H))
                    self.assertIsNone(ImageChops.difference(
                        output.crop((0,0,W,280)),ref.crop((0,0,W,280))).getbbox())
                    self.assertIsNone(ImageChops.difference(
                        output.crop((0,1320,W,H)),ref.crop((0,1320,W,H))).getbbox())
                    self.assertIsNotNone(ImageChops.difference(
                        output.crop((30,365,1090,1230)),
                        ref.crop((30,365,1090,1230))).getbbox())

    def test_quote_and_settlement_actually_change_picture(self):
        self.assertNotEqual(render(7),render(7,combined_odds=18.75))
        self.assertNotEqual(render(9),render(9,status="GEWONNEN"))

    def test_bookmaker_verified_combo_without_model_ev_uses_no_fake_ev(self):
        # A real, confirmed book quote must still render without a
        # fabricated EV metric. Offline fixture must never enter Telegram.
        raw=render(7,ev=None)
        with Image.open(io.BytesIO(raw)) as im:
            self.assertEqual(im.size,(W,H))
        self.assertNotEqual(raw,render(7,ev=3.1))

    def test_calculated_quote_without_combined_bookmaker_ticket(self):
        for n in (7,9):
            with self.subTest(n=n):
                image=render(n,combined_odds_observed=False,
                             combined_quote_id="",bookmaker="",
                             combined_odds=None)
                self.assertTrue(image.startswith(bytes((137,80,78,71))))

    def test_strict_observed_quote_crest_and_settlement(self):
        for kwargs in ({"combined_odds":float("nan")},
                       {"combined_odds":1.0},
                       {"crest_provider":lambda team: b""},
                       {"status":"GUESSED"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((ValueError,OSError)):
                    render(7,**kwargs)

    def test_derived_counts_keep_the_real_original_header_and_footer(self):
        for n in (3,4,5,6,8,10,11,12):
            with self.subTest(n=n):
                rendered=render(n,combined_odds_observed=False,
                                combined_quote_id="",bookmaker="",
                                combined_odds=None,ev=None)
                source_n=7 if n<=7 else 9
                with Image.open(io.BytesIO(rendered)) as output, Image.open(
                    ROOT/f"NETRATTLER_COMBO_{source_n}_originalkarte.png") as original:
                    original=original.convert("RGB").resize((W,H),Image.Resampling.LANCZOS)
                    self.assertEqual(output.width,W)
                    self.assertEqual(output.height,
                                     H+round(793*(n-source_n)/source_n))
                    # The metallic crown and source header remain pixel
                    # identical; the old baked 7/9 TIPPS label must change.
                    self.assertIsNone(ImageChops.difference(
                        output.crop((0,0,W,190)),
                        original.crop((0,0,W,190))).getbbox())
                    self.assertIsNotNone(ImageChops.difference(
                        output.crop((365,208,768,268)),
                        original.crop((365,208,768,268))).getbbox())
                    self.assertIsNone(ImageChops.difference(
                        output.crop((0,output.height-82,W,output.height)),
                        original.crop((0,H-82,W,H))).getbbox())
                    # No sample-leg text remains in the original row/footer seam.
                    shift=output.height-H
                    self.assertEqual(output.convert("RGB").getpixel(
                        (520,1109+shift)),(7,21,35))

    def test_only_unsupported_leg_counts_are_rejected(self):
        for n in (0,1,2,13):
            with self.subTest(n=n),self.assertRaises(ValueError):
                render(n)


if __name__=="__main__":
    unittest.main()
