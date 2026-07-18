#!/usr/bin/env python3
"""Deterministic offline regression tests for NETRATTLER core modules.

The test deliberately does not require a team-only England–Argentina builder.
Production may reject such a builder when verified combined odds stay below
NETRATTLER_BUILDER_MIN_ODDS or when Prop Builder is configured player-only.
"""
from __future__ import annotations

import os
from pathlib import Path

# Deterministic and aligned with the current production floor.
os.environ["NETRATTLER_BUILDER_MIN_ODDS"] = "5.0"
os.environ["NETRATTLER_BUILDER_MAX_ODDS"] = "150"

from netrattler_builder_engine import build_builder_picks, deduplicate_props


def row(
    player: str,
    match: str,
    market: str,
    category: str,
    line: float,
    odds: float,
    prob: float = 62,
    source: str = "pinnacle",
    team: str = "",
) -> dict:
    return {
        "player": player,
        "team": team,
        "match": match,
        "league": "FIFA - World Cup",
        "market": market,
        "category": category,
        "line": line,
        "odds": odds,
        "probability": prob,
        "source": source,
        "games": 10,
        "hit_rate": prob,
    }


eng_arg = "England vs Argentina"

# Team markets remain a parser regression only. They are not required to create
# a Prop Builder because current production may be player-only and min odds 5.0.
team_rows = [
    row("England To Score", eng_arg, "England To Score?", "match_goals", 1, 1.42, 70),
    row("Argentina To Score", eng_arg, "Argentina To Score?", "match_goals", 1, 1.48, 68),
    row(
        "Either Team To Score 1st Half",
        eng_arg,
        "Either Team To Score? 1st Half",
        "btts_ht",
        1,
        1.72,
        61,
    ),
]
normalized_team = deduplicate_props(team_rows)
assert len(normalized_team) == 3, "England-Argentina team markets were not normalized"
assert all(leg.match == eng_arg and leg.odds > 1 for leg in normalized_team)

# A team-only builder may legitimately be empty. If one is returned, validate it.
team_picks = build_builder_picks(team_rows, match_date="2026-07-15", max_builders=50)
for pick in team_picks:
    assert len(pick.legs) >= 2
    assert all(leg.match == eng_arg and leg.odds > 1 for leg in pick.legs)

# Real player-prop sample with verified bookmaker lines and odds.
player_rows = [
    row("Jude Bellingham", eng_arg, "2+ Shots on Target", "sot", 2, 2.40, 58, team="England"),
    row("Bukayo Saka", eng_arg, "3+ Shots", "shots", 3, 2.30, 61, team="England"),
    row("Declan Rice", eng_arg, "3+ Tackles Committed", "tackles_committed", 3, 2.35, 59, team="England"),
    row("Alexis Mac Allister", eng_arg, "3+ Tackles Committed", "tackles_committed", 3, 2.30, 57, team="Argentina"),
    row("Enzo Fernandez", eng_arg, "2+ Fouls Committed", "fouls", 2, 2.25, 58, team="Argentina"),
    row("Rodrigo De Paul", eng_arg, "3+ Tackles Received", "tackles_received", 3, 2.30, 56, team="Argentina"),
    row("Harry Kane", eng_arg, "2+ Shots on Target", "sot", 2, 2.35, 60, team="England"),
    row("Julian Alvarez", eng_arg, "3+ Shots", "shots", 3, 2.25, 59, team="Argentina"),
    row("Lisandro Martinez", eng_arg, "2+ Fouls Committed", "fouls", 2, 2.20, 60, team="Argentina"),
]

player_picks = build_builder_picks(
    player_rows,
    match_date="2026-07-15",
    max_builders=50,
)
assert player_picks, "Verified England-Argentina player props produced no builder"

player_categories = {
    "shots",
    "sot",
    "fouls",
    "fouls_won",
    "tackles",
    "tackles_committed",
    "tackles_received",
    "yellow_cards",
    "score",
    "score_assist",
    "assist",
    "saves",
}

valid_player_picks = []
for pick in player_picks:
    assert pick.total_odds >= 5.0, f"Builder below minimum odds: {pick.total_odds}"
    assert 2 <= len(pick.legs) <= 6
    assert len({leg.key() for leg in pick.legs}) == len(pick.legs)
    assert all(leg.match == eng_arg for leg in pick.legs)
    assert all(leg.odds > 1 and leg.line > 0 for leg in pick.legs)
    if all(leg.category in player_categories for leg in pick.legs):
        valid_player_picks.append(pick)

assert valid_player_picks, "No player-only builder was generated"
assert any(
    all(not leg.estimated for leg in pick.legs)
    for pick in valid_player_picks
), "No builder used only observed bookmaker lines and odds"

# Source/identity regression tests.
from netrattler_identity_hub import teams_match, normalize_team_name, explain_match
from netrattler_source_hub import (
    parse_openfootball_json,
    source_health_snapshot,
    FEATURE_RECIPES,
)
from netrattler_feature_hub import feature_plan_for_market, source_priority_for_market

assert normalize_team_name("England National Team") == "england"
assert teams_match("England", "England National Team") is True
assert teams_match("England", "New England Revolution II") is False, explain_match(
    "England",
    "New England Revolution II",
)
assert teams_match("Argentina", "Argentina Men") is True
assert teams_match("LDU de Quito", "LDU Quito") is True

_payload = {
    "name": "World Cup",
    "matches": [
        {
            "date": "2026-07-15",
            "team1": "England",
            "team2": "Argentina",
            "score": {"ft": [2, 1], "ht": [1, 0]},
        }
    ],
}
_rows = parse_openfootball_json(
    _payload,
    "2026-07-15",
    source="unit_openfootball",
    league="FIFA World Cup",
)
assert len(_rows) == 1
assert _rows[0]["home_team"] == "England"
assert _rows[0]["away_score"] == 1
assert any(item["source"] == "soccerdata" for item in source_health_snapshot())
assert "xthreat" in FEATURE_RECIPES
assert "xg" in feature_plan_for_market("shots")
assert source_priority_for_market("tackles_received")[0] == "pinnacle"

assert Path("btts_bot.py").is_file()

print(f"OK team-market normalization: {len(normalized_team)}")
print(f"OK player-only builders: {len(valid_player_picks)}")
print("NETRATTLER core regression: OK")
