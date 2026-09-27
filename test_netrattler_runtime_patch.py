#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import netrattler_prop_sources as prop_sources
import netrattler_runtime_patch as patch


def _reset_runtime_state():
    patch._TEAM_ODDS_CACHE.clear()
    patch._TEAM_ODDS_SOURCES.clear()
    patch._FALLBACK_LOGGED = 0
    patch._SKIP_DIAG_EMITTED = False


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
    _reset_runtime_state()

    class Bot:
        TELEGRAM_CHAT_ID = "AI"
        TELEGRAM_GROUPS = {"1x2": "LATE", "scorer": "LATE"}
        @staticmethod
        def env(name, default=""):
            return default
        @staticmethod
        def log(*_args, **_kwargs):
            pass
        @staticmethod
        def get_pinnacle_match_odds(*_args, **_kwargs):
            return {"home_win": 1.70, "draw": 4.10, "away_win": 5.00}
    bot = Bot()
    patch.install_bot(bot)
    assert bot.TELEGRAM_GROUPS["1x2"] == "AI"
    assert bot.TELEGRAM_GROUPS["scorer"] == "LATE"


def test_missing_team_market_quotes_fail_closed():
    _reset_runtime_state()
    old_free = patch.free_odds
    old_specials = prop_sources.fetch_kambi_team_specials
    try:
        class EmptyFree:
            @staticmethod
            def get_1xbet(*_args, **_kwargs): return {}
            @staticmethod
            def get_kambi(*_args, **_kwargs): return {}
            @staticmethod
            def get_odds_api_net(*_args, **_kwargs): return {}
        patch.free_odds = EmptyFree()
        prop_sources.fetch_kambi_team_specials = lambda *_args, **_kwargs: {}

        class Bot:
            TELEGRAM_CHAT_ID = "AI"
            TELEGRAM_GROUPS = {"1x2": "LATE", "scorer": "LATE"}
            @staticmethod
            def env(name, default=""): return default
            @staticmethod
            def log(*_args, **_kwargs): pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs):
                return {"home_win": 1.70, "draw": 4.10, "away_win": 5.00}
        bot = Bot()
        patch.install_bot(bot)
        odds = bot.get_pinnacle_match_odds("A", "B")
        assert odds["btts_yes"] == 1.0
        assert odds["over_25"] == 1.0
        assert odds["_btts_quote_missing"] is True
        assert odds["_over25_quote_missing"] is True
        assert odds["home_win"] == 1.70
    finally:
        patch.free_odds = old_free
        prop_sources.fetch_kambi_team_specials = old_specials


def test_real_team_market_quotes_are_preserved():
    _reset_runtime_state()

    class Bot:
        TELEGRAM_CHAT_ID = "AI"
        TELEGRAM_GROUPS = {"1x2": "LATE", "scorer": "LATE"}
        @staticmethod
        def env(name, default=""): return default
        @staticmethod
        def log(*_args, **_kwargs): pass
        @staticmethod
        def get_pinnacle_match_odds(*_args, **_kwargs):
            return {"btts_yes": 2.06, "over_25": 1.92, "home_win": 1.80}
    bot = Bot()
    patch.install_bot(bot)
    odds = bot.get_pinnacle_match_odds("A", "B")
    assert odds["btts_yes"] == 2.06
    assert odds["over_25"] == 1.92
    assert odds["_ntr_field_sources"]["btts_yes"] == "pinnacle"
    assert odds["_ntr_field_sources"]["over_25"] == "pinnacle"
    assert "_btts_quote_missing" not in odds
    assert "_over25_quote_missing" not in odds


def test_observed_fallback_chain_fills_only_missing_fields_and_tracks_source():
    _reset_runtime_state()
    old_free = patch.free_odds
    old_specials = prop_sources.fetch_kambi_team_specials
    try:
        class FakeFree:
            @staticmethod
            def get_1xbet(*_args, **_kwargs):
                return {"home": 1.74, "draw": 3.75, "away": 4.80, "over_25": 1.93, "_source": "1xbet_bulk"}
            @staticmethod
            def get_kambi(*_args, **_kwargs):
                return {"btts_yes": 1.91, "_source": "kambi_unibet"}
            @staticmethod
            def get_odds_api_net(*_args, **_kwargs):
                return {"btts_yes": 1.95, "over_25": 1.97, "_source": "odds_api_net"}
        patch.free_odds = FakeFree()
        prop_sources.fetch_kambi_team_specials = lambda *_args, **_kwargs: {
            "btts_yes_ht": 2.35,
            "over_15_ht": 2.05,
            "btts_over25_combo": 2.85,
        }

        class Bot:
            TELEGRAM_CHAT_ID = "AI"
            TELEGRAM_GROUPS = {"1x2": "LATE", "scorer": "LATE"}
            @staticmethod
            def env(name, default=""): return default
            @staticmethod
            def log(*_args, **_kwargs): pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs):
                return {"home_win": 1.80}
            @staticmethod
            def enrich_pinnacle_tip(tip, *_args, **_kwargs):
                tip["_source"] = "pinnacle"
                tip["reasoning"] = "Pinnacle Markt-Analyse"
                return tip

        bot = Bot()
        patch.install_bot(bot)
        odds = bot.get_pinnacle_match_odds("Arsenal", "Chelsea")
        assert odds["home_win"] == 1.80, "Pinnacle quote must never be overwritten"
        assert odds["draw"] == 3.75
        assert odds["away_win"] == 4.80
        assert odds["over_25"] == 1.93
        assert odds["btts_yes"] == 1.91
        assert odds["btts_yes_ht"] == 2.35
        assert odds["over_15_ht"] == 2.05
        assert odds["btts_over25_yes"] == 2.85
        assert odds["_ntr_field_sources"]["home_win"] == "pinnacle"
        assert odds["_ntr_field_sources"]["btts_yes"] == "kambi_unibet"
        assert odds["_ntr_field_sources"]["over_25"] == "1xbet_bulk"
        assert odds["_combo_source"].startswith("kambi_")

        tip = {"market": "btts", "tip": "YES", "_source": "pinnacle", "reasoning": "Pinnacle Markt-Analyse"}
        bot.enrich_pinnacle_tip(tip, "Arsenal", "Chelsea", "Premier League")
        assert tip["_source"] == "kambi_unibet"
        assert tip["reasoning"].startswith("kambi_unibet ")
    finally:
        patch.free_odds = old_free
        prop_sources.fetch_kambi_team_specials = old_specials


