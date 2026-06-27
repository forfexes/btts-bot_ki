#!/usr/bin/env python3
"""
NETRATTLER V15 — Data Fusion Layer

Uses Supabase feature tables in the main bot scoring step:
- football_team_history_features
- league_goal_features
- league_cards_features
- league_corners_features
- team_elo_history
- injury_reports
- weather_match_context (lightweight)
- odds_history (lightweight)

Safe design:
- silent fallback if tables are missing
- fast REST queries with limit
- no hard dependency outside requests
"""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests


_CACHE: Dict[str, Any] = {"loaded_at": 0}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _now_ts() -> float:
    return time.time()


def _norm(s: Any) -> str:
    s = str(s or "").lower()
    s = s.replace("&", "and")
    s = re.sub(r"\b(fc|cf|afc|sc|ac|fk|sk|if|bk|u19|u20|u21|women|wfc)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v or 0))
    except Exception:
        return default


def _clip(v: int, lo: int = 1, hi: int = 95) -> int:
    return max(lo, min(hi, int(v)))


def _split_match(match: str) -> Tuple[str, str]:
    if not match:
        return "", ""
    for sep in [" vs ", " v ", " - ", " — ", " – "]:
        if sep in match:
            a, b = match.split(sep, 1)
            return a.strip(), b.strip()
    return match.strip(), ""


def _rest_get(supabase_url: str, supabase_key: str, table: str, params: Dict[str, str], timeout: int = 8) -> List[Dict[str, Any]]:
    try:
        r = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/{table}",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            params=params,
            timeout=timeout,
        )
        if not r.ok:
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_cache(supabase_url: str, supabase_key: str, log: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    ttl = int(_env("DATA_FUSION_V15_CACHE_SECONDS", "900"))
    if _CACHE.get("loaded_at") and _now_ts() - float(_CACHE.get("loaded_at", 0)) < ttl:
        return _CACHE

    limit = int(_env("DATA_FUSION_V15_MAX_ROWS", "20000"))
    cache: Dict[str, Any] = {"loaded_at": _now_ts()}

    team_rows = _rest_get(
        supabase_url, supabase_key, "football_team_history_features",
        {"select": "team_name,division,source,matches,last_match_date,goals_for_pg,goals_against_pg,shots_for_pg,shots_against_pg,sot_for_pg,sot_against_pg,fouls_for_pg,fouls_against_pg,corners_for_pg,corners_against_pg,total_cards_pg,btts_rate,over25_rate,avg_elo,avg_form3,avg_form5", "limit": str(limit)},
    )
    cache["team_features"] = team_rows
    cache["team_by_norm"] = {}
    for r in team_rows:
        n = _norm(r.get("team_name"))
        if n and n not in cache["team_by_norm"]:
            cache["team_by_norm"][n] = r

    lg = _rest_get(
        supabase_url, supabase_key, "league_goal_features",
        {"select": "league,season,matches,goals_pg,home_goals_pg,away_goals_pg,btts_rate,over25_rate,home_win_rate,draw_rate,away_win_rate", "order": "season.desc", "limit": "5000"},
    )
    cache["league_goal"] = {}
    for r in lg:
        n = _norm(r.get("league"))
        if n and n not in cache["league_goal"]:
            cache["league_goal"][n] = r

    lc = _rest_get(
        supabase_url, supabase_key, "league_cards_features",
        {"select": "league,season,matches,yellow_cards_pg,red_cards_pg,total_cards_pg,home_yellow_pg,away_yellow_pg", "order": "season.desc", "limit": "5000"},
    )
    cache["league_cards"] = {}
    for r in lc:
        n = _norm(r.get("league"))
        if n and n not in cache["league_cards"]:
            cache["league_cards"][n] = r

    lcorn = _rest_get(
        supabase_url, supabase_key, "league_corners_features",
        {"select": "league,season,matches,corners_pg,home_corners_pg,away_corners_pg", "order": "season.desc", "limit": "5000"},
    )
    cache["league_corners"] = {}
    for r in lcorn:
        n = _norm(r.get("league"))
        if n and n not in cache["league_corners"]:
            cache["league_corners"][n] = r

    elo = _rest_get(
        supabase_url, supabase_key, "team_elo_history",
        {"select": "team_name,rating_date,elo,rank,country", "order": "rating_date.desc", "limit": "8000"},
    )
    cache["elo"] = {}
    for r in elo:
        n = _norm(r.get("team_name"))
        if n and n not in cache["elo"]:
            cache["elo"][n] = r

    injuries = _rest_get(
        supabase_url, supabase_key, "injury_reports",
        {"select": "player_name,team_name,report_date,injury,status,expected_return", "order": "report_date.desc", "limit": "1500"},
    )
    inj_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for r in injuries:
        tn = _norm(r.get("team_name"))
        if tn:
            inj_by_team.setdefault(tn, []).append(r)
    cache["injuries_by_team"] = inj_by_team

    _CACHE.clear()
    _CACHE.update(cache)
    if log:
        try:
            log(f"🧠 V15 Data Fusion geladen: teams={len(team_rows)}, leagues={len(lg)}, cards={len(lc)}, corners={len(lcorn)}, elo={len(elo)}, injuries={len(injuries)}")
        except Exception:
            pass
    return _CACHE


def _find_team(cache: Dict[str, Any], team: str) -> Optional[Dict[str, Any]]:
    n = _norm(team)
    if not n:
        return None
    direct = cache.get("team_by_norm", {}).get(n)
    if direct:
        return direct
    # light fuzzy: containment, but avoid too-short names
    if len(n) < 4:
        return None
    for k, v in cache.get("team_by_norm", {}).items():
        if n in k or k in n:
            return v
    return None


def _find_map(cache: Dict[str, Any], key: str, map_name: str) -> Optional[Dict[str, Any]]:
    n = _norm(key)
    if not n:
        return None
    mp = cache.get(map_name, {})
    if n in mp:
        return mp[n]
    if len(n) >= 4:
        for k, v in mp.items():
            if n in k or k in n:
                return v
    return None


def _injury_count(cache: Dict[str, Any], team: str) -> int:
    n = _norm(team)
    if not n:
        return 0
    rows = cache.get("injuries_by_team", {}).get(n, [])
    bad = 0
    for r in rows[:10]:
        st = str(r.get("status") or "").lower()
        if not any(x in st for x in ["fit", "available", "returned", "back"]):
            bad += 1
    return bad


def _market_kind(market: str, tip: Dict[str, Any]) -> str:
    raw = (market or tip.get("market") or tip.get("market_name") or tip.get("tip") or "").lower()
    if "corner" in raw or "ecken" in raw:
        return "corners"
    if "card" in raw or "yellow" in raw or "book" in raw or "karte" in raw:
        return "cards"
    if "over" in raw or "2.5" in raw or "1.5" in raw:
        return "over"
    if "btts" in raw or "both" in raw:
        return "btts"
    if "combo" in raw:
        return "combo"
    return raw or "generic"


def _rate_boost(rate: Optional[float], high: float, very_high: float, low: float) -> int:
    if rate is None:
        return 0
    if rate > 1:
        rate = rate / 100
    if rate >= very_high:
        return 5
    if rate >= high:
        return 3
    if rate <= low:
        return -3
    return 0


def enrich_tip(tip: Dict[str, Any], market: str, cache: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(tip)
    home, away = _split_match(str(t.get("match") or ""))
    league = str(t.get("league") or "")
    kind = _market_kind(market, t)

    hf = _find_team(cache, home)
    af = _find_team(cache, away)
    lg_goal = _find_map(cache, league, "league_goal")
    lg_cards = _find_map(cache, league, "league_cards")
    lg_corners = _find_map(cache, league, "league_corners")
    helo = _find_map(cache, home, "elo")
    aelo = _find_map(cache, away, "elo")

    boost = 0
    signals: List[str] = []

    # Goal/BTTS/Over rates
    if kind in ("btts", "combo"):
        vals = [
            _f(hf.get("btts_rate")) if hf else None,
            _f(af.get("btts_rate")) if af else None,
            _f(lg_goal.get("btts_rate")) if lg_goal else None,
        ]
        vals = [v for v in vals if v is not None]
        if vals:
            avg = sum(vals) / len(vals)
            b = _rate_boost(avg, 0.58, 0.64, 0.45)
            boost += b
            signals.append(f"BTTS-History {round(avg*100)}%")

    if kind in ("over", "combo"):
        vals = [
            _f(hf.get("over25_rate")) if hf else None,
            _f(af.get("over25_rate")) if af else None,
            _f(lg_goal.get("over25_rate")) if lg_goal else None,
        ]
        vals = [v for v in vals if v is not None]
        if vals:
            avg = sum(vals) / len(vals)
            b = _rate_boost(avg, 0.55, 0.62, 0.42)
            boost += b
            signals.append(f"Over-History {round(avg*100)}%")

    # Cards and fouls context for cards builders
    if kind in ("cards", "combo"):
        card_vals = [
            _f(hf.get("total_cards_pg")) if hf else None,
            _f(af.get("total_cards_pg")) if af else None,
            _f(lg_cards.get("total_cards_pg")) if lg_cards else None,
        ]
        card_vals = [v for v in card_vals if v is not None]
        if card_vals:
            avg = sum(card_vals) / len(card_vals)
            if avg >= 4.8:
                boost += 5
            elif avg >= 4.0:
                boost += 3
            elif avg <= 2.5:
                boost -= 3
            signals.append(f"Cards {avg:.1f}/Spiel")

    # Corners context
    if kind in ("corners", "combo"):
        vals = [
            _f(hf.get("corners_for_pg")) if hf else None,
            _f(af.get("corners_for_pg")) if af else None,
            _f(lg_corners.get("corners_pg")) if lg_corners else None,
        ]
        vals = [v for v in vals if v is not None]
        if vals:
            avg = sum(vals) / len(vals)
            if avg >= 9.5:
                boost += 4
            elif avg >= 8.5:
                boost += 2
            elif avg <= 6.5:
                boost -= 2
            signals.append(f"Corners {avg:.1f}/Spiel")

    # Elo mismatch: reduces BTTS a little if giant mismatch; boosts favorite/team strength context lightly for over/combo.
    eh = _f((helo or {}).get("elo")) or _f((hf or {}).get("avg_elo"))
    ea = _f((aelo or {}).get("elo")) or _f((af or {}).get("avg_elo"))
    if eh is not None and ea is not None:
        diff = eh - ea
        t["elo_home"] = round(eh, 1)
        t["elo_away"] = round(ea, 1)
        t["elo_diff"] = round(diff, 1)
        if abs(diff) >= 250 and kind == "btts":
            boost -= 2
            signals.append(f"Elo mismatch {round(diff)}")
        elif abs(diff) <= 100 and kind in ("btts", "combo"):
            boost += 1
            signals.append("Elo balanced")

    # Injuries: only small negative for goal markets
    inj_h = _injury_count(cache, home)
    inj_a = _injury_count(cache, away)
    if kind in ("btts", "over", "combo") and (inj_h + inj_a) >= 5:
        boost -= 2
        signals.append(f"Injuries {inj_h + inj_a}")

    # Apply boost, max guard to avoid crazy jumps
    max_boost = int(_env("DATA_FUSION_V15_MAX_BOOST", "7"))
    min_boost = int(_env("DATA_FUSION_V15_MIN_BOOST", "-5"))
    boost = max(min_boost, min(max_boost, boost))

    old_prob = _i(t.get("probability"), 0)
    if old_prob:
        new_prob = _clip(old_prob + boost, 1, 92)
        t["probability"] = new_prob
        if boost:
            t["_v15_boost"] = boost
            t["_v15_old_probability"] = old_prob
    conf = _i(t.get("confidence"), 0)
    if conf and boost >= 4:
        t["confidence"] = min(5, conf + 1)
    elif conf and boost <= -4:
        t["confidence"] = max(1, conf - 1)

    if signals:
        t["data_fusion_v15"] = " | ".join(signals[:4])
        prev = str(t.get("key_factor") or t.get("reasoning") or "").strip()
        addon = "V15: " + "; ".join(signals[:3])
        t["key_factor"] = (prev + " | " + addon).strip(" |")[:500] if prev else addon[:500]
        if not t.get("reasoning"):
            t["reasoning"] = addon[:500]

    return t


def apply_data_fusion_to_tips(
    tips_by_market: Dict[str, List[Dict[str, Any]]],
    supabase_url: str,
    supabase_key: str,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Enrich and re-rank tips_by_market using Supabase feature tables."""
    if _env("ENABLE_DATA_FUSION_V15", "true").lower() not in ("1", "true", "yes", "on"):
        return tips_by_market
    if not supabase_url or not supabase_key:
        return tips_by_market

    cache = _load_cache(supabase_url, supabase_key, log=log)
    out: Dict[str, List[Dict[str, Any]]] = {}
    changed = 0
    for market, tips in (tips_by_market or {}).items():
        enriched = []
        for tip in tips or []:
            nt = enrich_tip(tip, market, cache)
            if nt.get("_v15_boost"):
                changed += 1
            enriched.append(nt)
        enriched.sort(key=lambda x: (_i(x.get("probability")), _i(x.get("confidence")), _f(x.get("oddsYes") or x.get("odds"), 0) or 0), reverse=True)
        out[market] = enriched
    if log:
        try:
            log(f"🧠 V15 Data Fusion angewendet: {changed} Tipps geboostet/angepasst")
        except Exception:
            pass
    return out
