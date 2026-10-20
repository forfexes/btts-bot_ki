"""Kambi per-player line offers: player name comes from the criterion, not from 'Over 0.5'."""
import unittest
import netrattler_prop_sources as ps

class T(unittest.TestCase):
    def test_name_from_criterion(self):
        f = ps.kambi_player_from_criterion
        self.assertEqual(f("Florian Lejeune fouls committed (Settled using Opta data)"), "Florian Lejeune")
        self.assertEqual(f("Lejeune, Florian shots on target (Settled using Opta data)"), "Florian Lejeune")
        self.assertEqual(f("Player's shots (Settled using Opta data)"), "")
        self.assertEqual(f("Total Goals"), "")

    def test_offer_rows_keep_distinct_players(self):
        host = ps._KAMBI_HOSTS[0]
        ps._KAMBI_LIST_CACHE[(host, "ub")] = {"events": [{"event": {"id": 7, "homeName": "Getafe CF", "awayName": "Rayo Vallecano"}}]}
        def bo(name, odds):
            return {"criterion": {"label": f"{name} fouls committed (Settled using Opta data)"},
                    "betOfferType": {"name": "Player Occurrence Line"},
                    "outcomes": [{"label": "Over 0.5", "odds": odds, "line": 500},
                                 {"label": "Under 0.5", "odds": 1500, "line": 500}]}
        ps._KAMBI_OFFER_CACHE[(host, "ub", "7")] = {"betOffers": [bo("Florian Lejeune", 1600), bo("Mauro Arambarri", 1550)]}
        rows = ps.fetch_kambi_player_props("Getafe CF", "Rayo Vallecano", brand="ub")
        fouls = [r for r in rows if r["category"] in ("fouls", "fouls_committed")]
        self.assertEqual(sorted(r["player"] for r in fouls), ["Florian Lejeune", "Mauro Arambarri"])
        self.assertTrue(all(r["line"] == 0.5 for r in fouls))

if __name__ == "__main__":
    unittest.main()
