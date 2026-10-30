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

_PAGE_CACHE = {}


def _page(url):
    if url not in _PAGE_CACHE:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        _PAGE_CACHE[url] = r.text
    return _PAGE_CACHE[url]


def scrape_day(day: str):
    """Real dated fixtures only. A reachable homepage is never a match row."""
    from urllib.parse import urljoin, urlparse
    from netrattler_structured_pages import parse_public_page
    datetime.strptime(day, "%Y-%m-%d")
    html = _page(BASE)
    urls = []
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        url = urljoin(BASE, a.get("href"))
        parsed = urlparse(url)
        if parsed.hostname == "www.flashscore.com" and parsed.path.startswith("/match/football/") and url not in urls:
            urls.append(url)
        if len(urls) >= 8:
            break
    rows = []
    seen = set()
    for url in urls:
        try:
            context = parse_public_page(_page(url), url, target_date=day)
        except requests.RequestException as exc:
            log(f"detail unavailable: {type(exc).__name__}")
            continue
        for fx in context["fixtures"]:
            if fx["match_id"] in seen:
                continue
            seen.add(fx["match_id"])
            rows.append({"id": fx["match_id"], "match_date": fx["date"], "league": fx.get("league", ""),
                         "home_team": fx["home"], "away_team": fx["away"], "kickoff": fx["starts"],
                         "status": fx["status"], "raw": fx})
    return rows


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
        saved = supa.upsert("flashscore_matches", rows, on_conflict="id")
        log(f"saved {saved}/{len(rows)} actual fixtures")

if __name__ == "__main__":
    main()