def test_v37_snapshot_dict_is_read_as_real_odds():
    _reset_runtime_state()
    old_env = os.environ.get("NETRATTLER_ODDS_SNAPSHOT")
    try:
        with tempfile.TemporaryDirectory() as td:
            fn = Path(td) / "snapshot.json"
            fn.write_text(json.dumps({
                "version": "V37",
                "rows": [
                    {"home_team": "Arsenal", "away_team": "Chelsea", "market": "1x2", "selection": "home", "odds": 1.91, "bookmaker": "book_a"},
                    {"home_team": "Arsenal", "away_team": "Chelsea", "market": "totals_2_5", "selection": "over_2_5", "odds": 1.97, "bookmaker": "book_b", "raw": {"line": 2.5}},
                ],
            }), encoding="utf-8")
            os.environ["NETRATTLER_ODDS_SNAPSHOT"] = str(fn)
            odds = patch._snapshot_for_match("Arsenal", "Chelsea")
            assert odds["home_win"] == 1.91
            assert odds["over_25"] == 1.97
            assert odds["_field_sources"]["home_win"] == "book_a"
            assert odds["_field_sources"]["over_25"] == "book_b"
    finally:
        if old_env is None:
            os.environ.pop("NETRATTLER_ODDS_SNAPSHOT", None)
        else:
            os.environ["NETRATTLER_ODDS_SNAPSHOT"] = old_env


def test_coverage_aware_skip_keeps_loop_on_when_groups_are_empty():
    _reset_runtime_state()
    old_force = os.environ.pop("FORCE_LEAGUE_LOOP", None)
    try:
        class Bot:
            TELEGRAM_CHAT_ID = "AI"
            TELEGRAM_GROUPS = {}
            @staticmethod
            def env(name, default=""): return os.getenv(name, default).strip()
            @staticmethod
            def log(*_args, **_kwargs): pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs): return {}
        bot = Bot()
        patch.install_bot(bot)

        def ask_env():
            tips_by_market = {
                "btts": [1, 2, 3, 4, 5],
                "over25": [1, 2, 3, 4],
                "combo": [],
                "btts_ht": [],
                "over15_ht": [1, 2, 3],
                "1x2": [],
            }
            pinnacle_tips_count = 12
            return bot.env("FORCE_LEAGUE_LOOP", "false"), tips_by_market, pinnacle_tips_count

        value, _, _ = ask_env()
        assert value == "true", "Missing groups must force the fallback league loop to stay on"
    finally:
        if old_force is not None:
            os.environ["FORCE_LEAGUE_LOOP"] = old_force


def test_coverage_aware_skip_allows_speed_skip_only_with_full_market_coverage():
    _reset_runtime_state()
    old_force = os.environ.pop("FORCE_LEAGUE_LOOP", None)
    try:
        class Bot:
            TELEGRAM_CHAT_ID = "AI"
            TELEGRAM_GROUPS = {}
            @staticmethod
            def env(name, default=""): return os.getenv(name, default).strip()
            @staticmethod
            def log(*_args, **_kwargs): pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs): return {}
        bot = Bot()
        patch.install_bot(bot)

        def ask_env():
            tips_by_market = {
                "btts": [1, 2, 3],
                "over25": [1, 2],
                "combo": [1],
                "btts_ht": [1],
                "over15_ht": [1, 2],
                "1x2": [1],
            }
            pinnacle_tips_count = 10
            return bot.env("FORCE_LEAGUE_LOOP", "false"), tips_by_market, pinnacle_tips_count

        value, _, _ = ask_env()
        assert value == "false", "Speed skip is allowed only after all required markets have coverage"
    finally:
        if old_force is not None:
            os.environ["FORCE_LEAGUE_LOOP"] = old_force


def main():
    test_kambi_rich_market_parser()
    test_1x2_routes_to_main_only()
    test_missing_team_market_quotes_fail_closed()
    test_real_team_market_quotes_are_preserved()
    test_observed_fallback_chain_fills_only_missing_fields_and_tracks_source()
    test_v37_snapshot_dict_is_read_as_real_odds()
    test_coverage_aware_skip_keeps_loop_on_when_groups_are_empty()
    test_coverage_aware_skip_allows_speed_skip_only_with_full_market_coverage()
    print("OK: runtime odds fallbacks + source attribution + V37 snapshot + coverage-aware skip")


if __name__ == "__main__":
    main()
