#!/usr/bin/env python3
"""Goal Hunter two-stage public live feed: discover -> bounded detail polling.

The production event identity is FotMob's numeric fixture_id, unique + exact.
No live odds, synthetic xG, momentum proxies, or fabricated shots. No Supabase
writes: user-approved Goal Hunter source of truth remains the GitHub SQLite
state branch. A read-only/dry-run scan has no Telegram side effects.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import re
import time

import requests

import netrattler_lmg_free as common
import netrattler_lmg_fotmob as fotmob
from netrattler_lmg_shadow import build_snapshot, write_snapshots

MIN_DISCOVERY_MINUTE = 60
MAX_DISCOVERY_MINUTE = 85
MAX_DEEP_EVENTS = 6
POLL_SECONDS = 75
POLL_CYCLES = 3  # t=0,75,150 seconds; next GitHub cron refreshes discovery
TARGET_LEAGUES_ENV = "LMG_TARGET_LEAGUES"


def discover(feed: dict, *, league_filter: tuple[str, ...] = ()) -> list[dict]:
    """Read one lightweight day feed. Never poll every live game's details."""
    seen: set[int] = set()
    result: list[dict] = []
    accepted = {x.casefold().strip() for x in league_filter if x.strip()}
    for league in (feed or {}).get("leagues") or []:
        name = str(league.get("name") or "").strip()
        if accepted and name.casefold() not in accepted:
            continue
        for match in league.get("matches") or []:
            status = match.get("status") or {}
            live = status.get("liveTime") or {}
            half = status.get("halfs") or {}
            if (status.get("ongoing") is not True or status.get("started") is not True
                    or status.get("finished") is True or status.get("cancelled") is True):
                continue
            if not half.get("secondHalfStarted") and common._int(live.get("basePeriod")) != 90:
                continue
            clock = re.search(r"(\d{1,3})", str(live.get("short") or ""))
            minute = int(clock.group(1)) if clock else -1
            if not MIN_DISCOVERY_MINUTE <= minute <= MAX_DISCOVERY_MINUTE:
                continue
            score = fotmob._score(match)
            if score is None or abs(score[0] - score[1]) > 3:
                continue
            # At minute 60-64 only a 0:0 is added for early watch;
            # it cannot trigger a tip before the strict 65th-minute gate.
            if minute < common.MIN_MINUTE and score != (0, 0):
                continue
            event_id = common._int(match.get("id"))
            kickoff = common._date(status.get("utcTime"))
            home, away = match.get("home") or {}, match.get("away") or {}
            if (not event_id or event_id in seen or kickoff is None
                    or not home.get("name") or not away.get("name")):
                continue
            seen.add(event_id)
            result.append({
                "source":"fotmob", "fixture_id":event_id, "minute":minute,
                "clock":f"{minute}'", "home":str(home["name"]),
                "away":str(away["name"]), "home_id":"1", "away_id":"2",
                "home_logo_id":common._int(home.get("id")),
                "away_logo_id":common._int(away.get("id")),
                "hg":score[0], "ag":score[1],
                "kickoff":kickoff, "league":name,
            })
    # Prioritize live qualifying minute (65+) over early watch, then 0:0.
    result.sort(key=lambda r:(r["minute"] < common.MIN_MINUTE,
                              r["hg"]+r["ag"] != 0,
                              abs(75-r["minute"]),r["fixture_id"]))
    return result[:MAX_DEEP_EVENTS]


