#!/usr/bin/env python3
"""Licensed-friendly SportScore discovery heartbeat for Goal Hunter.

Data source: https://sportscore.com/developers/
Visible attribution required whenever this data is shown in a UI. No Telegram,
no odds, no goal signals, no upstream ID substitution and no Supabase.
GitHub's state/goal-hunter SQLite branch stores small bounded observations.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from urllib.parse import urlparse

import requests

from netrattler_lmg_external_sources import sportscore_discovery_report

API_URL = "https://sportscore.com/api/widget/matches/"
ATTRIBUTION = "Powered by SportScore — https://sportscore.com/"
KEEP_DAYS = 7
MAX_LIVE_ROWS = 3000
MAX_HEARTBEATS = 1008


def _event_path(url):
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlparse(url.strip())
    if parts.scheme and (parts.scheme != "https" or
                         parts.hostname not in ("sportscore.com", "www.sportscore.com")):
        return None
    path = parts.path.strip("/")
    if not path.startswith("football/match/") or len(path) > 250:
        return None
    return path


def _text(value, limit=120):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _goal(value):
    if type(value) is int and 0 <= value <= 99:
        return value
    if isinstance(value, str) and value.isdecimal() and 0 <= int(value) <= 99:
        return int(value)
    return None


def live_rows(payload, now):
    """Keep only explicitly in-play matches, never infer a game minute."""
    rows = payload.get("matches") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("sportscore_matches_missing")
    found = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict) or str(item.get("status") or "").casefold() not in (
                "live", "in_play", "second_half"):
            continue
        path = _event_path(item.get("url"))
        home, away = _text(item.get("home")), _text(item.get("away"))
        if not path or not home or not away or home.casefold() == away.casefold() or path in seen:
            continue
        seen.add(path)
        found.append({
            "provider": "sportscore",
            "source_event_path": path,
            "observed_at": now,
            "home": home,
            "away": away,
            "home_goals": _goal(item.get("home_score")),
            "away_goals": _goal(item.get("away_score")),
            "status_text": _text(item.get("status_text"), 40),
            "source_time_text": _text(item.get("time"), 80),
            "league": _text(item.get("competition"), 100),
        })
    return found


def collect(get=requests.get, *, now=None):
    if os.getenv("LMG_SPORTSCORE_SHADOW", "false").lower() != "true":
        raise RuntimeError("sportscore_shadow_disabled")
    if os.getenv("LMG_SEND", "false").lower() not in ("", "false", "0"):
        raise RuntimeError("sportscore_never_telegram")
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone_required")
    observed_at = now.astimezone(dt.timezone.utc).isoformat()
    result = get(API_URL,params={"sport":"football","limit":50,"src":"netrattler-sqlite-shadow"},
                 headers={"Accept":"application/json","User-Agent":"NETRATTLER-SourceHealth/1.0"},
                 timeout=12)
    result.raise_for_status()
    data = result.json()
    health = sportscore_discovery_report(data)
    fixtures = live_rows(data,observed_at)
    return health,fixtures


def save(health,fixtures, *, now=None):
    from netrattler_lmg_store import _connect, persist
    if not isinstance(health,dict) or health.get("provider") != "sportscore":
        raise ValueError("invalid_sportscore_provenance")
    now = now or dt.datetime.now(dt.timezone.utc)
    timestamp = now.astimezone(dt.timezone.utc).isoformat()
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).isoformat()
    if len(fixtures) > 50:
        raise ValueError("unbounded_sportscore_fixture_batch")
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS source_discovery_heartbeat (
                provider TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                total_matches INTEGER NOT NULL,
                live_matches INTEGER NOT NULL,
                strictly_matchable INTEGER NOT NULL,
                PRIMARY KEY(provider,observed_at)
            );
            CREATE TABLE IF NOT EXISTS source_live_fixtures (
                provider TEXT NOT NULL,
                source_event_path TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                home TEXT NOT NULL,
                away TEXT NOT NULL,
                home_goals INTEGER,
                away_goals INTEGER,
                status_text TEXT,
                source_time_text TEXT,
                league TEXT,
                PRIMARY KEY(provider,source_event_path,observed_at)
            );
        """)
        conn.execute("DELETE FROM source_discovery_heartbeat WHERE observed_at < ?",(cutoff,))
        conn.execute("DELETE FROM source_live_fixtures WHERE observed_at < ?",(cutoff,))
        conn.execute("""
            INSERT OR IGNORE INTO source_discovery_heartbeat
            (provider,observed_at,total_matches,live_matches,strictly_matchable)
            VALUES (?,?,?,?,?)
        """,("sportscore",timestamp,int(health["total_matches"]),
             int(health["live_matches"]),int(health["strictly_matchable"])))
        for item in fixtures:
            if item.get("provider") != "sportscore" or not _event_path(item.get("source_event_path")):
                raise ValueError("invalid_sportscore_fixture")
            conn.execute("""
                INSERT OR IGNORE INTO source_live_fixtures
                (provider,source_event_path,observed_at,home,away,home_goals,
                 away_goals,status_text,source_time_text,league)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,(item["provider"],item["source_event_path"],item["observed_at"],
                 item["home"],item["away"],item["home_goals"],item["away_goals"],
                 item["status_text"],item["source_time_text"],item["league"]))
        # Small rolling bounded SQLite state, not one row for every scraped event.
        for table,cap in (("source_discovery_heartbeat",MAX_HEARTBEATS),
                          ("source_live_fixtures",MAX_LIVE_ROWS)):
            count=conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > cap:
                conn.execute(f"""DELETE FROM {table} WHERE rowid IN
                    (SELECT rowid FROM {table} ORDER BY observed_at ASC LIMIT ?)""",(count-cap,))
        conn.commit()
    finally:
        conn.close()
    persist("record licensed SportScore read-only coverage")
    return {"status":"saved","live_rows":len(fixtures),
            "total_matches":health["total_matches"],
            "live_matches":health["live_matches"],
            "strictly_matchable":health["strictly_matchable"],
            "telegram_messages":0,
            "attribution":ATTRIBUTION}


def run():
    from netrattler_lmg_store import init
    init()
    health,fixtures=collect()
    report=save(health,fixtures)
    print("LMG_SPORTSCORE_SQLITE_SHADOW",json.dumps(report,ensure_ascii=False),flush=True)
    return report


if __name__=="__main__":
    run()
