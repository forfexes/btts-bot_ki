#!/usr/bin/env python3
from __future__ import annotations

import os

import netrattler_builder_engine as builder
import netrattler_builder_styles as styles
import netrattler_builder_concepts_v2 as concepts


def row(player, category, line, odds, prob, market=None):
    return {
        "player": player,
        "team": "A" if player in {"P1", "P2", "P3", "P4"} else "B",
        "match": "A vs B",
        "league": "Test",
        "market": market or f"Player {category} Over {line}",
        "category": category,
        "line": line,
        "odds": odds,
        "model_prob": prob,
        "source": "kambi_test",
        "real_observed_line": True,
    }


def test_extra_concepts_real_odds_only():
    os.environ["NETRATTLER_BUILDER_MIN_LEG_EDGE"] = "2"
    os.environ["NETRATTLER_BUILDER_MIN_ODDS"] = "2.0"
    styles.install()
    concepts.install()
    # Raw bookmaker thresholds: O1.5 means 2+, O2.5 means 3+.
    raw = [
        row("P1", "shots", 1.5, 1.90, 0.66),
        row("P2", "shots", 1.5, 1.85, 0.65),
        row("P3", "shots", 2.5, 2.40, 0.50),
        row("P4", "shots", 1.5, 1.80, 0.67),
        row("P5", "shots", 1.5, 1.95, 0.62),
        row("P6", "fouls", 1.5, 1.85, 0.64),
        row("P7", "fouls_won", 1.5, 1.90, 0.62),
        row("P8", "tackles_committed", 1.5, 1.80, 0.68),
        row("P9", "sot", 1.5, 1.75, 0.68),
    ]
    # Small cap deliberately proves the wrapper reserves one slot for every
    # available new screenshot family rather than silently truncating them.
    picks = builder.build_builder_picks(raw, match_date="2026-09-26", max_builders=8)
    styles_found = {p.style for p in picks}
    assert "SHOT BOMB" in styles_found, styles_found
    assert "CONTACT MIX" in styles_found, styles_found
    assert "ATTACK CONTACT MIX" in styles_found, styles_found
    assert "HIGH LINE MIX" in styles_found, styles_found
    for pick in picks:
        if pick.style in {"SHOT BOMB", "CONTACT MIX", "ATTACK CONTACT MIX", "HIGH LINE MIX"}:
            assert all(not leg.estimated and leg.odds > 1 and leg.edge >= 2 for leg in pick.legs)
            if len({leg.match for leg in pick.legs}) == 1:
                msg = builder.format_builder_message(pick)
                assert "live beim Bookmaker prüfen" in msg
                assert "synthetische Produktquote" in msg


def test_estimated_or_unmodelled_never_enters_new_concepts():
    bad = row("Bad", "shots", 2.5, 3.0, 0.0)
    leg = builder.normalize_prop(bad)
    # With no independent probability the engine explicitly keeps edge at zero.
    assert leg is not None and leg.edge == 0
    assert concepts._extra([bad], "2026-09-26") == []


def main():
    test_extra_concepts_real_odds_only()
    test_estimated_or_unmodelled_never_enters_new_concepts()
    print("OK: Contact/Attack-Contact/High-Line/Shot-Bomb concepts")


if __name__ == "__main__":
    main()
