#!/usr/bin/env python3
"""NETRATTLER runtime safety guard for player-prop builders and quote sanity.

Production rules enforced here:
- REAL_ODDS_ONLY remains mandatory.
- Pinnacle Arcadia prices are converted from American to decimal before use.
- Multi-player / specialty markets are not fed into single-player ML models.
- First-half player props are excluded until dedicated HT player models exist.
- Binary player markets use line=0.5, never bogus ``Over 1`` labels.
- Generic outcome labels such as ``Over 0.5`` are never accepted as player names.
- Trained player models are used only on exact supported lines.
- Modelled builder edge is model probability minus bookmaker implied probability.
- Implausibly large player-model gaps are rejected as parser/model mismatch.
- The old LLM Advanced-Props builder with estimated combo prices is disabled.
"""
from __future__ import annotations

import math
import os
import re
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
_GENERIC_PLAYER_RE = re.compile(
    r"^(?:over|under)?\s*[+-]?\d+(?:[\.,]\d+)?(?:\s*(?:goals?|shots?|cards?|tackles?|fouls?))?$",
    re.I,
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _pinnacle_decimal(value: Any) -> float:
    """Convert Pinnacle Arcadia American prices to decimal; keep decimal input."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v <= -100.0:
        return round(1.0 + 100.0 / abs(v), 4)
    if v >= 100.0:
        return round(1.0 + v / 100.0, 4)
    if 1.001 <= v <= 100.0:
        return round(v, 4)
    return 0.0


def _edge_pp_limit() -> float:
    raw = _as_float(os.getenv("NETRATTLER_PROP_BUILDER_MAX_ABS_EDGE", "0.30"), 0.30)
    if raw <= 0:
        return 0.0
    return raw * 100.0 if raw <= 1.0 else raw


def _model_market_ratio_limit() -> float:
    return max(0.0, _as_float(os.getenv("NETRATTLER_PROP_BUILDER_MAX_MODEL_MARKET_RATIO", "4.0"), 4.0))


def _is_multi_player(player: str, market: str) -> bool:
    text = f" {player} {market} ".lower()
    return any(term in text for term in _MULTI_PLAYER_TERMS)


def _is_generic_player_label(player: str) -> bool:
    text = str(player or "").strip()
    low = text.lower()
    if not text or low in {"over", "under", "yes", "no", "home", "away", "draw", "player", "total"}:
        return True
    if _GENERIC_PLAYER_RE.match(text):
        return True
    if low.startswith("over ") or low.startswith("under "):
        return True
    return False


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
    if _is_generic_player_label(player):
        return None
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
        if implied <= 0:
            return None
        edge_pp = (leg.probability - implied) * 100.0

        min_edge_raw = _as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_EDGE", "0.02"), 0.02)
        min_edge_pp = min_edge_raw * 100.0 if 0 < min_edge_raw <= 1 else min_edge_raw
        if edge_pp < min_edge_pp:
            return None

        max_edge_pp = _edge_pp_limit()
        if max_edge_pp > 0 and abs(edge_pp) > max_edge_pp:
            return None

        ratio_limit = _model_market_ratio_limit()
        model_market_ratio = leg.probability / implied
        if ratio_limit > 0 and model_market_ratio > ratio_limit:
            return None

        fair = 1.0 / leg.probability if leg.probability > 0 else 0.0
        leg = replace(leg, edge=round(edge_pp, 2), fair_odds=round(fair, 2))
    else:
        leg = replace(leg, edge=0.0)

    return leg


builder.normalize_prop = normalize_prop_safe


def _install_pinnacle_guard(bot) -> None:
    """Replace the buggy direct Pinnacle reader that treated American odds as decimal."""
    def fetch_pinnacle_match_odds_safe(match_id: int):
        cache_key = f"odds_{match_id}"
        cached = bot._cache_get(bot._PIN_ODDS_CACHE, cache_key)
        if cached is not None:
            return cached
        try:
            r = bot.requests.get(
                f"{bot.PINNACLE_BASE}/matchups/{match_id}/markets/related/straight",
                headers=bot.PINNACLE_HEADERS,
                timeout=10,
            )
            if not r.ok:
                bot._cache_set(bot._PIN_ODDS_CACHE, cache_key, None)
                return None

            result = {"match_id": match_id}
            for market in r.json() or []:
                mtype = str(market.get("type") or "").lower()
                period = int(market.get("period") or 0)
                for price in market.get("prices") or []:
                    pv = _pinnacle_decimal(price.get("price"))
                    des = str(price.get("designation") or "").lower()
                    pts = price.get("points")
                    if pv <= 1:
                        continue
                    if mtype == "moneyline" and period == 0:
                        if des == "home":
                            result["home_win"] = pv
                        elif des == "draw":
                            result["draw"] = pv
                        elif des == "away":
                            result["away_win"] = pv
                    elif mtype == "total" and period == 0 and pts == 2.5:
                        if des == "over":
                            result["over_25"] = pv
                        elif des == "under":
                            result["under_25"] = pv
                    elif mtype == "total" and period == 1:
                        if pts == 1.5 and des == "over":
                            result["over_15_ht"] = pv
                        elif pts == 0.5 and des == "over":
                            result["over_05_ht"] = pv

            try:
                r2 = bot.requests.get(
                    f"{bot.PINNACLE_BASE}/matchups/{match_id}/related",
                    headers=bot.PINNACLE_HEADERS,
                    timeout=8,
                )
                if r2.ok:
                    for sub in r2.json() or []:
                        desc = str((sub.get("special") or {}).get("description") or sub.get("description") or "").lower()
                        is_btts = "both teams to score" in desc or "btts" in desc
                        is_combo = is_btts and ("over 2.5" in desc or "over 2,5" in desc or "2.5 goals" in desc)
                        if not is_btts:
                            continue
                        sub_id = sub.get("id")
                        if not sub_id:
                            continue
                        rs = bot.requests.get(
                            f"{bot.PINNACLE_BASE}/matchups/{sub_id}/markets/straight",
                            headers=bot.PINNACLE_HEADERS,
                            timeout=8,
                        )
                        if not rs.ok:
                            continue
                        for m in rs.json() or []:
                            pp = int(m.get("period") or 0)
                            for p in m.get("prices") or []:
                                designation = str(p.get("designation") or "").lower()
                                if designation not in {"yes", "over", "home"} and "yes" not in designation:
                                    continue
                                observed = _pinnacle_decimal(p.get("price"))
                                if observed <= 1:
                                    continue
                                if is_combo and pp == 0:
                                    result["btts_over25_yes"] = observed
                                elif pp == 0:
                                    result["btts_yes"] = observed
                                elif pp == 1:
                                    result["btts_yes_ht"] = observed
            except Exception:
                pass

            bot._cache_set(bot._PIN_ODDS_CACHE, cache_key, result)
            return result
        except Exception:
            bot._cache_set(bot._PIN_ODDS_CACHE, cache_key, None)
            return None

    bot.fetch_pinnacle_match_odds = fetch_pinnacle_match_odds_safe

    # Respect the configured cap for normal match singles after quote conversion.
    original_filter = bot.filter_tips_legacy_safe

    def filter_tips_legacy_safe_guarded(tips, market="btts", odds_data=None):
        rows = original_filter(tips, market=market, odds_data=odds_data)
        market_key = str(market or "").lower()
        if market_key not in {"1x2", "btts", "over25"}:
            return rows
        max_single = _as_float(os.getenv("NETRATTLER_MAX_SINGLE_ODDS", "0"), 0.0)
        if max_single <= 0:
            return rows
        clean = []
        for row in rows:
            q = _as_float(row.get("odds") or row.get("oddsYes"), 0.0)
            if 1.0 < q <= max_single:
                clean.append(row)
        return clean

    bot.filter_tips_legacy_safe = filter_tips_legacy_safe_guarded


def main() -> None:
    import btts_bot

    _install_pinnacle_guard(btts_bot)

    def _legacy_estimated_builder_disabled(*_args, **_kwargs):
        try:
            btts_bot.log("🔑 Legacy Advanced-Props LLM Builder übersprungen — REAL_ODDS_ONLY")
        except Exception:
            pass
        return None

    btts_bot.run_advanced_props_bot = _legacy_estimated_builder_disabled
    btts_bot.main()


if __name__ == "__main__":
    main()
