#!/usr/bin/env python3
"""NETRATTLER keyless Goal Hunter: reliable FotMob live fixtures + exact full-match stats.

Signals start at minute 65. One more goal in the remaining match time (Over 0.5),
with no betting odds or made-up percentages. No sends in dry-run.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import requests

import netrattler_lmg_free as common

DAILY="https://www.fotmob.com/api/data/matches"
DETAIL="https://www.fotmob.com/api/data/matchDetails"
MAX_EVENTS=16


def _score(match):
    home, away=(match.get("home") or {}), (match.get("away") or {})
    hg, ag=common._int(home.get("score")),common._int(away.get("score"))
    raw=str((match.get("status") or {}).get("scoreStr") or "")
    m=re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*",raw)
    if m:
        observed=(int(m.group(1)),int(m.group(2)))
        if hg is not None and ag is not None and (hg,ag)!=observed:
            return None
        return (hg,ag) if hg is not None and ag is not None else observed
    return (hg,ag) if hg is not None and ag is not None else None


def fixtures_from_fotmob(payload):
    out=[]
    for league in (payload or {}).get("leagues") or []:
        for match in league.get("matches") or []:
            status=match.get("status") or {}
            live_time=status.get("liveTime") or {}
            halves=status.get("halfs") or {}
            if (status.get("ongoing") is not True or status.get("finished") is True
                    or status.get("cancelled") is True or status.get("started") is not True):
                continue
            # Never infer second half from elapsed wall clock alone.
            if not halves.get("secondHalfStarted") and common._int(live_time.get("basePeriod")) != 90:
                continue
            clock=str(live_time.get("short") or "")
            m=re.search(r"(\d{1,3})",clock)
            minute=int(m.group(1)) if m else -1
            if not common.MIN_MINUTE <= minute <= common.MAX_MINUTE:
                continue
            score=_score(match)
            if score is None:
                continue
            home, away=match.get("home") or {},match.get("away") or {}
            eid=common._int(match.get("id"))
            kickoff=common._date(status.get("utcTime"))
            if (eid is None or kickoff is None or not home.get("name") or not away.get("name")):
                continue
            out.append({"source":"fotmob", "fixture_id":eid, "minute":minute,
                        "clock":str(minute)+"'", "home":str(home["name"]),
                        "away":str(away["name"]), "home_id":"1", "away_id":"2",
                        "hg":score[0], "ag":score[1], "kickoff":kickoff,
                        "league":str(league.get("name") or "")})
    return out


def _key(label):
    return re.sub(r"[^a-z0-9]","",str(label or "").lower())


def _intvalue(value):
    if isinstance(value,dict):
        return common._int(value.get("value"))
    return common._int(value)


def metrics_from_fotmob(detail,fixture):
    content=(detail or {}).get("content") or {}
    stats=content.get("stats") or {}
    periods=stats.get("Periods") or {} if isinstance(stats,dict) else {}
    if not isinstance(periods,dict) or "All" not in periods:
        return None
    found={}
    stack=[periods["All"]]
    aliases={"totalshots":"Total Shots", "shotsontarget":"Shots on Goal",
             "shotsongoal":"Shots on Goal", "corners":"Corner Kicks",
             "cornerkicks":"Corner Kicks", "redcards":"Red Cards"}
    while stack:
        node=stack.pop()
        if isinstance(node,list):
            stack.extend(node)
        elif isinstance(node,dict):
            label=aliases.get(_key(node.get("key"))) or aliases.get(_key(node.get("title")))
            values=node.get("stats")
            if label and isinstance(values,list) and len(values)==2:
                pair=tuple(_intvalue(v) for v in values)
                if all(v is not None for v in pair):
                    if label in found and found[label]!=pair:
                        return None  # incompatible copies: fail closed
                    found[label]=pair
            stack.extend(node.values())
    rows=[{"team":{"id":side}, "statistics":[{"type":label,"value":pair[i]}
          for label,pair in found.items()]} for i,side in enumerate(("1","2"))]
    return common.match_metrics(rows,fixture)


def fetch_fotmob(day):
    # Public feed only; respect 403/429, never bypass access restrictions.
    try:
        return common._get(DAILY,params={"date":day})
    except requests.HTTPError as exc:
        if getattr(exc.response,"status_code",0)!=404:
            raise
    return common._get("https://www.fotmob.com/api/matches",params={"date":day})


def run():
    send_enabled=(os.getenv("LMG_SEND") or "false").lower() in ("1","yes","true")
    day=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    try:
        feed=fetch_fotmob(day)
    except requests.RequestException as exc:
        print("LMG_FOTMOB_UNAVAILABLE",str(exc)[:140],flush=True)
        return common.main()  # only if primary free feed unavailable
    fixtures=fixtures_from_fotmob(feed)
    if not fixtures:
        print("LMG_FOTMOB_NO_LATE_MATCHES_ESPN_BACKUP",flush=True)
        return common.main()
    fixtures.sort(key=lambda x:(x["minute"],x["fixture_id"]))
    report={"source":"fotmob","live_candidates":len(fixtures),"stats_checked":0,
            "missing_stats":0,"tier_rejected":0,"qualified":0,"sent":0,"odds_calls":0,
            "send_enabled":send_enabled}
    for fx in fixtures[:MAX_EVENTS]:
        try:
            detail=common._get(DETAIL,params={"matchId":fx["fixture_id"]})
        except requests.HTTPError as exc:
            if getattr(exc.response,"status_code",0)==404:
                try:
                    detail=common._get("https://www.fotmob.com/api/matchDetails",
                                       params={"matchId":fx["fixture_id"]})
                except requests.RequestException:
                    report["missing_stats"]+=1
                    continue
            else:
                report["missing_stats"]+=1
                continue
        except requests.RequestException:
            report["missing_stats"]+=1
            continue
        report["stats_checked"]+=1
        metrics=metrics_from_fotmob(detail,fx)
        if not metrics:
            report["missing_stats"]+=1
            continue
        tier=common.select_goal_tier(fx,metrics)
        if tier is None:
            report["tier_rejected"]+=1
            continue
        metrics["tier"]=tier
        report["qualified"]+=1
        print("LMG_FOTMOB_SIGNAL",json.dumps({
            "fixture":fx["fixture_id"],"minute":fx["minute"],
            "score":[fx["hg"],fx["ag"]],"target":"one_more_goal",
            "stats":metrics},ensure_ascii=False),flush=True)
        if send_enabled:
            key=common.reserve_alert(fx)
            if key:
                message_id=common.send_alert(fx,metrics)
                common.mark_sent(key,message_id)
                report["sent"]+=1
    print("LMG_FOTMOB_SUMMARY",json.dumps(report),flush=True)
    return report


if __name__=="__main__":
    try:
        run()
    except (requests.RequestException,RuntimeError,ValueError) as exc:
        print("LMG_FOTMOB_FAIL_CLOSED",str(exc).splitlines()[0][:180],file=sys.stderr)
        raise SystemExit(1)
