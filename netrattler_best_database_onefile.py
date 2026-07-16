#!/usr/bin/env python3
"""
NETRATTLER BEST DATABASE SIMPLE - ONEFILE V31 REAL SUPABASE SCHEMA

Schema matched to current Supabase:
- netrattler_source_registry: source
- netrattler_source_health: source
- netrattler_source_trust_scores: source + score_date
- netrattler_source_coverage: source_id + coverage_date
- netrattler_github_open_source_sources: repo_full_name
"""

from __future__ import annotations

import os
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import requests


SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""

TODAY = date.today().isoformat()
NOW = datetime.now(timezone.utc).isoformat()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

BASE_SOURCES = [
    ("football-data", "Odds/Fixtures", "api", "https://www.football-data.org", True, True, 92, "Football-Data API"),
    ("api-football", "Fixtures/Stats", "api", "https://www.api-football.com", False, True, 88, "API-Football"),
    ("pinnacle", "Odds", "odds", "https://www.pinnacle.com", False, False, 91, "Pinnacle odds/parser"),
    ("the-odds-api", "Odds", "api", "https://the-odds-api.com", False, True, 83, "Odds API"),
    ("football-data-co-uk", "Historical Odds", "csv", "https://www.football-data.co.uk", True, False, 82, "Historical CSV odds/results"),
    ("statsbomb-open-data", "Stats", "github", "https://github.com/statsbomb/open-data", True, False, 91, "StatsBomb open data"),
    ("openfootball", "Fixtures/Results", "github", "https://github.com/openfootball", True, False, 80, "OpenFootball data"),
    ("opendligadb", "Fixtures/Results", "api", "https://www.openligadb.de", True, False, 78, "OpenLigaDB"),
    ("fotmob", "Stats", "scraper", "https://www.fotmob.com", True, False, 74, "FotMob scraper/fallback"),
    ("fbref", "Player Stats", "scraper", "https://fbref.com", True, False, 76, "FBref via soccerdata when available"),
    ("sofascore", "Player Stats", "scraper", "https://www.sofascore.com", True, False, 70, "SofaScore optional"),
    ("espn", "Fixtures/Results", "api", "https://site.api.espn.com", True, False, 70, "ESPN scoreboard"),
    ("thesportsdb", "Fixtures/Results", "api", "https://www.thesportsdb.com", True, True, 66, "TheSportsDB optional"),
    ("prop_builder_engine", "Builder", "internal", "internal", True, False, 86, "NETRATTLER V31 Builder Engine"),
    ("settlement_engine", "Settlement", "internal", "internal", True, False, 88, "NETRATTLER Settlement Engine"),
]

GITHUB_SOURCES = [
    ("openfootball/football.json", "https://github.com/openfootball/football.json", "fixtures/results", 82),
    ("openfootball/worldcup.json", "https://github.com/openfootball/worldcup.json", "worldcup", 80),
    ("openfootball/south-america", "https://github.com/openfootball/south-america", "south-america", 78),
    ("openfootball/europe", "https://github.com/openfootball/europe", "europe", 78),
    ("openfootball/champions-league", "https://github.com/openfootball/champions-league", "champions-league", 78),
    ("openfootball/internationals", "https://github.com/openfootball/internationals", "internationals", 76),
    ("openfootball/players", "https://github.com/openfootball/players", "players", 74),
    ("openfootball/clubs", "https://github.com/openfootball/clubs", "clubs", 74),
    ("martj42/international_results", "https://github.com/martj42/international_results", "nationalteams", 86),
    ("probberechts/soccerdata", "https://github.com/probberechts/soccerdata", "multi-source-stats", 84),
    ("davidrocha9/fotmob-scraper", "https://github.com/davidrocha9/fotmob-scraper", "fotmob", 74),
    ("withqwerty/reep", "https://github.com/withqwerty/reep", "identity", 72),
    ("OddsHarvester", "https://github.com/search?q=OddsHarvester", "odds-reference", 70),
    ("salimt/football-datasets", "https://github.com/salimt/football-datasets", "datasets", 70),
    ("eddwebster/football_analytics", "https://github.com/eddwebster/football_analytics", "analytics", 68),
    ("Simatwa/livescore-api", "https://github.com/Simatwa/livescore-api", "livescore", 64),
]


def api_url(table: str, conflict: Optional[str] = None) -> str:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict:
        url += f"?on_conflict={conflict}"
    return url


def post(table: str, rows: List[Dict[str, Any]], conflict: Optional[str] = None) -> int:
    rows = [r for r in rows if r]
    if not rows:
        return 0
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"WARNING {table}: missing SUPABASE_URL/SUPABASE_KEY")
        return 0

    response = requests.post(api_url(table, conflict), headers=HEADERS, data=json.dumps(rows), timeout=45)
    if response.status_code >= 300:
        print(f"WARNING {table} {response.status_code}: {response.text[:800]}")
        return 0
    return len(rows)


def get_count(table: str) -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    headers = dict(HEADERS)
    headers["Prefer"] = "count=exact"
    try:
        response = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?select=*", headers=headers, timeout=30)
        content_range = response.headers.get("content-range") or ""
        if "/" in content_range:
            return int(content_range.split("/")[-1])
    except Exception:
        pass
    return 0


