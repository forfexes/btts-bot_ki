#!/usr/bin/env python3
"""Deterministic offline regression checks for NETRATTLER builder/quote guard."""
from __future__ import annotations

import os
from types import SimpleNamespace

import netrattler_builder_guard as guard


def _row(**overrides):
    row = {
        "player": "Test Player",
        "team": "Portugal",
        "match": "Portugal vs Wales",
        "league": "International",
        "market": "Player Shots Over 1.5",
        "category": "shots",
        "line": 1.5,
        "odds": 2.20,
        "source": "kambi_ub",
    }
    row.update(overrides)
    return row


def test_binary_semantics():
    clean = guard._sanitize_row(_row(category="assist", market="To give an assist Over 1", line=1.0))
    assert clean is not None
    assert clean["line"] == 0.5
    assert clean["market"] == "To Give an Assist"

    clean = guard._sanitize_row(_row(category="yellow_cards", market="To Get a Card Over 1", line=1.0))
    assert clean is not None
    assert clean["line"] == 0.5
    assert clean["market"] == "To Get a Card"


def test_bad_semantics_rejected():
    assert guard._sanitize_row(_row(
        player="Cristiano Ronaldo || Rafael Leao Either Player",
        market="Either Player To Score Over 0.5",
        category="score",
        line=0.5,
    )) is None
    assert guard._sanitize_row(_row(
        market="Player’s Shots on Target - 1st Half Over 0.5",
        category="sot",
        line=0.5,
    )) is None
    assert guard._sanitize_row(_row(
        market="To score from a header",
        category="score",
        line=0.5,
    )) is None
    # Kambi sometimes exposes the outcome label as the "participant".  It is
    # a line/selection, not a player and must never reach Telegram.
    assert guard._sanitize_row(_row(
        player="Over 0.5",
        market="To Get a Card",
        category="yellow_cards",
        line=0.5,
    )) is None


def test_exact_models_only():
    assert guard.model_for_exact("shots", 1.5) == "player_shots_over15_model"
    assert guard.model_for_exact("shots", 2.0) is None
    assert guard.model_for_exact("assist", 0.5) == "player_assist_over05_model"
    assert guard.model_for_exact("tackles_received", 0.5) is None
    assert guard.model_for_exact("sot_outside_box", 0.5) is None


def test_pinnacle_american_conversion():
    assert abs(guard._pinnacle_decimal(105) - 2.05) < 1e-9
    assert abs(guard._pinnacle_decimal(398) - 4.98) < 1e-9
    assert abs(guard._pinnacle_decimal(-150) - 1.6667) < 1e-9
    assert abs(guard._pinnacle_decimal(-125) - 1.8) < 1e-9
    assert guard._pinnacle_decimal(2.15) == 2.15


class _FakeResponse:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok
    def json(self):
        return self._payload


class _FakeRequests:
    def get(self, url, **kwargs):
        if url.endswith("/markets/related/straight"):
            return _FakeResponse([
                {"type": "moneyline", "period": 0, "prices": [
                    {"designation": "home", "price": 398},
                    {"designation": "draw", "price": 220},
                    {"designation": "away", "price": -150},
                ]},
                {"type": "total", "period": 0, "prices": [
                    {"designation": "over", "points": 2.5, "price": 105},
                    {"designation": "under", "points": 2.5, "price": -125},
                ]},
            ])
        if url.endswith("/related"):
            return _FakeResponse([])
        return _FakeResponse([], ok=False)