def poll_once(candidates: list[dict], *, first_pass: bool, send: bool,
              shadow: bool, observations: list[dict] | None = None,
              fetch=fotmob.common._get) -> dict:
    report={"candidates":len(candidates),"detail_requests":0,"stats_verified":0,
            "missing_stats":0,"qualified":0,"sent":0,"already_alerted":0,
            "snapshots":0,"errors":0}
    snapshots=[]
    for fx in candidates:
        try:
            detail=fetch(fotmob.DETAIL, params={"matchId":fx["fixture_id"]})
            report["detail_requests"]+=1
            metrics=fotmob.metrics_from_fotmob(detail,fx)
        except (requests.RequestException,TypeError,ValueError,KeyError):
            report["errors"]+=1
            continue
        if metrics is None:
            report["missing_stats"]+=1
        else:
            report["stats_verified"]+=1
            if observations is not None:
                teams=metrics.get("teams") or {}
                home,away=teams.get("home") or {},teams.get("away") or {}
                observations.append({
                    "provider":"fotmob","fixture_id":fx["fixture_id"],
                    "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                    "discovery_minute":fx["minute"],
                    "shots":metrics.get("shots"),"shots_on_target":metrics.get("sot"),
                    "corners":metrics.get("corners"),
                    "home_xg":home.get("xg"),"away_xg":away.get("xg"),
                })
        # Historical evidence only: never post from a stale minute/score on
        # later polls without refreshing the discovery feed.
        eligible=common.MIN_MINUTE <= fx["minute"] <= common.MAX_MINUTE
        if shadow and eligible and first_pass:
            try:
                snapshots.append(build_snapshot(fx,metrics,
                                "fotmob" if metrics else None))
            except (ValueError,TypeError):
                report["errors"]+=1
        if not (first_pass and send and eligible and metrics):
            continue
        tier=common.select_goal_tier(fx,metrics)
        if tier is None:
            continue
        report["qualified"]+=1
        metrics["tier"]=tier
        metrics["next_goal_side"]=common.select_next_goal(metrics)
        key=common.reserve_alert(fx,metrics)  # durable Git SQLite reservation
        if key is None:
            report["already_alerted"]+=1
            continue
        message_id=common.send_alert(fx,metrics)
        common.mark_sent(key,message_id)
        report["sent"]+=1
    if shadow and snapshots:
        saved=write_snapshots(snapshots,enabled=True)
        report["snapshots"]=saved.get("inserted",0)
        report["snapshot_status"]=saved.get("status")
    return report


def run(*, feed=None, cycles=None, sleep=time.sleep, fetch=fotmob.common._get) -> dict:
    """One discovery per run, at most 3 detail rounds spaced 75 seconds."""
    is_send=os.getenv("LMG_SEND","false").lower() == "true"
    is_shadow=os.getenv("LMG_SHADOW_ENABLED","false").lower() == "true"
    leagues=tuple(x.strip() for x in os.getenv(TARGET_LEAGUES_ENV,"").split(",")
                  if x.strip())
    if feed is None:
        day=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        feed=fotmob.fetch_fotmob(day)
    candidates=discover(feed,league_filter=leagues)
    # SportScore is an additional independent discovery cross-check only.
    # Never promote score-only matches into a Goal Hunter tip: the API may not
    # contain a verified live minute or UTC kickoff. No Telegram reuse.
    external_audit=None
    if os.getenv("LMG_SOURCE_SPORTSCORE_READ_ONLY")=="true":
        from netrattler_lmg_external_sources import probe_external
        env={"LMG_EXTERNAL_SOURCES_SHADOW":"true",
             "LMG_SOURCE_SPORTSCORE_READ_ONLY":"true"}
        external_audit=probe_external(day=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
                                     primary=candidates,env=env)
    count=cycles if cycles is not None else int(os.getenv("LMG_DEEP_POLL_CYCLES",str(POLL_CYCLES)))
    if type(count) is not int or not 1 <= count <= POLL_CYCLES:
        raise ValueError("invalid_bounded_poll_cycles")
    reports=[]
    observations=[]
    if not candidates:
        report={"discovered":0,"poll_cycles":0,"sent":0,"reason":"no_eligible_live_candidates"}
        if external_audit is not None:
            report["external_source_audit"]=external_audit
        print("LMG_TWO_STAGE_SUMMARY",json.dumps(report),flush=True)
        return report
    for i in range(count):
        if i:
            sleep(POLL_SECONDS)
        round_report=poll_once(candidates,first_pass=i==0,send=is_send,
                               shadow=is_shadow,observations=observations if is_shadow else None,
                               fetch=fetch)
        round_report["pass"]=i+1
        reports.append(round_report)
        print("LMG_DEEP_POLL",json.dumps(round_report),flush=True)
    deep_saved={"inserted":0,"status":"disabled"}
    if is_shadow and observations:
        from netrattler_lmg_store import write_deep_observations
        deep_saved=write_deep_observations(observations)
    result={"discovered":len(candidates),"poll_cycles":len(reports),
            "details":sum(x["detail_requests"] for x in reports),
            "sent":sum(x["sent"] for x in reports),
            "snapshots":sum(x["snapshots"] for x in reports),
            "deep_observations_saved":deep_saved["inserted"],
            "external_source_audit":external_audit,
            "reason":"sent" if any(x["sent"] for x in reports) else
              "no_verified_qualifying_signal",
            "backend":"sqlite_git"}
    print("LMG_TWO_STAGE_SUMMARY",json.dumps(result),flush=True)
    return result


if __name__=="__main__":
    run()
