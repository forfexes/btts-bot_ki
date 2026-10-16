#!/usr/bin/env python3
"""Bounded public-web browser support and reliable ESPN JSON fixture handling.

Playwright renders public JavaScript pages when explicitly enabled; it is not
a means of bypassing authentication, CAPTCHA or site access restrictions.
The ESPN scoreboard is a JSON API, not a page that needs Chromium.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import os
import time
from typing import Any, Dict, List
from urllib.parse import urlparse


def _bounded_int(name: str, default: int, high: int) -> int:
    try:
        return max(0, min(high, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _espn_fixtures(bot: Any, league_name: str, target_date: Any) -> List[Dict[str, Any]]:
    leagues = getattr(bot, "ESPN_LEAGUE_IDS", {})
    league_info = leagues.get(league_name)
    if not league_info:
        return []
    sport, league_id = league_info
    cache_key = f"espn_{league_name}_{target_date}"
    cache = getattr(bot, "ESPN_CACHE", {})
    if cache_key in cache:
        return cache[cache_key]
    fallback = getattr(bot, "_AF_BULK_FIXTURES", {}).get(league_name, [])
    date_str = str(target_date).replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/scoreboard"
    try:
        response = bot.requests.get(
            url,
            params={"dates": date_str},
            headers={"Accept": "application/json", "User-Agent": "NETRATTLER/1.0"},
            timeout=8,
        )
        if not response.ok:
            # Error status (including 400/401/403/429) is not valid JSON fixture
            # data and must not be retried through a fake HTML-to-JSON browser.
            bot.log(f"ESPN scoreboard unavailable for {league_name}: HTTP {response.status_code}", "WARN")
            cache[cache_key] = list(fallback)
            return list(fallback)
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("events") or [], list):
            raise ValueError("invalid ESPN scoreboard JSON")
        now = datetime.now(timezone.utc)
        fixtures: List[Dict[str, Any]] = []
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            try:
                comps = event.get("competitions") or []
                comp = comps[0]
                competitors = comp.get("competitors") or []
                if len(competitors) < 2:
                    continue
                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if home is None or away is None:
                    continue
                home_team = home.get("team") or {}
                away_team = away.get("team") or {}
                home_name = home_team.get("displayName") or ""
                away_name = away_team.get("displayName") or ""
                if not home_name or not away_name or home_name == away_name:
                    continue
                if str((comp.get("status") or {}).get("type", {}).get("name") or "") in {
                    "STATUS_FINAL", "STATUS_IN_PROGRESS"
                }:
                    continue
                kickoff_str = str(event.get("date") or "")
                if not kickoff_str:
                    continue
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff.tzinfo is None:
                    continue
                if kickoff <= now:
                    continue
                fixtures.append({
                    "home": home_name, "away": away_name,
                    "match_id": event.get("id", ""),
                    "home_id": home_team.get("id"), "away_id": away_team.get("id"),
                    "time_utc": kickoff_str, "time_local": bot.get_local_time(kickoff_str),
                    "source": "espn",
                })
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
        cache[cache_key] = fixtures
        return fixtures
    except Exception as exc:
        bot.log(f"ESPN JSON fixture error for {league_name}: {type(exc).__name__}", "WARN")
        cache[cache_key] = list(fallback)
        return list(fallback)


def _guard_fbref_advanced(bot: Any) -> None:
    """Stop repeated failed FBref advanced-stat fetches across leagues.

    When a source repeatedly returns no usable data, trying it for every
    league wastes requests and logs. This is a run-local circuit breaker;
    it does not fabricate replacement statistics and does not bypass 403/429.
    """
    manager = getattr(bot, "AdvancedPropsManager", None)
    method = getattr(manager, "scrape_fbref_advanced_stats", None) if manager else None
    if not callable(method) or getattr(method, "_ntr_fbref_circuit", False):
        return
    max_failures = max(1, _bounded_int("NETRATTLER_FBREF_MAX_FAILED_LEAGUES", 2, 10))
    state = {"failures": 0, "open": False, "notice": False}

    def guarded(self, league_name: str):
        if state["open"]:
            # No extra FBref requests, browsers, or repeated warnings.
            return {}
        result = method(self, league_name)
        if result:
            state["failures"] = 0
        else:
            state["failures"] += 1
            if state["failures"] >= max_failures:
                state["open"] = True
                if not state["notice"]:
                    state["notice"] = True
                    try:
                        bot.log(
                            f"FBref advanced stats unavailable across {max_failures} leagues; "
                            "source paused for this run; using available independent stats",
                            "WARN",
                        )
                    except Exception:
                        pass
        return result

    guarded._ntr_fbref_circuit = True
    guarded._ntr_fbref_state = state
    setattr(manager, "scrape_fbref_advanced_stats", guarded)


def install(bot: Any) -> None:
    """Attach conservative Playwright page budget and ESPN JSON-only provider."""
    current = getattr(bot, "scrape_with_playwright", None)
    if callable(current) and getattr(current, "_ntr_browser_budget_guard", False) is not True:
        enabled = str(os.environ.get("NETRATTLER_PLAYWRIGHT_ENABLED", "false")).lower() in {"1", "yes", "true", "on"}
        available = importlib.util.find_spec("playwright") is not None
        bot.PLAYWRIGHT_AVAILABLE = bool(enabled and available)
        max_pages = _bounded_int("NETRATTLER_PLAYWRIGHT_MAX_PAGES", 4, 12)
        seconds = _bounded_int("NETRATTLER_PLAYWRIGHT_BUDGET_SEC", 45, 120)
        stats = {"used": 0, "first": None, "warned": False}

        def browser(url: str, wait_for=None, timeout=8000):
            if not bot.PLAYWRIGHT_AVAILABLE or max_pages == 0:
                return None
            parsed = urlparse(str(url or ""))
            if parsed.scheme not in ("https", "http") or not parsed.hostname:
                return None
            if parsed.hostname == "fbref.com" or parsed.hostname.endswith(".fbref.com"):
                # The caller only launches a browser here after an explicit
                # 403/429; do not try to defeat the upstream access restriction.
                return None
            elapsed = 0 if stats["first"] is None else time.monotonic() - stats["first"]
            if stats["used"] >= max_pages or elapsed >= seconds:
                if not stats["warned"]:
                    stats["warned"] = True
                    bot.log(f"Playwright browser budget reached ({stats['used']} pages / {seconds}s); using other sources", "WARN")
                return None
            if stats["first"] is None:
                stats["first"] = time.monotonic()
            stats["used"] += 1
            return current(url, wait_for=wait_for, timeout=min(int(timeout), 8000))

        browser._ntr_browser_budget_guard = True
        browser._ntr_browser_stats = stats
        bot.scrape_with_playwright = browser

    _guard_fbref_advanced(bot)

    original = getattr(bot, "fetch_espn_fixtures", None)
    if callable(original) and getattr(original, "_ntr_json_guard", False) is not True:
        def fetch(league_name, target_date):
            return _espn_fixtures(bot, league_name, target_date)
        fetch._ntr_json_guard = True
        bot.fetch_espn_fixtures = fetch
