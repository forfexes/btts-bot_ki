#!/usr/bin/env python3
"""Bounded TheSportsDB day cache for NETRATTLER match discovery.

The upstream eventsday endpoint is shared across every league. Fetch once per
UTC day and filter locally, rather than repeat a failing network request for
every league. Failure is isolated; remaining fixture providers still run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import os

_DAY_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_WARNED: set[str] = set()


def _events_for_date(bot: Any, day: str) -> List[Dict[str, Any]]:
    if day in _DAY_CACHE:
        return _DAY_CACHE[day]
    try:
        timeout = max(1.0, min(12.0, float(os.getenv("NETRATTLER_TSDB_TIMEOUT_SEC", "5"))))
        r = bot.requests.get(
            "https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
            params={"d": day, "s": "Soccer"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        if not r.ok:
            raise ValueError(f"HTTP {r.status_code}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected TheSportsDB JSON response")
        events = data.get("events") or []
        if not isinstance(events, list):
            raise ValueError("Invalid events payload")
        _DAY_CACHE[day] = [e for e in events if isinstance(e, dict)]
    except Exception as exc:
        # One bounded failure per day; no repeated 12-second timeouts.
        _DAY_CACHE[day] = []
        if day not in _WARNED:
            _WARNED.add(day)
            try:
                bot.log(f"TheSportsDB day feed unavailable: {str(exc)[:90]}; switching to other fixture sources", "WARN")
            except Exception:
                pass
    return _DAY_CACHE[day]


def install(bot: Any) -> None:
    original = getattr(bot, "fetch_thesportsdb_fixtures", None)
    if not callable(original) or getattr(original, "_ntr_day_cached", False):
        return

    def cached_fixtures(league_name: str, target_date: Any):
        league_id = getattr(bot, "THESPORTSDB_LEAGUE_IDS", {}).get(league_name)
        if not league_id:
            return []
        day = str(target_date)[:10]
        key = f"tsdb_{league_name}_{target_date}"
        cache = getattr(bot, "THESPORTSDB_FIXTURES_CACHE", None)
        if isinstance(cache, dict) and key in cache:
            return cache[key]
        now = datetime.now(timezone.utc)
        fixtures: List[Dict[str, Any]] = []
        for e in _events_for_date(bot, day):
            if str(e.get("dateEvent") or "") != day:
                continue
            if str(e.get("idLeague") or "") != str(league_id):
                continue
            status = str(e.get("strStatus") or "").lower()
            if status in {"match finished", "ft", "aet", "pen", "after extra time"}:
                continue
            home, away = str(e.get("strHomeTeam") or ""), str(e.get("strAwayTeam") or "")
            if not home or not away or home == away:
                continue
            kickoff_str = f"{day}T{str(e.get('strTime') or '12:00:00')}Z"
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if kickoff <= now:
                continue
            fixtures.append({
                "home": home, "away": away,
                "match_id": str(e.get("idEvent") or ""),
                "time_utc": kickoff_str,
                "time_local": bot.get_local_time(kickoff_str),
                "source": "thesportsdb",
            })
        if isinstance(cache, dict):
            cache[key] = fixtures
        return fixtures

    cached_fixtures._ntr_day_cached = True
    cached_fixtures._ntr_original = original
    bot.fetch_thesportsdb_fixtures = cached_fixtures
