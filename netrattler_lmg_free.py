#!/usr/bin/env python3
"""Free ESPN live-score and match-stats scan; optional observed PulseScore live quotes.
This does NOT call API-Football or invent goal percentages, xG, odds or events.
No Telegram/Supabase side-effects unless LMG_SEND=true and a real price exists.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import re
import sys
import unicodedata
import requests

from netrattler_last_minute_goal import match_metrics, market_targets, reserve, send, delivered

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
PULSE = "https://api.pulsescore.net/api/v3/bet365/live-events"


def _get(url, *, params=None, headers=None):
    response = requests.get(url, params=params, headers=headers or {"Accept": "application/json"}, timeout=18)
    response.raise_for_status()
    return response.json()


def _int(v):
    if isinstance(v, bool) or not re.fullmatch(r"\d+(?:\.0+)?", str(v or "")):
        return None
    try:
        return int(float(v))
    except (ValueError, OverflowError):
        return None


def _date(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except (ValueError, TypeError):
        return None


def fixtures_from_espn(payload):
    out = []
    for e in (payload or {}).get("events") or []:
        try:
            st = e.get("status") or {}
            if (st.get("type") or {}).get("state") != "in" or _int(st.get("period")) != 2:
                continue
            mt = re.match(r"^(\d{1,2})(?::\d{2})?", str(st.get("displayClock") or ""))
            minute = int(mt.group(1)) if mt else -1
            if not 55 <= minute <= 88:
                continue
            comp = (e.get("competitions") or [])[0]
            sides = {x.get("homeAway"): x for x in comp.get("competitors") or []}
            h, a = sides["home"], sides["away"]
            hg, ag = _int(h.get("score")), _int(a.get("score"))
            ht, at = h.get("team") or {}, a.get("team") or {}
            kickoff, event_id = _date(e.get("date")), _int(e.get("id"))
            if (hg is None or ag is None or hg + ag > 5 or not ht.get("id") or not at.get("id")
                    or not ht.get("displayName") or not at.get("displayName") or not kickoff
                    or event_id is None):
                continue
            lg = e.get("league") or comp.get("league") or {}
            all_lg = payload.get("leagues") or []
            league = lg.get("name") or (all_lg[0].get("name") if len(all_lg) == 1 else "")
            out.append({"fixture_id": event_id, "minute": minute, "home": ht["displayName"],
                        "away": at["displayName"], "home_id": str(ht["id"]), "away_id": str(at["id"]),
                        "hg": hg, "ag": ag, "kickoff": kickoff, "league": league,
                        "slug": lg.get("slug") or "all"})
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            continue
    return out


def metrics_from_espn(summary, fixture):
    rows = []
    aliases = {"Shots on Goal": ("shotsontarget", "shotsongoal"),
               "Total Shots": ("totalshots", "shots"),
               "Corner Kicks": ("cornerkicks", "corners"),
               "Red Cards": ("redcards", "redcard")}
    for row in ((summary or {}).get("boxscore") or {}).get("teams") or []:
        team = row.get("team") or {}
        tid = str(team.get("id") or "")
        if tid not in {fixture["home_id"], fixture["away_id"]}:
            continue
        fields = {}
        for stat in row.get("statistics") or []:
            name = str(stat.get("name") or "").strip().lower()
            value = _int(stat.get("value"))
            if value is None:
                value = _int(stat.get("displayValue"))
            if value is not None:
                fields[name] = value
        parsed = []
        for label, keys in aliases.items():
            for key in keys:
                if key in fields:
                    parsed.append({"type": label, "value": fields[key]})
                    break
        rows.append({"team": {"id": tid}, "statistics": parsed})
    return match_metrics(rows, fixture)


def _norm(name):
    normalized = unicodedata.normalize("NFKD", str(name or "").casefold())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in normalized if not unicodedata.combining(c)))


def pulse_prices(events, fixture, now=None):
    """Only accept one exact, contemporaneous live match and full-time overs."""
    now = now or dt.datetime.now(dt.timezone.utc)
    matches = []
    for e in events if isinstance(events, list) else []:
        kickoff = _date(e.get("startTime"))
        if (e.get("live") is True and _norm(e.get("home")) == _norm(fixture["home"])
                and _norm(e.get("away")) == _norm(fixture["away"]) and kickoff
                and abs((kickoff-fixture["kickoff"]).total_seconds()) <= 1200
                and 0 <= (now-kickoff).total_seconds() <= 130*60):
            matches.append(e)
    if len(matches) != 1:
        return {}
    primary, secondary = market_targets(fixture)
    prices = {}
    for line in (primary, secondary):
        values = []
        for m in matches[0].get("markets") or []:
            try:
                market_line = float(m.get("line"))
            except (TypeError, ValueError):
                continue
            if m.get("canonicalMarket") != "total_goals" or m.get("period") != "fulltime" or market_line != line:
                continue
            for sel in m.get("selections") or []:
                if str(sel.get("name") or "").casefold().strip() != f"over {line:.1f}":
                    continue
                try:
                    odd = float(sel.get("decimal"))
                except (TypeError, ValueError):
                    continue
                if 1.30 <= odd <= 30.0:
                    values.append(round(odd, 3))
        if len(values) == 1:
            prices[line] = values[0]
    return prices


def main():
    send_enabled = os.getenv("LMG_SEND", "false").casefold() in {"1", "true", "yes"}
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    board = _get(f"{ESPN}/all/scoreboard", params={"dates": day, "limit": "1000"})
    fixtures = fixtures_from_espn(board)
    fixtures.sort(key=lambda f: (abs(f["minute"]-65), f["fixture_id"]))
    result = {"live_candidates": len(fixtures), "stats_checked": 0, "odds_calls": 0,
              "qualified": 0, "sent": 0, "send_enabled": send_enabled}
    key = os.getenv("PULSESCORE_API_KEY", "").strip()
    feed = None
    for fx in fixtures[:4]:
        try:
            summary = _get(f"{ESPN}/{fx['slug']}/summary", params={"event": str(fx["fixture_id"])})
        except requests.HTTPError as exc:
            # Respect denied or unavailable data instead of evading access controls.
            print("LMG_SUMMARY_UNAVAILABLE", str(exc).splitlines()[0][:160])
            continue
        result["stats_checked"] += 1
        metrics = metrics_from_espn(summary, fx)
        if not metrics:
            continue
        if not key:
            print("LMG_PRESSURE_ONLY", json.dumps({"fixture": fx["fixture_id"], "stats": metrics}))
            continue
        if feed is None:  # One REST call at most per run (free plan: 500/month).
            feed = _get(PULSE, params={"sport": "soccer"},
                        headers={"X-Secret": key, "Accept": "application/json"})
            result["odds_calls"] += 1
        prices = pulse_prices(feed, fx)
        primary = market_targets(fx)[0]
        if primary not in prices:
            continue
        result["qualified"] += 1
        print("LMG_REAL_ODDS", json.dumps({"fixture": fx["fixture_id"], "line": primary,
                                           "price": prices[primary], "stats": metrics}))
        if send_enabled:
            alert = reserve(fx, prices[primary])
            if alert:
                message_id = send(fx, metrics, prices)
                delivered(alert, message_id)
                result["sent"] += 1
    print("LMG_FREE_SUMMARY", json.dumps(result))
    return result


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, requests.RequestException) as e:
        print("LMG_FREE_FAIL_CLOSED", str(e).splitlines()[0], file=sys.stderr)
        raise SystemExit(1)
