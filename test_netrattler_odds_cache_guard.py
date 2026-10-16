#!/usr/bin/env python3
from __future__ import annotations

import netrattler_odds_cache_guard as guard


def test_best_observed_market_mapping_and_source():
    rows = [
        {"source": "pinnacle", "bookmaker": "BookA", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.91, "raw": {}},
        {"source": "the_odds_api", "bookmaker": "BookB", "home_team": "Arsenal", "away_team": "Chelsea", "market": "totals_2_5", "selection": "over_2_5", "odds": 1.97, "raw": {"line": 2.5}},
        {"source": "pinnacle", "bookmaker": "pinnacle", "home_team": "Arsenal", "away_team": "Chelsea", "market": "1x2", "selection": "home", "odds": 1.82, "raw": {}},
        {"source": "pinnacle", "bookmaker": "BookC", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts_ht", "selection": "yes", "odds": 2.45, "raw": {}},
        {"source": "pinnacle", "bookmaker": "BookC", "home_team": "Arsenal", "away_team": "Chelsea", "market": "totals_ht_1_5", "selection": "over_1_5", "odds": 2.05, "raw": {"line": 1.5}},
    ]
    odds, sources = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert odds["btts_yes"] == 1.91
    assert odds["over_25"] == 1.97
    assert odds["home_win"] == 1.82
    assert odds["btts_yes_ht"] == 2.45
    assert odds["over_15_ht"] == 2.05
    assert sources["btts_yes"] == "pinnacle:BookA"


def test_best_price_wins_for_same_exact_market():
    rows = [
        {"source": "pinnacle", "bookmaker": "A", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.80, "raw": {}},
        {"source": "the_odds_api", "bookmaker": "B", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 1.94, "raw": {}},
    ]
    odds, sources = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert odds["btts_yes"] == 1.94
    assert sources["btts_yes"] == "the_odds_api:B"


def test_wrong_match_and_unknown_market_are_ignored():
    rows = [
        {"source": "pinnacle", "bookmaker": "X", "home_team": "Liverpool", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 2.0, "raw": {}},
        {"source": "pinnacle", "bookmaker": "X", "home_team": "Arsenal", "away_team": "Chelsea", "market": "prediction", "selection": "yes", "odds": 9.0, "raw": {}},
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
            {"btts_yes": "pinnacle:BookA", "over_25": "the_odds_api:BookB", "home_win": "cache"},
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
        assert out["_ntr_field_sources"]["btts_yes"] == "pinnacle:BookA"
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
        guard.best_observed_for_match = lambda *_args, **_kwargs: ({"btts_yes": 1.95}, {"btts_yes": "pinnacle:Book"})

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



def test_verified_bwin_live_but_unlabelled_codes_stay_shadow():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"source": "bwin", "bookmaker": "bwin", "home_team": "Arsenal", "away_team": "Chelsea",
         "market": "btts_ht", "selection": "yes", "odds": 2.50, "raw": {"captured_at": now}},
        {"source": "bwin", "bookmaker": "bwin", "home_team": "Arsenal", "away_team": "Chelsea",
         "market": "totals_ht_1_5", "selection": "over_1_5", "odds": 2.10,
         "raw": {"captured_at": now}},
        {"source": "1xbet_platform", "bookmaker": "1x_22bet", "home_team": "Arsenal",
         "away_team": "Chelsea", "market": "btts_ht", "selection": "yes", "odds": 9,
         "raw": {"captured_at": now}},
    ]
    prices, src = guard.best_observed_for_match("Arsenal", "Chelsea", rows)
    assert prices == {"btts_yes_ht": 2.5, "over_15_ht": 2.1}
    assert src["btts_yes_ht"] == "bwin"


def test_cache_selects_only_relevant_markets_and_paginates():
    from unittest.mock import patch
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    row = {"source": "bwin", "bookmaker": "bwin", "home_team": "Arsenal",
           "away_team": "Chelsea", "match_date": now[:10], "market": "btts",
           "selection": "yes", "odds": 1.90, "raw": {"captured_at": now}}
    calls = []
    class Response:
        def __init__(self, records): self.records = records
        def raise_for_status(self): pass
        def json(self): return self.records
    def fake_get(_url, *, params, **_kwargs):
        calls.append(params)
        return Response([dict(row), dict(row)] if params["offset"] == "0" else [dict(row)])
    with (patch.object(guard, "SUPABASE_URL", "https://example.supabase.co"),
          patch.object(guard, "SUPABASE_KEY", "test-token"),
          patch.object(guard, "PAGE_SIZE", 2),
          patch.object(guard, "MAX_ROWS", 6),
          patch.object(guard.requests, "get", side_effect=fake_get)):
        got = guard._load_rows(force=True)
    assert len(got) == 3
    assert len(calls) == 2
    assert all("bwin" in call["source"] and "1xbet_platform" not in call["source"] for call in calls)
    assert all("btts_ht" in call["market"] and "totals_ht_1_5" in call["market"] for call in calls)
    assert [x["offset"] for x in calls] == ["0", "2"]