def registry_rows() -> List[Dict[str, Any]]:
    rows = []
    for source, category, source_type, url, is_free, requires_key, base_trust, notes in BASE_SOURCES:
        rows.append({
            "source": source,
            "source_id": source,
            "source_name": source,
            "category": category,
            "source_type": source_type,
            "url": url,
            "is_free": is_free,
            "requires_key": requires_key,
            "priority": int(base_trust),
            "base_trust": float(base_trust),
            "description": notes,
            "notes": notes,
            "is_active": True,
            "updated_at": NOW,
        })
    for repo, url, tag, trust in GITHUB_SOURCES:
        source = f"github:{repo}"
        rows.append({
            "source": source,
            "source_id": source,
            "source_name": repo,
            "category": "GitHub/Open Source",
            "source_type": "github",
            "url": url,
            "is_free": True,
            "requires_key": False,
            "priority": int(trust),
            "base_trust": float(trust),
            "description": f"GitHub source: {repo}",
            "notes": "NETRATTLER V31 source hub",
            "is_active": True,
            "updated_at": NOW,
        })
    return rows


def health_rows() -> List[Dict[str, Any]]:
    rows = []
    for row in registry_rows():
        source = row["source"]
        rows.append({
            "source": source,
            "source_id": row.get("source_id") or source,
            "source_name": row.get("source_name") or source,
            "status": "ok",
            "http_status": 200,
            "rows": 0,
            "latency_ms": 0,
            "message": "registered",
            "checked_at": NOW,
            "last_checked_at": NOW,
            "notes": "Best Database V31 real-schema heartbeat",
            "updated_at": NOW,
        })
    return rows


def trust_rows() -> List[Dict[str, Any]]:
    rows = []
    for row in registry_rows():
        base = float(row.get("base_trust") or row.get("priority") or 70)
        source = row["source"]
        rows.append({
            "source": source,
            "source_id": row.get("source_id") or source,
            "source_name": row.get("source_name") or source,
            "score_date": TODAY,
            "trust_score": base,
            "health_score": 75,
            "coverage_score": 70,
            "clv_score": 50,
            "roi_score": 50,
            "freshness_score": 75,
            "penalty_score": 0,
            "samples": 0,
            "reason": "Best Database V31 bootstrap score",
            "updated_at": NOW,
        })
    return rows


def coverage_rows() -> List[Dict[str, Any]]:
    return [{
        "source_id": row["source"],
        "source_name": row.get("source_name") or row["source"],
        "category": row.get("category") or "unknown",
        "coverage_date": TODAY,
        "items_seen": 1,
        "updated_at": NOW,
    } for row in registry_rows()]


def github_rows() -> List[Dict[str, Any]]:
    rows = []
    for repo, url, tag, trust in GITHUB_SOURCES:
        rows.append({
            "repo_full_name": repo,
            "url": url,
            "category": "GitHub/Open Source",
            "description": f"NETRATTLER V31 source: {repo}",
            "stars": 0,
            "forks": 0,
            "license": None,
            "trust_score": float(trust),
            "tags": [tag, "netrattler", "football"],
            "raw": {"repo": repo, "tag": tag, "source": "NETRATTLER V31"},
            "updated_at": NOW,
            "repo": repo,
            "name": repo,
            "tag": tag,
            "source_type": "github",
            "is_active": True,
            "notes": "NETRATTLER V31 source hub",
        })
    return rows


def optional_rows() -> None:
    post("netrattler_learning", [{
        "key": f"best_database_run:{TODAY}",
        "value": {"status": "ok", "version": "V31_REAL_SCHEMA", "updated_at": NOW},
        "updated_at": NOW,
    }], conflict="key")

    post("netrattler_roi", [{
        "date": TODAY,
        "market": "best_database",
        "profit_units": 0,
        "staked_units": 0,
        "roi": 0,
        "notes": "heartbeat",
        "updated_at": NOW,
    }], conflict="date,market")

    post("netrattler_clv", [{
        "date": TODAY,
        "source": "best_database",
        "clv": 0,
        "notes": "heartbeat",
        "updated_at": NOW,
    }], conflict="date,source")


def main() -> None:
    print("NETRATTLER BEST DATABASE SIMPLE - ONEFILE V31 REAL SCHEMA")

    print("netrattler_source_registry", post("netrattler_source_registry", registry_rows(), conflict="source"))
    print("netrattler_source_health", post("netrattler_source_health", health_rows(), conflict="source"))
    print("netrattler_source_trust_scores", post("netrattler_source_trust_scores", trust_rows(), conflict="source,score_date"))
    print("netrattler_source_coverage", post("netrattler_source_coverage", coverage_rows(), conflict="source_id,coverage_date"))
    print("netrattler_github_open_source_sources", post("netrattler_github_open_source_sources", github_rows(), conflict="repo_full_name"))

    optional_rows()

    overview = {
        "Odds": get_count("prop_picks"),
        "Props": get_count("tips"),
        "Stats": get_count("player_match_stats"),
        "Results": get_count("match_results"),
        "CLV": get_count("netrattler_clv"),
        "News": 0,
        "Social Signals": 0,
        "GitHub/Open Source": get_count("netrattler_github_open_source_sources"),
        "Learning": get_count("netrattler_learning"),
        "ROI": get_count("netrattler_roi"),
        "Source Trust": get_count("netrattler_source_trust_scores"),
        "Coverage": get_count("netrattler_source_coverage"),
    }
    print(overview)
    print("Fertig")


if __name__ == "__main__":
    main()
