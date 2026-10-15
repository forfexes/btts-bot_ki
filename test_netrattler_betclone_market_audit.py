import unittest
from netrattler_betclone_market_audit import (
    sample_x1_events, summarize_x1, summarize_bwin, market_family, summarize_market_families
)


class MarketAuditTests(unittest.TestCase):
    def test_x1_detects_only_games_with_teams(self):
        p = {"Value": [{"O1": "A", "O2": "B", "E": [{"T": 180, "C": 1.75}]},
                       {"O1": "", "O2": "B", "E": [{"T": 1, "C": 2}]}]}
        self.assertEqual(len(sample_x1_events(p)), 1)
        result = summarize_x1(p)
        self.assertEqual(result["valid_price_selections"], 1)
        self.assertEqual(result["market_type_codes"][0]["type_code"], "180")

    def test_x1_counts_alternative_markets_without_labelling_unknown_codes(self):
        p = {"Value": [{"O1": "A", "O2": "B", "E": [{"T": 999, "C": 4.5, "P": 2.5}], "AE": []}]}
        result = summarize_x1(p)
        self.assertEqual(result["market_type_codes"][0]["raw_labels"], [])
        self.assertEqual(result["market_type_codes"][0]["line_parameter_count"], 1)

    def test_bwin_prices_are_counted_only_if_numeric(self):
        p = {"fixtures": [{"games": [{"name": {"value": "Both Teams To Score"},
            "results": [{"name": {"value": "Yes"}, "odds": 1.83},
                        {"name": {"value": "No"}, "odds": None}]}]}]}
        r = summarize_bwin(p)
        self.assertEqual(r["markets"][0]["valid_price_selections"], 1)
        self.assertEqual(summarize_market_families(r)["btts"]["priced_outcomes"], 1)

    def test_specific_markets(self):
        self.assertEqual(market_family("Both Teams To Score - 1st Half"), "btts_ht")
        self.assertEqual(market_family("Anytime Goalscorer"), "goalscorer")
        self.assertEqual(market_family("Player Shots On Target"), "shots_on_target")
        self.assertEqual(market_family("1st Half - Total Goals"), "first_half_other")


if __name__ == "__main__":
    unittest.main()
