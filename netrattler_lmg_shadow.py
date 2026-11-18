#!/usr/bin/env python3
"""Bounded, independent GOAL HUNTER in-play evidence collection (SHADOW ONLY).

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


def _database() -> tuple[str, dict]:
    endpoint, headers = common._db()
    return endpoint.rsplit("/", 1)[0] + "/" + TABLE, headers


def _count_rows(url: str, headers: dict) -> int:
    r = requests.get(url, headers={**headers, "Prefer":"count=exact"},
                     params={"select":"fixture_id", "limit":"1"}, timeout=15)
    r.raise_for_status()
    count = str(r.headers.get("Content-Range", "")).rsplit("/", 1)[-1]
    if not count.isdecimal():
        raise RuntimeError("shadow_row_count_unavailable")
    return int(count)


def write_snapshots(rows: list[dict], *, enabled: bool = False,
                    now: dt.datetime | None = None) -> dict:
    """Fail closed on capacity or API errors. Idempotent on provider+event+bin."""
    if not enabled:
        return {"status":"disabled", "attempted":0}
    if not rows:
        return {"status":"empty", "attempted":0}
    if len(rows) > MAX_BATCH:
        raise ValueError("shadow_batch_exceeds_maximum")
    by_key = {}
    for row in rows:
        key = (row["provider"], row["fixture_id"], row["slot"])
        if key in by_key and by_key[key] != row:
            raise ValueError("conflicting_same_batch_snapshot")
        by_key[key] = row
    url, headers = _database()
    now = now or utcnow()
    cutoff = (now-dt.timedelta(days=KEEP_DAYS)).astimezone(dt.timezone.utc).isoformat()
    cleaned = requests.delete(url, headers={**headers, "Prefer":"return=minimal"},
                              params={"collected_at":"lt."+cutoff}, timeout=15)
    cleaned.raise_for_status()
    count = _count_rows(url, headers)
    if count + len(by_key) > MAX_ROWS:
        print("LMG_SHADOW_CAPACITY_LIMIT", json.dumps({
            "rows":count,"incoming":len(by_key),"max":MAX_ROWS}),flush=True)
        return {"status":"capacity_limit","attempted":len(by_key),"rows":count}
    response = requests.post(url, headers={**headers,
                "Prefer":"resolution=ignore-duplicates,return=minimal"},
                params={"on_conflict":"provider,fixture_id,slot"},
                json=list(by_key.values()), timeout=20)
    response.raise_for_status()
    return {"status":"saved","attempted":len(by_key),"existing":count}


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
    """Attach final result to original snapshots; never change Telegram tips."""
    if not enabled:
        return {"status":"disabled"}
    from netrattler_lmg_fotmob import fetch_fotmob
    now=now or utcnow()
    url,headers=_database()
    cutoff=(now-dt.timedelta(days=4)).isoformat()
    response=requests.get(url,headers=headers,params={
        "select":"provider,fixture_id,kickoff,home,away,home_goals,away_goals",
        "final_verified_at":"is.null","collected_at":"gte."+cutoff,
        "order":"collected_at.asc","limit":"120"},timeout=20)
    response.raise_for_status()
    rows=response.json()
    unique={}
    for row in rows:
        unique.setdefault((row["provider"],row["fixture_id"]),row)
    cached={}
    settled=0
    for (provider,fixture_id),row in unique.items():
        if provider != "fotmob":
            continue  # ESPN final results need a separate explicitly verified path.
        day=common._date(row["kickoff"])
        if day is None:
            continue
        day=day.strftime("%Y%m%d")
        if day not in cached:
            cached[day]=fetch_fotmob(day)
        final=_finished(cached[day],row)
        if final is None:
            continue
        patch=requests.patch(url,headers={**headers,"Prefer":"return=minimal"},
            params={"provider":"eq.fotmob","fixture_id":"eq."+str(fixture_id),
                    "final_verified_at":"is.null"},
            json={"final_home_goals":final[0],"final_away_goals":final[1],
                  "final_verified_at":now.isoformat()},timeout=15)
        patch.raise_for_status()
        settled+=1
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
