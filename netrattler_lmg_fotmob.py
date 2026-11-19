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
import unicodedata

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
                        "home_logo_id":common._int(home.get("id")),
                        "away_logo_id":common._int(away.get("id")),
                        "hg":score[0], "ag":score[1], "kickoff":kickoff,
                        "league":str(league.get("name") or "")})
    return out


def _key(label):
    return re.sub(r"[^a-z0-9]","",str(label or "").lower())


def _floatvalue(value):
    if isinstance(value,dict):
        value=value.get("value")
    if value is None or isinstance(value,bool):
        return None
    raw=str(value).strip().replace(",",".")
    if not re.fullmatch(r"\d+(?:\.\d+)?",raw):
        return None
    number=float(raw)
    return number if 0<=number<=20 else None


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
    xg=None
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
            if _key(node.get("key")) in ("expectedgoals","xg") or _key(node.get("title")) in ("expectedgoals","xg"):
                if isinstance(values,list) and len(values)==2:
                    pair=tuple(_floatvalue(v) for v in values)
                    if all(v is not None for v in pair):
                        if xg is not None and xg!=pair:
                            return None
                        xg=pair
            if label and isinstance(values,list) and len(values)==2:
                pair=tuple(_intvalue(v) for v in values)
                if all(v is not None for v in pair):
                    if label in found and found[label]!=pair:
                        return None  # incompatible copies: fail closed
                    found[label]=pair
            stack.extend(node.values())
    rows=[{"team":{"id":side}, "statistics":[{"type":label,"value":pair[i]}
          for label,pair in found.items()]} for i,side in enumerate(("1","2"))]
    metrics=common.match_metrics(rows,fixture)
    if metrics is None:
        return None
    metrics["teams"]={
        "home":{**{key:found[label][0] for key,label in (("shots","Total Shots"),("sot","Shots on Goal"),("corners","Corner Kicks")) if label in found},
                **({"xg":xg[0]} if xg is not None else {})},
        "away":{**{key:found[label][1] for key,label in (("shots","Total Shots"),("sot","Shots on Goal"),("corners","Corner Kicks")) if label in found},
                **({"xg":xg[1]} if xg is not None else {})},
    }
    return metrics


def _club_name(name):
    # Conservative comparison: do not pair matches based only on fuzzy team names.
    ascii_name=unicodedata.normalize("NFKD",str(name)).encode("ascii","ignore").decode()
    words=re.findall(r"[a-z0-9]+",ascii_name.casefold())
    return " ".join(w for w in words if w not in ("fc","afc","cf","sc","fk"))


def recover_espn_metrics(fx,board):
    """Use ESPN stats ONLY for the exact live FotMob fixture, retaining its ID.

    Guard against wrong opponents, stale scores, wrong date and ambiguous fixtures.
    FotMob remains authoritative for fixture ID and post-match settlement.
    """
    matches=[]
    for candidate in common.fixtures_from_espn(board):
        if (_club_name(candidate["home"])!=_club_name(fx["home"])
                or _club_name(candidate["away"])!=_club_name(fx["away"])):
            continue
        if abs((candidate["kickoff"]-fx["kickoff"]).total_seconds())>900:
            continue
        if (candidate["hg"],candidate["ag"])!=(fx["hg"],fx["ag"]):
            continue
        if abs(candidate["minute"]-fx["minute"])>5:
            continue
        matches.append(candidate)
    if len(matches)!=1:
        return None
    candidate=matches[0]
    try:
        summary=common._get(f"{common.ESPN}/{candidate['slug']}/summary",
                            params={"event":str(candidate["fixture_id"])})
    except requests.RequestException:
        return None
    return common.metrics_from_espn(summary,candidate)


