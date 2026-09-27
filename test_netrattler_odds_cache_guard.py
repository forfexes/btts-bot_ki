#!/usr/bin/env python3
from __future__ import annotations

import netrattler_odds_cache_guard as guard


def test_best_observed_market_mapping_and_source():
    rows = [
        {"source": "aiscore", "bookmaker": "BookA", "home_team": "Arsenal FC", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.91, "raw": {}},
        {"source": "the_odds_api", "bookmaker": "BookB", "home_team": "Arsenal", "away_team": "Chelsea FC", "market": "totals_2_5", "selection": "over_2_5", "odds": 1.97, "raw": {"line": 2.5}},
        {"source": "pinnacle", "bookmaker": "pinnacle", "home_team": "Arsenal", "away_team": "Chelsea", "market": "1x2", "selection": "home", "odds": 1.82, "raw": {}},
        {"source": "aiscore", "bookmaker": "BookC", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts_ht", "selection": "yes", "odds": 2.45, "raw": {}},
        {"source": "aiscore", "bookmaker": "BookC", "home_team": "Arsenal", "away_team": "Chelsea", "market": "totals_ht_1_5", "selection": "over_1_5", "odds": 2.05, "raw": {"line": 1.5}},
    ]
    odds, sources = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert odds["btts_yes"] == 1.91
    assert odds["over_25"] == 1.97
    assert odds["home_win"] == 1.82
    assert odds["btts_yes_ht"] == 2.45
    assert odds["over_15_ht"] == 2.05
    assert sources["btts_yes"] == "aiscore:BookA"


def test_best_price_wins_for_same_exact_market():
    rows = [
        {"source": "a", "bookmaker": "A", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.80, "raw": {}},
        {"source": "b", "bookmaker": "B", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.94, "raw": {}},
    ]
    odds, sources = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert odds["btts_yes"] == 1.94
    assert sources["btts_yes"] == "b:B"


def test_wrong_match_and_unknown_market_are_ignored():
    rows = [
        {"source": "x", "bookmaker": "X", "home_team": "Liverpool", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 2.0, "raw": {}},
        {"source": "x", "bookmaker": "X", "home_team": "Arsenal", "away_team": "Chelsea", "market": "prediction", "selection": "yes", "odds": 9.0, "raw": {}},
    ]
    odds, _ = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert odds == {}


def test_wrapper_fills_only_missing_and_preserves_existing_real_quote():
    old_history = guard.best_observed_for_match
    old_kambi = guard.kambi_team
    try:
        # Isolate this unit test from live keyless Kambi networking. Kambi has its
        # own parser/integration tests; this test is specifically for odds_history.
        guard.kambi_team = None
        guard.best_observed_for_match = lambda *_args, **_kwargs: (
            {"btts_yes": 1.92, "over_25": 1.98, "home_win": 2.10},
            {"btts_yes": "aiscore:BookA", "over_25": "the_odds_api:BookB", "home_win": "cache"},
        )

        class Bot:
            @staticmethod
            def log(*_args, **_kwargs):
                pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs):
                return {
                    "btts_yes": 1.0,
                    "_btts_quote_missing": True,
                    "over_25": 1.86,
                    "home_win": 1.88,
                    "_ntr_field_sources": {"over_25": "pinnacle", "home_win": "pinnacle"},
                }

        bot = Bot()
        guard.install(bot)
        out = bot.get_pinnacle_match_odds("Arsenal", "Chelsea")
        assert out["btts_yes"] == 1.92
        assert "_btts_quote_missing" not in out
        assert out["over_25"] == 1.86, "existing observed quote must not be overwritten"
        assert out["home_win"] == 1.88, "existing observed quote must not be overwritten"
        assert out["_ntr_field_sources"]["btts_yes"] == "aiscore:BookA"
    finally:
        guard.best_observed_for_match = old_history
        guard.kambi_team = old_kambi


def test_wrapper_uses_kambi_before_history_for_missing_market():
    old_history = guard.best_observed_for_match
    old_kambi = guard.kambi_team
    try:
        class FakeKambi:
            @staticmethod
            def get_multi_brand_team_odds(*_args, **_kwargs):
                return {"btts_yes": 1.89}, {"btts_yes": "kambi_bs"}
        guard.kambi_team = FakeKambi()
        guard.best_observed_for_match = lambda *_args, **_kwargs: ({"btts_yes": 1.95}, {"btts_yes": "aiscore:Book"})

        class Bot:
            @staticmethod
            def log(*_args, **_kwargs): pass
            @staticmethod
            def get_pinnacle_match_odds(*_args, **_kwargs):
                return {"btts_yes": 1.0, "_btts_quote_missing": True}

        bot = Bot(); guard.install(bot)
        out = bot.get_pinnacle_match_odds("A", "B")
        assert out["btts_yes"] == 1.89
        assert out["_ntr_field_sources"]["btts_yes"] == "kambi_bs"
    finally:
        guard.best_observed_for_match = old_history
        guard.kambi_team = old_kambi


def main():
    test_best_observed_market_mapping_and_source()
    test_best_price_wins_for_same_exact_market()
    test_wrong_match_and_unknown_market_are_ignored()
    test_wrapper_fills_only_missing_and_preserves_existing_real_quote()
    test_wrapper_uses_kambi_before_history_for_missing_market()
    print("OK: multi-brand Kambi + fresh odds_history final fallback guard")


if __name__ == "__main__":
    main()
