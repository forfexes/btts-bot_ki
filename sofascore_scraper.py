#!/usr/bin/env python3
import os, time, argparse, requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from supabase_client import SupabaseRest

BASE = "https://www.sofascore.com/api/v1"
SLEEP = float(os.getenv("SCRAPER_SLEEP_SECONDS", "7"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/124 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Referer": "https://www.sofascore.com/football",
    "Origin": "https://www.sofascore.com",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_json(url: str, retries: int = 3) -> Dict[str, Any]:
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code in (403, 429):
                time.sleep(SLEEP * attempt * 2)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(SLEEP * attempt)
    raise RuntimeError(f"SofaScore failed: {url} {last}")

def fetch_events(day: str) -> List[Dict[str, Any]]:
    return get_json(f"{BASE}/sport/football/scheduled-events/{day}").get("events", [])

def event_to_row(ev: Dict[str, Any], day: str) -> Dict[str, Any]:
    return {
        "id": str(ev.get("id")),
        "event_date": day,
        "tournament": (ev.get("tournament") or {}).get("name"),
        "season": (ev.get("season") or {}).get("name"),
        "home_team": (ev.get("homeTeam") or {}).get("name"),
        "away_team": (ev.get("awayTeam") or {}).get("name"),
        "start_timestamp": ev.get("startTimestamp"),
        "status": (ev.get("status") or {}).get("description") or (ev.get("status") or {}).get("type"),
        "raw": ev,
    }

def fetch_player_stats(event_id: str, event_date: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        data = get_json(f"{BASE}/event/{event_id}/lineups")
    except Exception as e:
        log(f"no lineups/stats for {event_id}: {str(e)[:80]}")
        return rows

    for side_key in ("home", "away"):
        side = data.get(side_key) or {}
        team_name = (side.get("team") or {}).get("name") or side.get("teamName")
        for p in side.get("players", []) or []:
            player = p.get("player") or {}
            stats = p.get("statistics") or {}
            pid = player.get("id")
            name = player.get("name")
            if not pid or not name:
                continue
            rows.append({
                "event_id": str(event_id),
                "event_date": event_date,
                "player_id": str(pid),
                "player_name": name,
                "team_name": team_name,
                "position": p.get("position") or player.get("position"),
                "minutes": stats.get("minutesPlayed") or stats.get("minutes"),
                "stats": stats or p,
            })
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-ahead", type=int, default=int(os.getenv("SCRAPE_DAYS_AHEAD", "2")))
    ap.add_argument("--days-back", type=int, default=1)
    ap.add_argument("--with-player-stats", action="store_true")
    ap.add_argument("--max-events", type=int, default=0)
    args = ap.parse_args()

    supa = SupabaseRest()
    today = datetime.now(timezone.utc).date()
    all_events, all_stats = [], []

    for i in range(-args.days_back, args.days_ahead + 1):
        day = (today + timedelta(days=i)).isoformat()
        log(f"SofaScore {day}")
        events = fetch_events(day)
        if args.max_events:
            events = events[:args.max_events]
        rows = [event_to_row(e, day) for e in events if e.get("id")]
        all_events.extend(rows)

        if args.with_player_stats:
            for ev in rows:
                status = str(ev.get("status") or "").lower()
                if "not started" in status:
                    continue
                all_stats.extend(fetch_player_stats(ev["id"], day))
                time.sleep(SLEEP)
        time.sleep(SLEEP)

    if all_events:
        log(f"save events {len(all_events)}")
        supa.upsert("sofascore_events", all_events, on_conflict="id")
    if all_stats:
        log(f"save player stats {len(all_stats)}")
        supa.upsert("sofascore_player_match_stats", all_stats, on_conflict="event_id,player_id")

if __name__ == "__main__":
    main()
