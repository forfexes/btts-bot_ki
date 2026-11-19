#!/usr/bin/env python3
"""Optional API-Football *verified* live-stats recovery for Goal Hunter.

Only use if an already configured API-SPORTS key exists. FotMob remains the
fixture/settlement authority. Reject mismatched, ambiguous, stale or incomplete
provider matches; never fabricate stats, xG, odds, or confidence values.
The SQLite reservation below limits API calls across scheduled Actions runners.
"""
from __future__ import annotations

import os
import re

import requests

import netrattler_lmg_free as common
import netrattler_lmg_fotmob as fotmob
from netrattler_last_minute_goal import match_metrics
from netrattler_lmg_store import reserve_source_calls

BASE = "https://v3.football.api-sports.io"
RESERVED_CALLS_PER_ATTEMPT = 2
MIN_REMAINING_REQUESTS = 20


def configured_key() -> str:
    raw = os.getenv("API_FOOTBALL_KEYS") or os.getenv("API_FOOTBALL_KEY") or ""
    return next((value.strip() for value in raw.replace("\n", ",").split(",")
                 if value.strip()), "")


def _query(path: str, params: dict, key: str) -> tuple[list, int | None]:
    response = requests.get(
        BASE + path, params=params, headers={"x-apisports-key": key},
        timeout=18,
    )
    response.raise_for_status()
    doc = response.json()
    if not isinstance(doc, dict) or doc.get("errors") or not isinstance(doc.get("response"), list):
        raise ValueError("api_football_invalid_response")
    left = response.headers.get("x-ratelimit-requests-remaining")
    remain = int(left) if left is not None and str(left).isdecimal() else None
    return doc["response"], remain


def unique_live_match(fx: dict, rows: list[dict]) -> dict | None:
    """Prove one provider event has the same real match, not just same names."""
    found = []
    for row in rows:
        fixture = row.get("fixture") or {}
        status = fixture.get("status") or {}
        if status.get("short") != "2H":
            continue
        minute = common._int(status.get("elapsed"))
        kickoff = common._date(fixture.get("date"))
        if minute is None or kickoff is None or abs(minute - fx["minute"]) > 5:
            continue
        if abs((kickoff - fx["kickoff"]).total_seconds()) > 900:
            continue
        teams, score = row.get("teams") or {}, row.get("goals") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        homeid, awayid = common._int(home.get("id")), common._int(away.get("id"))
        fixtureid = common._int(fixture.get("id"))
        if not all((homeid, awayid, fixtureid)):
            continue
        if (fotmob._club_name(home.get("name")) != fotmob._club_name(fx["home"])
                or fotmob._club_name(away.get("name")) != fotmob._club_name(fx["away"])):
            continue
        if (common._int(score.get("home")), common._int(score.get("away"))) != (fx["hg"], fx["ag"]):
            continue
        # The shared real-stat validator needs the *observed* clock/score,
        # not only team IDs. Omitting them raises KeyError and blocks fallback.
        found.append({"fixture_id":fixtureid, "home_id":homeid, "away_id":awayid,
                      "minute":minute, "hg":fx["hg"], "ag":fx["ag"]})
    return found[0] if len(found) == 1 else None


def verified_stats(rows: list[dict], candidate: dict) -> dict | None:
    """Only numeric stats supplied under the actual provider team IDs."""
    expected = {str(candidate["home_id"]), str(candidate["away_id"])}
    if len(rows) != 2 or {str((r.get("team") or {}).get("id")) for r in rows} != expected:
        return None
    metrics = match_metrics(rows, candidate)
    if metrics is None:
        return None
    output = {}
    for row in rows:
        tid = str(row["team"]["id"])
        side = "home" if tid == str(candidate["home_id"]) else "away"
        statdict = {re.sub(r"[^a-z0-9]", "", str(x.get("type") or "").lower()):
                    common._int(x.get("value")) for x in (row.get("statistics") or [])
                    if isinstance(x,dict)}
        shots = statdict.get("totalshots")
        sot = statdict.get("shotsongoal")
        if sot is None or shots is None or sot > shots:
            return None
        output[side] = {"shots": shots, "sot": sot}
        corners = statdict.get("cornerkicks")
        if corners is not None:
            output[side]["corners"] = corners
    if output["home"]["shots"] + output["away"]["shots"] != metrics["shots"]:
        return None
    if output["home"]["sot"] + output["away"]["sot"] != metrics["sot"]:
        return None
    metrics["teams"] = output
    return metrics


def recover(fx: dict) -> dict | None:
    """Spend at most two requests per permitted attempt, never on missing keys."""
    key = configured_key()
    if not key:
        return None
    if not reserve_source_calls("api_football", count=RESERVED_CALLS_PER_ATTEMPT,
                                max_per_day=24, cooldown_seconds=3600):
        return None
    try:
        events, remaining = _query("/fixtures", {"live": "all"}, key)
        if remaining is not None and remaining < MIN_REMAINING_REQUESTS:
            print("LMG_API_FOOTBALL_QUOTA_RESERVE", remaining, flush=True)
            return None
        candidate = unique_live_match(fx, events)
        if candidate is None:
            return None
        rows, _ = _query("/fixtures/statistics",
                         {"fixture":candidate["fixture_id"]}, key)
        metrics = verified_stats(rows, candidate)
        if metrics:
            print("LMG_API_FOOTBALL_LIVE_STATS_VERIFIED",
                  fx["fixture_id"], candidate["fixture_id"], fx["minute"], flush=True)
        return metrics
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        # A source failure is never permission to send an unverified tip.
        print("LMG_API_FOOTBALL_UNAVAILABLE", type(exc).__name__, flush=True)
        return None
