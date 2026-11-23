"""All NETRATTLER match markets use one authentic, floating logo rule.

No internet, Telegram, Supabase or bookmaker calls. Tests the common
badge placement underlying match cards, Builder, player props and GOAL cards.
"""
import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

import netrattler_stats_match_cards as cards


def authentic_logo(extra=0):
    w,h=60+2*extra,94+2*extra
    pic=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(pic)
    d.rectangle((extra+15,extra+11,extra+45,extra+82),
                fill=(244,20,35,255))
    out=io.BytesIO()
    pic.save(out,"PNG")
    return out.getvalue()


class AllFootballFloatingOriginalCrests(unittest.TestCase):
    def place(self,payload,mode="RGB"):
        bg=Image.new(mode,(220,190),(6,23,38,255) if mode=="RGBA" else (6,23,38))
        before=bg.copy()
        with patch.object(cards,"_badge_bytes",return_value=payload):
            cards._paste_badge(bg,ImageDraw.Draw(bg),"VERIFIED TEAM",
                              (30,20,130,120),None)
        return bg,before

    def test_exact_alpha_and_original_background_no_fake_circle(self):
        actual,original=self.place(authentic_logo())
        # In the 100x100 slot only genuine rectangular logo pixels may
        # change. A synthetic ring/disc would color transparent corners.
        self.assertEqual(actual.getpixel((31,21)),original.getpixel((31,21)))
        self.assertEqual(actual.getpixel((129,119)),original.getpixel((129,119)))
        self.assertEqual(actual.getpixel((160,70)),original.getpixel((160,70)))
        red=actual.getpixel((80,70))
        self.assertGreater(red[0],220)
        self.assertLess(red[1],60)

    def test_opaque_sticker_tile_never_replaces_original_stadium(self):
        opaque=Image.new("RGB",(140,140),(250,250,250))
        ImageDraw.Draw(opaque).rectangle(
            (30,20,110,120),fill=(244,20,35))
        stream=io.BytesIO()
        opaque.save(stream,"PNG")
        stadium=Image.new("RGBA",(220,190),(6,23,38,255))
        before=stadium.copy()
        with patch.object(cards,"_badge_bytes",return_value=stream.getvalue()):
            with self.assertRaisesRegex(ValueError,"Invalid genuine club crest"):
                cards._paste_badge(stadium,ImageDraw.Draw(stadium),"OPAQUE TILE",
                                   (30,20,130,120),None)
        self.assertIsNone(ImageChops.difference(stadium,before).getbbox())

    def test_provider_transparency_padding_cannot_shrink_logo(self):
        for mode in ("RGB","RGBA"):
            with self.subTest(mode=mode):
                tight,_=self.place(authentic_logo(),mode)
                padded,_=self.place(authentic_logo(70),mode)
                self.assertIsNone(ImageChops.difference(tight,padded).getbbox())

    def test_missing_or_tiny_art_is_blocked_without_placeholder(self):
        bg=Image.new("RGB",(220,190),(6,23,38))
        original=bg.copy()
        with patch.object(cards,"_badge_bytes",return_value=b""):
            with self.assertRaisesRegex(ValueError,"authentic club crest"):
                cards._paste_badge(bg,ImageDraw.Draw(bg),"UNKNOWN CLUB",
                                  (30,20,130,120),None)
        self.assertIsNone(ImageChops.difference(bg,original).getbbox())
        tiny=Image.new("RGBA",(12,12),(244,20,35,255))
        payload=io.BytesIO();tiny.save(payload,"PNG")
        with patch.object(cards,"_badge_bytes",return_value=payload.getvalue()):
            with self.assertRaises(ValueError):
                cards._paste_badge(bg,ImageDraw.Draw(bg),"VERIFIED CLUB",
                                  (30,20,130,120),None)
        self.assertIsNone(ImageChops.difference(bg,original).getbbox())


if __name__=="__main__":
    unittest.main(verbosity=2)
