#!/usr/bin/env python3
"""
NETRATTLER - scrape_player_stats.py V2
=====================================
Sammelt Post-Match Spieler-Stats aus SofaScore, FotMob und StatsBomb.
Speichert direkt in Supabase:

1) player_match_stats  = einzelne Spieler-Stat-Zeilen pro Spiel
2) player_avg_stats    = automatische Prop-Hit-Rates / Durchschnitte

Verwendung:
  python scrape_player_stats.py
  python scrape_player_stats.py --date 2026-06-23
  python scrape_player_stats.py --source sofascore --event-id 11352565
  python scrape_player_stats.py --source fotmob --match-id 4193452
  python scrape_player_stats.py --source statsbomb
  python scrape_player_stats.py --rebuild-averages

GitHub Actions:
  täglich nach Spielende laufen lassen.
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict

import requests

try:
    import cloudscraper as _cloudscraper
    _SCRAPER = _cloudscraper.create_scraper()
except Exception:
    _SCRAPER = requests.Session()


# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY", "")
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_GROUP_STATS") or os.environ.get("TELEGRAM_CHAT_ID", "")

PLAYER_MATCH_TABLE = "player_match_stats"
PLAYER_AVG_TABLE = "player_avg_stats"

HEADERS_SOFA = {
    "User-Agent": "Mozilla/5.0 NetrattlerBot/2.0 private football analytics",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}

HEADERS_FOTMOB = {
    "User-Agent": "Mozilla/5.0 NetrattlerBot/2.0 private football analytics",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.fotmob.com/",
}


# ── Utils ─────────────────────────────────────────────────────────────────────

def log(msg: str):
    print(msg, flush=True)


def get_json(url: str, headers: dict = None, pause: float = 1.5) -> Optional[Any]:
    time.sleep(pause)
    try:
        r = _SCRAPER.get(url, headers=headers or HEADERS_SOFA, timeout=30)
        log(f"  [GET] {r.status_code} {url}")
        if not r.ok:
            return None
        return r.json()
    except Exception as e:
        log(f"  [ERROR] {url} → {e}")
        return None


def sb_headers(prefer: str = "resolution=merge-duplicates,return=minimal") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def make_row(
    source,
    event_id,
    player_id,
    player_name,
    stat_name,
    stat_value,
    team=None,
    league=None,
    home_team=None,
    away_team=None,
    match_date=None,
    raw=None,
) -> Dict[str, Any]:
    try:
        num = float(stat_value)
        stat_text = None
    except Exception:
        num = None
        stat_text = None if stat_value is None else str(stat_value)

    return {
        "source": source,
        "event_id": str(event_id),
        "player_id": str(player_id) if player_id is not None else None,
        "player_name": player_name or "Unknown",
        "team": team,
        "league": league,
        "home_team": home_team,
        "away_team": away_team,
        "match_date": match_date,
        "stat_name": str(stat_name),
        "stat_value": num,
        "stat_text": stat_text,
        "raw": raw or {},
    }


def sb_upsert(table: str, rows: list, on_conflict: Optional[str] = None, batch_size: int = 500) -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        log("  ⚠️ Supabase nicht konfiguriert oder keine Rows")
        return 0

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"

    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        r = requests.post(
            url,
            headers=sb_headers(),
            json=chunk,
            timeout=45,
        )
        if r.ok:
            total += len(chunk)
            log(f"  ✅ {table}: {len(chunk)} Rows gespeichert")
        else:
            log(f"  ❌ Supabase {table} Error {r.status_code}: {r.text[:300]}")
    return total


def sb_select(table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=sb_headers(),
        params=params,
        timeout=60,
    )
    if not r.ok:
        log(f"  ❌ Supabase select {table} {r.status_code}: {r.text[:250]}")
        return []
    try:
        return r.json()
    except Exception:
        return []


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception:
        pass


# ── SofaScore ─────────────────────────────────────────────────────────────────

def sofa_meta(event_id: str) -> dict:
    data = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}") or {}
    ev = data.get("event", {})
    match_date = None
    if ev.get("startTimestamp"):
        match_date = datetime.fromtimestamp(ev["startTimestamp"], timezone.utc).isoformat()
    return {
        "league": ev.get("tournament", {}).get("name"),
        "home_team": ev.get("homeTeam", {}).get("name"),
        "away_team": ev.get("awayTeam", {}).get("name"),
        "match_date": match_date,
    }


def scrape_sofascore(event_id: str) -> List[dict]:
    log(f"\n⚽ SofaScore Event {event_id}")
    meta = sofa_meta(event_id)
    rows = []

    lineups = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}/lineups") or {}

    for side, team_name in [("home", meta.get("home_team")), ("away", meta.get("away_team"))]:
        for item in lineups.get(side, {}).get("players", []) or []:
            p = item.get("player", {}) or {}
            pid = p.get("id")
            pn = p.get("name")
            stats = dict(item.get("statistics") or {})

            if item.get("shirtNumber") is not None:
                stats["shirt_number"] = item["shirtNumber"]
            if item.get("position"):
                stats["position"] = item["position"]
            if item.get("substitute") is not None:
                stats["substitute"] = int(bool(item["substitute"]))

            for sn, sv in stats.items():
                rows.append(
                    make_row(
                        "sofascore",
                        event_id,
                        pid,
                        pn,
                        sn,
                        sv,
                        team=team_name,
                        raw=item,
                        **meta,
                    )
                )

    shotmap = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}/shotmap") or {}
    for shot in shotmap.get("shotmap", []) or []:
        sp = shot.get("player", {}) or {}
        pid = sp.get("id")
        pn = sp.get("name")
        team = meta.get("home_team") if shot.get("isHome") else meta.get("away_team")
        for sn in ["xg", "xgot", "shotType", "situation", "bodyPart", "time", "goal"]:
            if sn in shot:
                rows.append(
                    make_row(
                        "sofascore",
                        event_id,
                        pid,
                        pn,
                        f"shot_{sn}",
                        shot[sn],
                        team=team,
                        raw=shot,
                        **meta,
                    )
                )

    log(f"  → {len(rows)} Rows")
    return rows


# ── FotMob ────────────────────────────────────────────────────────────────────

def scrape_fotmob(match_id: str) -> List[dict]:
    log(f"\n⚽ FotMob Match {match_id}")
    data = get_json(
        f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
        headers=HEADERS_FOTMOB,
    ) or {}
    rows = []

    general = data.get("general", {}) or {}
    header = data.get("header", {}) or {}
    teams = header.get("teams", []) or []

    home_team = teams[0].get("name") if len(teams) > 0 else None
    away_team = teams[1].get("name") if len(teams) > 1 else None
    league = general.get("leagueName")
    match_date = general.get("matchTimeUTCDate")

    content = data.get("content", {}) or {}
    lineup = content.get("lineup", {}) or {}

    for team_block in lineup.get("lineup", []) or []:
        team_name = team_block.get("teamName")
        for group in team_block.get("players", []) or []:
            for p in (group.get("players", []) if isinstance(group, dict) else []):
                pid = p.get("id")
                name = p.get("name", {})
                pn = name.get("fullName") if isinstance(name, dict) else str(name)
                for sn, sv in (p.get("stats") or {}).items():
                    val = sv.get("value") if isinstance(sv, dict) else sv
                    rows.append(
                        make_row(
                            "fotmob",
                            match_id,
                            pid,
                            pn,
                            sn,
                            val,
                            team=team_name,
                            league=league,
                            home_team=home_team,
                            away_team=away_team,
                            match_date=match_date,
                            raw=p,
                        )
                    )

    log(f"  → {len(rows)} Rows")
    return rows


# ── StatsBomb Open Data ───────────────────────────────────────────────────────

def scrape_statsbomb() -> List[dict]:
    log("\n📊 StatsBomb Open Data")
    data = get_json(
        "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
        pause=1.0,
    ) or []
    rows = []
    for comp in data:
        eid = f"{comp.get('competition_id')}_{comp.get('season_id')}"
        rows.append(
            make_row(
                "statsbomb_open",
                eid,
                None,
                "COMPETITION_RECORD",
                "competition_available",
                1,
                league=comp.get("competition_name"),
                raw=comp,
            )
        )
    log(f"  → {len(rows)} Rows")
    return rows


# ── Auto-Datum: alle beendeten Spiele scrapen ─────────────────────────────────

def scrape_date(date_str: str) -> int:
    log(f"\n📅 Scrape Player Stats für {date_str}")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    events = (get_json(url) or {}).get("events", [])

    finished = [
        e for e in events
        if e.get("status", {}).get("type") in ("finished",)
        or e.get("status", {}).get("code") in (100,)
    ]
    log(f"  → {len(events)} Events total, {len(finished)} beendet")

    all_rows = []
    for ev in finished:
        ev_id = str(ev.get("id", ""))
        home = ev.get("homeTeam", {}).get("name", "")
        away = ev.get("awayTeam", {}).get("name", "")
        log(f"  ⚽ {home} vs {away} (ID: {ev_id})")
        try:
            rows = scrape_sofascore(ev_id)
            all_rows.extend(rows)
        except Exception as e:
            log(f"    ⚠️ {e}")
        time.sleep(1.0)

    total = sb_upsert(
        PLAYER_MATCH_TABLE,
        all_rows,
        on_conflict="source,event_id,player_id,stat_name",
    )

    report = (
        f"📊 <b>NETRATTLER Player Stats V2</b>\n\n"
        f"Datum: <b>{date_str}</b>\n"
        f"Spiele: <b>{len(finished)}</b>\n"
        f"Rows gespeichert: <b>{total}</b>"
    )
    log(f"\n{report}")
    send_telegram(report)
    return total


# ── Player Average / Hit Rate Engine ─────────────────────────────────────────

STAT_ALIASES = {
    "goals": ["goals", "goal", "shot_goal"],
    "assists": ["goalAssist", "assists", "assist"],
    "shots": ["totalShots", "shots", "shot_total", "shot_time"],
    "sot": ["onTargetScoringAttempt", "shotsOnTarget", "shot_xgot"],
    "xg": ["expectedGoals", "xg", "shot_xg"],
    "tackles": ["totalTackle", "tackles", "wonTackle"],
    "fouls": ["fouls", "foulsCommitted"],
    "fouls_drawn": ["wasFouled", "foulsDrawn"],
    "cards": ["yellowCards", "redCards", "cards"],
    "offsides": ["offsides"],
    "minutes": ["minutesPlayed", "minutes"],
}

PROP_LINES = {
    "goals": [0.5],
    "assists": [0.5],
    "shots": [0.5, 1.5, 2.5],
    "sot": [0.5, 1.5],
    "xg": [0.1, 0.3, 0.5],
    "tackles": [0.5, 1.5, 2.5],
    "fouls": [0.5, 1.5, 2.5],
    "fouls_drawn": [0.5, 1.5, 2.5],
    "cards": [0.5],
    "offsides": [0.5, 1.5],
}

def canonical_stat(stat_name: str) -> Optional[str]:
    s = (stat_name or "").strip()
    for canon, names in STAT_ALIASES.items():
        if s in names:
            return canon
    return None


def rebuild_player_averages(days_back: int = 180) -> int:
    """
    Liest player_match_stats aus Supabase und baut player_avg_stats.
    Diese Tabelle ist die Grundlage für Prop Builder Hit-Rates.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
    log(f"\n🧠 Rebuild player_avg_stats, seit {since}")

    rows = sb_select(
        PLAYER_MATCH_TABLE,
        {
            "select": "player_name,team,league,match_date,event_id,stat_name,stat_value",
            "match_date": f"gte.{since}",
            "limit": "50000",
        },
    )
    log(f"  → geladene Stat-Zeilen: {len(rows)}")

    # player/event/stat aggregieren
    per_player_event = defaultdict(lambda: defaultdict(float))
    player_meta = {}

    for r in rows:
        player = r.get("player_name") or "Unknown"
        event_id = r.get("event_id") or ""
        canon = canonical_stat(r.get("stat_name"))
        if not canon:
            continue
        val = r.get("stat_value")
        if val is None:
            continue
        try:
            val = float(val)
        except Exception:
            continue

        key = (player, event_id)
        per_player_event[key][canon] += val
        player_meta[player] = {
            "team": r.get("team"),
            "league": r.get("league"),
        }

    # player -> stat -> values
    player_stat_values = defaultdict(lambda: defaultdict(list))
    for (player, event_id), stats in per_player_event.items():
        for stat, val in stats.items():
            player_stat_values[player][stat].append(val)

    avg_rows = []
    now = datetime.now(timezone.utc).isoformat()

    for player, statmap in player_stat_values.items():
        for stat, values in statmap.items():
            if not values:
                continue
            games = len(values)
            avg = sum(values) / games
            avg_rows.append({
                "player_name": player,
                "stat_name": stat,
                "avg_value": round(avg, 4),
                "hit_rate_pct": None,
                "games": games,
                "updated_at": now,
            })

            for line in PROP_LINES.get(stat, []):
                hits = sum(1 for v in values if v > line)
                hit_rate = round(hits / games * 100, 2) if games else 0
                avg_rows.append({
                    "player_name": player,
                    "stat_name": f"{stat}_over_{str(line).replace('.', '_')}",
                    "avg_value": round(avg, 4),
                    "hit_rate_pct": hit_rate,
                    "games": games,
                    "updated_at": now,
                })

    total = sb_upsert(
        PLAYER_AVG_TABLE,
        avg_rows,
        on_conflict="player_name,stat_name",
        batch_size=500,
    )
    log(f"  ✅ player_avg_stats aktualisiert: {total}")

    send_telegram(
        f"🧠 <b>NETRATTLER Player Averages</b>\n"
        f"Stats-Zeilen: <b>{len(rows)}</b>\n"
        f"Averages: <b>{total}</b>"
    )
    return total


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["sofascore", "fotmob", "statsbomb", "auto"], default="auto")
    parser.add_argument("--event-id", help="SofaScore Event-ID")
    parser.add_argument("--match-id", help="FotMob Match-ID")
    parser.add_argument("--date", default=None)
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--output", default=None, help="JSON-Output statt Supabase")
    parser.add_argument("--rebuild-averages", action="store_true")
    parser.add_argument("--days-back", type=int, default=180)
    args = parser.parse_args()

    if args.rebuild_averages:
        rebuild_player_averages(days_back=args.days_back)
        return

    if args.yesterday or (args.source == "auto" and not args.date):
        args.date = str((datetime.now(timezone.utc) - timedelta(days=1)).date())

    rows = []

    if args.source == "sofascore" and args.event_id:
        rows = scrape_sofascore(args.event_id)
    elif args.source == "fotmob" and args.match_id:
        rows = scrape_fotmob(args.match_id)
    elif args.source == "statsbomb":
        rows = scrape_statsbomb()
    else:
        scrape_date(args.date or str(datetime.now(timezone.utc).date()))
        rebuild_player_averages(days_back=args.days_back)
        return

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        log(f"\n✅ Gespeichert: {args.output} ({len(rows)} Rows)")
    else:
        total = sb_upsert(
            PLAYER_MATCH_TABLE,
            rows,
            on_conflict="source,event_id,player_id,stat_name",
        )
        rebuild_player_averages(days_back=args.days_back)
        players = len(set(r["player_name"] for r in rows))
        send_telegram(
            f"📊 <b>Player Stats Import V2</b>\n"
            f"Rows: <b>{total}</b> | Spieler: <b>{players}</b>"
        )


if __name__ == "__main__":
    main()