def coverage_diagnostics(feed):
    """Count real live periods to distinguish no matches from missing data."""
    total=0
    live=0
    early=0
    in_window=0
    late=0
    unknown=0
    for league in (feed or {}).get("leagues") or []:
        for match in league.get("matches") or []:
            total+=1
            status=match.get("status") or {}
            if status.get("ongoing") is not True:
                continue
            live+=1
            raw=str((status.get("liveTime") or {}).get("short") or "")
            found=re.search(r"(\d{1,3})",raw)
            if not found:
                unknown+=1
                continue
            minute=int(found.group(1))
            if minute < common.MIN_MINUTE:
                early+=1
            elif minute > common.MAX_MINUTE:
                late+=1
            else:
                in_window+=1
    result={"fixtures":total,"live":live,"before_65":early,
            "minute_65_85":in_window,"after_85":late,
            "no_clock":unknown}
    print("LMG_FEED_COVERAGE",json.dumps(result),flush=True)
    return result


def fetch_fotmob(day):
    # Public feed only; respect 403/429, never bypass access restrictions.
    try:
        return common._get(DAILY,params={"date":day})
    except requests.HTTPError as exc:
        if getattr(exc.response,"status_code",0)!=404:
            raise
    return common._get("https://www.fotmob.com/api/matches",params={"date":day})


def _espn_fallback(reason):
    """Record why the primary live source produced no Goal Hunter alert."""
    result=common.main()
    if isinstance(result,dict):
        print("LMG_SCAN_REASON",json.dumps({
            "source":"espn_backup","reason":reason,
            "live_candidates":result.get("live_candidates"),
            "qualified":result.get("qualified"),"sent":result.get("sent")
        },ensure_ascii=False),flush=True)
    return result


