#!/usr/bin/env python3
"""NETRATTLER Goal Hunter: ESPN live data, only a further 0.5 goal from minute 65.

No API-Football, bookmaker odds, fabricated percentages or second goal lines.
One Telegram alert per verified fixture. Fail closed on missing statistics.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import requests

from netrattler_last_minute_goal import match_metrics
from netrattler_lmg_next_goal import select_next_goal

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
MIN_MINUTE = 65
MAX_FIXTURES_PER_RUN = 16
MAX_MINUTE = 85


def _get(url, *, params=None):
    response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=18)
    response.raise_for_status()
    return response.json()


def _int(value):
    if value is None or isinstance(value, bool):
        return None
    string = str(value).strip()
    if not re.fullmatch(r"\d+(?:\.0+)?", string):
        return None
    try:
        return int(float(string))
    except (ValueError, OverflowError):
        return None


def _date(value):
    try:
        date = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date.astimezone(dt.timezone.utc) if date.tzinfo else None
    except (TypeError, ValueError):
        return None


def fixtures_from_espn(payload):
    out = []
    for event in (payload or {}).get("events") or []:
        try:
            status = event.get("status") or {}
            kind = status.get("type") or {}
            if kind.get("state") != "in" or _int(status.get("period")) != 2:
                continue
            clock = str(status.get("displayClock") or "").strip()
            matched = re.match(r"^(\d{1,3})(?:[:+']|$)", clock)
            minute = int(matched.group(1)) if matched else -1
            if minute < MIN_MINUTE or minute > MAX_MINUTE:
                continue
            competition = (event.get("competitions") or [])[0]
            participants = {x.get("homeAway"): x for x in competition.get("competitors") or []}
            home_row, away_row = participants["home"], participants["away"]
            home_goals, away_goals = _int(home_row.get("score")), _int(away_row.get("score"))
            home, away = home_row.get("team") or {}, away_row.get("team") or {}
            kickoff, event_id = _date(event.get("date")), _int(event.get("id"))
            if (home_goals is None or away_goals is None or kickoff is None or event_id is None
                    or not home.get("id") or not away.get("id")
                    or not home.get("displayName") or not away.get("displayName")):
                continue
            league = event.get("league") or competition.get("league") or {}
            leagues = payload.get("leagues") or []
            league_name = league.get("name") or (leagues[0].get("name") if len(leagues) == 1 else "")
            # Use the provider's competition code when present, not the display name.
            slug = league.get("slug") or league.get("abbreviation") or "all"
            out.append({"fixture_id": event_id, "minute": minute, "clock": clock,
                        "home": home["displayName"], "away": away["displayName"],
                        "home_id": str(home["id"]), "away_id": str(away["id"]),
                        "hg": home_goals, "ag": away_goals, "kickoff": kickoff,
                        "league": league_name, "slug": slug})
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            continue
    return out


def metrics_from_espn(summary, fixture):
    rows = []
    by_team = {}
    aliases = {"Shots on Goal": ("shotsontarget", "shotsongoal"),
               "Total Shots": ("totalshots", "shots"),
               "Corner Kicks": ("cornerkicks", "corners"),
               "Red Cards": ("redcards", "redcard")}
    for entry in ((summary or {}).get("boxscore") or {}).get("teams") or []:
        team_id = str((entry.get("team") or {}).get("id") or "")
        if team_id not in (fixture["home_id"], fixture["away_id"]):
            continue
        values = {}
        for stat in entry.get("statistics") or []:
            key = re.sub(r"[^a-z0-9]", "", str(stat.get("name") or "").lower())
            value = _int(stat.get("value"))
            if value is None:
                value = _int(stat.get("displayValue"))
            if value is not None:
                values[key] = value
        prepared = []
        for label, keys in aliases.items():
            for key in keys:
                if key in values:
                    prepared.append({"type": label, "value": values[key]})
                    break
        rows.append({"team": {"id": team_id}, "statistics": prepared})
        by_team[team_id] = {entry["type"]: entry["value"] for entry in prepared}
    metrics = match_metrics(rows, fixture)
    if metrics is None:
        return None
    # ESPN is only used for a team when the provider's real team ID is verified.
    home_stats = by_team.get(str(fixture["home_id"])) or {}
    away_stats = by_team.get(str(fixture["away_id"])) or {}
    metrics["teams"] = {
        "home": {out: home_stats[title] for out, title in
                 (("shots", "Total Shots"), ("sot", "Shots on Goal"), ("corners", "Corner Kicks"))
                 if title in home_stats},
        "away": {out: away_stats[title] for out, title in
                 (("shots", "Total Shots"), ("sot", "Shots on Goal"), ("corners", "Corner Kicks"))
                 if title in away_stats},
    }
    return metrics


def select_goal_tier(fixture, metrics):
    """Use only verified cumulative shots and available corners, never invented momentum."""
    minute = fixture["minute"]
    if not MIN_MINUTE <= minute <= MAX_MINUTE or not metrics:
        return None
    shots, on_target, corners = metrics["shots"], metrics["sot"], metrics.get("corners")
    if minute >= 81:
        # Final five minutes need demonstrably stronger pressure.
        if on_target < 9 or shots < 18 or (corners is not None and corners < 4):
            return None
        return "PREMIUM"
    if on_target >= 8 and shots >= 16:
        return "PREMIUM"
    return "STANDARD"


def format_tip(fixture, metrics):
    corners = metrics.get("corners")
    teams = metrics.get("teams") or {}
    team_lines = []
    if "home" in teams and "away" in teams:
        for side, name in (("home",fixture["home"]),("away",fixture["away"])):
            values=teams[side]
            parts=[]
            if values.get("shots") is not None:
                parts.append(f"Schüsse {values['shots']}")
            if values.get("sot") is not None:
                parts.append(f"aufs Tor {values['sot']}")
            if values.get("corners") is not None:
                parts.append(f"Ecken {values['corners']}")
            if values.get("xg") is not None:
                parts.append(f"xG {values['xg']:.2f}")
            if parts:
                team_lines.append(f"• {name}: " + " · ".join(parts))
    stats_line = ("📊 Teamstatistik\n" + "\n".join(team_lines) if len(team_lines)==2
                  else f"📊 Schüsse {metrics['shots']} · aufs Tor {metrics['sot']}"
                       + (f" · Ecken {corners}" if corners is not None else ""))
    return (f"⚽ NETRATTLER · LAST MINUTE GOAL\n"
            f"🎯 OVER 0.5 RESTSPIELZEIT · {metrics['tier']}\n\n"
            f"🏆 {fixture['league'] or 'Fussball'}\n"
            f"🏟 {fixture['home']} – {fixture['away']}\n"
            f"⏱ {fixture.get('clock') or str(fixture['minute']) + chr(39)} · {fixture['hg']}:{fixture['ag']}\n"
            f"✅ Prognose: Noch mindestens 1 Tor ab jetzt\n"
            f"{stats_line}\n"
            f"🏁 Auswertung: ⏳ offen")


def reserve_alert(fixture, metrics=None):
    """Durably reserve a match in GitHub-backed SQLite BEFORE Telegram delivery."""
    from netrattler_lmg_store import reserve_alert as sqlite_reserve
    return sqlite_reserve(fixture, metrics)


def send_alert(fixture, metrics):
    """Send ONLY the approved GOAL HUNTER image, without repeated caption text.

    All information including the optional next-goal side and @prophunter
    is already rendered into the image. Telegram caption stays absent.
    """
    from netrattler_lmg_card import make_card
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_GROUP_LATE_GOALS")
    if not token or not chat:
        raise RuntimeError("Telegram Goal Hunter group/bot secret missing")
    photo=make_card(fixture,metrics)
    resp=requests.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data={"chat_id":chat},
        files={"photo":("goal_hunter.jpg",photo,"image/jpeg")},timeout=30)
    resp.raise_for_status()
    payload=resp.json()
    message_id=(payload.get("result") or {}).get("message_id")
    if not payload.get("ok") or message_id is None:
        raise RuntimeError("Telegram photo delivery not confirmed")
    return message_id


def mark_sent(key, message_id):
    from netrattler_lmg_store import mark_sent as sqlite_mark_sent
    return sqlite_mark_sent(key, message_id)


def main():
    send_enabled = (os.getenv("LMG_SEND") or "false").lower() in {"true", "yes", "1"}
    board = _get(f"{ESPN}/all/scoreboard",
                 params={"dates": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"), "limit": "1000"})
    fixtures = fixtures_from_espn(board)
    fixtures.sort(key=lambda f: (f["minute"], f["fixture_id"]))
    report = {"live_candidates": len(fixtures), "stats_checked": 0,
              "qualified": 0, "sent": 0, "odds_calls": 0, "send_enabled": send_enabled}
    for fixture in fixtures[:MAX_FIXTURES_PER_RUN]:
        try:
            summary = _get(f"{ESPN}/{fixture['slug']}/summary",
                           params={"event": str(fixture["fixture_id"])})
        except requests.HTTPError as exc:
            print("LMG_STATS_UNAVAILABLE", fixture["fixture_id"], str(exc)[:110])
            continue
        report["stats_checked"] += 1
        metrics = metrics_from_espn(summary, fixture)
        tier = select_goal_tier(fixture, metrics)
        if tier is None:
            continue
        metrics["tier"] = tier
        metrics["next_goal_side"] = select_next_goal(metrics)
        report["qualified"] += 1
        print("LMG_SIGNAL", json.dumps({"fixture": fixture["fixture_id"],
                                       "minute": fixture["minute"], "score": [fixture["hg"], fixture["ag"]],
                                       "target": "one_more_goal", "metrics": metrics}))
        if send_enabled:
            key = reserve_alert(fixture, metrics)
            if key:
                msg_id = send_alert(fixture, metrics)
                mark_sent(key, msg_id)
                report["sent"] += 1
    print("LMG_FREE_SUMMARY", json.dumps(report))
    return report


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        print("LMG_FAIL_CLOSED", str(exc).splitlines()[0][:180], file=sys.stderr)
        raise SystemExit(1)