def test_installed_pinnacle_guard_and_single_cap():
    cache = {}
    fake = SimpleNamespace(
        _PIN_ODDS_CACHE=cache,
        _cache_get=lambda c, k: c.get(k),
        _cache_set=lambda c, k, v: c.__setitem__(k, v),
        requests=_FakeRequests(),
        PINNACLE_BASE="https://pinnacle.test",
        PINNACLE_HEADERS={},
        filter_tips_legacy_safe=lambda tips, market="btts", odds_data=None: list(tips),
    )
    guard._install_pinnacle_guard(fake)
    odds = fake.fetch_pinnacle_match_odds(123)
    assert odds is not None
    assert abs(odds["home_win"] - 4.98) < 1e-9
    assert abs(odds["away_win"] - 1.6667) < 1e-9
    assert abs(odds["over_25"] - 2.05) < 1e-9
    assert abs(odds["under_25"] - 1.8) < 1e-9

    old_cap = os.environ.get("NETRATTLER_MAX_SINGLE_ODDS")
    try:
        os.environ["NETRATTLER_MAX_SINGLE_ODDS"] = "3.0"
        kept = fake.filter_tips_legacy_safe(
            [{"odds": 4.98}, {"odds": 2.09}], market="1x2"
        )
        assert kept == [{"odds": 2.09}]
    finally:
        if old_cap is None:
            os.environ.pop("NETRATTLER_MAX_SINGLE_ODDS", None)
        else:
            os.environ["NETRATTLER_MAX_SINGLE_ODDS"] = old_cap


def test_real_odds_only_and_edge_sanity():
    old_min = os.environ.get("NETRATTLER_PROP_BUILDER_MIN_EDGE")
    old_max = os.environ.get("NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE")
    old_ratio = os.environ.get("NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO")
    try:
        os.environ["NETRATTLER_PROP_BUILDER_MIN_EDGE"] = "0.02"
        os.environ["NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE"] = "0.30"
        os.environ["NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO"] = "4.0"

        assert guard.normalize_prop_safe(_row(odds=0, fair_odds=2.0, model_prob=0.60)) is None
        assert guard.normalize_prop_safe(_row(estimated_odds=True, model_prob=0.60)) is None
        assert guard.normalize_prop_safe(_row(odds=1.80, model_prob=0.55)) is None
        assert guard.normalize_prop_safe(_row(odds=4.00, model_prob=0.95)) is None

        leg = guard.normalize_prop_safe(_row(odds=2.20, model_prob=0.58))
        assert leg is not None
        expected = (0.58 - 1 / 2.20) * 100
        assert abs(leg.edge - expected) < 0.02

        leg = guard.normalize_prop_safe(_row(odds=2.20))
        assert leg is not None
        assert leg.edge == 0.0

        # Pinnacle/Kambi sometimes expose a probability derived from the same
        # bookmaker quote. That is not independent model evidence and must not
        # be rejected as negative edge; REAL_ODDS_ONLY compatibility keeps it
        # with edge=0 until player ML/history enriches the row.
        leg = guard.normalize_prop_safe(_row(
            odds=2.20, probability=43.0, source="pinnacle"
        ))
        assert leg is not None
        assert leg.edge == 0.0

        # Explicit player-history/model provenance remains subject to the
        # positive-edge guard.
        leg = guard.normalize_prop_safe(_row(
            odds=2.20, probability=0.58, probability_source="player_history"
        ))
        assert leg is not None
        expected = (0.58 - 1 / 2.20) * 100
        assert abs(leg.edge - expected) < 0.02
    finally:
        if old_min is None:
            os.environ.pop("NETRATTLER_PROP_BUILDER_MIN_EDGE", None)
        else:
            os.environ["NETRATTLER_PROP_BUILDER_MIN_EDGE"] = old_min
        if old_max is None:
            os.environ.pop("NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE", None)
        else:
            os.environ["NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE"] = old_max
        if old_ratio is None:
            os.environ.pop("NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO", None)
        else:
            os.environ["NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO"] = old_ratio


def main():
    test_binary_semantics()
    test_bad_semantics_rejected()
    test_exact_models_only()
    test_pinnacle_american_conversion()
    test_installed_pinnacle_guard_and_single_cap()
    test_real_odds_only_and_edge_sanity()
    print("OK: NETRATTLER builder/quote guard regression passed")


if __name__ == "__main__":
    main()
