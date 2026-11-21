"""Offline send-path regression: new premium masters, no old BIS Telegram cards."""
import io
import os
import unittest
from unittest.mock import patch

from PIL import Image
import netrattler_stats_match_cards as cards


def tip(market="over25"):
    return {"match":"Example United vs Sample Town", "league":"Test League",
            "time_local":"19:30", "oddsYes":1.75, "probability":65.0,
            "_source":"observed_bookmaker", "bookmaker":"verified_bookmaker",
            "tip":"YES", "market":market}


def crest():
    im=Image.new("RGBA",(120,120),(30,150,220,255))
    with io.BytesIO() as f:
        im.save(f,"PNG")
        return f.getvalue()


class PremiumTelegramDispatchTests(unittest.TestCase):
    def test_owner_only_premium_ai_never_sends_unapproved_stickered_master(self):
        # In production, even a verified bookmaker quote is NOT permission to
        # cover a sample-filled owner screenshot with a generic SVG template.
        with patch.dict(os.environ, {"NETRATTLER_ORIGINAL_ONLY":"1"}), \
             patch("netrattler_premium_telegram_adapter.render",
                   side_effect=AssertionError("unapproved premium SVG produced")), \
             patch.object(cards, "render_bis_card",
                          side_effect=AssertionError("old BIS image produced")):
            for market in ("over25","btts_ht","over15_ht","1x2","var",
                           "scorer","corners","combo"):
                with self.subTest(market=market), self.assertRaisesRegex(
                        ValueError, "premium_ai_master_not_owner_approved"):
                    cards.render_card([(market, tip(market))], "2026-11-21")
            self.assertRaisesRegex(
                ValueError,"premium_ai_master_not_owner_approved",
                cards.render_card,
                [("over25",tip()),("btts",tip("btts"))],"2026-11-21")
            # The real BTTS owner renderer is still allowed.
            with patch("netrattler_premium_telegram_adapter.render",
                       return_value=b"owner-original-btts") as approved:
                self.assertEqual(
                    cards.render_card([("btts",tip("btts"))],"2026-11-21"),
                    b"owner-original-btts")
                approved.assert_called_once()

    def test_owner_only_direct_senders_never_repaint_old_sample_tips(self):
        import netrattler_corner_cards as corner
        import netrattler_builder_cards as builder
        with patch.dict(os.environ, {"NETRATTLER_ORIGINAL_ONLY":"1"}), \
             patch.object(cards, "_send_photo",
                          side_effect=AssertionError("unapproved card sent")) as upload, \
             patch.object(cards, "render_scorer_card",
                          side_effect=AssertionError("scorer old card drawn")), \
             patch.object(corner, "render_corner_card",
                          side_effect=AssertionError("corner old card drawn")), \
             patch.object(builder, "render_builder_card",
                          side_effect=AssertionError("builder old card drawn")):
            self.assertFalse(cards.send_scorer_card("token","chat",tip("scorer"),
                                                   "2026-11-21"))
            self.assertIsNone(corner.send_corner_card("token","chat",tip("corners"),
                                                      "2026-11-21"))
            self.assertIsNone(builder.send_builder_card(
                "token","chat",object()))
            upload.assert_not_called()

    def test_owner_only_filters_unapproved_cards_before_crest_cache_or_telegram(self):
        # Verify actual send_cards preflight, not just direct render_card().
        with patch.dict(os.environ, {"NETRATTLER_ORIGINAL_ONLY": "1"}), \
             patch.object(cards, "select_cards", return_value=[
                 [("over25", tip("over25"))],
                 [("scorer", tip("scorer"))],
                 [("corners", tip("corners"))],
                 [("combo", tip("combo"))],
             ]), \
             patch.object(cards, "_crest_cache_load",
                          side_effect=AssertionError("unapproved crest prefetch")), \
             patch.object(cards, "_send_photo",
                          side_effect=AssertionError("unapproved Telegram upload")):
            self.assertEqual(cards.send_cards({}, "2026-11-21", "test", "chat",
                                              log=lambda *_: None), 0)

    def test_owner_only_btts_ignores_legacy_bis_even_with_sandbox_flags(self):
        with patch.dict(os.environ, {"NETRATTLER_ORIGINAL_ONLY": "1",
                                      "NETRATTLER_CARD_LAYOUT": "bis",
                                      "NETRATTLER_SANDBOX_HARDTEST": "1"}), \
             patch.object(cards, "render_bis_card",
                          side_effect=AssertionError("legacy BIS rendered")), \
             patch("netrattler_premium_telegram_adapter.render",
                   return_value=b"approved-owner-btts"):
            self.assertEqual(
                cards.render_card([("btts", tip("btts"))], "2026-11-21"),
                b"approved-owner-btts")

    def test_new_regular_single_market_is_not_old_bis_by_default(self):
        with patch.dict(os.environ,{"NETRATTLER_CARD_LAYOUT":""}), \
             patch.object(cards,"_badge_bytes",return_value=crest()), \
             patch.object(cards,"render_bis_card",side_effect=AssertionError("OLD CARD SENT")):
            raw=cards.render_card([("over25",tip())],"2026-11-19")
        with Image.open(io.BytesIO(raw)) as im:
            self.assertEqual(im.size,(1122,1402))

    def test_no_selection_may_be_silently_reversed_to_yes(self):
        for market in ("btts", "over25", "btts_ht", "over15_ht", "combo"):
            entry = tip(market)
            entry["selection"] = "NO"
            with self.subTest(market=market), \
                 patch.object(cards, "_badge_bytes", return_value=crest()), \
                 patch.object(cards, "render_bis_card",
                              side_effect=AssertionError("Legacy image used")):
                with self.assertRaisesRegex(ValueError, "contradicts"):
                    cards.render_card([(market, entry)], "2026-11-20")

    def test_var_requires_verified_match_kickoff_and_settlement_rules(self):
        base = tip("var")
        base.update(selection="YES", tip_eligible=True,
                    settlement_rule_verified=True,
                    commence_time="2026-11-19T18:30:00Z")
        for bad in ({"tip_eligible": False}, {"settlement_rule_verified": False},
                    {"commence_time": ""}, {"match": "One Team"}):
            with self.subTest(bad=bad), \
                 patch.object(cards, "_badge_bytes", return_value=crest()), \
                 patch.object(cards, "render_bis_card",
                              side_effect=AssertionError("legacy fallback")):
                with self.assertRaises(ValueError):
                    cards.render_card([("var", {**base, **bad})], "2026-11-19")
        with patch.object(cards, "_badge_bytes", return_value=crest()), \
             patch.object(cards, "render_bis_card",
                          side_effect=AssertionError("legacy fallback")):
            image = cards.render_card([("var", base)], "2026-11-19")
        with Image.open(io.BytesIO(image)) as output:
            self.assertEqual(output.size, (1122, 1402))

    def test_conflicting_selection_fields_never_publish_wrong_yes_market(self):
        for market in ("btts", "over25", "btts_ht", "over15_ht", "combo"):
            for contradict in ({"selection": "YES", "tip": "NO"},
                               {"selection": "NO", "tip": "YES"}):
                item = {**tip(market), **contradict}
                with self.subTest(market=market, contradict=contradict), \
                     patch.object(cards, "_badge_bytes", return_value=crest()), \
                     patch.object(cards, "render_bis_card",
                                  side_effect=AssertionError("legacy fallback")):
                    with self.assertRaisesRegex(ValueError, "contradicts"):
                        cards.render_card([(market, item)], "2026-11-21")

    def test_unconfirmed_combo_total_never_enters_telegram_queue(self):
        combo = tip("combo")
        for flags in ({}, {"combined_odds_observed": True},
                      {"combined_quote_id": "BOOK-123"},
                      {"combined_odds_observed": True, "combined_quote_id": ""}):
            with self.subTest(flags=flags):
                self.assertEqual(cards.select_cards({"combo": [{**combo, **flags}]}), [])
        confirmed = {**combo, "combined_odds_observed": True,
                     "combined_quote_id": "BOOK-123", "combined_odds": 3.45}
        selected = cards.select_cards({"combo": [confirmed]})
        self.assertEqual(selected[0][0][0], "combo")
        # Many feeds provide only the ticket-specific combined_odds field.
        only_ticket = {**confirmed, "combined_odds": 3.45}
        only_ticket.pop("oddsYes", None)
        only_ticket.pop("odds", None)
        self.assertEqual(cards.select_cards({"combo": [only_ticket]})[0][0][0], "combo")
        # A single-leg YES quote must never qualify an unpriced combo.
        leg_only = {**confirmed, "oddsYes": 1.65}
        leg_only.pop("odds", None)
        leg_only.pop("combined_odds", None)
        self.assertEqual(cards.select_cards({"combo": [leg_only]}), [])

    def test_unverified_var_never_enters_telegram_send_queue(self):
        var = tip("var")
        var.update(selection="YES", commence_time="2026-11-21T18:30:00Z")
        # Observed bookmaker market by itself is not a valid settlement rule.
        for flags in ({}, {"tip_eligible": True},
                      {"settlement_rule_verified": True},
                      {"tip_eligible": True, "settlement_rule_verified": False}):
            with self.subTest(flags=flags):
                assert cards.select_cards({"var": [{**var, **flags}]}) == []
        eligible = {**var, "tip_eligible": True,
                    "settlement_rule_verified": True}
        qualified = cards.select_cards({"var": [eligible]})
        self.assertEqual(len(qualified), 1)
        self.assertEqual(qualified[0][0][0], "var")
        for bad in ({"commence_time": None},
                    {"commence_time": "2026-11-21T18:30:00"},
                    {"commence_time": "not-a-date"},
                    {"match": "Only One Team"},
                    {"selection": "NO"},
                    {"selection": "YES", "tip": "NO"}):
            with self.subTest(bad=bad):
                self.assertEqual(cards.select_cards({"var": [{**eligible, **bad}]}), [])

    def test_no_silent_fallback_to_old_when_premium_fails(self):
        with patch.dict(os.environ,{"NETRATTLER_CARD_LAYOUT":""}), \
             patch.object(cards,"_badge_bytes",return_value=b""), \
             patch.object(cards,"render_bis_card",side_effect=AssertionError("OLD CARD SENT")):
            with self.assertRaises(ValueError):
                cards.render_card([("over25",tip())],"2026-11-19")

    def test_mixed_market_group_becomes_two_premium_cards(self):
        options={"over25":[tip("over25")],"btts":[tip("btts")]}
        sent=[]
        def fake_send(_token,_chat,_caption,payload,_log):
            with Image.open(io.BytesIO(payload)) as im:
                self.assertEqual(im.size,(1122,1402))
            sent.append(payload)
            return True
        with patch.dict(os.environ,{
                "NETRATTLER_CARD_LAYOUT":"",
                "CREST_PREFETCH_BUDGET_SEC":"0",
                "STATS_MATCH_CARDS_SEND_DELAY_SEC":"0",
                "ENABLE_STATS_MATCH_CARDS":"true",
                "SUPABASE_URL":"",
                "SUPABASE_KEY":"",
            }), \
             patch.object(cards,"_badge_bytes",return_value=crest()), \
             patch.object(cards,"_crest_cache_load"), \
             patch.object(cards,"_crest_cache_save"), \
             patch.object(cards,"_existing_card_signatures",return_value=set()), \
             patch.object(cards,"render_bis_card",side_effect=AssertionError("OLD CARD SENT")), \
             patch.object(cards,"_send_photo",side_effect=fake_send):
            count=cards.send_cards(options,"2026-11-19","dummy","dummy",log=lambda *a:None)
        self.assertEqual(count,2)
        self.assertEqual(len(sent),2)

    def test_old_dashboard_requires_explicit_offline_sandbox(self):
        # Legacy artwork is permitted for isolated regression only.
        fake=b"explicit_offline_legacy"
        with patch.dict(os.environ,{"NETRATTLER_CARD_LAYOUT":"bis",
                                    "NETRATTLER_SANDBOX_HARDTEST":"1"}), \
             patch.object(cards,"render_bis_card",return_value=fake):
            self.assertEqual(cards.render_card([("over25",tip())],"2026-11-19"),fake)

    def test_accidental_legacy_env_flag_does_not_publish_old_card(self):
        with patch.dict(os.environ,{"NETRATTLER_CARD_LAYOUT":"bis",
                                    "NETRATTLER_SANDBOX_HARDTEST":"0"}), \
             patch("netrattler_premium_telegram_adapter.render",
                   return_value=b"PREMIUM") as premium, \
             patch.object(cards,"render_bis_card",
                          side_effect=AssertionError("legacy card sent")):
            self.assertEqual(cards.render_card([("over25",tip())],
                                               "2026-11-19"),b"PREMIUM")
            premium.assert_called_once()


    def test_verified_long_combo_ticket_uses_actual_total_not_leg_odds(self):
        from netrattler_premium_telegram_adapter import _price as premium_price

        verified = {"combined_odds_observed": True,
                    "combined_quote_id": "QA_ACTUAL_BOOKMAKER_TICKET_12",
                    "combined_odds": 312.5, "odds": 1.75}
        self.assertEqual(premium_price(verified, "combo"), 312.5)
        # An alternative observed-total field is valid; the leg's odds is not.
        total_only = {**verified, "total_odds": 312.5}
        total_only.pop("combined_odds")
        self.assertEqual(premium_price(total_only, "combo"), 312.5)
        leg_only = {**verified}
        leg_only.pop("combined_odds")
        with self.assertRaises(ValueError):
            premium_price(leg_only, "combo")
        for field, invalid in (("combined_odds_observed", False),
                               ("combined_quote_id", "  "),
                               ("combined_quote_calculated", True)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    premium_price({**verified, field: invalid}, "combo")
        with self.assertRaises(ValueError):
            premium_price({**verified, "combined_odds": float("inf")}, "combo")
        # Preserve the tighter cap for singles; 312.5 must not become a leg.
        self.assertEqual(premium_price({"oddsYes": 1.75}, "over25"), 1.75)
        with self.assertRaises(ValueError):
            premium_price({"oddsYes": 312.5}, "over25")


    def test_direct_owner_renderers_cannot_bypass_live_overpaint_block(self):
        from netrattler_btts_owner_original import render as owner_btts
        from netrattler_combo_owner_original import render_original_combo
        with patch.dict(os.environ, {"NETRATTLER_BLOCK_OVERPAINTED_MASTERS": "1"}):
            # Both entrypoints must reject before any image processing or
            # external crest lookup, even when called outside send_cards().
            with self.assertRaisesRegex(ValueError, "overpainted"):
                owner_btts({}, "HOME", "AWAY", None, None, 1.75)
            with self.assertRaisesRegex(ValueError, "overpainted"):
                render_original_combo([], combined_odds=None, probability=None,
                    ev=None, confidence=None, stake=None,
                    combined_odds_observed=False, combined_quote_id="",
                    bookmaker="", crest_provider=None)

    def test_production_blocks_opaque_rectangles_on_owner_originals(self):
        # A successful mock PNG is NOT approval for legacy painted screenshot.
        with patch.dict(os.environ, {"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"1"}):
            with patch.object(cards, "render_bis_card",
                              side_effect=AssertionError("legacy fallback")):
                with self.assertRaisesRegex(ValueError, "overpainted"):
                    cards.render_card([("btts", tip("btts"))], "2026-11-21")
            from netrattler_original_template_renderer import render_builder, render_goal
            with self.assertRaisesRegex(ValueError, "overlay-free"):
                render_builder(None)
            with self.assertRaisesRegex(ValueError, "overlay-free"):
                render_goal({}, "2026-11-21")


if __name__=="__main__":
    unittest.main()


def test_owner_verified_large_combos_are_not_mistaken_for_single_market_odds():
    from netrattler_stats_match_cards import _price, select_cards
    verified={
        "market":"combo", "match":"Real Home vs Real Away",
        "source":"QA_REAL_BOOK_SIMULATION", "bookmaker":"QA_REAL_BOOK_SIMULATION",
        "combined_odds":312.5,
        "combined_odds_observed":True,
        "combined_quote_id":"QA_BOOK_TICKET_ORIGINAL",
        "probability":12.5,
    }
    assert _price(verified,"combo")==312.5
    chosen=select_cards({"combo":[verified]})
    assert len(chosen)==1 and chosen[0][0][0]=="combo"
    for key in ("combined_odds_observed","combined_quote_id"):
        bad=dict(verified)
        bad[key]=False if key=="combined_odds_observed" else "  "
        assert _price(bad,"combo") is None
        assert select_cards({"combo":[bad]})==[]
    assert _price({"market":"btts","odds":312.5},"btts") is None
