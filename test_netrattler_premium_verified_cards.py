"""Sandbox-only verified premium PNG test; no API, Telegram or database access."""
import io
import unittest

from PIL import Image

from netrattler_premium_verified_cards import render_verified_png
from netrattler_premium_telegram_adapter import render, MARKETS


def crest():
    im = Image.new("RGBA", (120, 120), (0, 160, 240, 255))
    im.putpixel((60, 60), (252, 220, 30, 255))
    with io.BytesIO() as out:
        im.save(out, format="PNG")
        return out.getvalue()


def tip():
    return {"match":"Example United vs Sample Town", "league":"Test League",
            "time_local":"19:30", "oddsYes":1.75,
            "probability":65.0, "bookmaker":"verified_bookmaker"}


class PremiumVerifiedCardsTests(unittest.TestCase):
    def test_all_supported_regular_market_masters_render_nonempty_png(self):
        for market in MARKETS:
            with self.subTest(market=market):
                item=tip()
                if market=="1x2":
                    item["selection"]="1"
                raw=render([(market,item)],"2026-11-19",crest_provider=lambda _:crest())
                with Image.open(io.BytesIO(raw)) as im:
                    self.assertEqual(im.format,"PNG")
                    self.assertEqual(im.size,(1122,1402))
                    self.assertGreater(im.convert("RGB").getextrema()[0][1],170)

    def test_result_is_drawn_on_same_premium_master(self):
        before=render([("over25",tip())],"2026-11-19",
                      crest_provider=lambda _:crest())
        after=render([("over25",tip())],"2026-11-19",
                     crest_provider=lambda _:crest(),
                     result={"marks":{"0":"win"},"ft":"3:2"})
        self.assertNotEqual(before,after)

    def test_fake_odds_and_missing_real_crests_fail_closed(self):
        original=tip()
        for change in ({"oddsYes":0},{"bookmaker":""},{"_no_real_odds":True},
                       {"synthetic":True},{"estimated_odds":True}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    render([("over25",{**original,**change})],"2026-11-19",
                           crest_provider=lambda _:crest())
        with self.assertRaisesRegex(ValueError,"crest"):
            render([("over25",original)],"2026-11-19",
                   crest_provider=lambda _:b"")
        with self.assertRaisesRegex(ValueError,"crest"):
            render([("over25",original)],"2026-11-19",
                   crest_provider=lambda _:b"not-an-image"*50)

    def test_never_silently_drop_a_second_market(self):
        with self.assertRaisesRegex(ValueError,"single-market"):
            render([("over25",tip()),("btts",tip())],"2026-11-19",
                   crest_provider=lambda _:crest())

    def test_direct_master_denies_unverified_source(self):
        with self.assertRaises(ValueError):
            render_verified_png("over",[{"match":"A vs B","market":"OVER 2.5 YES",
                                         "bookmaker_odds":1.75,"bookmaker":""}])


if __name__=="__main__":
    unittest.main()
