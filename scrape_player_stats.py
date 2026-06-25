#!/usr/bin/env python3
"""
NETRATTLER - scrape_player_stats.py
=====================================
Post-Match Spieler-Stats aus SofaScore, FotMob und StatsBomb.
Speichert direkt in Supabase (player_match_stats).

Verwendung:
  python scrape_player_stats.py                    # gestern
  python scrape_player_stats.py --date 2026-06-23  # bestimmtes Datum
  python scrape_player_stats.py --source sofascore --event-id 11352565
  python scrape_player_stats.py --source fotmob --match-id 4193452
  python scrape_player_stats.py --source statsbomb  # StatsBomb Open Data

Automatisch via GitHub Actions (scrape_player_stats.yml) täglich 02:00 UTC.
"""

import argparse, json, os, time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests
try:
    import cloudscraper as _cloudscraper
    _SCRAPER = _cloudscraper.create_scraper()
except ImportError:
    _SCRAPER = requests.Session()

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                 or os.environ.get("SUPABASE_KEY", ""))
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_GROUP_STATS") or os.environ.get("TELEGRAM_CHAT_ID", "")
TABLE_NAME = "player_match_stats"

HEADERS_SOFA = {
    "User-Agent": "Mozilla/5.0 NetrattlerBot/1.0 private football analytics",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}
HEADERS_FOTMOB = {
    "User-Agent": "Mozilla/5.0 NetrattlerBot/1.0 private football analytics",
}


# ── Utils ─────────────────────────────────────────────────────────────────────

def get_json(url: str, headers: dict = None, pause: float = 2.0) -> Optional[dict]:
    time.sleep(pause)
    try:
        r = requests.get(url, headers=headers or HEADERS_SOFA, timeout=25)
        print(f"  [GET] {r.status_code} {url}")
        return r.json() if r.ok else None
    except Exception as e:
        print(f"  [ERROR] {url} → {e}")
        return None


def make_row(source, event_id, player_id, player_name, stat_name, stat_value,
             team=None, league=None, home_team=None, away_team=None,
             match_date=None, raw=None) -> Dict[str, Any]:
    return {
        "source":      source,
        "event_id":    str(event_id),
        "player_id":   str(player_id) if player_id is not None else None,
        "player_name": player_name or "Unknown",
        "team":        team,
        "league":      league,
        "home_team":   home_team,
        "away_team":   away_team,
        "match_date":  match_date,
        "stat_name":   stat_name,
        "stat_value":  stat_value if isinstance(stat_value, (int, float)) else None,
        "stat_text":   None if isinstance(stat_value, (int, float)) else str(stat_value),
        "raw":         raw or {},
    }


# ── Supabase ──────────────────────────────────────────────────────────────────

def sb_upsert(rows: list) -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        print(f"  ⚠️  Supabase nicht konfiguriert oder keine Rows")
        return 0

    allowed = {"source","event_id","player_id","player_name","team","league",
               "home_team","away_team","match_date","stat_name","stat_value",
               "stat_text","raw"}
    cleaned = [{k: v for k, v in r.items() if k in allowed} for r in rows]

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    total = 0
    for i in range(0, len(cleaned), 500):
        chunk = cleaned[i:i+500]
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}",
            headers=headers,
            json=chunk,
            timeout=30,
        )
        if r.ok:
            total += len(chunk)
            print(f"  ✅ {len(chunk)} Rows gespeichert")
        else:
            print(f"  ❌ Supabase Error {r.status_code}: {r.text[:200]}")
    return total


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )


# ── SofaScore ─────────────────────────────────────────────────────────────────

def sofa_meta(event_id: str) -> dict:
    data = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}") or {}
    ev = data.get("event", {})
    match_date = None
    if ev.get("startTimestamp"):
        match_date = datetime.fromtimestamp(ev["startTimestamp"], timezone.utc).isoformat()
    return {
        "league":     ev.get("tournament", {}).get("name"),
        "home_team":  ev.get("homeTeam", {}).get("name"),
        "away_team":  ev.get("awayTeam", {}).get("name"),
        "match_date": match_date,
    }


def scrape_sofascore(event_id: str) -> List[dict]:
    print(f"\n⚽ SofaScore Event {event_id}")
    meta  = sofa_meta(event_id)
    rows  = []

    # Lineups + Spieler-Stats
    lineups = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}/lineups") or {}
    for side, team_name in [("home", meta.get("home_team")), ("away", meta.get("away_team"))]:
        for item in lineups.get(side, {}).get("players", []) or []:
            p  = item.get("player", {}) or {}
            pid = p.get("id")
            pn  = p.get("name")
            stats = dict(item.get("statistics") or {})
            # Extra Felder
            if item.get("shirtNumber") is not None:
                stats["shirt_number"] = item["shirtNumber"]
            if item.get("position"):
                stats["position"] = item["position"]
            if item.get("substitute") is not None:
                stats["substitute"] = int(item["substitute"])
            for sn, sv in stats.items():
                rows.append(make_row("sofascore", event_id, pid, pn, sn, sv,
                                     team=team_name, raw=item, **meta))

    # Shotmap (xG, xGOT, bodyPart...)
    shotmap = get_json(f"https://api.sofascore.com/api/v1/event/{event_id}/shotmap") or {}
    for shot in shotmap.get("shotmap", []) or []:
        sp  = shot.get("player", {}) or {}
        pid = sp.get("id")
        pn  = sp.get("name")
        team = meta.get("home_team") if shot.get("isHome") else meta.get("away_team")
        for sn in ["xg", "xgot", "shotType", "situation", "bodyPart", "time", "goal"]:
            if sn in shot:
                rows.append(make_row("sofascore", event_id, pid, pn,
                                     f"shot_{sn}", shot[sn], team=team,
                                     raw=shot, **meta))

    print(f"  → {len(rows)} Rows")
    return rows