def test_rolling_utc_window_uses_yesterday_but_filters_stale_prices():
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch
    now = datetime.now(timezone.utc)
    current = (now - timedelta(hours=4)).isoformat()
    stale = (now - timedelta(hours=30)).isoformat()
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    def row(stamp, captured):
        return {"source": "bwin", "bookmaker": "bwin", "home_team": "Arsenal",
                "away_team": "Chelsea", "match_date": today, "captured_date": captured,
                "market": "btts_ht", "selection": "yes", "odds": 2.4,
                "raw": {"captured_at": stamp}}
    fresh_yesterday = row(current, yesterday)
    stale_yesterday = row(stale, yesterday)
    no_timestamp_yesterday = dict(row(current, yesterday), raw={})

    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return [fresh_yesterday, stale_yesterday, no_timestamp_yesterday]
    def fake_get(_url, *, params, **_kwargs):
        calls.append(params)
        return Response()

    with (patch.object(guard, "SUPABASE_URL", "https://example.supabase.co"),
          patch.object(guard, "SUPABASE_KEY", "token"),
          patch.object(guard.requests, "get", side_effect=fake_get)):
        output = guard._load_rows(force=True)
        assert len(output) == 1, output
        assert calls[0]["captured_date"] == f"gte.{yesterday}"
        assert calls[0]["match_date"] == f"gte.{today}"
        # A second lookup with an empty cache must not issue repeated DB requests.
        guard._load_rows()
        assert len(calls) == 1
    assert guard._fresh(fresh_yesterday)
    assert not guard._fresh(stale_yesterday)


def test_db_failure_clears_stale_match_index():
    from unittest.mock import patch
    stale = {"source": "bwin", "home_team": "Arsenal", "away_team": "Chelsea",
             "market": "btts", "selection": "yes", "odds": 1.91, "raw": {}}
    original_index, original_cache = guard._MATCH_INDEX, guard._CACHE
    try:
        guard._MATCH_INDEX = guard._index_rows([stale])
        with (patch.object(guard, "SUPABASE_URL", "https://example.supabase.co"),
              patch.object(guard, "SUPABASE_KEY", "token"),
              patch.object(guard.requests, "get", side_effect=guard.requests.RequestException("offline"))):
            assert guard._load_rows(force=True) == []
            assert guard._MATCH_INDEX == {}, "Never serve stale quotes after query failure"
    finally:
        guard._MATCH_INDEX, guard._CACHE = original_index, original_cache


def test_live_cache_index_uses_exact_match_and_current_rows_only():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    good = {"source": "bwin", "bookmaker": "bwin", "home_team": "Arsenal",
            "away_team": "Chelsea", "match_date": now[:10], "market": "btts",
            "selection": "yes", "odds": 1.94, "raw": {"captured_at": now}}
    unrelated = dict(good, home_team="Liverpool", odds=5.0)
    indexed = guard._index_rows([good, unrelated])
    old_load, old_index = guard._load_rows, guard._MATCH_INDEX
    try:
        guard._MATCH_INDEX = indexed
        guard._load_rows = lambda **_kwargs: [good, unrelated]
        odds, sources = guard.best_observed_for_match("Arsenal", "Chelsea")
        assert odds == {"btts_yes": 1.94}
        assert sources["btts_yes"] == "bwin"
        assert guard.best_observed_for_match("Arsenal FC", "Chelsea")[0] == {}
    finally:
        guard._load_rows, guard._MATCH_INDEX = old_load, old_index


def main():
    test_best_observed_market_mapping_and_source()
    test_best_price_wins_for_same_exact_market()
    test_wrong_match_and_unknown_market_are_ignored()
    test_wrapper_fills_only_missing_and_preserves_existing_real_quote()
    test_wrapper_uses_kambi_before_history_for_missing_market()
    test_shadow_and_fuzzy_names_never_enter_live()
    test_verified_bwin_live_but_unlabelled_codes_stay_shadow()
    test_cache_selects_only_relevant_markets_and_paginates()
    test_rolling_utc_window_uses_yesterday_but_filters_stale_prices()
    test_db_failure_clears_stale_match_index()
    test_live_cache_index_uses_exact_match_and_current_rows_only()
    print("OK: multi-brand Kambi + fresh odds_history final fallback guard")


def test_shadow_and_fuzzy_names_never_enter_live():
    rows = [
        {"source": "1xbet_platform", "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 9.0, "raw": {}},
        {"source": "pinnacle", "home_team": "Arsenal FC", "away_team": "Chelsea", "market": "btts", "selection": "yes", "odds": 2.0, "raw": {}},
        {"source": "pinnacle", "home_team": "Arsenal", "away_team": "Chelsea", "market": "corners_2_5", "selection": "over", "odds": 3.0, "raw": {}},
    ]
    assert guard.best_observed_for_match("Arsenal", "Chelsea", rows)[0] == {}


if __name__ == "__main__":
    main()