def run():
    send_enabled=(os.getenv("LMG_SEND") or "false").lower() in ("1","yes","true")
    day=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    try:
        feed=fetch_fotmob(day)
    except requests.RequestException as exc:
        print("LMG_FOTMOB_UNAVAILABLE",str(exc)[:140],flush=True)
        return _espn_fallback("fotmob_feed_unavailable")  # one safe independent backup
    coverage_diagnostics(feed)
    fixtures=fixtures_from_fotmob(feed)
    if not fixtures:
        print("LMG_FOTMOB_NO_LATE_MATCHES_ESPN_BACKUP",flush=True)
        return _espn_fallback("fotmob_no_65_85_matches")
    fixtures.sort(key=lambda x:(x["minute"],x["fixture_id"]))
    report={"source":"fotmob","live_candidates":len(fixtures),"stats_checked":0,
            "missing_stats":0,"detail_errors":0,"espn_recovered":0,
            "api_football_checked":0,"api_football_recovered":0,
            "tier_rejected":0,"qualified":0,"sent":0,"already_alerted":0,"odds_calls":0,
            "send_enabled":send_enabled}
    espn_board=None
    espn_board_loaded=False
    api_fallback_checked=False
    shadow_enabled=os.getenv("LMG_SHADOW_ENABLED","false").lower()=="true"
    shadow_batch=[]
    for fx in fixtures[:MAX_EVENTS]:
        detail=None
        try:
            detail=common._get(DETAIL,params={"matchId":fx["fixture_id"]})
        except requests.RequestException:
            report["detail_errors"]+=1
        metrics=None
        data_provider=None
        if detail is not None:
            report["stats_checked"]+=1
            metrics=metrics_from_fotmob(detail,fx)
            if metrics:
                data_provider="fotmob"
        if not metrics:
            if detail is not None:
                content=(detail or {}).get("content") or {}
                stats=content.get("stats") or {}
                periods=(stats.get("Periods") or {}) if isinstance(stats,dict) else {}
                shotmap=content.get("shotmap")
                sample=(shotmap[:2] if isinstance(shotmap,list)
                        else (str(shotmap)[:500] if shotmap is not None else None))
                print("LMG_DETAIL_MISSING_STATS",json.dumps({
                    "fixture":fx["fixture_id"],"minute":fx["minute"],
                    "home":fx["home"],"away":fx["away"],
                    "detail_keys":list(content)[:15],
                    "stats_periods":list(periods)[:8] if isinstance(periods,dict) else [],
                    "shotmap_type":type(shotmap).__name__,
                    "shotmap_sample":str(sample)[:600],
                    "liveticker_type":type(content.get("liveticker")).__name__
                },ensure_ascii=False),flush=True)
            # Prefer recovery of THIS SAME FotMob fixture, not an unrelated
            # ESPN fixture whose final result could not be settled by FotMob.
            if not espn_board_loaded:
                espn_board_loaded=True
                try:
                    espn_board=common._get(f"{common.ESPN}/all/scoreboard",
                        params={"dates":day,"limit":"1000"})
                except requests.RequestException as exc:
                    print("LMG_ESPN_STATS_BACKUP_UNAVAILABLE",
                          str(exc).splitlines()[0][:120],flush=True)
            if espn_board is not None:
                metrics=recover_espn_metrics(fx,espn_board)
                if metrics:
                    data_provider="espn"
                    report["espn_recovered"]+=1
                    print("LMG_FOTMOB_ESPN_STATS_RECOVERED",
                          fx["fixture_id"],fx["minute"],flush=True)
        # Free-plan quota is conserved: at most one additional API-Football
        # recovery attempt per scanner run, and only for a real unverified match.
        # In dry-run/smoke mode never use the optional credential or paid quota.
        if not metrics and send_enabled and not api_fallback_checked:
            from netrattler_lmg_api_fallback import configured_key, recover
            if configured_key():
                api_fallback_checked=True
                report["api_football_checked"]+=1
                metrics=recover(fx)
                if metrics:
                    data_provider="api_football"
                    report["api_football_recovered"]+=1
        if shadow_enabled:
            # Side-channel evidence only; no extra Telegram messages and no
            # changes to selection/settlement when the shadow DB is unavailable.
            from netrattler_lmg_shadow import build_snapshot
            try:
                shadow_batch.append(build_snapshot(fx,metrics,data_provider))
            except (ValueError,TypeError) as exc:
                print("LMG_SHADOW_BAD_SNAPSHOT",str(exc)[:100],flush=True)
        if not metrics:
            report["missing_stats"]+=1
            continue
        tier=common.select_goal_tier(fx,metrics)
        if tier is None:
            report["tier_rejected"]+=1
            continue
        metrics["tier"]=tier
        metrics["next_goal_side"]=common.select_next_goal(metrics)
        report["qualified"]+=1
        print("LMG_FOTMOB_SIGNAL",json.dumps({
            "fixture":fx["fixture_id"],"minute":fx["minute"],
            "score":[fx["hg"],fx["ag"]],"target":"one_more_goal",
            "stats":metrics},ensure_ascii=False),flush=True)
        if send_enabled:
            key=common.reserve_alert(fx,metrics)
            if key:
                message_id=common.send_alert(fx,metrics)
                common.mark_sent(key,message_id)
                report["sent"]+=1
            else:
                report["already_alerted"]+=1
    if shadow_enabled:
        from netrattler_lmg_shadow import write_snapshots
        try:
            shadow_report=write_snapshots(shadow_batch,enabled=True)
            print("LMG_SHADOW_CAPTURE",json.dumps(shadow_report),flush=True)
        except (requests.RequestException,RuntimeError,ValueError,TypeError) as exc:
            print("LMG_SHADOW_CAPTURE_UNAVAILABLE",
                  type(exc).__name__,str(exc)[:100],flush=True)
    if report["sent"]:
        reason="sent"
    elif not send_enabled:
        reason="dry_run"
    elif report["qualified"] and report["already_alerted"] == report["qualified"]:
        reason="already_alerted"
    elif report["qualified"]:
        reason="qualified_but_no_confirmed_send"
    elif report["missing_stats"]:
        reason="missing_verified_live_stats"
    elif report["tier_rejected"]:
        reason="below_signal_threshold"
    else:
        reason="no_qualified_live_candidates"
    report["no_tip_reason"]=reason
    print("LMG_SCAN_REASON",json.dumps({"source":"fotmob",**report},ensure_ascii=False),flush=True)
    print("LMG_FOTMOB_SUMMARY",json.dumps(report),flush=True)
    return report


if __name__=="__main__":
    try:
        run()
    except (requests.RequestException,RuntimeError,ValueError) as exc:
        print("LMG_FOTMOB_FAIL_CLOSED",str(exc).splitlines()[0][:180],file=sys.stderr)
        raise SystemExit(1)
