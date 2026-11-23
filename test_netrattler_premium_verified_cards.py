"""Sandbox-only verified premium PNG test; no API, Telegram or database access."""
import io
import unittest

from PIL import Image, ImageChops, ImageDraw

from netrattler_premium_verified_cards import render_verified_png
from netrattler_premium_telegram_adapter import render, MARKETS


def crest():
    # Real premium emblems have a transparent external boundary. An
    # opaque, rectangular blue mock would be correctly rejected as a
    # pasted-on sticker on the original stadium owner artwork.
    im = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((12, 12, 108, 108),
                               fill=(0, 160, 240, 255))
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
                if market=="combo":
                    item.update(combined_odds_observed=True, combined_odds=2.10,
                                combined_quote_id="QA-OBSERVED-BOOKMAKER-TICKET")
                if market=="var":
                    item.update(selection="YES", tip_eligible=True,
                                settlement_rule_verified=True,
                                commence_time="2026-11-19T18:30:00Z")
                raw=render([(market,item)],"2026-11-19",crest_provider=lambda _:crest())
                with Image.open(io.BytesIO(raw)) as im:
                    self.assertEqual(im.format,"PNG")
                    self.assertEqual(im.size,(1122,1402))
                    self.assertGreater(im.convert("RGB").getextrema()[0][1],170)

    def test_combo_requires_observed_bookmaker_ticket(self):
        base=tip()
        for unsafe in ({}, {"combined_odds_observed": True},
                       {"combined_quote_id": "book-ticket"},
                       {"combined_odds_observed": True, "combined_quote_id": ""}):
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(ValueError,"combined bookmaker"):
                render([("combo", {**base, **unsafe})], "2026-11-19",
                       crest_provider=lambda _:crest())
        ok={**base,"combined_odds_observed":True,"combined_quote_id":"QA-CONFIRMED",
            "combined_odds":3.15}
        with Image.open(io.BytesIO(render([("combo",ok)],"2026-11-19",
                       crest_provider=lambda _:crest()))) as image:
            self.assertEqual(image.size,(1122,1402))

    def test_combo_uses_real_total_not_single_leg_odds_yes(self):
        from unittest.mock import patch
        base={**tip(),"oddsYes":1.40,"odds":1.75,"combined_odds":3.15,
              "combined_odds_observed":True,"combined_quote_id":"QA-COMBINED"}
        with patch("netrattler_premium_telegram_adapter.render_verified_png",
                   wraps=render_verified_png) as renderer:
            render([("combo",base)],"2026-11-19",
                   crest_provider=lambda _:crest())
        self.assertEqual(renderer.call_args.args[1][0]["bookmaker_odds"],3.15)
        with self.assertRaisesRegex(ValueError,"odds missing"):
            render([("combo",{**base,"combined_odds":None})],"2026-11-19",
                   crest_provider=lambda _:crest())

    def test_one_x_two_conflicting_directions_rejected(self):
        for pair in ({"selection":"1","tip":"2"}, {"selection":"X","tip":"HOME"},
                     {"selection":"1X","tip":"X2"}):
            with self.subTest(pair=pair),self.assertRaisesRegex(ValueError,"Conflicting 1X2"):
                render([("1x2",{**tip(),**pair})],"2026-11-19",
                       crest_provider=lambda _:crest())
        for choice in ("1","X","2","1X","X2","12"):
            raw=render([("1x2",{**tip(),"selection":choice,"tip":choice})],
                       "2026-11-19",crest_provider=lambda _:crest())
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.size,(1122,1402))

    def test_var_card_has_real_fixture_and_kickoff_no_unsafe_publication(self):
        from unittest.mock import patch
        base=tip()
        base.update(selection="YES", tip_eligible=True,
                    settlement_rule_verified=True,
                    commence_time="2026-11-19T18:30:00Z")
        with patch("netrattler_premium_telegram_adapter.render_verified_png",
                   wraps=render_verified_png) as renders:
            raw=render([("var",base)],"2026-11-19",
                       crest_provider=lambda _:crest())
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size,(1122,1402))
        self.assertEqual(renders.call_args.args[0],"var")
        self.assertIn("Example United vs Sample Town",
                      renders.call_args.args[1][0]["match"])
        for unsafe in (
            {"tip_eligible":False},
            {"settlement_rule_verified":False},
            {"commence_time":None},
            {"commence_time":"2026-11-19T18:30:00"},
            {"selection":"NO"},
            {"selection":"YES", "tip":"NO"},
            {"selection":"NO", "tip":"YES"},
            {"match":"Example United"},
            {"bookmaker":""},
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                render([("var",{**base,**unsafe})],"2026-11-19",
                       crest_provider=lambda _:crest())

    def test_pixel_inspection_preserves_premium_master_header_and_real_crests(self):
        source=render_verified_png("over",[{
            "match":"Example United vs Sample Town",
            "market":"OVER 2.5 YES",
            "bookmaker_odds":1.75,
            "bookmaker":"verified_bookmaker",
        }])
        target=render([("over25",tip())],"2026-11-19",
                      crest_provider=lambda _:crest())
        with Image.open(io.BytesIO(source)) as base, Image.open(io.BytesIO(target)) as result:
            before=base.convert("RGB").crop((0,0,1122,225))
            after=result.convert("RGB").crop((0,0,1122,225))
            self.assertIsNone(ImageChops.difference(before,after).getbbox(),
                              "Premium header artwork must remain pixel-identical")
            # Our small real test crests have a measurable blue body in both slots.
            home=result.convert("RGB").crop((220,243,340,355))
            away=result.convert("RGB").crop((782,243,902,355))
            # Sample safely inside the flat-colour crest area, not its gold
            # centre marker (which is resampled during thumbnail creation).
            self.assertEqual(home.getpixel((25,25)),(0,160,240))
            self.assertEqual(away.getpixel((25,25)),(0,160,240))

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
