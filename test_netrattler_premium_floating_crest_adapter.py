"""No pasted-on club-logo tiles in ANY derived NETRATTLER premium card.

Only synthetic offline QA. The global production original-artwork lock
remains enabled by default and is never bypassed by an actual Telegram send.
"""
import io
import os
import unittest
from unittest.mock import patch

from PIL import Image,ImageDraw,ImageChops

import netrattler_premium_telegram_adapter as adapter


def genuine_crest(pad=0):
    pic=Image.new("RGBA",(90+2*pad,110+2*pad),(0,0,0,0))
    ImageDraw.Draw(pic).rectangle(
        (pad+29,pad+17,pad+59,pad+92),fill=(238,30,50,255))
    out=io.BytesIO()
    pic.save(out,"PNG")
    return out.getvalue()


def opaque_sticker():
    pic=Image.new("RGB",(110,110),(255,255,255))
    ImageDraw.Draw(pic).rectangle((28,12,82,95),fill=(238,30,50))
    out=io.BytesIO()
    pic.save(out,"PNG")
    return out.getvalue()


class OriginalCrestsFloatWithoutPastedDiscs(unittest.TestCase):
    def sample_tip(self):
        return {"match":"QA Home vs QA Away","bookmaker":"OFFLINE QA ONLY",
                "oddsYes":1.75,"probability":70.0,
                "league":"TEST LEAGUE","time_local":"19:30","tip":"YES"}

    def render(self,provider):
        bg=Image.new("RGB",(1122,1402),(5,22,37))
        b=io.BytesIO()
        bg.save(b,"PNG")
        with patch.dict(os.environ,{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"}),patch.object(
            adapter,"render_verified_png",return_value=b.getvalue()):
            return adapter.render(
                [("over25",self.sample_tip())],"2026-11-23",
                crest_provider=provider)

    def test_two_real_logos_centered_with_alpha_not_stickers(self):
        tight=self.render(lambda team:genuine_crest())
        padded=self.render(lambda team:genuine_crest(150))
        with Image.open(io.BytesIO(tight)) as a,Image.open(io.BytesIO(padded)) as b:
            aa=a.convert("RGB")
            bb=b.convert("RGB")
            self.assertIsNone(ImageChops.difference(aa,bb).getbbox())
            # The source stadium is untouched outside the actual crest:
            for pixel in ((215,248),(345,248),(777,248),(895,248)):
                self.assertEqual(aa.getpixel(pixel),(5,22,37))
            for cx in (280,842):
                self.assertEqual(aa.getpixel((cx,300)),(238,30,50))
            # 116px tall, vertically centred on y=280. The 12px
            # gap before the team-name label must remain pure stadium.
            self.assertEqual(aa.getpixel((280,235)),(238,30,50))
            self.assertEqual(aa.getpixel((280,325)),(238,30,50))
            self.assertEqual(aa.getpixel((280,341)),(5,22,37))

    def test_opaque_rectangle_is_blocked_not_glued_to_original_background(self):
        for data in (opaque_sticker(),b""):
            with self.subTest(size=len(data)),self.assertRaises(ValueError):
                adapter._crest(data)

    def test_premium_originals_stay_blocked_for_real_telegram(self):
        with patch.dict(os.environ,{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"1"}):
            with self.assertRaisesRegex(ValueError,"premium_master_not_visually_approved"):
                adapter.render([("over25",self.sample_tip())],"2026-11-23",
                               crest_provider=lambda t: (_ for _ in ()).throw(
                                   AssertionError("Should not fetch club crests")))


if __name__=="__main__":
    unittest.main(verbosity=2)
