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
- Cross-match combos 3-11 use the best validated tips across all groups, including
  independently modelled player props, with a different market mix per leg count.
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


def _prob01(value: Any) -> float:
    p = _as_float(value, 0.0)
    if p > 1.0:
        p /= 100.0
    return min(0.999, max(0.0, p))


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

    probability_source = str(
        safe_row.get("probability_source")
        or safe_row.get("model_source")
        or safe_row.get("history_source")
        or ""
    ).strip().lower()
    has_independent = (
        _as_float(safe_row.get("model_prob")) > 0
        or any(token in probability_source for token in (
            "model", "history", "empirical", "fbref", "statsbomb", "fotmob", "supabase"
        ))
    )

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


def _combo_group(row: Dict[str, Any]) -> str:
    market = str(row.get("market") or "").lower()
    if market in {"btts", "over25", "combo", "btts_ht", "over15_ht", "1x2", "corners", "scorer"}:
        return market
    if market == "player_prop" or row.get("player"):
        return "player_prop"
    return market or "other"


def _combo_quality(row: Dict[str, Any], num_tips: int = 3) -> float:
    q = _as_float(row.get("odds") or row.get("oddsYes"), 0.0)
    p = _prob01(row.get("probability") or row.get("model_prob") or row.get("prob"))
    edge_pp = _as_float(row.get("edge_pct"), 0.0)
    if edge_pp == 0.0 and q > 1 and p > 0:
        edge_pp = (p - 1.0 / q) * 100.0
    confidence = _as_float(row.get("confidence"), 3.0)
    score = p * 100.0 + max(-10.0, min(30.0, edge_pp)) * 1.20 + confidence * 1.5
    # Longer accumulators should prefer stronger/lower-odds legs so 9-11 legs
    # can still fit inside the configured total-odds safety cap.
    if q > 1 and num_tips >= 7:
        score -= math.log(q) * (num_tips - 6) * 5.0
    return score


def _player_prop_combo_candidates(bot) -> List[Dict[str, Any]]:
    """Expose only independently modelled REAL-ODDS player props to cross-match combos."""
    out: List[Dict[str, Any]] = []
    min_prob = _as_float(os.getenv("NETRATTLER_PLAYER_PROP_MIN_PROB", "0.55"), 0.55)
    if min_prob > 1:
        min_prob /= 100.0
    min_edge = _as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_EDGE", "0.02"), 0.02)
    if min_edge > 1:
        min_edge /= 100.0

    for raw in list(getattr(bot, "_NTR_BUILDER_PROP_POOL", []) or []):
        if not isinstance(raw, dict):
            continue
        safe = _sanitize_row(raw)
        if safe is None:
            continue
        q = _as_float(safe.get("odds"), 0.0)
        if q <= 1 or safe.get("real_observed_line") is False:
            continue

        p_raw = safe.get("model_prob")
        if p_raw in (None, "", 0, 0.0):
            p_raw = safe.get("probability") or safe.get("prob") or safe.get("hit_rate")
        p = _prob01(p_raw)
        if p < min_prob:
            continue
        edge = p - (1.0 / q)
        if edge < min_edge:
            continue

        player = str(safe.get("player") or "").strip()
        market_label = str(safe.get("market") or safe.get("category") or "Player Prop").strip()
        if not player or _is_generic_player_label(player):
            continue
        category = str(safe.get("category") or "player_prop").lower()
        market = "scorer" if category in {"score", "first_scorer", "last_scorer"} else "player_prop"
        selection = f"{player} — {market_label}"
        out.append({
            "match": safe.get("match", ""),
            "league": safe.get("league", ""),
            "market": market,
            "tip": selection,
            "selection": selection,
            "player": player,
            "category": category,
            "line": safe.get("line"),
            "odds": q,
            "oddsYes": q,
            "probability": round(p * 100.0, 2),
            "confidence": 3,
            "edge": round(edge, 6),
            "edge_pct": round(edge * 100.0, 2),
            "_no_real_odds": False,
            "_source": safe.get("source") or "observed_player_prop",
        })
    return out


