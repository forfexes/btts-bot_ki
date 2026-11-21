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
                     "combined_quote_id": "BOOK-123"}
        selected = cards.select_cards({"combo": [confirmed]})
        self.assertEqual(selected[0][0][0], "combo")

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


if __name__=="__main__":
    unittest.main()
