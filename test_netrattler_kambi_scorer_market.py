#!/usr/bin/env python3
"""Check Kambi first/last scorer odds cannot masquerade as anytime goalscorer."""
import unittest
from unittest.mock import patch
import netrattler_prop_sources as props


def offer(criterion, offer_type, player, price):
    return {"criterion": {"label": criterion}, "betOfferType": {"name": offer_type},
            "outcomes": [{"participant": player, "label": player, "odds": price}]}


class KambiGoalscorerMarketTests(unittest.TestCase):
    def test_only_explicit_anytime_scorers_survive(self):
        host = props._KAMBI_HOSTS[0]
        brand = "ub"
        eid = 76543210
        listing = {"events": [{"event": {
            "id": eid, "homeName": "Arsenal", "awayName": "Chelsea"}}]}
        offers = {"betOffers": [
            offer("Goalscorer", "First Goalscorer", "John Smith", 41000),
            offer("Goalscorer", "Last Goalscorer", "Alex Jones", 26000),
            offer("Goalscorer", "Goalscorer", "Generic Player", 12000),
            offer("Goalscorer", "Anytime Goalscorer", "Bukayo Saka", 2300),
            offer("Anytime Goalscorer", "Standard", "Martin Odegaard", 2800),
            offer("Player To Score", "Anytime", "Cole Palmer", 3200),
            offer("Goalscorer", "First Half Anytime", "Short Half", 5000),
            offer("Anytime Goalscorer", "To Score 2+", "Multi Goals", 9000),
        ]}
        with (patch.dict(props._KAMBI_LIST_CACHE, {(host, brand): listing}, clear=True),
              patch.dict(props._KAMBI_OFFER_CACHE, {(host, brand, str(eid)): offers}, clear=True)):
            rows = props.fetch_kambi_player_props("Arsenal", "Chelsea", brand=brand)
        players = {row["player"] for row in rows if row["category"] == "score"}
        self.assertEqual(players, {"Bukayo Saka", "Martin Odegaard", "Cole Palmer"})
        self.assertTrue(all(row["odds"] < 4 for row in rows))
        self.assertTrue(all("Anytime" in row["market"] or "To Score" in row["market"]
                            for row in rows))

    def test_unrelated_player_market_unaffected(self):
        host = props._KAMBI_HOSTS[0]
        brand, eid = "ub", 76543211
        listing = {"events": [{"event": {
            "id": eid, "homeName": "Arsenal", "awayName": "Chelsea"}}]}
        offers = {"betOffers": [offer("Player Shots on Target", "Over/Under", "Bukayo Saka", 1850)]}
        with (patch.dict(props._KAMBI_LIST_CACHE, {(host, brand): listing}, clear=True),
              patch.dict(props._KAMBI_OFFER_CACHE, {(host, brand, str(eid)): offers}, clear=True)):
            rows = props.fetch_kambi_player_props("Arsenal", "Chelsea", brand=brand)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "sot")


if __name__ == "__main__":
    unittest.main()
