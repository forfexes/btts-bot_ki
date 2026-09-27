#!/usr/bin/env python3
"""Final REAL_ODDS_ONLY fallback layer for NETRATTLER.

After Pinnacle and the fast runtime fallbacks, this guard fills still-missing team
markets from two observed-only sources:
1) multi-brand Kambi (Unibet/Betsson/888/NordicBet),
2) fresh Supabase odds_history rows written by asynchronous collectors such as
   The Odds API and AiScore.

It never creates fair/model/default odds and never overwrites an already valid
observed price returned by an earlier layer.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests

try:
    import netrattler_kambi_team_odds as kambi_team
except Exception:  # optional/fault isolated
    kambi_team = None

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
TIMEOUT = float(os.getenv("NETRATTLER_ODDS_CACHE_TIMEOUT", "8"))
TTL = int(os.getenv("NETRATTLER_ODDS_CACHE_TTL", "600"))
MAX_ROWS = int(os.getenv("NETRATTLER_ODDS_CACHE_MAX_ROWS", "5000"))
MAX_AGE_HOURS = float(os.getenv("NETRATTLER_ODDS_CACHE_MAX_AGE_HOURS", "18"))

_CACHE: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
_INSTALLED = False
_LOGGED = 0


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _teams_match(candidate: Any, target: Any) -> bool:
    a, b = _norm(candidate), _norm(target)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    aa = {x for x in a.split() if len(x) >= 4 and x not in {"club", "city", "united"}}
    bb = {x for x in b.split() if len(x) >= 4 and x not in {"club", "city", "united"}}
    return bool(aa and bb and (aa & bb))


def _price(value: Any, hi: float = 100.0) -> Optional[float]:
    try:
        x = float(str(value).replace(",", "."))
    except Exception:
        return None
    return round(x, 4) if 1.0001 < x <= hi else None


def _fresh(row: Mapping[str, Any]) -> bool:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    stamp = raw.get("captured_at") or raw.get("timestamp") or raw.get("updated_at")
    if not stamp:
        return True
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
        return -1.0 <= age <= MAX_AGE_HOURS
    except Exception:
        return True


def _load_rows(force: bool = False) -> List[Dict[str, Any]]:
    global _CACHE
    now = time.time()
    if not force and _CACHE[1] and now - _CACHE[0] < TTL:
        return _CACHE[1]
    if not SUPABASE_URL or not SUPABASE_KEY:
        _CACHE = (now, [])
        return []
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/odds_history",
            headers=headers,
            params={
                "captured_date": f"eq.{today}",
                "select": "source,bookmaker,home_team,away_team,match_date,market,selection,odds,raw",
                "limit": str(MAX_ROWS),
            },
            timeout=TIMEOUT,
        )
        data = r.json() if r.ok and r.text else []
        rows = [dict(x) for x in data if isinstance(x, dict) and _fresh(x)] if isinstance(data, list) else []
        _CACHE = (now, rows)
        return rows
    except Exception:
        _CACHE = (now, [])
        return []


def _field_for_row(row: Mapping[str, Any]) -> Optional[str]:
    market = str(row.get("market") or "").lower().replace("-", "_")
    selection = str(row.get("selection") or "").lower().strip()
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    line = raw.get("line")
    try:
        line_f = float(line) if line not in (None, "") else None
    except Exception:
        line_f = None
    if market in {"1x2", "h2h", "moneyline"}:
        return {"home": "home_win", "1": "home_win", "draw": "draw", "x": "draw", "away": "away_win", "2": "away_win"}.get(selection)
    if market in {"btts", "both_teams_to_score"} or ("btts" in market and "ht" not in market and "half" not in market and "combo" not in market and "over" not in market):
        return "btts_yes" if selection in {"yes", "y"} else None
    if market in {"btts_ht", "btts_1h"} or ("btts" in market and ("ht" in market or "half" in market)):
        return "btts_yes_ht" if selection in {"yes", "y"} else None
    if market in {"totals_ht_1_5", "over_under_ht_1_5"} or (("1_5" in market or line_f == 1.5) and ("ht" in market or "half" in market)):
        return "over_15_ht" if selection.startswith("over") else None
    if market in {"totals_2_5", "over_under_2_5"} or ("2_5" in market and "corner" not in market):
        return "over_25" if selection.startswith("over") else None
    if "btts" in market and ("over25" in market or "over_2_5" in market or "over2_5" in market or "combo" in market):
        return "btts_over25_yes" if ("yes" in selection or selection in {"over", "btts_over"}) else None
    return None


def best_observed_for_match(home: str, away: str, rows: Optional[Iterable[Mapping[str, Any]]] = None) -> Tuple[Dict[str, float], Dict[str, str]]:
    best: Dict[str, float] = {}
    sources: Dict[str, str] = {}
    for row in (list(rows) if rows is not None else _load_rows()):
        if not (_teams_match(row.get("home_team"), home) and _teams_match(row.get("away_team"), away)):
            continue
        field = _field_for_row(row)
        if not field:
            continue
        p = _price(row.get("odds"), 60.0 if field == "btts_over25_yes" else 30.0)
        if p is None:
            continue
        if p > best.get(field, 0.0):
            best[field] = p
            source = str(row.get("bookmaker") or row.get("source") or "odds_history")
            root = str(row.get("source") or "")
            sources[field] = f"{root}:{source}" if root and root != source else source
    return best, sources


def _fill_missing(odds: Dict[str, Any], observed: Mapping[str, Any], sources: Mapping[str, str]) -> List[str]:
    added: List[str] = []
    for field, value in observed.items():
        hi = 60.0 if field == "btts_over25_yes" else 30.0
        if _price(odds.get(field), hi) is not None:
            continue
        p = _price(value, hi)
        if p is None:
            continue
        odds[field] = p
        added.append(field)
        source = sources.get(field, "observed_fallback")
        odds.setdefault("_ntr_field_sources", {})[field] = source
        if field == "btts_yes":
            odds.pop("_btts_quote_missing", None)
        elif field == "over_25":
            odds.pop("_over25_quote_missing", None)
        elif field == "btts_yes_ht":
            odds["_btts_ht_source"] = source
        elif field == "over_15_ht":
            odds["_over15_ht_source"] = source
        elif field == "btts_over25_yes":
            odds["_combo_source"] = source
    return added


def install(bot) -> None:
    """Wrap the already-guarded quote lookup with observed-only final fallbacks."""
    global _INSTALLED
    original = getattr(bot, "get_pinnacle_match_odds", None)
    if not callable(original) or getattr(original, "_ntr_odds_cache_guard", False):
        return

    def guarded(home: str, away: str, *args, **kwargs):
        global _LOGGED
        raw = original(home, away, *args, **kwargs)
        odds = dict(raw) if isinstance(raw, dict) else {}
        all_added: List[Tuple[str, str]] = []

        # Multi-brand Kambi first: live bookmaker offers, no key.
        if kambi_team is not None:
            try:
                k_odds, k_sources = kambi_team.get_multi_brand_team_odds(home, away)
                for field in _fill_missing(odds, k_odds, k_sources):
                    all_added.append((field, k_sources.get(field, "kambi")))
            except Exception:
                pass

        # Then fresh persisted prices (AiScore, The Odds API, etc.).
        observed, sources = best_observed_for_match(home, away)
        for field in _fill_missing(odds, observed, sources):
            all_added.append((field, sources.get(field, "odds_history")))

        if all_added and _LOGGED < int(os.getenv("NETRATTLER_ODDS_CACHE_LOG_LIMIT", "20")):
            try:
                detail = ", ".join(f"{field}={source}" for field, source in all_added)
                bot.log(f"   🗄️ Final Real-Odds Fallback {home} vs {away}: {detail}")
                _LOGGED += 1
            except Exception:
                pass
        return odds

    guarded._ntr_odds_cache_guard = True
    guarded._ntr_original = original
    bot.get_pinnacle_match_odds = guarded
    _INSTALLED = True


__all__ = ["best_observed_for_match", "install"]
