#!/usr/bin/env python3
"""
NETRATTLER Source Hub V34
=========================
Modulare, fehlertolerante Integration der GitHub/Open-Source-Quellen:
- probberechts/soccerdata
- statsbomb/open-data
- davidrocha9/fotmob-scraper (Logik/Schema als Adapter, optional)
- withqwerty/reep
- OddsHarvester
- Simatwa/livescore-api
- openfootball/football.json, worldcup.json, south-america, europe, champions-league,
  internationals, players, clubs
- salimt/football-datasets
- eddwebster/football_analytics (Feature-/Research-Katalog)

Keine Quelle darf den Hauptlauf stoppen. Alles ist optional, mit Timeout, Cache,
Health-Status und normalisiertem Datenformat.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from netrattler_identity_hub import normalize_team_name, teams_match

UA = "NETRATTLER-SourceHub/34.0 (+https://github.com/forfexes/btts-bot_ki)"
DEFAULT_TIMEOUT = int(os.getenv("NTR_SOURCE_TIMEOUT", "18"))
CACHE_DIR = os.getenv("NTR_SOURCE_CACHE_DIR", ".netrattler_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


@dataclass
class SourceAdapter:
    name: str
    repo: str
    tier: str
    role: str
    enabled_env: str = ""
    default_enabled: bool = True
    package: str = ""
    license_note: str = "check-upstream"
    requires_playwright: bool = False
    urls: Tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        if self.enabled_env:
            raw = os.getenv(self.enabled_env, "")
            if raw:
                return raw.lower() in {"1", "true", "yes", "on"}
        return self.default_enabled


SOURCES: Tuple[SourceAdapter, ...] = (
    SourceAdapter("soccerdata", "probberechts/soccerdata", "player_stats", "FBref/SofaScore/ESPN/Understat/WhoScored/ClubElo wrapper", "ENABLE_SOCCERDATA", True, "soccerdata", "Apache-2.0"),
    SourceAdapter("statsbomb_open_data", "statsbomb/open-data", "event_data", "historical event/player features", "ENABLE_STATSBOMB", True, "", "open-data terms", urls=("https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",)),
    SourceAdapter("fotmob_scraper", "davidrocha9/fotmob-scraper", "player_stats", "FotMob fixtures/squads/player stats/Supabase sync pattern", "ENABLE_FOTMOB", True, "", "check-upstream"),
    SourceAdapter("reep_identity", "withqwerty/reep", "identity", "provider identity mapping: Transfermarkt/FBref/UEFA/SofaScore", "ENABLE_REEP", True, "", "check-upstream"),
    SourceAdapter("oddsharvester", "jordantete/OddsHarvester", "odds_clv", "OddsPortal historical/closing odds fallback via Playwright", "ENABLE_ODDSHARVESTER", True, "", "MIT", True),
    SourceAdapter("livescore_api", "Simatwa/livescore-api", "results_live", "Livescore.com unofficial results fallback", "ENABLE_LIVESCORE_API", True, "livescore_api", "MIT-ish check", True),
    SourceAdapter("openfootball_football_json", "openfootball/football.json", "results", "free fixture/result fallback", "ENABLE_OPENFOOTBALL", True, "", "CC0", urls=("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json",)),
    SourceAdapter("openfootball_worldcup_json", "openfootball/worldcup.json", "worldcup_results", "World Cup JSON settlement fallback", "ENABLE_OPENFOOTBALL_WC", True, "", "CC0"),
    SourceAdapter("openfootball_south_america", "openfootball/south-america", "south_america_results", "Ecuador/Brazil/Argentina/Libertadores settlement fallback", "ENABLE_OPENFOOTBALL_SA", True, "", "CC0"),
    SourceAdapter("openfootball_europe", "openfootball/europe", "europe_results", "European cups and national results fallback", "ENABLE_OPENFOOTBALL_EUROPE", True, "", "CC0"),
    SourceAdapter("openfootball_champions_league", "openfootball/champions-league", "ucl_results", "UCL settlement fallback", "ENABLE_OPENFOOTBALL_UCL", True, "", "CC0"),
    SourceAdapter("openfootball_internationals", "openfootball/internationals", "international_results", "national-team fixtures/results fallback", "ENABLE_OPENFOOTBALL_INTL", True, "", "CC0"),
    SourceAdapter("openfootball_players", "openfootball/players", "identity", "player alias/source registry", "ENABLE_OPENFOOTBALL_PLAYERS", True, "", "CC0"),
    SourceAdapter("openfootball_clubs", "openfootball/clubs", "identity", "club alias/source registry", "ENABLE_OPENFOOTBALL_CLUBS", True, "", "CC0"),
    SourceAdapter("football_datasets", "salimt/football-datasets", "features", "Transfermarkt-like features: players/clubs/values/transfers", "ENABLE_FOOTBALL_DATASETS", True, "", "check-upstream"),
    SourceAdapter("football_analytics", "eddwebster/football_analytics", "feature_catalog", "research catalog for models/features/data recipes", "ENABLE_FOOTBALL_ANALYTICS", True, "", "check-upstream"),
    SourceAdapter("martj42_international_results", "martj42/international_results", "results", "international match results", "ENABLE_MARTJ42", True, "", "open-data"),
    SourceAdapter("openfootball_worldcup_txt", "openfootball/worldcup", "worldcup_results", "World Cup Football.TXT source", "ENABLE_OPENFOOTBALL_WC", True, "", "CC0"),
    SourceAdapter("openfootball_world", "openfootball/world", "world_results", "worldwide Football.TXT leagues", "ENABLE_OPENFOOTBALL_WORLD", True, "", "CC0"),
    SourceAdapter("openfootball_euro", "openfootball/euro.json", "euro_results", "European Championship JSON", "ENABLE_OPENFOOTBALL_EURO", True, "", "CC0"),
)

FEATURE_RECIPES: Dict[str, Dict[str, Any]] = {
    "xg_xa": {"source": "football_analytics/understat/statsbomb", "markets": ["score", "assist", "shots", "sot"]},
    "xthreat": {"source": "football_analytics/socceraction", "markets": ["passes", "progressive_carries", "assist"]},
    "pressing": {"source": "statsbomb/open-data", "markets": ["tackles_committed", "fouls", "interceptions"]},
    "duels": {"source": "statsbomb/open-data/fotmob", "markets": ["tackles_received", "fouls_won", "aerial_duels"]},
    "identity": {"source": "reep/openfootball_players/openfootball_clubs", "markets": ["all"]},
    "clv": {"source": "pinnacle/oddsharvester", "markets": ["all"]},
}


def log(msg: str) -> None:
    print(msg, flush=True)


def _headers() -> Dict[str, str]:
    headers = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def cache_path(key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", key)[:180]
    return os.path.join(CACHE_DIR, safe + ".json")


def http_get(url: str, *, timeout: int = DEFAULT_TIMEOUT, kind: str = "json", cache_key: str = "") -> Optional[Any]:
    key = cache_key or hashlib.sha1(url.encode()).hexdigest()
    path = cache_path(key)
    ttl = int(os.getenv("NTR_SOURCE_CACHE_TTL_SECONDS", "21600"))
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("data")
        except Exception:
            pass
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        if not r.ok:
            return None
        data = r.json() if kind == "json" else r.text
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}, f, ensure_ascii=False)
        except Exception:
            pass
        return data
    except Exception:
        return None


def source_health_snapshot() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in SOURCES:
        package_ok = True
        if src.package:
            package_ok = importlib.util.find_spec(src.package) is not None
        rows.append({
            "source": src.name,
            "repo": src.repo,
            "tier": src.tier,
            "role": src.role,
            "enabled": src.enabled,
            "package": src.package,
            "package_ok": package_ok,
            "requires_playwright": src.requires_playwright,
            "license_note": src.license_note,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def parse_openfootball_json(payload: Any, day: str, *, source: str, league: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows
    matches = payload.get("matches") or payload.get("games") or []
    for m in matches:
        if not isinstance(m, dict):
            continue
        mday = str(m.get("date") or m.get("matchDate") or "")[:10]
        if day and mday != day:
            continue
        score = m.get("score") or m.get("goals") or {}
        ft = score.get("ft") or score.get("fulltime") or score.get("fullTime") or [] if isinstance(score, dict) else []
        ht = score.get("ht") or score.get("halftime") or score.get("halfTime") or [] if isinstance(score, dict) else []
        if isinstance(ft, dict):
            ft = [ft.get("home"), ft.get("away")]
        if not isinstance(ft, (list, tuple)) or len(ft) < 2 or ft[0] is None or ft[1] is None:
            continue
        home = m.get("team1") or m.get("home") or m.get("home_team") or m.get("homeTeam")
        away = m.get("team2") or m.get("away") or m.get("away_team") or m.get("awayTeam")
        try:
            hs, aw = int(ft[0]), int(ft[1])
        except Exception:
            continue
        row = {
            "source": source,
            "event_id": hashlib.sha1(f"{source}|{day}|{home}|{away}".encode()).hexdigest()[:24],
            "match_date": day,
            "home_team": str(home or ""),
            "away_team": str(away or ""),
            "home_score": hs,
            "away_score": aw,
            "ht_home": int(ht[0]) if isinstance(ht, (list, tuple)) and len(ht) >= 2 and str(ht[0]).isdigit() else None,
            "ht_away": int(ht[1]) if isinstance(ht, (list, tuple)) and len(ht) >= 2 and str(ht[1]).isdigit() else None,
            "league": league or str(payload.get("name") or payload.get("league") or ""),
            "country": str(payload.get("country") or ""),
            "status": "finished",
            "raw": m,
        }
        rows.append(row)
    return rows


def parse_football_txt(text: str, day: str, *, source: str, league: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not text:
        return rows
    current_date = ""
    # Handles lines like: [Sat Jul/15] England 2-1 Argentina
    score_re = re.compile(r"^(?P<home>.+?)\s+(?P<hs>\d+)\s*[-:]\s*(?P<aw>\d+)\s+(?P<away>.+?)\s*$")
    iso_re = re.compile(r"(20\d{2}-\d{2}-\d{2})")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        iso = iso_re.search(line)
        if iso:
            current_date = iso.group(1)
            continue
        if day and current_date and current_date != day:
            continue
        m = score_re.match(line)
        if not m:
            continue
        home, away = m.group("home").strip(), m.group("away").strip()
        rows.append({
            "source": source,
            "event_id": hashlib.sha1(f"{source}|{day}|{home}|{away}".encode()).hexdigest()[:24],
            "match_date": day or current_date,
            "home_team": home,
            "away_team": away,
            "home_score": int(m.group("hs")),
            "away_score": int(m.group("aw")),
            "ht_home": None,
            "ht_away": None,
            "league": league,
            "country": "",
            "status": "finished",
            "raw": {"line": line},
        })
    return rows


def openfootball_url_candidates(day: str) -> List[Tuple[str, str, str, str]]:
    year = int(day[:4])
    season = f"{year-1}-{str(year)[-2:]}"
    next_season = f"{year}-{str(year+1)[-2:]}"
    candidates: List[Tuple[str, str, str, str]] = []

    # football.json major leagues
    for code, league in [("en.1", "Premier League"), ("de.1", "Bundesliga"), ("es.1", "La Liga"), ("it.1", "Serie A"), ("fr.1", "Ligue 1")]:
        for s in [season, next_season]:
            candidates.append((f"https://raw.githubusercontent.com/openfootball/football.json/master/{s}/{code}.json", "openfootball_football_json", league, "json"))

    # World Cup and internationals: paths differ by repo, failures are normal.
    for url in [
        "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
        "https://raw.githubusercontent.com/openfootball/worldcup.json/master/worldcup.json",
        "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026.json",
        "https://raw.githubusercontent.com/openfootball/internationals/master/2026/worldcup.txt",
        "https://raw.githubusercontent.com/openfootball/internationals/master/worldcup/2026.txt",
    ]:
        candidates.append((url, "openfootball_worldcup_json" if url.endswith(".json") else "openfootball_internationals", "FIFA World Cup", "json" if url.endswith(".json") else "txt"))

    # South America / Ecuador / Libertadores common naming variants.
    for url, league in [
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/ec-1.txt", "Ecuador"),
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/ec.1.txt", "Ecuador"),
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/copa-libertadores.txt", "Copa Libertadores"),
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/copa-sudamericana.txt", "Copa Sudamericana"),
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/br.1.txt", "Brazil Serie A"),
        ("https://raw.githubusercontent.com/openfootball/south-america/master/2026/ar.1.txt", "Argentina"),
    ]:
        candidates.append((url, "openfootball_south_america", league, "txt"))
    return candidates


def fetch_openfootball_results(day: str, *, max_urls: int = 60) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for url, source, league, kind in openfootball_url_candidates(day)[:max_urls]:
        payload = http_get(url, kind=kind, cache_key=f"{source}_{day}_{hashlib.sha1(url.encode()).hexdigest()[:10]}")
        if not payload:
            continue
        found = parse_openfootball_json(payload, day, source=source, league=league) if kind == "json" else parse_football_txt(str(payload), day, source=source, league=league)
        for row in found:
            key = (normalize_team_name(row["home_team"]), normalize_team_name(row["away_team"]), row["match_date"], row["home_score"], row["away_score"])
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def fetch_livescore_results(day: str) -> List[Dict[str, Any]]:
    if os.getenv("ENABLE_LIVESCORE_API", "0").lower() not in {"1", "true", "yes", "on"}:
        return []
    try:
        # Package APIs have changed across versions; keep this isolated.
        import livescore_api  # type: ignore  # noqa: F401
    except Exception:
        return []
    # Do not assume a stable API. This module is a guarded placeholder until the package is verified in Actions.
    return []


def public_result_fallbacks(day: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.extend(fetch_openfootball_results(day))
    rows.extend(fetch_livescore_results(day))
    return rows


def rows_to_settlement_results(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "date": r.get("match_date"),
            "match_date": r.get("match_date"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "home_score": r.get("home_score"),
            "away_score": r.get("away_score"),
            "ht_home": r.get("ht_home"),
            "ht_away": r.get("ht_away"),
            "league": r.get("league"),
            "source": r.get("source"),
            "raw": r.get("raw") or r,
            "_result_table": r.get("source") or "netrattler_source_hub",
        })
    return out


def sb_headers(key: str, prefer: str = "resolution=merge-duplicates,return=minimal") -> Dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer}


def supabase_upsert(table: str, rows: Sequence[Dict[str, Any]], *, conflict: str = "source,event_id", url: str = "", key: str = "") -> int:
    url = (url or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not url or not key or not rows:
        return 0
    saved = 0
    for i in range(0, len(rows), 500):
        chunk = list(rows[i:i+500])
        try:
            r = requests.post(f"{url}/rest/v1/{table}", params={"on_conflict": conflict}, headers=sb_headers(key), data=json.dumps(chunk, ensure_ascii=False, default=str), timeout=30)
            if r.status_code in (200, 201, 204):
                saved += len(chunk)
        except Exception:
            pass
    return saved


def persist_source_health(url: str = "", key: str = "") -> int:
    rows = []
    for row in source_health_snapshot():
        rows.append({
            "component": "source_hub:" + row["source"],
            "status": "enabled" if row["enabled"] else "disabled",
            "row_count": 1 if row.get("package_ok") else 0,
            "message": f"{row['repo']} | {row['role']} | package_ok={row.get('package_ok')}",
            "checked_at": row["checked_at"],
        })
    return supabase_upsert("best_database_status", rows, conflict="component", url=url, key=key)


def write_summary(path: str = "netrattler_source_hub_summary.json") -> None:
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": source_health_snapshot(), "feature_recipes": FEATURE_RECIPES}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    write_summary()
    persist_source_health()
    print("✅ Source Hub summary written")