def _install_multi_combo_guard(bot) -> None:
    """Build 3-11 leg variants from the best validated tips across every group."""
    original_generate = bot.generate_multi_combo_bets

    profiles = [
        ["btts", "over25", "corners", "1x2", "player_prop", "btts_ht", "over15_ht", "combo", "scorer"],
        ["player_prop", "1x2", "btts_ht", "over25", "corners", "btts", "scorer", "combo", "over15_ht"],
        ["corners", "combo", "scorer", "btts", "over15_ht", "player_prop", "1x2", "over25", "btts_ht"],
        ["1x2", "btts", "player_prop", "over25", "btts_ht", "corners", "combo", "scorer", "over15_ht"],
    ]

    def generate_all_groups_combo(all_tips, num_tips=3):
        try:
            n = max(3, min(11, int(num_tips)))
        except Exception:
            n = 3

        pool: List[Dict[str, Any]] = [dict(x) for x in (all_tips or []) if isinstance(x, dict)]
        pool.extend(_player_prop_combo_candidates(bot))

        # Deduplicate exact selections while retaining the strongest version.
        best: Dict[tuple, Dict[str, Any]] = {}
        for row in pool:
            q = _as_float(row.get("odds") or row.get("oddsYes"), 0.0)
            p = _prob01(row.get("probability") or row.get("model_prob") or row.get("prob"))
            match = str(row.get("match") or "").strip()
            selection = str(row.get("selection") or row.get("tip") or "").strip()
            if not match or " vs " not in match or q <= 1 or p <= 0 or row.get("_no_real_odds") is True:
                continue
            key = (
                match.lower(), _combo_group(row), selection.lower(),
                str(row.get("player") or "").lower(), str(row.get("line") or ""),
            )
            prev = best.get(key)
            if prev is None or _combo_quality(row, n) > _combo_quality(prev, n):
                best[key] = row
        pool = list(best.values())
        if len(pool) < n:
            return original_generate(all_tips, num_tips=n)

        by_group: Dict[str, List[Dict[str, Any]]] = {}
        for row in pool:
            by_group.setdefault(_combo_group(row), []).append(row)
        for rows in by_group.values():
            rows.sort(key=lambda r: _combo_quality(r, n), reverse=True)

        profile = profiles[(n - 3) % len(profiles)]
        selected: List[Dict[str, Any]] = []
        used_matches = set()
        used_keys = set()

        def add_row(row: Dict[str, Any]) -> bool:
            match_key = str(row.get("match") or "").lower().strip()
            key = (
                match_key, _combo_group(row),
                str(row.get("selection") or row.get("tip") or "").lower(),
            )
            if not match_key or match_key in used_matches or key in used_keys:
                return False
            selected.append(row)
            used_matches.add(match_key)
            used_keys.add(key)
            return True

        # First pass deliberately rotates groups, preventing the old corner-only
        # nesting (3L subset of 4L subset of 5L) and producing distinct variants.
        for group in profile:
            if len(selected) >= n:
                break
            for row in by_group.get(group, []):
                if add_row(row):
                    break

        # Fill remaining slots with the strongest unused tips from every group.
        if len(selected) < n:
            remaining = sorted(pool, key=lambda r: _combo_quality(r, n), reverse=True)
            for row in remaining:
                if len(selected) >= n:
                    break
                add_row(row)

        if len(selected) < n:
            return None

        # Respect the existing combined-odds cap. If the diversified selection is
        # too expensive, rebuild with quality/odds efficiency for long combos.
        cap = _as_float(
            os.getenv("NETRATTLER_MULTI_COMBO_MAX_TOTAL_ODDS")
            or os.getenv("NETRATTLER_MULTI_COMBO_MAX_ODDS", "500"),
            500.0,
        )
        product = 1.0
        for row in selected:
            product *= _as_float(row.get("odds") or row.get("oddsYes"), 1.0)
        if cap > 0 and product > cap:
            selected = []
            used_matches.clear()
            efficiency = sorted(
                pool,
                key=lambda r: (
                    _combo_quality(r, n) / max(1.0, math.log(max(1.0001, _as_float(r.get("odds") or r.get("oddsYes"), 1.01))) + 1.0),
                    _combo_quality(r, n),
                ),
                reverse=True,
            )
            running = 1.0
            for row in efficiency:
                if len(selected) >= n:
                    break
                q = _as_float(row.get("odds") or row.get("oddsYes"), 0.0)
                match_key = str(row.get("match") or "").lower().strip()
                if q <= 1 or not match_key or match_key in used_matches:
                    continue
                # Keep room under the hard cap; for the final slot exact cap applies.
                if cap > 0 and running * q > cap:
                    continue
                selected.append(row)
                used_matches.add(match_key)
                running *= q
            if len(selected) < n:
                return None

        result = original_generate(selected, num_tips=n)
        if result:
            groups = []
            for row in result.get("tips", []) or []:
                g = _combo_group(row)
                if g not in groups:
                    groups.append(g)
            result["combo_variant"] = f"mix-{(n - 3) % len(profiles) + 1}"
            result["source_groups"] = groups
            result["desc"] = f"ALL-GROUPS MIX · {', '.join(groups)}"
            try:
                bot.log(f"🎰 Combo {n}: All-Groups Mix · {', '.join(groups)}")
            except Exception:
                pass
        return result

    bot.generate_multi_combo_bets = generate_all_groups_combo


def main() -> None:
    import btts_bot

    _install_pinnacle_guard(btts_bot)
    _install_multi_combo_guard(btts_bot)

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
