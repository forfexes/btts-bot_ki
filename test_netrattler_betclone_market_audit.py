import unittest
from netrattler_betclone_market_audit import (
    sample_x1_events, summarize_x1, summarize_bwin, market_family, summarize_market_families, quantify_bwin_harvester_mapping, summarize_x1_game_detail, x1_detail_probe
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

    def test_x1_full_market_tree_parses_nested_groups(self):
        sample = {"Value": {"O1": "A", "O2": "B", "GE": [
            {"G": 1, "GN": "Totals", "E": [[{"T": 9, "C": 1.8, "N": "Over 1.5"}],
                                             [{"T": 10, "C": 2.0, "N": "Under 1.5"}]]}
        ]}}
        result = summarize_x1_game_detail(sample)
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["raw_type_counts"].get("9"), 1)
        self.assertEqual(result["raw_type_counts"].get("10"), 1)
        self.assertIn("Totals", result["group_labels"])

    def test_x1_detail_missing_event_fails_closed(self):
        result = summarize_x1_game_detail({"Value": []})
        self.assertFalse(result["has_event"])
        self.assertEqual(result["group_count"], 0)

    def test_bwin_prices_are_counted_only_if_numeric(self):
        p = {"fixtures": [{"games": [{"name": {"value": "Both Teams To Score"},
            "results": [{"name": {"value": "Yes"}, "odds": 1.83},
                        {"name": {"value": "No"}, "odds": None}]}]}]}
        r = summarize_bwin(p)
        self.assertEqual(r["markets"][0]["valid_price_selections"], 1)
        self.assertEqual(summarize_market_families(r)["btts"]["priced_outcomes"], 1)

    def test_existing_bwin_parser_supports_first_half_btts_and_totals(self):
        fixture = {
            "id": 123,
            "startDate": "2026-10-15T18:00:00Z",
            "name": {"value": "A - B"},
            "participants": [{"name": {"value": "A"}}, {"name": {"value": "B"}}],
            "games": [
                {"name": {"value": "Both Teams To Score 1st Half"}, "status": "Visible",
                 "results": [
                     {"name": {"value": "Yes"}, "odds": 1.95},
                     {"name": {"value": "No"}, "odds": 1.82}
                 ]},
                {"name": {"value": "1st Half - Total Goals"}, "status": "Visible",
                 "results": [
                     {"name": {"value": "Over 1.5"}, "odds": 2.0},
                     {"name": {"value": "Under 1.5"}, "odds": 1.75}
                 ]},
            ],
        }
        result = quantify_bwin_harvester_mapping({"fixtures": [fixture]})
        self.assertEqual(result["critical_market_counts"]["btts_ht"], 2)
        self.assertEqual(result["critical_market_counts"]["totals_ht_1_5"], 2)
        self.assertEqual(result["mapped_odds_rows"], 4)

    def test_specific_markets(self):
        self.assertEqual(market_family("Both Teams To Score - 1st Half"), "btts_ht")
        self.assertEqual(market_family("Anytime Goalscorer"), "goalscorer")
        self.assertEqual(market_family("Player Shots On Target"), "shots_on_target")
        self.assertEqual(market_family("1st Half - Total Goals"), "first_half_other")


if __name__ == "__main__":
    unittest.main()
