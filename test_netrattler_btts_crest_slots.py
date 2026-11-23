"""NETRATTLER BTTS owner crests occupy original slots, not stickers.

Offline synthetic sources; never sends Telegram, queries bookmaker providers
or changes the owner's immutable 1122×1402 stadium / crown artwork.
"""
import unittest
from PIL import Image, ImageDraw

from netrattler_btts_owner_original import _crest


def emblem(pad=0):
    # Both variants carry the SAME real visible 30x92 emblem. Only the
    # untrusted provider's invisible canvas border is different.
    img=Image.new("RGBA",(40+2*pad,102+2*pad),(0,0,0,0))
    ImageDraw.Draw(img).rectangle(
        (pad+5,pad+5,pad+34,pad+96),fill=(241,22,39,255))
    return img


def box_of_red(img):
    mask=Image.new("L",img.size,0)
    from PIL import ImageChops
    px=img.convert("RGB").load(); out=mask.load()
    for y in range(330,545):
        for x in range(150,420):
            r,g,b=px[x,y]
            if r>225 and g<60 and b<70:
                out[x,y]=255
    return mask.getbbox()


class ActualBttsCrestSlotQA(unittest.TestCase):
    def test_padding_cannot_shrink_or_shift_real_logo(self):
        tight=Image.new("RGBA",(1122,1402),(8,24,39,255))
        padded=tight.copy()
        _crest(tight,emblem(),281)
        _crest(padded,emblem(60),281)
        self.assertEqual(tight.tobytes(),padded.tobytes())
        bounds=box_of_red(tight)
        self.assertIsNotNone(bounds)
        x0,y0,x1,y1=bounds
        self.assertLessEqual(abs((x0+x1)/2-281),1)
        self.assertLessEqual(abs((y0+y1)/2-427.5),1)
        self.assertEqual(y1-y0,155)
        self.assertEqual(tight.getpixel((0,0)),(8,24,39,255))
        self.assertEqual(tight.getpixel((550,800)),(8,24,39,255))

    def test_invisible_or_microscopic_crest_is_rejected(self):
        for logo in (Image.new("RGBA",(200,200),(0,0,0,0)),
                     Image.new("RGBA",(100,100),(0,0,0,0))):
            with self.assertRaisesRegex(ValueError,"visible"):
                _crest(Image.new("RGBA",(1122,1402)),logo,281)
        tiny=Image.new("RGBA",(100,100),(0,0,0,0))
        tiny.putpixel((50,50),(241,22,39,255))
        with self.assertRaisesRegex(ValueError,"too small"):
            _crest(Image.new("RGBA",(1122,1402)),tiny,281)


if __name__=="__main__":
    unittest.main(verbosity=2)
