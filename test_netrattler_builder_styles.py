#!/usr/bin/env python3
from __future__ import annotations

import os

import netrattler_builder_engine as builder
import netrattler_builder_styles as styles

styles.install()

os.environ["NETRATTLER_BUILDER_MIN_ODDS"] = "2.5"
os.environ["NETRATTLER_PROP_BUILDER_MIN_ODDS"] = "2.5"
os.environ["NETRATTLER_BUILDER_MAX_LEGS"] = "9"
os.environ["NETRATTLER_BUILDER_MIN_LEG_EDGE"] = "2.0"


def row(player, market, category, line, odds, prob, match="Sunderland vs Arsenal"):
    return {
        "player": player, "team": "", "match": match, "league": "PL",
        "market": market, "category": category, "line": line, "odds": odds,
        "source": "kambi_ub", "model_prob": prob, "probability": prob,
        "hit_rate": prob, "games": 15,
    }


def test_tips_bible_and_nate():
    rows = [
        row("Bukayo Saka", "To Score or Assist", "score_assist", .5, 1.75, .66),
        row("Kai Havertz", "1+ Shots on Target", "sot", .5, 1.45, .74),
        row("Bukayo Saka", "1+ Shots on Target", "sot", .5, 1.38, .78),
        row("Enzo Le Fee", "1+ Shots", "shots", .5, 1.28, .84),
        row("Nordi Mukiele", "2+ Tackles", "tackles", 1.5, 1.55, .71),
        row("Jurrien Timber", "1+ Tackles", "tackles", .5, 1.30, .82),
        row("Riccardo Calafiori", "1+ Tackles", "tackles", .5, 1.32, .80),
        row("Bukayo Saka", "2+ Fouls Won", "fouls_won", 1.5, 1.80, .65),
        row("Granit Xhaka", "1+ Tackles", "tackles", .5, 1.35, .79),
        row("Declan Rice", "1+ Fouls Committed", "fouls", .5, 1.30, .83),
        row("Martin Odegaard", "1+ Fouls Won", "fouls_won", .5, 1.40, .76),
    ]
    picks = builder.build_builder_picks(rows, match_date="2026-09-25", max_builders=30)
    assert any(p.style == "TIPS BIBLE" for p in picks)
    assert any(p.style == "NATE CATEGORY" for p in picks)
    assert any(p.style == "GODTIPSTER PROFILE" for p in picks)
    noisy = {"SAME GAME MIXED", "SAME MATCH AVAILABLE", "MIXED EDGE", "FAVORITE SCRIPT", "ATTACK SCRIPT"}
    assert all(p.style not in noisy for p in picks)
    same = next(p for p in picks if p.style == "TIPS BIBLE")
    msg = builder.format_builder_message(same)
    assert "Builder-Quote" in msg and "Keine synthetische Produktquote" in msg
    assert "Gesamt-Quote" not in msg
    db = same.to_row()
    assert db["total_odds"] == 0.0 and db["stake"] == 0.0 and db["estimated_odds"] is True


def test_aystar_and_alt_lines():
    cards = [
        row("Bruno Fernandes", "To Score or Assist", "score_assist", .5, 2.10, .55, "Man Utd vs Man City"),
        row("Phil Foden", "To Score or Assist", "score_assist", .5, 2.00, .57, "Man Utd vs Man City"),
        row("Patrick Dorgu", "To Get a Card", "yellow_cards", .5, 3.00, .39, "Man Utd vs Man City"),
        row("Lisandro Martinez", "To Get a Card", "yellow_cards", .5, 3.20, .38, "Man Utd vs Man City"),
    ]
    picks = builder.build_builder_picks(cards, match_date="2026-09-25", max_builders=20)
    assert any(p.style == "AYSTAR BOOKING" for p in picks)
    assert any(p.style == "AYSTAR MIX" for p in picks)
    assert all("SAFE" not in p.variant for p in picks if p.style.startswith("AYSTAR"))

    alts = [
        row("Player X", "1+ Tackles", "tackles", .5, 1.45, .78, "M vs N"),
        row("Player X", "2+ Tackles", "tackles", 1.5, 2.10, .58, "M vs N"),
        row("Player X", "3+ Tackles", "tackles", 2.5, 3.40, .38, "M vs N"),
        row("Player Y", "1+ Fouls", "fouls", .5, 1.40, .76, "M vs N"),
        row("Player Z", "1+ SOT", "sot", .5, 1.50, .72, "M vs N"),
    ]
    picks = builder.build_builder_picks(alts, match_date="2026-09-25", max_builders=20)
    nate = [p for p in picks if p.style == "NATE ALT-LINE"]
    assert len(nate) >= 2
    for pick in nate:
        px = [x for x in pick.legs if x.player == "Player X"]
        assert len(px) == 1


def test_library_cross_match_uses_distinct_games():
    rows = [
        row("P1", "2+ Shots", "shots", 1.5, 1.65, .72, "Game A vs Game B"),
        row("P2", "1+ SOT", "sot", .5, 1.70, .70, "Game C vs Game D"),
        row("P3", "2+ Fouls Won", "fouls_won", 1.5, 1.80, .67, "Game E vs Game F"),
        row("P4", "To Get a Card", "yellow_cards", .5, 2.20, .55, "Game G vs Game H"),
        row("P5", "2+ Tackles", "tackles", 1.5, 1.75, .68, "Game I vs Game J"),
    ]
    picks = builder.build_builder_picks(rows, match_date="2026-09-25", max_builders=30)
    cross = [p for p in picks if p.style == "LIBRARY CROSS MATCH"]
    assert any(len(p.legs) == 2 for p in cross), cross
    assert any(len(p.legs) >= 3 for p in cross), cross
    for pick in cross:
        assert len({x.match for x in pick.legs}) == len(pick.legs), pick


def test_unmodelled_and_bad_correlation_rejected():
    unmodelled = [
        {"player": "A", "match": "A vs B", "league": "X", "market": "1+ Shots",
         "category": "shots", "line": .5, "odds": 1.40, "source": "kambi_ub"},
        {"player": "B", "match": "A vs B", "league": "X", "market": "1+ SOT",
         "category": "sot", "line": .5, "odds": 1.50, "source": "kambi_ub"},
        {"player": "C", "match": "A vs B", "league": "X", "market": "1+ Fouls",
         "category": "fouls", "line": .5, "odds": 1.50, "source": "kambi_ub"},
    ]
    assert builder.build_builder_picks(unmodelled, match_date="2026-09-25", max_builders=20) == []

    score = builder.normalize_prop(row("P", "To Score", "score", .5, 2.4, .50, "Q vs R"))
    assist = builder.normalize_prop(row("P", "To Give an Assist", "assist", .5, 3.0, .40, "Q vs R"))
    assert score and assist
    assert builder.valid_builder([score, assist]) is False


def main():
    test_tips_bible_and_nate()
    test_aystar_and_alt_lines()
    test_library_cross_match_uses_distinct_games()
    test_unmodelled_and_bad_correlation_rejected()
    print("OK: NETRATTLER screenshot builder styles regression passed")


if __name__ == "__main__":
    main()
