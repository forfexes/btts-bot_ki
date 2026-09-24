#!/usr/bin/env python3
"""NETRATTLER runtime safety guard for player-prop builders.

This wrapper leaves the stable production pipeline untouched and only hardens
player-prop normalization before ``btts_bot.main()`` runs.

Rules:
- REAL_ODDS_ONLY remains untouched.
- Multi-player / specialty markets are not fed into single-player ML models.
- First-half player props are excluded until dedicated HT player models exist.
- Binary player markets use line=0.5, never bogus ``Over 1`` labels.
- Trained player models are used only on exact supported lines.
- Builder edge is displayed as probability-point edge (model p - implied p),
  consistent with the main bot, not EV ROI percentage.
- Modelled legs below the configured minimum edge are rejected; bookmaker-only
  legs without an independent probability remain eligible for compatibility.
"""
from __future__ import annotations

import math
import os
from dataclasses import replace
from typing import Any, Dict, List

import netrattler_builder_engine as builder
import netrattler_ml_player as player_ml
import netrattler_prop_sources as prop_sources


_BINARY_CATEGORIES = {"score", "assist", "yellow_cards", "first_scorer", "last_scorer", "score_assist"}
_SPECIALTY_SCORER_TERMS = (
    "header", "headed", "outside the box", "outside box", "from outside",
    "penalty", "free kick", "first goal", "last goal", "next goal",
    "either player", "any of", "both players",
)
_HALF_TERMS = ("1st half", "first half", "1st-half", "first-half", "1h")
_MULTI_PLAYER_TERMS = ("||", " either player", "both players", "any of ")
_CLEAN_BINARY_MARKET = {
    "score": "To Score",
    "assist": "To Give an Assist",
    "yellow_cards": "To Get a Card",
    "first_scorer": "First Goalscorer",
    "last_scorer": "Last Goalscorer",
    "score_assist": "To Score or Assist",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _is_multi_player(player: str, market: str) -> bool:
    text = f" {player} {market} ".lower()
    return any(term in text for term in _MULTI_PLAYER_TERMS)


def _is_unsupported_specialty(category: str, market: str) -> bool:
    low = str(market or "").lower()
    if category in {"score", "first_scorer", "last_scorer", "score_assist"}:
        if any(term in low for term in _SPECIALTY_SCORER_TERMS):
            return True
    if category in builder.PLAYER_CATEGORIES and any(term in low for term in _HALF_TERMS):
        return True
    return False


def _sanitize_row(row: Dict[str, Any]) -> Dict[str, Any] | None:
    out = dict(row or {})
    category = str(out.get("category") or "").strip().lower()
    category = {
        "booked": "yellow_cards",
        "cards": "yellow_cards",
        "fouls_committed": "fouls",
        "fouls_drawn": "fouls_won",
        "tackles_made": "tackles_committed",
        "tackles_won": "tackles_committed",
        "tackled": "tackles_received",
        "saves": "goalkeeper_saves",
    }.get(category, category)
    out["category"] = category
    player = str(out.get("player") or out.get("selection") or "").strip()
    market = str(out.get("market") or out.get("type") or "").strip()

    if not player or not market:
        return out
    if _is_multi_player(player, market):
        return None
    if _is_unsupported_specialty(category, market):
        return None

    if category in _BINARY_CATEGORIES:
        out["line"] = 0.5
        out["market"] = _CLEAN_BINARY_MARKET.get(category, market)

    return out


_orig_fetch_kambi_player_props = prop_sources.fetch_kambi_player_props


def fetch_kambi_player_props_safe(home: str, away: str, brand: str = "ub") -> List[Dict[str, Any]]:
    rows = _orig_fetch_kambi_player_props(home, away, brand=brand) or []
    clean: List[Dict[str, Any]] = []
    for row in rows:
        safe = _sanitize_row(row)
        if safe is not None:
            clean.append(safe)
    return clean


prop_sources.fetch_kambi_player_props = fetch_kambi_player_props_safe


def model_for_exact(category: str, line: float):
    table = player_ml._LINE_MODELS.get(category)
    if not table:
        return None
    if category in {"first_scorer", "last_scorer", "sot_outside_box", "tackles_received"}:
        return None
    try:
        target = float(line if line is not None else 0.5)
    except (TypeError, ValueError):
        return None
    for supported_line, name in table.items():
        if math.isclose(float(supported_line), target, rel_tol=0.0, abs_tol=1e-6):
            return name
    return None


player_ml.model_for = model_for_exact


_orig_normalize_prop = builder.normalize_prop


def normalize_prop_safe(row: Dict[str, Any]):
    safe_row = _sanitize_row(row)
    if safe_row is None:
        return None

    leg = _orig_normalize_prop(safe_row)
    if leg is None:
        return None

    independent_values = [
        _as_float(safe_row.get("model_prob")),
        _as_float(safe_row.get("probability")),
        _as_float(safe_row.get("prob")),
        _as_float(safe_row.get("hit_rate")),
    ]
    has_independent = any(v > 0 for v in independent_values)

    if has_independent and leg.odds > 1:
        implied = 1.0 / leg.odds
        edge_pp = (leg.probability - implied) * 100.0
        min_edge_raw = _as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_EDGE", "0.02"), 0.02)
        min_edge_pp = min_edge_raw * 100.0 if 0 < min_edge_raw <= 1 else min_edge_raw
        if edge_pp < min_edge_pp:
            return None
        fair = 1.0 / leg.probability if leg.probability > 0 else 0.0
        leg = replace(leg, edge=round(edge_pp, 2), fair_odds=round(fair, 2))
    else:
        leg = replace(leg, edge=0.0)

    return leg


builder.normalize_prop = normalize_prop_safe


def main() -> None:
    import btts_bot
    btts_bot.main()


if __name__ == "__main__":
    main()
