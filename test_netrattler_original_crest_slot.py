"""Offline source-original crest geometry (no network, no Telegram).

Missing or padded genuine crests must never become floating stickers. The
existing owner logo, frame, and background are kept pixel-identical outside
the authorized dynamic club-crest slot.
"""
import io
import unittest

from PIL import Image, ImageDraw

from netrattler_original_template_renderer import _crest


def sample_badge(empty=False):
    im = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    if not empty:
        ImageDraw.Draw(im).rectangle(
            (57, 17, 79, 121), fill=(240, 20, 30, 255))
    out=io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


class Provider:
    def __init__(self, payload):
        self.payload=payload

    def _badge_bytes(self, team):
        assert team == "VERIFIED CLUB"
        return self.payload


def red_bbox(im):
    box=Image.new("L", im.size, 0)
    p=im.convert("RGB").load()
    q=box.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b=p[x,y]
            if r>225 and g<50 and b<50:
                q[x,y]=255
    return box.getbbox()


class OriginalCrestTests(unittest.TestCase):
    def test_small_real_crest_expands_to_owner_ring_without_fake_disc(self):
        badge=Image.new("RGBA",(140,140),(0,0,0,0))
        ImageDraw.Draw(badge).rectangle((55,55,84,84),
                                        fill=(240,20,30,255))
        raw=io.BytesIO()
        badge.save(raw,"PNG")
        canvas=Image.new("RGBA",(240,200),(9,20,36,255))
        _crest(canvas,Provider(raw.getvalue()),"VERIFIED CLUB",
               (40,20,120,100))
        x0,y0,x1,y1=red_bbox(canvas)
        self.assertEqual((x1-x0,y1-y0),(80,80))
        self.assertEqual((x0,y0),(40,20))
        self.assertEqual(canvas.getpixel((0,0)),(9,20,36,255))
        # Reject artifacts that would need a >4x upscale: no blurry sticker.
        miniature=Image.new("RGBA",(12,12),(240,20,30,255))
        raw=io.BytesIO()
        miniature.save(raw,"PNG")
        with self.assertRaises(ValueError):
            _crest(Image.new("RGBA",(240,200)),
                   Provider(raw.getvalue()),"VERIFIED CLUB",
                   (40,20,120,100))

    def test_alpha_trim_and_two_axis_center_in_existing_slot(self):
        im=Image.new("RGBA", (240, 200), (9, 20, 36, 255))
        original=im.copy()
        slot=(40, 20, 120, 100)
        _crest(im, Provider(sample_badge()), "VERIFIED CLUB", slot)
        x0,y0,x1,y1=red_bbox(im)
        self.assertLessEqual(abs((x0+x1)/2-80),1)
        self.assertLessEqual(abs((y0+y1)/2-60),1)
        self.assertLessEqual(x1-x0,80)
        self.assertLessEqual(y1-y0,80)
        for pos in ((0,0),(20,40),(130,60),(80,115)):
            self.assertEqual(original.getpixel(pos),im.getpixel(pos))
        self.assertEqual(im.getpixel((80,60))[:3],(240,20,30))

    def test_original_rgb_stadium_can_accept_same_authentic_alpha_crest(self):
        im=Image.new("RGB", (240, 200), (9, 20, 36))
        _crest(im, Provider(sample_badge()), "VERIFIED CLUB", (40,20,120,100))
        x0,y0,x1,y1=red_bbox(im)
        self.assertLessEqual(abs((x0+x1)/2 - 80), 1)
        self.assertLessEqual(abs((y0+y1)/2 - 60), 1)
        self.assertEqual(im.getpixel((0,0)), (9,20,36))

    def test_missing_or_unrenderable_club_logo_must_fail(self):
        for raw in (b"",sample_badge(empty=True)):
            with self.subTest(case=len(raw)),self.assertRaises(ValueError):
                _crest(Image.new("RGBA", (200,200)),Provider(raw),
                       "VERIFIED CLUB",(20,20,100,100))
        with self.assertRaises(ValueError):
            _crest(Image.new("RGBA", (200,200)),
                   Provider(sample_badge()),"VERIFIED CLUB",(60,20,20,100))


if __name__ == "__main__":
    unittest.main(verbosity=2)
