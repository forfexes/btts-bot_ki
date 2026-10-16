#!/usr/bin/env python3
"""Read-only L30 scorer history fallback, used only when the aggregate view has no goals.

Never infer player identity from surname alone or from bookmaker prices.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping
import re
import inspect
import unicodedata

import requests

_RECENT_CACHE: Dict[str, Dict[str, Any]] = {}


def _exact_name(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold().strip()


def _goal_view_available(stats: Any) -> bool:
    if not isinstance(stats, Mapping):
        return False
    for key, entry in stats.items():
        if str(key).lower().replace(" ", "_").replace("-", "_") not in {
            "goals", "goal", "goals_per_game", "goals_pg", "goals_scored"
        }:
            continue
        try:
            # A goal average from one or two appearances is not enough to
            # suppress the L30 fallback. The final model also requires >=3 games.
            return float((entry or {}).get("games") or 0) >= 3
        except (AttributeError, TypeError, ValueError):
            return False
    return False


def recent_goals(player_name: str, url: str, key: str) -> Dict[str, Any]:
    """Recent observed goals, L30, exact player name and unique player ID required."""
    name = str(player_name or "").strip()
    if not url or not key or not 3 <= len(name) <= 100:
        return {}
    # Reject PostgREST ilike wildcards and query separators; never broaden identity.
    if re.search(r"[%*_,()\\\r\n]", name):
        return {}
    cache_key = _exact_name(name)
    if cache_key in _RECENT_CACHE:
        return dict(_RECENT_CACHE[cache_key])
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat()
    result: Dict[str, Any] = {}
    try:
        response = requests.get(
            f"{url.rstrip('/')}/rest/v1/player_game_log",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"player_name": f"ilike.{name}", "goals": "not.is.null",
                    "minutes": "gt.0", "match_date": f"gte.{cutoff}",
                    "select": "player_id,player_name,event_id,match_date,goals,minutes",
                    "order": "match_date.desc", "limit": "30"},
            timeout=5,
        )
        if response.ok:
            rows = response.json()
            if isinstance(rows, list):
                ids = set()
                unique = set()
                goals = []
                for row in rows:
                    if not isinstance(row, dict) or _exact_name(row.get("player_name")) != cache_key:
                        continue
                    pid, event_id = str(row.get("player_id") or ""), str(row.get("event_id") or "")
                    if not pid or not event_id:
                        continue
                    ids.add(pid)
                    if event_id in unique:
                        continue
                    unique.add(event_id)
                    try:
                        n = float(row.get("goals"))
                        minutes = float(row.get("minutes"))
                    except (TypeError, ValueError):
                        continue
                    if 0 <= n <= 6 and minutes > 0:
                        goals.append(n)
                # Name collision protection. No goal probabilities without 3 actual matches.
                if len(ids) == 1 and len(goals) >= 3:
                    avg = sum(goals) / len(goals)
                    result = {"goals": {"avg": round(avg, 5),
                                        "hit_rate": round(100 * sum(g > 0 for g in goals) / len(goals), 3),
                                        "games": len(goals)}}
    except (requests.RequestException, ValueError, TypeError):
        result = {}
    _RECENT_CACHE[cache_key] = dict(result)
    return result


def install(bot) -> None:
    """Add L30 player_game_log fallback without changing valid player_avg_stats values."""
    original = getattr(bot, "get_supabase_player_avg_stats", None)
    if not callable(original) or getattr(original, "_ntr_scorer_l30", False):
        return

    def guarded(player_name):
        existing = original(player_name) or {}
        if _goal_view_available(existing):
            return existing
        # The same average-stats function is used by thousands of player-prop
        # lookups. Run extra Supabase I/O ONLY for the goalscorer history pipeline.
        frame = inspect.currentframe()
        try:
            parent = frame.f_back if frame is not None else None
            qualified = parent.f_code.co_qualname if parent is not None else ""
        finally:
            del frame
        if not qualified.endswith("_ntr_history_scorers_from_quotes.<locals>._one"):
            return existing
        try:
            url = getattr(bot, "SUPABASE_URL", "")
            key = getattr(bot, "SUPABASE_KEY", "")
            new = recent_goals(player_name, url, key)
            if new:
                return {**existing, **new}
        except Exception:
            pass
        return existing

    guarded._ntr_scorer_l30 = True
    bot.get_supabase_player_avg_stats = guarded
