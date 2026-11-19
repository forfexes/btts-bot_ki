#!/usr/bin/env python3
"""Bounded, independent GOAL HUNTER in-play evidence collection (SHADOW ONLY).

Storage: Git-versioned SQLite in the same repository, not Supabase.

Capture true data *as retrieved* in the 65–85 minute window, not final-match
data. Keep at most four observations per provider fixture (one per minute bin).
No simulated xG, fabricated quotes, production tips or additional Telegram posts.
No claims about extra-source uplift until a genuinely paired live replay exists.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys
from typing import Any

import requests

import netrattler_lmg_free as common

TABLE = "netrattler_lmg_shadow_snapshots"
KEEP_DAYS = 45
MAX_ROWS = 4500
MAX_BATCH = 16
BIN_LIMITS = (69, 74, 79, 85)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _count(x: Any, upper: int = 200) -> int | None:
    return x if type(x) is int and 0 <= x <= upper else None


def _xg(x: Any) -> float | None:
    return round(float(x), 2) if type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 20 else None


def build_snapshot(fixture: dict, metrics: dict | None,
                   data_provider: str | None = None,
                   observed_at: dt.datetime | None = None) -> dict:
    """One evidence row. Missing data stays NULL, never zero.

    collected_at is the actual local capture time after fetching the live feed;
    it is NOT a fabricated upstream provider data timestamp.
    """
    minute = fixture.get("minute")
    if type(minute) is not int or not common.MIN_MINUTE <= minute <= common.MAX_MINUTE:
        raise ValueError("invalid_live_minute")
    source = fixture.get("source") or "fotmob"
    if source not in ("fotmob", "espn") or (
            data_provider is not None and data_provider not in ("fotmob", "espn")):
        raise ValueError("unverified_provider")
    eid = _count(fixture.get("fixture_id"), 10**17)
    kickoff = fixture.get("kickoff")
    observed_at = observed_at or utcnow()
    if eid is None or eid == 0 or not isinstance(kickoff, dt.datetime):
        raise ValueError("missing_fixture_identity")
    if kickoff.tzinfo is None or kickoff.utcoffset() is None or (
            observed_at.tzinfo is None or observed_at.utcoffset() is None):
        raise ValueError("timezone_required")
    if abs((observed_at - kickoff).total_seconds()) > 36*3600:
        raise ValueError("kickoff_out_of_range")
    if not fixture.get("home") or not fixture.get("away") or fixture["home"] == fixture["away"]:
        raise ValueError("invalid_team_identity")
    home_goals = _count(fixture.get("hg"), 99)
    away_goals = _count(fixture.get("ag"), 99)
    if home_goals is None or away_goals is None:
        raise ValueError("invalid_live_score")
    slot = next(i for i, maximum in enumerate(BIN_LIMITS) if minute <= maximum)
    row = {
        "provider": source, "fixture_id": eid, "slot": slot,
        "kickoff": kickoff.astimezone(dt.timezone.utc).isoformat(),
        "collected_at": observed_at.astimezone(dt.timezone.utc).isoformat(),
        "minute": minute, "home": fixture["home"], "away": fixture["away"],
        "home_goals": home_goals, "away_goals": away_goals,
        "data_provider": None, "stats_available": False, "baseline_send": None,
        "candidate_send": None, "candidate_source": None,
        "home_shots": None, "away_shots": None,
        "home_sot": None, "away_sot": None,
        "home_corners": None, "away_corners": None,
        "home_xg": None, "away_xg": None,
    }
    if not metrics:
        return row
    teams = metrics.get("teams") if isinstance(metrics, dict) else None
    if not isinstance(teams, dict):
        return row
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if not isinstance(home, dict) or not isinstance(away, dict):
        return row
    hs, aws = _count(home.get("shots")), _count(away.get("shots"))
    ht, at = _count(home.get("sot")), _count(away.get("sot"))
    if any(x is None for x in (hs, aws, ht, at)):
        return row
    if ht > hs or at > aws:
        raise ValueError("impossible_live_shot_totals")
    if (metrics.get("shots") != hs + aws or metrics.get("sot") != ht + at):
        raise ValueError("provider_live_totals_conflict")
    if data_provider is None:
        raise ValueError("live_stats_missing_provider_proof")
    hc, ac = _count(home.get("corners"), 100), _count(away.get("corners"), 100)
    hx, ax = _xg(home.get("xg")), _xg(away.get("xg"))
    row.update({
        "data_provider": data_provider, "stats_available": True,
        "home_shots": hs, "away_shots": aws, "home_sot": ht, "away_sot": at,
        "home_corners": hc, "away_corners": ac,
        "home_xg": hx if hx is not None and ax is not None else None,
        "away_xg": ax if hx is not None and ax is not None else None,
        "baseline_send": common.select_goal_tier(fixture, metrics) is not None,
    })
    return row


def write_snapshots(rows: list[dict], *, enabled: bool = False,
                    now: dt.datetime | None = None) -> dict:
    """Persist bounded, verified original observations to GitHub-backed SQLite."""
    from netrattler_lmg_store import write_snapshots as sqlite_write
    return sqlite_write(rows, enabled=enabled, now=now)


def _finished(feed: dict, row: dict) -> tuple[int, int] | None:
    """Settle solely from the exact FotMob fixture, not team names or history."""
    from netrattler_lmg_fotmob import _score
    for league in (feed or {}).get("leagues") or []:
        for match in league.get("matches") or []:
            if common._int(match.get("id")) != row["fixture_id"]:
                continue
            status = match.get("status") or {}
            if status.get("finished") is not True or status.get("cancelled") is True:
                return None
            home,away = match.get("home") or {},match.get("away") or {}
            if home.get("name") != row["home"] or away.get("name") != row["away"]:
                return None
            kickoff=common._date(status.get("utcTime"))
            old_kickoff=common._date(row.get("kickoff"))
            if not kickoff or not old_kickoff or abs((kickoff-old_kickoff).total_seconds())>600:
                return None
            score=_score(match)
            if score is None or score[0] < row["home_goals"] or score[1] < row["away_goals"]:
                return None
            return score
    return None


def settle_snapshots(*, enabled: bool = False, now: dt.datetime | None = None) -> dict:
    """Use only the original exact FotMob fixture for finished live snapshots."""
    if not enabled:
        return {"status":"disabled"}
    from netrattler_lmg_store import pending_snapshots, settle_snapshot
    from netrattler_lmg_fotmob import fetch_fotmob
    now = now or utcnow()
    rows = pending_snapshots(now)
    unique = {}
    for row in rows:
        unique.setdefault((row["provider"], row["fixture_id"]), row)
    cached = {}
    settled = 0
    for (provider, fixture_id), row in unique.items():
        if provider != "fotmob":
            continue  # ESPN rows require a separate source-verifiable final.
        kickoff = common._date(row.get("kickoff"))
        if kickoff is None:
            continue
        day = kickoff.strftime("%Y%m%d")
        if day not in cached:
            cached[day] = fetch_fotmob(day)
        final = _finished(cached[day], row)
        if final is None:
            continue
        if settle_snapshot(provider, fixture_id, final, now):
            settled += 1
    return {"status":"ok","pending_fixtures":len(unique),
            "settled_fixtures":settled}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv)>1 else "status"
    enabled = os.getenv("LMG_SHADOW_ENABLED","false").lower() == "true"
    if mode == "settle":
        try:
            print("LMG_SHADOW_SETTLE",json.dumps(settle_snapshots(enabled=enabled)),flush=True)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print("LMG_SHADOW_SETTLE_UNAVAILABLE",type(exc).__name__,str(exc)[:120],flush=True)
    elif mode == "status":
        print("LMG_SHADOW_STATUS",json.dumps({"enabled":enabled,
              "max_rows":MAX_ROWS,"retention_days":KEEP_DAYS,
              "telegram_posts":0,"extra_source_proven":False}),flush=True)
    else:
        raise SystemExit("usage: netrattler_lmg_shadow.py [status|settle]")


if __name__ == "__main__":
    main()
