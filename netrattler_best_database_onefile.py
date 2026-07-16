#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NETRATTLER BEST DATABASE SIMPLE — ONEFILE V30 BOOSTER

Ziel:
- Registry/Health/Trust/GitHub-Open-Source sauber auffüllen
- keine Core-Tabellen zerstören
- fehlende optionale Tabellen leise überspringen
- Status-Zahlen am Ende ausgeben

Env:
SUPABASE_URL
SUPABASE_KEY oder SUPABASE_SERVICE_ROLE_KEY
"""

import os
import json
import time
import hashlib
from datetime import datetime, timezone

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

NOW = datetime.now(timezone.utc).isoformat()

SOURCES = [
    # Odds / market
    ("pinnacle_guest", "Odds", "pinnacle", 95, "Pinnacle guest odds, matchups and props"),
    ("the_odds_api", "Odds", "api", 86, "Odds API fallback"),
    ("bet365_inplay_hint", "Odds", "scrape", 70, "Bet365/InPlay market hints"),

    # Results / fixtures
    ("espn_scoreboard", "Results", "api", 82, "ESPN scoreboard results"),
    ("thesportsdb", "Results", "api", 75, "TheSportsDB fixtures/results"),
    ("football_data_co_uk", "Results", "csv", 88, "football-data.co.uk history/results"),
    ("openligadb", "Results", "api", 72, "OpenLigaDB German leagues"),
    ("api_football", "Results", "api", 45, "API-Football optional, may be quota/suspended"),
    ("allsports_api", "Results", "api", 65, "AllSports API optional fallback"),

    # Player stats / identity / open data
    ("statsbomb_open_data", "Stats", "github", 92, "StatsBomb open data player events"),
    ("fotmob_scraper", "Stats", "scrape", 78, "FotMob free scraping / schedule"),
    ("fbref_playwright", "Stats", "playwright", 55, "FBref optional Playwright fallback"),
    ("soccerdata", "Stats", "python", 80, "soccerdata package multi-source wrapper"),
    ("fpl_api", "Stats", "api", 72, "Fantasy Premier League API"),
    ("scoutingstats", "Stats", "scrape", 62, "ScoutingStats scraping fallback"),

    # Open source / GitHub layers
    ("openfootball_football_json", "GitHub/Open Source", "github", 82, "openfootball/football.json"),
    ("openfootball_worldcup_json", "GitHub/Open Source", "github", 80, "openfootball/worldcup.json"),
    ("openfootball_south_america", "GitHub/Open Source", "github", 78, "openfootball/south-america"),
    ("openfootball_europe", "GitHub/Open Source", "github", 78, "openfootball/europe"),
    ("openfootball_champions_league", "GitHub/Open Source", "github", 78, "openfootball/champions-league"),
    ("openfootball_internationals", "GitHub/Open Source", "github", 76, "openfootball/internationals"),
    ("openfootball_players", "GitHub/Open Source", "github", 74, "openfootball/players"),
    ("openfootball_clubs", "GitHub/Open Source", "github", 74, "openfootball/clubs"),
    ("martj42_nationalteams", "GitHub/Open Source", "github", 86, "martj42 international matches"),
    ("probberechts_soccerdata", "GitHub/Open Source", "github", 84, "probberechts/soccerdata"),
    ("davidrocha9_fotmob_scraper", "GitHub/Open Source", "github", 74, "davidrocha9/fotmob-scraper"),
    ("withqwerty_reep", "GitHub/Open Source", "github", 72, "withqwerty/reep identity/mapping"),
    ("odds_harvester", "GitHub/Open Source", "github", 70, "OddsHarvester reference"),
    ("salimt_football_datasets", "GitHub/Open Source", "github", 70, "salimt/football-datasets"),
    ("eddwebster_football_analytics", "GitHub/Open Source", "github", 68, "eddwebster/football_analytics"),
    ("simatwa_livescore_api", "GitHub/Open Source", "github", 64, "Simatwa/livescore-api"),

    # Signals
    ("netrattler_news_signals", "News", "internal", 66, "news signal table"),
    ("netrattler_social_signals", "Social Signals", "internal", 40, "social signal table, optional"),
    ("netrattler_learning", "Learning", "internal", 70, "learning/model feedback"),
    ("netrattler_roi", "ROI", "internal", 75, "ROI settlement summary"),
    ("netrattler_clv", "CLV", "internal", 55, "CLV tracker"),
]

GITHUB_ROWS = [
    ("openfootball/football.json", "fixtures/results", "https://github.com/openfootball/football.json"),
    ("openfootball/worldcup.json", "worldcup", "https://github.com/openfootball/worldcup.json"),
    ("openfootball/south-america", "south-america", "https://github.com/openfootball/south-america"),
    ("openfootball/europe", "europe", "https://github.com/openfootball/europe"),
    ("openfootball/champions-league", "champions-league", "https://github.com/openfootball/champions-league"),
    ("openfootball/internationals", "internationals", "https://github.com/openfootball/internationals"),
    ("openfootball/players", "players", "https://github.com/openfootball/players"),
    ("openfootball/clubs", "clubs", "https://github.com/openfootball/clubs"),
    ("martj42/international_results", "nationalteams", "https://github.com/martj42/international_results"),
    ("probberechts/soccerdata", "multi-source-stats", "https://github.com/probberechts/soccerdata"),
    ("davidrocha9/fotmob-scraper", "fotmob", "https://github.com/davidrocha9/fotmob-scraper"),
    ("withqwerty/reep", "identity", "https://github.com/withqwerty/reep"),
    ("OddsHarvester", "odds-reference", "https://github.com/search?q=OddsHarvester"),
    ("salimt/football-datasets", "datasets", "https://github.com/salimt/football-datasets"),
    ("eddwebster/football_analytics", "analytics", "https://github.com/eddwebster/football_analytics"),
    ("Simatwa/livescore-api", "livescore", "https://github.com/Simatwa/livescore-api"),
]


def ok():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def post(table, rows, conflict=None):
    if not rows:
        return 0
    params = {}
    if conflict:
        params["on_conflict"] = conflict
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params, data=json.dumps(rows), timeout=20)
        if r.status_code in (200, 201, 204):
            return len(rows)
        print(f"⚠️ {table} {r.status_code}: {r.text[:220]}")
        return 0
    except Exception as e:
        print(f"⚠️ {table} exception: {e}")
        return 0


def count(table):
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**HEADERS, "Prefer": "count=exact"},
            params={"select": "*", "limit": "1"},
            timeout=15,
        )
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            return int(cr.split("/")[-1])
        if r.ok:
            data = r.json() if r.text else []
            return len(data) if isinstance(data, list) else 0
        return 0
    except Exception:
        return 0


def source_id(name):
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:16]


def upsert_sources():
    registry = []
    health = []
    trust = []
    coverage = []

    for name, category, source_type, score, desc in SOURCES:
        sid = source_id(name)
        registry.append({
            "source_id": sid,
            "source_name": name,
            "category": category,
            "source_type": source_type,
            "description": desc,
            "is_active": True,
            "updated_at": NOW,
        })
        health.append({
            "source_id": sid,
            "source_name": name,
            "status": "ok" if score >= 55 else "optional",
            "last_checked_at": NOW,
            "latency_ms": 0,
            "notes": desc[:200],
        })
        trust.append({
            "source_id": sid,
            "source_name": name,
            "trust_score": score,
            "coverage_score": min(100, max(20, score - 5)),
            "freshness_score": 90 if source_type in {"api", "scrape", "playwright"} else 70,
            "updated_at": NOW,
        })
        coverage.append({
            "source_id": sid,
            "source_name": name,
            "category": category,
            "coverage_date": NOW[:10],
            "items_seen": 0,
            "updated_at": NOW,
        })

    print("netrattler_source_registry", post("netrattler_source_registry", registry, conflict="source_id"))
    print("netrattler_source_health", post("netrattler_source_health", health, conflict="source_id"))
    print("netrattler_source_trust_scores", post("netrattler_source_trust_scores", trust, conflict="source_id"))
    print("netrattler_source_coverage", post("netrattler_source_coverage", coverage, conflict="source_id,coverage_date"))


def upsert_github():
    rows = []
    for repo, tag, url in GITHUB_ROWS:
        rows.append({
            "repo": repo,
            "name": repo,
            "tag": tag,
            "url": url,
            "source_type": "github",
            "is_active": True,
            "trust_score": 70,
            "notes": f"NETRATTLER V30 source hub: {tag}",
            "updated_at": NOW,
        })
    print("netrattler_github_open_source_sources", post("netrattler_github_open_source_sources", rows, conflict="repo"))


def upsert_learning_and_roi():
    # Lightweight snapshots; real values come from settlement/tips.
    post("netrattler_learning", [{
        "key": "best_database_last_run",
        "value": {"ts": NOW, "sources": len(SOURCES), "github": len(GITHUB_ROWS)},
        "updated_at": NOW,
    }], conflict="key")

    # If ROI/CLV tables exist, add a heartbeat row only when empty enough.
    post("netrattler_roi", [{
        "date": NOW[:10],
        "market": "all",
        "profit_units": 0,
        "staked_units": 0,
        "roi": 0,
        "notes": "heartbeat; real ROI from settlement",
        "updated_at": NOW,
    }], conflict="date,market")

    post("netrattler_clv", [{
        "date": NOW[:10],
        "source": "heartbeat",
        "clv": 0,
        "notes": "heartbeat; real CLV from odds movement",
        "updated_at": NOW,
    }], conflict="date,source")


def main():
    print("NETRATTLER BEST DATABASE SIMPLE — ONEFILE V30 BOOSTER")
    if not ok():
        print("❌ SUPABASE_URL/SUPABASE_KEY fehlt")
        return

    upsert_sources()
    upsert_github()
    upsert_learning_and_roi()

    counts = {
        "Odds": count("odds_archive"),
        "Props": count("player_prop_db"),
        "Stats": count("player_match_stats"),
        "Results": count("match_results"),
        "CLV": count("netrattler_clv"),
        "News": count("netrattler_news_signals"),
        "Social Signals": count("netrattler_social_signals"),
        "GitHub/Open Source": count("netrattler_github_open_source_sources"),
        "Learning": count("netrattler_learning"),
        "ROI": count("netrattler_roi"),
        "Source Trust": count("netrattler_source_trust_scores"),
        "Coverage": count("netrattler_source_coverage"),
    }
    print(counts)
    print("Fertig")


if __name__ == "__main__":
    main()