# ── FotMob ────────────────────────────────────────────────────────────────────

def scrape_fotmob(match_id: str) -> List[dict]:
    print(f"\n⚽ FotMob Match {match_id}")
    data = get_json(
        f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
        headers=HEADERS_FOTMOB
    ) or {}
    rows = []

    general = data.get("general", {}) or {}
    header  = data.get("header", {}) or {}
    teams   = header.get("teams", []) or []
    home_team   = teams[0].get("name") if len(teams) > 0 else None
    away_team   = teams[1].get("name") if len(teams) > 1 else None
    league      = general.get("leagueName")
    match_date  = general.get("matchTimeUTCDate")

    content  = data.get("content", {}) or {}
    lineup   = content.get("lineup", {}) or {}

    for team_block in lineup.get("lineup", []) or []:
        team_name = team_block.get("teamName")
        for group in team_block.get("players", []) or []:
            for p in (group.get("players", []) if isinstance(group, dict) else []):
                pid  = p.get("id")
                name = p.get("name", {})
                pn   = name.get("fullName") if isinstance(name, dict) else str(name)
                for sn, sv in (p.get("stats") or {}).items():
                    val = sv.get("value") if isinstance(sv, dict) else sv
                    rows.append(make_row("fotmob", match_id, pid, pn, sn, val,
                                        team=team_name, league=league,
                                        home_team=home_team, away_team=away_team,
                                        match_date=match_date, raw=p))

    print(f"  → {len(rows)} Rows")
    return rows


# ── StatsBomb Open Data ───────────────────────────────────────────────────────

def scrape_statsbomb() -> List[dict]:
    """Lädt StatsBomb Open Data competitions als Referenz-Datensatz."""
    print("\n📊 StatsBomb Open Data")
    data = get_json(
        "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
        pause=1.0
    ) or []
    rows = []
    for comp in data:
        eid = f"{comp.get('competition_id')}_{comp.get('season_id')}"
        rows.append(make_row(
            "statsbomb_open", eid, None, "COMPETITION_RECORD",
            "competition_available", 1,
            league=comp.get("competition_name"), raw=comp,
        ))
    print(f"  → {len(rows)} Rows")
    return rows


# ── Auto-Datum: alle beendeten Spiele scrapen ─────────────────────────────────

def scrape_date(date_str: str):
    print(f"\n📅 Scrape Player Stats für {date_str}")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    events = (get_json(url) or {}).get("events", [])

    finished = [
        e for e in events
        if e.get("status", {}).get("type") in ("finished",)
        or e.get("status", {}).get("code") in (100,)
    ]
    print(f"  → {len(events)} Events total, {len(finished)} beendet")

    all_rows = []
    for ev in finished:
        ev_id    = str(ev.get("id", ""))
        home     = ev.get("homeTeam", {}).get("name", "")
        away     = ev.get("awayTeam", {}).get("name", "")
        print(f"  ⚽ {home} vs {away} (ID: {ev_id})")
        try:
            rows = scrape_sofascore(ev_id)
            all_rows.extend(rows)
        except Exception as e:
            print(f"    ⚠️  {e}")

    total = sb_upsert(all_rows)

    report = (
        f"📊 <b>NETRATTLER Player Stats</b>\n\n"
        f"Datum: <b>{date_str}</b>\n"
        f"Spiele: <b>{len(finished)}</b>\n"
        f"Rows gespeichert: <b>{total}</b>"
    )
    print(f"\n{report}")
    send_telegram(report)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["sofascore", "fotmob", "statsbomb", "auto"], default="auto")
    parser.add_argument("--event-id",  help="SofaScore Event-ID")
    parser.add_argument("--match-id",  help="FotMob Match-ID")
    parser.add_argument("--date",      default=None)
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--output",    default=None,
                        help="JSON-Output (kein Supabase, nur Datei)")
    args = parser.parse_args()

    # Datum bestimmen
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
        return

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Gespeichert: {args.output} ({len(rows)} Rows)")
    else:
        total = sb_upsert(rows)
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            players = len(set(r["player_name"] for r in rows))
            send_telegram(
                f"📊 <b>Player Stats Import</b>\n"
                f"Rows: <b>{total}</b> | Spieler: <b>{players}</b>"
            )


if __name__ == "__main__":
    main()
