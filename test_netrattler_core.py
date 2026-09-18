#!/usr/bin/env python3
"""Deterministic offline regression tests for the V37 NETRATTLER core.

Targets the production invariants rather than legacy presentation code:
- real observed prices only;
- positive-edge legs;
- published builders are 3-9 legs;
- player, match and mixed builder families can coexist;
- statistical/model sources cannot smuggle a fabricated decimal quote;
- identity/source helpers remain stable.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ["NETRATTLER_BUILDER_MIN_ODDS"] = "2.5"
os.environ["NETRATTLER_BUILDER_MAX_ODDS"] = "150"
os.environ["NETRATTLER_BUILDER_MAX_LEGS"] = "9"
os.environ["NETRATTLER_BUILDER_MIN_LEG_EDGE"] = "2.0"
os.environ["NETRATTLER_PROP_BUILDER_MIN_EDGE"] = "0.02"

from netrattler_builder_engine import build_builder_picks, deduplicate_props


def row(
    player: str,
    match: str,
    market: str,
    category: str,
    line: float,
    odds: float,
    prob: float = 65,
    source: str = "pinnacle",
    team: str = "",
    *,
    observed: bool = True,
    estimated: bool = False,
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
        "real_observed_line": observed,
        "estimated": estimated,
        "games": 20,
        "hit_rate": prob,
    }


eng_arg = "England vs Argentina"

# Match markets with exact bookmaker lines/quotes must be usable by MATCH/MIXED builders.
team_rows = [
    row("BTTS Yes", eng_arg, "Both Teams To Score - Yes", "btts", 0.5, 1.95, 64),
    row("Over 2.5", eng_arg, "Over 2.5 Goals", "over_goals", 2.5, 2.05, 62),
    row("Over 8.5 Corners", eng_arg, "Over 8.5 Corners", "match_corners", 8.5, 1.90, 66),
]
normalized_team = deduplicate_props(team_rows)
assert len(normalized_team) == 3, "Observed match markets were not normalized"
assert all(leg.match == eng_arg and leg.odds > 1 and not leg.estimated for leg in normalized_team)

team_picks = build_builder_picks(team_rows, match_date="2026-07-15", max_builders=50)
assert team_picks, "Observed match markets produced no builder"
assert any(p.family == "match" for p in team_picks), "No MATCH builder family was generated"
assert all(3 <= len(p.legs) <= 9 for p in team_picks)

# Real player-prop sample with verified bookmaker lines and prices.
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

player_categories = {
    "shots", "sot", "fouls", "fouls_won", "tackles", "tackles_committed",
    "tackles_received", "yellow_cards", "score", "score_assist", "assist",
    "goalkeeper_saves", "offsides",
}
player_picks = build_builder_picks(player_rows, match_date="2026-07-15", max_builders=50)
assert player_picks, "Verified player props produced no builder"
valid_player_picks = [p for p in player_picks if p.family == "player"]
assert valid_player_picks, "No player-only builder was generated"
for pick in valid_player_picks:
    assert pick.total_odds >= 2.5
    assert 3 <= len(pick.legs) <= 9
    assert len({leg.key() for leg in pick.legs}) == len(pick.legs)
    assert all(leg.match == eng_arg for leg in pick.legs)
    assert all(leg.odds > 1 and leg.line > 0 and not leg.estimated for leg in pick.legs)
    assert all(leg.category in player_categories for leg in pick.legs)
    assert all(leg.probability > (1.0 / leg.odds) for leg in pick.legs)

# Mixed pool must preserve valid player builders and unlock explicit MIXED builders.
mixed_picks = build_builder_picks(team_rows + player_rows, match_date="2026-07-15", max_builders=80)
assert mixed_picks, "Mixed pool produced no builders"
assert any(p.family == "player" for p in mixed_picks), "Mixed pool lost player builders"
assert any(p.family == "match" for p in mixed_picks), "Mixed pool lost match builders"
assert any(p.family == "mixed" for p in mixed_picks), "No mixed same-game builder was generated"
assert all(3 <= len(p.legs) <= 9 for p in mixed_picks)

# Negative edge: no leg may enter a published builder.
negative_edge_rows = [
    row("Player A", eng_arg, "2+ Shots", "shots", 2, 1.50, 50, team="England"),
    row("Player B", eng_arg, "2+ SOT", "sot", 2, 1.55, 50, team="Argentina"),
    row("Player C", eng_arg, "2+ Fouls", "fouls", 2, 1.60, 50, team="England"),
]
assert build_builder_picks(negative_edge_rows, match_date="2026-07-15", max_builders=50) == [], \
    "Negative-edge builder was generated"

# Two real legs are still not a publishable builder: production floor is 3.
two_leg_rows = [
    row("Player D", eng_arg, "1+ Shot", "shots", 1, 1.60, 75, team="England"),
    row("Player E", eng_arg, "1+ SOT", "sot", 1, 1.65, 72, team="Argentina"),
]
assert build_builder_picks(two_leg_rows, match_date="2026-07-15", max_builders=50) == [], \
    "Two-leg builder escaped the 3-leg production floor"

# Stat/model sources with a decimal number must not masquerade as a bookmaker quote.
stat_only_rows = [
    row("Player F", eng_arg, "2+ Shots", "shots", 2, 2.50, 60, source="fotmob", team="England", observed=False),
    row("Player G", eng_arg, "2+ SOT", "sot", 2, 2.50, 60, source="statsbomb", team="Argentina", observed=False),
    row("Player H", eng_arg, "2+ Fouls", "fouls", 2, 2.50, 60, source="fbref", team="England", observed=False),
]
assert deduplicate_props(stat_only_rows) == [], "Stat-only sources smuggled fabricated odds into builder"

estimated_rows = [
    row("Player I", eng_arg, "2+ Shots", "shots", 2, 2.50, 60, source="pinnacle", estimated=True),
    row("Player J", eng_arg, "2+ SOT", "sot", 2, 2.50, 60, source="bet365", estimated=True),
    row("Player K", eng_arg, "2+ Fouls", "fouls", 2, 2.50, 60, source="odds_api", estimated=True),
]
assert deduplicate_props(estimated_rows) == [], "Estimated odds were accepted"

# Source/identity regression tests.
from netrattler_identity_hub import teams_match, normalize_team_name, explain_match
from netrattler_source_hub import parse_openfootball_json, source_health_snapshot, FEATURE_RECIPES
from netrattler_feature_hub import feature_plan_for_market, source_priority_for_market
from netrattler_model_registry_v37 import feature_hash, training_fingerprint

assert normalize_team_name("England National Team") == "england"
assert teams_match("England", "England National Team") is True
assert teams_match("England", "New England Revolution II") is False, explain_match("England", "New England Revolution II")
assert teams_match("Argentina", "Argentina Men") is True
assert teams_match("LDU de Quito", "LDU Quito") is True

_payload = {
    "name": "World Cup",
    "matches": [{"date": "2026-07-15", "team1": "England", "team2": "Argentina", "score": {"ft": [2, 1], "ht": [1, 0]}}],
}
_rows = parse_openfootball_json(_payload, "2026-07-15", source="unit_openfootball", league="FIFA World Cup")
assert len(_rows) == 1
assert _rows[0]["home_team"] == "England"
assert _rows[0]["away_score"] == 1
assert any(item["source"] == "soccerdata" for item in source_health_snapshot())
assert "xthreat" in FEATURE_RECIPES
assert "xg" in feature_plan_for_market("shots")
assert source_priority_for_market("tackles_received")[0] == "pinnacle"

# Registry fingerprints/signatures are stable and order-sensitive where appropriate.
assert feature_hash(["a", "b"]) == feature_hash(["a", "b"])
assert feature_hash(["a", "b"]) != feature_hash(["b", "a"])
assert training_fingerprint(rows=100, columns=["b", "a"], max_date="2026-09-01") == \
       training_fingerprint(rows=100, columns=["a", "b"], max_date="2026-09-01")

assert Path("btts_bot.py").is_file()
print(f"OK match builders: {sum(p.family == 'match' for p in team_picks)}")
print(f"OK player builders: {len(valid_player_picks)}")
print(f"OK mixed builders: {sum(p.family == 'mixed' for p in mixed_picks)}")
print("NETRATTLER V37 core regression: OK")
