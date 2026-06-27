#!/usr/bin/env python3
import os, time, argparse, requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from supabase_client import SupabaseRest

BASE = "https://www.flashscore.com/football/"
SLEEP = float(os.getenv("SCRAPER_SLEEP_SECONDS", "10"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def scrape_day(day: str):
    r = requests.get(BASE, headers=HEADERS, timeout=35)
    if r.status_code in (403, 429, 503):
        raise RuntimeError(f"Flashscore blocked {r.status_code}")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    sample = soup.get_text(" ", strip=True)[:300]
    return [{
        "id": f"flashscore_health_{day}",
        "match_date": day,
        "league": "healthcheck",
        "home_team": None,
        "away_team": None,
        "kickoff": None,
        "status": "html_reachable",
        "raw": {"chars": len(r.text), "sample": sample},
    }]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-ahead", type=int, default=1)
    ap.add_argument("--days-back", type=int, default=0)
    args = ap.parse_args()

    supa = SupabaseRest()
    today = datetime.now(timezone.utc).date()
    rows = []
    for i in range(-args.days_back, args.days_ahead + 1):
        day = (today + timedelta(days=i)).isoformat()
        try:
            log(f"Flashscore {day}")
            rows.extend(scrape_day(day))
        except Exception as e:
            log(f"skip {day}: {e}")
        time.sleep(SLEEP)

    if rows:
        supa.upsert("flashscore_matches", rows, on_conflict="id")
        log(f"saved {len(rows)}")

if __name__ == "__main__":
    main()
