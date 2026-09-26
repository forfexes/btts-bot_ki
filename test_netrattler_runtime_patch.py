#!/usr/bin/env python3
from __future__ import annotations

import netrattler_prop_sources as prop_sources
import netrattler_runtime_patch as patch


def test_kambi_rich_market_parser():
    old_list = dict(prop_sources._KAMBI_LIST_CACHE)
    old_offer = dict(prop_sources._KAMBI_OFFER_CACHE)
    try:
        host = prop_sources._KAMBI_HOSTS[0]
        prop_sources._KAMBI_LIST_CACHE.clear()
        prop_sources._KAMBI_OFFER_CACHE.clear()
        prop_sources._KAMBI_LIST_CACHE[(host, "ub")] = {
            "events": [{"event": {"id": 77, "homeName": "Arsenal", "awayName": "Chelsea"}}]
        }
        prop_sources._KAMBI_OFFER_CACHE[(host, "ub", "77")] = {
            "betOffers": [
                {
                    "criterion": {"label": "Player Performance"},
                    "betOfferType": {"name": "Player Shots on Target"},
                    "outcomes": [{"participant": "Bukayo Saka", "label": "Over 0.5", "line": 500, "odds": 1720}],
                },
                {
                    "criterion": {"label": "Player Tackles"},
                    "outcomes": [{"participant": "Declan Rice", "label": "Over 1.5", "line": 1500, "odds": 1900}],
                },
                {
                    "criterion": {"label": "Player Fouls Won"},
                    "outcomes": [{"participant": "Cole Palmer", "label": "Over 0.5", "line": 500, "odds": 1650}],
                },
            ]
        }
        rows = patch.fetch_kambi_player_props_rich("Arsenal", "Chelsea", "ub")
        cats = {row["category"] for row in rows}
        assert {"sot", "tackles_committed", "fouls_won"}.issubset(cats), cats
        assert all(row["odds"] > 1 and row["real_observed_line"] is True for row in rows)
    finally:
        prop_sources._KAMBI_LIST_CACHE.clear(); prop_sources._KAMBI_LIST_CACHE.update(old_list)
        prop_sources._KAMBI_OFFER_CACHE.clear(); prop_sources._KAMBI_OFFER_CACHE.update(old_offer)


def test_1x2_routes_to_main_only():
    class Bot:
        TELEGRAM_CHAT_ID = "AI"
        TELEGRAM_GROUPS = {"1x2": "LATE", "scorer": "LATE"}
    bot = Bot()
    patch.install_bot(bot)
    assert bot.TELEGRAM_GROUPS["1x2"] == "AI"
    assert bot.TELEGRAM_GROUPS["scorer"] == "LATE"


def main():
    test_kambi_rich_market_parser()
    test_1x2_routes_to_main_only()
    print("OK: runtime routing + rich Kambi prop parser")


if __name__ == "__main__":
    main()
