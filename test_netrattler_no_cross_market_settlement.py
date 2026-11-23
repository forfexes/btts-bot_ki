"""No football result may settle a different premium Telegram photo.

Bookmaker prices can coincide between BTTS, Over and HT markets. Matching
odds alone never proves market or pick identity. No network/Telegram access.
"""
import unittest

from netrattler_stats_match_cards import _result_matches_card_entry


class NoCrossMarketSettlementQA(unittest.TestCase):
    def test_same_price_never_matches_another_market(self):
        tip={"match":"HOME vs AWAY","odds":1.85}
        entries=[("btts",tip),("over25",{**tip,"odds":1.85})]
        for market,group in (
            ("btts","over25"),("over25","btts"),
            ("btts_ht","btts"),("over15_ht","over25"),
            ("combo","btts"),("corners","over25"),
        ):
            with self.subTest(market=market,group=group):
                self.assertFalse(_result_matches_card_entry(
                    market,tip,{"group":group,"odds":1.85},entries))

    def test_known_identical_market_keys_can_still_match(self):
        for market,group in (
            ("btts","btts"),("over25","over"),("over","over25"),
            ("over15_ht","over15_ht"),("corner","corners"),
            ("combo_multi","combo_multi"),
        ):
            with self.subTest(market=market,group=group):
                self.assertTrue(_result_matches_card_entry(
                    market,{"odds":1.78},{"group":group,"odds":1.78},
                    [(market,{"odds":1.78})]))

    def test_duplicate_same_market_requires_matching_actual_price(self):
        entries=[("btts",{"odds":1.85}),("btts",{"odds":2.05})]
        self.assertFalse(_result_matches_card_entry(
            "btts",{"odds":2.05},{"group":"btts","odds":1.85},entries))
        self.assertTrue(_result_matches_card_entry(
            "btts",{"odds":1.85},{"group":"btts","odds":1.85},entries))

    def test_missing_result_market_is_not_any_bets_market(self):
        self.assertFalse(_result_matches_card_entry(
            "btts",{"odds":1.85},{"odds":1.85},[("btts",{})]))


if __name__=="__main__":
    unittest.main(verbosity=2)
