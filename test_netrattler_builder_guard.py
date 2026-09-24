#!/usr/bin/env python3
"""Deterministic offline regression checks for NETRATTLER builder guard."""
from __future__ import annotations

import os

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


def test_exact_models_only():
    assert guard.model_for_exact("shots", 1.5) == "player_shots_over15_model"
    assert guard.model_for_exact("shots", 2.0) is None
    assert guard.model_for_exact("assist", 0.5) == "player_assist_over05_model"
    assert guard.model_for_exact("tackles_received", 0.5) is None
    assert guard.model_for_exact("sot_outside_box", 0.5) is None


def test_real_odds_only_and_edge_sanity():
    old_min = os.environ.get("NETRATTLER_PROP_BUILDER_MIN_EDGE")
    old_max = os.environ.get("NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE")
    old_ratio = os.environ.get("NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO")
    try:
        os.environ["NETRATTLER_PROP_BUILDER_MIN_EDGE"] = "0.02"
        os.environ["NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE"] = "0.30"
        os.environ["NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO"] = "4.0"

        # No observed quote: fair/model odds may never become bookmaker odds.
        assert guard.normalize_prop_safe(_row(odds=0, fair_odds=2.0, model_prob=0.60)) is None

        # Explicit estimated price is never publishable.
        assert guard.normalize_prop_safe(_row(estimated_odds=True, model_prob=0.60)) is None

        # Low/negative independent edge is rejected.
        assert guard.normalize_prop_safe(_row(odds=1.80, model_prob=0.55)) is None

        # Implausibly huge model-vs-market gap is rejected.
        assert guard.normalize_prop_safe(_row(odds=4.00, model_prob=0.95)) is None

        # A sane real quote + independent probability survives and uses pp edge.
        leg = guard.normalize_prop_safe(_row(odds=2.20, model_prob=0.58))
        assert leg is not None
        expected = (0.58 - 1 / 2.20) * 100
        assert abs(leg.edge - expected) < 0.02

        # Bookmaker-only real prop remains eligible but gets no invented edge.
        leg = guard.normalize_prop_safe(_row(odds=2.20))
        assert leg is not None
        assert leg.edge == 0.0
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
    test_real_odds_only_and_edge_sanity()
    print("OK: NETRATTLER builder guard regression passed")


if __name__ == "__main__":
    main()
