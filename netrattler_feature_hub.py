#!/usr/bin/env python3
"""NETRATTLER Feature Hub V30 — feature recipes inspired by football_analytics."""
from __future__ import annotations
from typing import Any, Dict, List

FEATURE_GROUPS: Dict[str, Dict[str, Any]] = {
    "finishing": {"features": ["xg", "non_pen_xg", "shots", "sot", "box_touches"], "markets": ["score", "shots", "sot"]},
    "creation": {"features": ["xa", "key_passes", "passes_into_box", "progressive_passes", "xthreat"], "markets": ["assist", "passes"]},
    "ball_progression": {"features": ["progressive_carries", "carries_into_box", "deep_completions", "touches_final_third"], "markets": ["shots", "assist"]},
    "defensive_activity": {"features": ["tackles", "interceptions", "pressures", "recoveries", "clearances"], "markets": ["tackles_committed", "interceptions", "clearances"]},
    "contact_profile": {"features": ["fouls_committed", "fouls_won", "tackles_received", "duels", "aerial_duels"], "markets": ["fouls", "fouls_won", "tackles_received", "yellow_cards"]},
    "keeper": {"features": ["saves", "post_shot_xg", "crosses_stopped"], "markets": ["saves"]},
    "team_context": {"features": ["elo", "form5", "xg_for", "xg_against", "pace", "pressing", "ref_cards"], "markets": ["btts", "over_goals", "team_cards", "team_corners"]},
}


def feature_plan_for_market(market: str) -> List[str]:
    market = str(market or "").lower()
    out: List[str] = []
    for group in FEATURE_GROUPS.values():
        if market in group.get("markets", []):
            out.extend(group.get("features", []))
    return list(dict.fromkeys(out))


def source_priority_for_market(market: str) -> List[str]:
    market = str(market or "").lower()
    if market in {"shots", "sot", "score", "assist"}:
        return ["pinnacle", "fotmob", "sofascore", "bigballs", "fbref", "understat", "statsbomb"]
    if market in {"fouls", "fouls_won", "tackles_committed", "tackles_received", "yellow_cards"}:
        return ["pinnacle", "fotmob", "sofascore", "bigballs", "statsbomb", "fbref"]
    if market in {"btts", "over_goals", "team_corners", "team_cards"}:
        return ["pinnacle", "bigballs", "football-data.co.uk", "clubelo", "openfootball", "espn"]
    return ["pinnacle", "supabase", "soccerdata", "openfootball"]
