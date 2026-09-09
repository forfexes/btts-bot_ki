#!/usr/bin/env python3
"""
NETRATTLER ALL SOURCE HARVESTER V34 — DATA LAKE + PLAYER STATS + ODDS + SOURCE FALLBACK
============================================================================

Zweck:
- Holt alles, was wir kostenlos/öffentlich sinnvoll greifen können.
- Speichert Rohdaten zuerst in netrattler_data_lake_raw.
- Baut aus Eventdaten player_match_stats und player_avg_stats.
- Entdeckt neue GitHub/Open-Source Quellen per Tags.
- Macht Upsert/Dedupe über data_hash, damit Supabase nicht zugemüllt wird.
- Läuft unabhängig vom btts_bot.py.

ENV:
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY  empfohlen
SUPABASE_KEY               fallback
GITHUB_TOKEN               optional, höhere Rate Limits
THESPORTSDB_API_KEY        optional
ENABLE_SOCCERDATA=1        standard, nutzt soccerdata wenn installiert
MAX_STATSBOMB_MATCHES=40
MAX_OPENFOOTBALL_FILES=80
MAX_FOOTBALL_DATA_ROWS_PER_CSV=800
SEASONS=2526,2425,2324
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""

NOW = datetime.now(timezone.utc).isoformat()
TODAY = datetime.now(timezone.utc).date().isoformat()

TIMEOUT = 25
UA = "NETRATTLER-AllSourceHarvester/34.0 (+https://github.com/forfexes/btts-bot_ki)"


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"{ts} {level:<7} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────
# BASIC HELPERS
# ─────────────────────────────────────────────────────────────

def stable_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(obj), ensure_ascii=False, sort_keys=True)


def hsh(*parts: Any) -> str:
    raw = "||".join(stable_json(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def norm(s: Any) -> str:
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9äöüßáéíóúàèìòùâêîôûãõñç\s+._/-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def first(d: Dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for n in names:
        if n in d and d.get(n) not in (None, ""):
            return d.get(n)
    return default


def as_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "."))
    except Exception:
        return default


def as_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(str(x).replace(",", ".")))
    except Exception:
        return default


def http_get(url: str, *, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None,
             timeout: int = TIMEOUT, text: bool = False) -> Any:
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, params=params, timeout=timeout)
    r.raise_for_status()
    return r.text if text else r.json()


def chunks(items: List[Dict[str, Any]], n: int = 250):
    for i in range(0, len(items), n):
        yield items[i:i+n]


# ─────────────────────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────────────────────

def sb_headers(prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def sb_insert(table: str, rows: List[Dict[str, Any]], *, on_conflict: Optional[str] = None) -> Tuple[int, int]:
    if not rows:
        return 0, 0
    if not SUPABASE_URL or not SUPABASE_KEY:
        log(f"Supabase ENV fehlt — {table}: {len(rows)} rows nur lokal gezählt", "WARN")
        return 0, len(rows)

    ok = 0
    fail = 0
    params = {}
    prefer = "return=minimal"
    if on_conflict:
        params["on_conflict"] = on_conflict
        prefer = "resolution=merge-duplicates,return=minimal"

    for part in chunks(rows, 200):
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers=sb_headers(prefer),
                params=params,
                data=json.dumps(part, ensure_ascii=False),
                timeout=30,
            )
            if r.status_code in (200, 201, 204):
                ok += len(part)
            else:
                fail += len(part)
                log(f"Supabase {table} HTTP {r.status_code}: {r.text[:240]}", "WARN")
        except Exception as e:
            fail += len(part)
            log(f"Supabase {table}: {str(e)[:160]}", "WARN")
    return ok, fail


def data_lake_row(source: str, source_type: str, entity_type: str, payload: Dict[str, Any],
                  *, url: str = "", league: str = "", season: str = "", match_date: str = "",
                  entity_name: str = "", market: str = "", category: str = "") -> Dict[str, Any]:
    return {
        "source": source,
        "source_type": source_type,
        "url": url,
        "league": league,
        "season": season,
        "match_date": match_date or None,
        "entity_type": entity_type,
        "entity_name": entity_name,
        "market": market,
        "category": category,
        "payload": payload,
        "data_hash": hsh(source, source_type, entity_type, entity_name, market, category, payload),
        "collected_at": NOW,
    }


def push_lake(rows: List[Dict[str, Any]]) -> None:
    ok, fail = sb_insert("netrattler_data_lake_raw", rows, on_conflict="data_hash")
    log(f"data_lake: {ok} ok / {fail} fail")


# ─────────────────────────────────────────────────────────────
# SOURCE REGISTRY + DISCOVERY
# ─────────────────────────────────────────────────────────────

KNOWN_SOURCES = [
    {
        "name": "soccerdata",
        "url": "https://github.com/probberechts/soccerdata",
        "kind": "python_package",
        "tags": ["fbref", "understat", "sofascore", "whoscored", "clubelo", "football-data", "espn", "sofifa", "player-stats"],
        "notes": "Python Scraper-Sammlung für mehrere Football-Datenquellen.",
        "priority": 100,
    },
    {
        "name": "StatsBomb Open Data",
        "url": "https://github.com/statsbomb/open-data",
        "kind": "open_data",
        "tags": ["events", "lineups", "shots", "fouls", "cards", "tackles", "competitions", "free"],
        "notes": "Freie Event- und Lineupdaten, gut für player_match_stats.",
        "priority": 98,
    },
    {
        "name": "statsbombpy",
        "url": "https://github.com/statsbomb/statsbombpy",
        "kind": "python_package",
        "tags": ["statsbomb", "python", "events", "lineups", "free-data"],
        "notes": "Python-Zugriff auf StatsBomb Free Data.",
        "priority": 92,
    },
    {
        "name": "kloppy",
        "url": "https://github.com/PySport/kloppy",
        "kind": "python_package",
        "tags": ["event-data", "tracking-data", "standard-model", "statsbomb", "wyscout", "opta", "sportec"],
        "notes": "Standardisiert Event-/Trackingdaten verschiedener Provider.",
        "priority": 88,
    },
    {
        "name": "openfootball / football.json",
        "url": "https://github.com/openfootball/football.json",
        "kind": "open_data",
        "tags": ["fixtures", "results", "json", "public-domain", "no-key"],
        "notes": "Public-domain JSON-Daten für Ligen/Turniere.",
        "priority": 84,
    },
    {
        "name": "football.db",
        "url": "https://openfootball.github.io/",
        "kind": "open_data",
        "tags": ["fixtures", "results", "football.txt", "public-domain", "no-key"],
        "notes": "Open public domain football database & schema.",
        "priority": 82,
    },
    {
        "name": "Football-Data.co.uk",
        "url": "https://www.football-data.co.uk/data.php",
        "kind": "csv",
        "tags": ["historical", "odds", "results", "cards", "corners", "shots", "free"],
        "notes": "CSV-History für Team/League/Odds/Market-Kontext.",
        "priority": 86,
    },
    {
        "name": "OpenLigaDB",
        "url": "https://api.openligadb.de",
        "kind": "api",
        "tags": ["germany", "fixtures", "results", "free", "no-key"],
        "notes": "Deutsche Ligen, kostenlos ohne Key.",
        "priority": 76,
    },
    {
        "name": "OddsHarvester",
        "url": "https://github.com/jordantete/OddsHarvester",
        "kind": "open_source_scraper",
        "tags": ["oddsportal", "odds", "playwright", "historical-odds", "multi-sport"],
        "notes": "Open-source OddsPortal Harvester, gut als Zusatzpipeline.",
        "priority": 78,
    },
    {
        "name": "soccerapi",
        "url": "https://github.com/S1M0N38/soccerapi",
        "kind": "open_source_scraper",
        "tags": ["odds", "bookmakers", "bet365", "unibet", "888sport"],
        "notes": "Alter/kleiner Bookmaker-Odds-Wrapper. Nur als Discovery/Idee.",
        "priority": 55,
    },
    {
        "name": "EasySoccerData",
        "url": "https://github.com/manucabral/EasySoccerData",
        "kind": "python_package",
        "tags": ["sofascore", "fbref", "promiedos", "player-stats", "live-stats"],
        "notes": "GitHub Topic Quelle für Sofascore/FBref.",
        "priority": 72,
    },
    {
        "name": "football-data-webscraping",
        "url": "https://github.com/sahil-gidwani/football-data-webscraping",
        "kind": "open_source_scraper",
        "tags": ["fbref", "transfermarkt", "understat", "sofascore", "whoscored", "scraper"],
        "notes": "Toolkit/Vorlage für mehrere Football-Scraper.",
        "priority": 70,
    },
    {
        "name": "Reep entity register",
        "url": "https://github.com/withqwerty/reep",
        "kind": "identity_mapping",
        "tags": ["player-ids", "team-ids", "transfermarkt", "fbref", "uefa", "sofascore", "30-providers"],
        "notes": "Identitätsmapping für Spieler/Teams über viele Provider.",
        "priority": 90,
    },
]


def collect_known_sources() -> None:
    rows = []
    lake = []
    for s in KNOWN_SOURCES:
        row = {
            "source_name": s["name"],
            "url": s["url"],
            "kind": s["kind"],
            "tags": s["tags"],
            "score": s["priority"],
            "payload": s,
            "data_hash": hsh("known_source", s["name"], s["url"]),
            "collected_at": NOW,
        }
        rows.append(row)
        lake.append(data_lake_row("KnownSourceRegistry", "registry", "source", s, url=s["url"], entity_name=s["name"], category=s["kind"]))

    ok, fail = sb_insert("netrattler_source_discovery", rows, on_conflict="data_hash")
    log(f"known sources: {len(rows)} | discovery {ok} ok / {fail} fail")
    push_lake(lake)


GITHUB_QUERIES = [
    "soccerdata football data",
    "fbref scraper football",
    "sofascore scraper football",
    "fotmob scraper football",
    "whoscored scraper football",
    "understat football scraper",
    "statsbomb football data",
    "football player stats scraper",
    "soccer player props odds",
    "football betting odds scraper",
    "oddsportal scraper football",
    "pinnacle odds football scraper",
    "bet builder football",
    "same game parlay soccer",
    "football entity mapping fbref sofascore transfermarkt",
]


def github_headers() -> Dict[str, str]:
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def collect_github_discovery() -> None:
    rows = []
    lake = []
    for q in GITHUB_QUERIES:
        try:
            js = http_get(
                "https://api.github.com/search/repositories",
                headers=github_headers(),
                params={"q": q, "sort": "updated", "order": "desc", "per_page": "15"},
                timeout=25,
            )
            for item in js.get("items", [])[:15]:
                payload = {
                    "query": q,
                    "name": item.get("full_name"),
                    "url": item.get("html_url"),
                    "description": item.get("description"),
                    "stars": item.get("stargazers_count"),
                    "forks": item.get("forks_count"),
                    "language": item.get("language"),
                    "topics": item.get("topics") or [],
                    "updated_at": item.get("updated_at"),
                    "license": (item.get("license") or {}).get("spdx_id"),
                }
                tags = sorted(set([norm(q).replace(" ", "-"), str(item.get("language") or "").lower()] + (item.get("topics") or [])))
                score = int(item.get("stargazers_count") or 0) + int(item.get("forks_count") or 0)
                row = {
                    "source_name": item.get("full_name"),
                    "url": item.get("html_url"),
                    "kind": "github_repo",
                    "tags": tags[:30],
                    "score": min(9999, score),
                    "payload": payload,
                    "data_hash": hsh("github_repo", item.get("full_name"), item.get("html_url")),
                    "collected_at": NOW,
                }
                rows.append(row)
                lake.append(data_lake_row("GitHubSearch", "github", "repo", payload, url=item.get("html_url") or "", entity_name=item.get("full_name") or "", category="github_repo"))
            time.sleep(1.2)
        except Exception as e:
            log(f"GitHub query '{q}': {str(e)[:160]}", "WARN")

    # Dedup by data_hash
    uniq = {}
    for r in rows:
        uniq[r["data_hash"]] = r
    rows = list(uniq.values())
    ok, fail = sb_insert("netrattler_source_discovery", rows, on_conflict="data_hash")
    log(f"github discovery: {len(rows)} repos | {ok} ok / {fail} fail")
    push_lake(lake)


# ─────────────────────────────────────────────────────────────
# STATSBOMB OPEN DATA
# ─────────────────────────────────────────────────────────────

SB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


def sb_player_name(ev: Dict[str, Any]) -> str:
    return ((ev.get("player") or {}).get("name") or "").strip()


def sb_team_name(ev: Dict[str, Any]) -> str:
    return ((ev.get("team") or {}).get("name") or "").strip()


def statbomb_event_to_player_stats(events: List[Dict[str, Any]], match_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    agg = defaultdict(lambda: {
        "shots": 0, "shots_on_target": 0, "fouls_committed": 0, "fouls_won": 0,
        "tackles": 0, "yellow_cards": 0, "red_cards": 0, "goals": 0
    })
    team_of = {}
    for ev in events:
        player = sb_player_name(ev)
        if not player:
            continue
        team = sb_team_name(ev)
        team_of[player] = team or team_of.get(player, "")
        typ = ((ev.get("type") or {}).get("name") or "").strip()
        a = agg[player]

        if typ == "Shot":
            a["shots"] += 1
            out = (((ev.get("shot") or {}).get("outcome") or {}).get("name") or "")
            if out in {"Goal", "Saved", "Saved to Post"}:
                a["shots_on_target"] += 1
            if out == "Goal":
                a["goals"] += 1

        elif typ == "Foul Committed":
            a["fouls_committed"] += 1
            card = (((ev.get("foul_committed") or {}).get("card") or {}).get("name") or "")
            if "Yellow" in card:
                a["yellow_cards"] += 1
            if "Red" in card:
                a["red_cards"] += 1

        elif typ == "Foul Won":
            a["fouls_won"] += 1

        elif typ == "Duel":
            duel = ev.get("duel") or {}
            duel_type = ((duel.get("type") or {}).get("name") or "")
            if duel_type == "Tackle":
                a["tackles"] += 1

        elif typ == "Bad Behaviour":
            card = (((ev.get("bad_behaviour") or {}).get("card") or {}).get("name") or "")
            if "Yellow" in card:
                a["yellow_cards"] += 1
            if "Red" in card:
                a["red_cards"] += 1

    rows = []
    for player, a in agg.items():
        match_label = f"{match_info.get('home_team','')} vs {match_info.get('away_team','')}".strip(" vs ")
        payload = {
            "source": "StatsBombOpenData",
            "match_id": match_info.get("match_id"),
            "competition": match_info.get("competition"),
            "season": match_info.get("season"),
            "match_date": match_info.get("match_date"),
            "player": player,
            "team": team_of.get(player, ""),
            **a,
        }
        rows.append({
            "player": player,
            "team": team_of.get(player, ""),
            "match": match_label,
            "league": match_info.get("competition") or "",
            "date": match_info.get("match_date") or None,
            "source": "StatsBombOpenData",
            "match_id": str(match_info.get("match_id") or ""),
            "shots": a["shots"],
            "shots_on_target": a["shots_on_target"],
            "fouls_committed": a["fouls_committed"],
            "fouls_won": a["fouls_won"],
            "tackles": a["tackles"],
            "yellow_cards": a["yellow_cards"],
            "raw": payload,
            "data_hash": hsh("StatsBombOpenData", match_info.get("match_id"), player, payload),
            "collected_at": NOW,
        })
    return rows


def avg_rows_from_match_stats(rows: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    per = defaultdict(list)
    for r in rows:
        per[norm(r.get("player"))].append(r)

    out = []
    metrics = [
        ("shots", "shots", 2),
        ("sot", "shots_on_target", 1),
        ("fouls", "fouls_committed", 2),
        ("fouls_won", "fouls_won", 1),
        ("tackles", "tackles", 2),
        ("yellow_cards", "yellow_cards", 1),
    ]
    for _, rs in per.items():
        if not rs:
            continue
        player = rs[0].get("player") or ""
        team = rs[-1].get("team") or ""
        games = len(rs)
        if games < 1:
            continue
        for metric, col, line in metrics:
            vals = [as_float(r.get(col)) for r in rs]
            avg = sum(vals) / max(1, len(vals))
            hit = 100.0 * sum(1 for v in vals if v >= line) / max(1, len(vals))
            payload = {"player": player, "team": team, "metric": metric, "avg": avg, "hit_rate": hit, "games": games, "source": source, "line": line}
            out.append({
                "player": player,
                "team": team,
                "metric": metric,
                "stat_type": metric,
                "avg": round(avg, 4),
                "hit_rate": round(hit, 2),
                "games": games,
                "source": source,
                "raw": payload,
                "data_hash": hsh(source, "avg", player, metric, payload),
                "updated_at": NOW,
            })
    return out


def collect_statsbomb_open_data() -> None:
    max_matches = int(os.getenv("MAX_STATSBOMB_MATCHES", "40"))
    try:
        comps = http_get(f"{SB_BASE}/competitions.json")
    except Exception as e:
        log(f"StatsBomb competitions: {str(e)[:160]}", "WARN")
        return

    # latest/relevant competitions first
    comps = sorted(comps, key=lambda x: (str(x.get("competition_name")), str(x.get("season_name"))), reverse=True)
    preferred = []
    for c in comps:
        name = str(c.get("competition_name") or "")
        if any(k in name.lower() for k in ["world cup", "euro", "copa america", "champions league", "laliga", "premier league", "bundesliga"]):
            preferred.append(c)
    if not preferred:
        preferred = comps[:10]

    lake_rows = []
    match_stat_rows = []
    used_matches = 0

    for c in preferred[:12]:
        if used_matches >= max_matches:
            break
        cid = c.get("competition_id")
        sid = c.get("season_id")
        try:
            matches = http_get(f"{SB_BASE}/matches/{cid}/{sid}.json")
        except Exception:
            continue
        for m in matches:
            if used_matches >= max_matches:
                break
            mid = m.get("match_id")
            try:
                events = http_get(f"{SB_BASE}/events/{mid}.json")
            except Exception:
                continue

            home = ((m.get("home_team") or {}).get("home_team_name") or "")
            away = ((m.get("away_team") or {}).get("away_team_name") or "")
            mi = {
                "match_id": mid,
                "competition": c.get("competition_name"),
                "season": c.get("season_name"),
                "match_date": m.get("match_date"),
                "home_team": home,
                "away_team": away,
            }

            lake_rows.append(data_lake_row(
                "StatsBombOpenData", "events", "match_events",
                {"match": mi, "events_count": len(events), "sample": events[:20]},
                url=f"https://github.com/statsbomb/open-data/blob/master/data/events/{mid}.json",
                league=mi["competition"] or "", season=mi["season"] or "", match_date=mi["match_date"] or "",
                entity_name=f"{home} vs {away}", category="events"
            ))

            match_stat_rows.extend(statbomb_event_to_player_stats(events, mi))
            used_matches += 1

    log(f"StatsBomb: matches={used_matches}, player_match_rows={len(match_stat_rows)}")
    push_lake(lake_rows)
    ok, fail = sb_insert("player_match_stats", match_stat_rows, on_conflict="data_hash")
    log(f"player_match_stats StatsBomb: {ok} ok / {fail} fail")

    # player_avg_stats is a Supabase VIEW in this repo, not a writable table.
    # The view recalculates averages from player_match_stats automatically.
    # Do not insert here, otherwise Supabase returns PGRST204 if the view schema
    # does not contain legacy columns such as "avg".
    avg_rows = avg_rows_from_match_stats(match_stat_rows, "StatsBombOpenData")
    log(f"player_avg_stats StatsBomb: view-only — {len(avg_rows)} averages skipped, calculated by DB view")


# ─────────────────────────────────────────────────────────────
# FOOTBALL-DATA.CO.UK
# ─────────────────────────────────────────────────────────────

FD_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC",
    "D1", "D2",
    "I1", "I2",
    "SP1", "SP2",
    "F1", "F2",
    "N1",
    "B1",
    "P1",
    "T1",
    "G1",
    "SC0", "SC1", "SC2", "SC3",
]

def collect_football_data_uk() -> None:
    seasons = [s.strip() for s in os.getenv("SEASONS", "2526,2425,2324").split(",") if s.strip()]
    max_rows = int(os.getenv("MAX_FOOTBALL_DATA_ROWS_PER_CSV", "800"))
    lake_rows = []
    count = 0

    for season in seasons:
        for code in FD_LEAGUES:
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
            try:
                text = http_get(url, text=True, timeout=20)
                if not text or "<html" in text[:200].lower():
                    continue
                reader = csv.DictReader(StringIO(text))
                local = 0
                for row in reader:
                    if not row:
                        continue
                    home = row.get("HomeTeam") or row.get("Home") or ""
                    away = row.get("AwayTeam") or row.get("Away") or ""
                    dt = row.get("Date") or ""
                    payload = dict(row)
                    payload["season_code"] = season
                    payload["league_code"] = code
                    lake_rows.append(data_lake_row(
                        "Football-Data.co.uk", "csv", "match",
                        payload, url=url, league=code, season=season,
                        match_date="", entity_name=f"{home} vs {away}", category="historical_match"
                    ))
                    count += 1
                    local += 1
                    if local >= max_rows:
                        break
            except Exception as e:
                log(f"FDCOUK {season}/{code}: {str(e)[:100]}", "WARN")
    log(f"Football-Data.co.uk rows={count}")
    push_lake(lake_rows)


# ─────────────────────────────────────────────────────────────
# OPENFOOTBALL / FOOTBALL.JSON
# ─────────────────────────────────────────────────────────────

OPENFOOTBALL_REPOS = [
    "openfootball/football.json",
    "openfootball/worldcup.json",
    "openfootball/euro.json",
    "openfootball/worldcup",
    "openfootball/south-america",
    "openfootball/europe",
    "openfootball/champions-league",
    "openfootball/internationals",
    "openfootball/world",
    "openfootball/england",
    "openfootball/deutschland",
    "openfootball/italy",
    "openfootball/espana",
    "openfootball/france",
    "openfootball/players",
    "openfootball/clubs",
    "martj42/international_results",
    "withqwerty/reep",
    "salimt/football-datasets",
]


def collect_openfootball() -> None:
    """Fetch actual data files from every free GitHub data repo; one repo failure never stops the next."""
    max_files = int(os.getenv("MAX_OPENFOOTBALL_FILES", "180"))
    rows = []
    files_seen = 0

    for repo in OPENFOOTBALL_REPOS:
        if files_seen >= max_files:
            break
        try:
            meta = http_get(f"https://api.github.com/repos/{repo}", headers=github_headers(), timeout=25)
            branch = meta.get("default_branch") or "master"
            tree = http_get(f"https://api.github.com/repos/{repo}/git/trees/{branch}",
                            headers=github_headers(), params={"recursive": "1"}, timeout=35)
        except Exception as e:
            log(f"GitHub data tree {repo}: {str(e)[:120]} — next source", "WARN")
            continue
        candidates = []
        for item in tree.get("tree", []):
            path = item.get("path") or ""
            if item.get("type") != "blob" or not path.lower().endswith((".json", ".csv", ".tsv", ".txt", ".ndjson", ".jsonl")):
                continue
            if any(x in path.lower() for x in ("node_modules/", "vendor/", ".github/", "test/", "spec/")):
                continue
            candidates.append(path)
        candidates.sort(key=lambda p: (0 if any(k in p.lower() for k in ("2026", "2025", "match", "result", "player", "club", "data")) else 1, p))
        repo_count = 0
        for path in candidates:
            if files_seen >= max_files:
                break
            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
            try:
                raw = http_get(raw_url, timeout=30, text=True)
            except Exception:
                continue
            # Keep payload bounded; huge public datasets are represented by a sample + metadata.
            max_chars = int(os.getenv("MAX_GITHUB_RAW_CHARS", "1500000"))
            payload = {
                "repo": repo, "path": path,
                "content": raw[:max_chars], "truncated": len(raw) > max_chars,
                "size_chars": len(raw),
            }
            rows.append(data_lake_row(
                f"GitHub:{repo}", path.rsplit(".", 1)[-1].lower(), "open_source_file",
                payload, url=raw_url, league=repo.split("/")[-1],
                season=next((x for x in path.split("/") if re.match(r"^20\\d{2}(?:-\\d{2})?$", x)), ""),
                entity_name=path, category="fixtures_results_players_identity"
            ))
            files_seen += 1
            repo_count += 1
            if repo_count >= int(os.getenv("MAX_FILES_PER_GITHUB_REPO", "25")):
                break
            time.sleep(0.08)
        log(f"GitHub data {repo}: files={repo_count}")
        if len(rows) >= 100:
            push_lake(rows); rows = []
    if rows:
        push_lake(rows)
    log(f"GitHub/OpenFootball actual files={files_seen}")


# ─────────────────────────────────────────────────────────────
# OPENLIGADB
# ─────────────────────────────────────────────────────────────

def collect_openligadb() -> None:
    rows = []
    try:
        leagues = http_get("https://api.openligadb.de/getavailableleagues", timeout=20)
    except Exception as e:
        log(f"OpenLigaDB leagues: {str(e)[:120]}", "WARN")
        return

    for lg in leagues[:40]:
        shortcut = lg.get("leagueShortcut")
        season = lg.get("leagueSeason")
        if not shortcut or not season:
            continue
        try:
            matches = http_get(f"https://api.openligadb.de/getmatchdata/{shortcut}/{season}", timeout=20)
        except Exception:
            continue
        rows.append(data_lake_row(
            "OpenLigaDB", "api", "league_matches",
            {"league": lg, "matches": matches[:200] if isinstance(matches, list) else matches},
            url=f"https://api.openligadb.de/getmatchdata/{shortcut}/{season}",
            league=shortcut, season=str(season), category="fixtures_results"
        ))
        time.sleep(0.15)

    log(f"OpenLigaDB league payloads={len(rows)}")
    push_lake(rows)


# ─────────────────────────────────────────────────────────────
# THESPORTSDB OPTIONAL
# ─────────────────────────────────────────────────────────────

def collect_thesportsdb() -> None:
    key = os.getenv("THESPORTSDB_API_KEY") or ""
    if not key:
        log("TheSportsDB: kein Key — übersprungen (optional)", "WARN")
        return

    # Basic soccer search / events by popular league IDs can be expanded.
    league_ids = [4328, 4331, 4332, 4334, 4335, 4337, 4338, 4344]
    rows = []
    for lid in league_ids:
        try:
            js = http_get(f"https://www.thesportsdb.com/api/v1/json/{key}/eventsnextleague.php", params={"id": str(lid)}, timeout=20)
            rows.append(data_lake_row(
                "TheSportsDB", "api", "next_league_events", js,
                url="https://www.thesportsdb.com/api.php", league=str(lid), category="fixtures"
            ))
        except Exception as e:
            log(f"TheSportsDB {lid}: {str(e)[:100]}", "WARN")
    log(f"TheSportsDB payloads={len(rows)}")
    push_lake(rows)


# ─────────────────────────────────────────────────────────────
# SOCCERDATA OPTIONAL
# ─────────────────────────────────────────────────────────────

def df_to_records(df: Any, limit: int = 2500) -> List[Dict[str, Any]]:
    try:
        df = df.reset_index()
        records = df.head(limit).to_dict(orient="records")
        clean = []
        for r in records:
            out = {}
            for k, v in r.items():
                try:
                    if hasattr(v, "isoformat"):
                        v = v.isoformat()
                    elif str(type(v)).find("numpy") >= 0:
                        v = v.item()
                except Exception:
                    v = str(v)
                if isinstance(v, float) and (v != v):
                    v = None
                out[str(k)] = v
            clean.append(out)
        return clean
    except Exception:
        return []


def collect_soccerdata_optional() -> None:
    if os.getenv("ENABLE_SOCCERDATA", "1") != "1":
        log("soccerdata optional: ENABLE_SOCCERDATA=0 — nur registriert, nicht ausgeführt")
        return

    try:
        import soccerdata as sd  # type: ignore
    except Exception as e:
        log(f"soccerdata nicht installiert/importierbar: {e}", "WARN")
        return

    leagues = [x.strip() for x in os.getenv("SOCCERDATA_LEAGUES", "ENG-Premier League,ESP-La Liga,ITA-Serie A,GER-Bundesliga,FRA-Ligue 1").split(",") if x.strip()]
    seasons = [x.strip() for x in os.getenv("SOCCERDATA_SEASONS", "2025-2026,2024-2025").split(",") if x.strip()]
    rows = []

    # FootballData via soccerdata
    try:
        fd = sd.FootballData(leagues=leagues, seasons=seasons)
        games = fd.read_games()
        recs = df_to_records(games, 3000)
        rows.append(data_lake_row("soccerdata.FootballData", "python_package", "games", {"rows": recs}, category="games"))
        log(f"soccerdata FootballData rows={len(recs)}")
    except Exception as e:
        log(f"soccerdata FootballData: {str(e)[:140]}", "WARN")

    # FBref player stats
    try:
        fb = sd.FBref(leagues=leagues, seasons=seasons)
        for stat_type in ["standard", "shooting", "misc", "defense", "passing", "playing_time"]:
            try:
                df = fb.read_player_season_stats(stat_type=stat_type)
                recs = df_to_records(df, 3000)
                rows.append(data_lake_row("soccerdata.FBref", "python_package", "player_season_stats", {"stat_type": stat_type, "rows": recs}, category=stat_type))
                log(f"soccerdata FBref {stat_type} rows={len(recs)}")
            except Exception as e:
                log(f"soccerdata FBref {stat_type}: {str(e)[:120]}", "WARN")
    except Exception as e:
        log(f"soccerdata FBref init: {str(e)[:140]}", "WARN")

    # Understat where available
    try:
        us = sd.Understat(leagues=leagues, seasons=seasons)
        for method in ["read_team_match_stats", "read_player_season_stats", "read_schedule"]:
            if hasattr(us, method):
                try:
                    df = getattr(us, method)()
                    recs = df_to_records(df, 3000)
                    rows.append(data_lake_row("soccerdata.Understat", "python_package", method, {"rows": recs}, category=method))
                    log(f"soccerdata Understat {method} rows={len(recs)}")
                except Exception as e:
                    log(f"soccerdata Understat {method}: {str(e)[:120]}", "WARN")
    except Exception as e:
        log(f"soccerdata Understat init: {str(e)[:140]}", "WARN")

    push_lake(rows)



# ─────────────────────────────────────────────────────────────
# BOOKMAKER ODDS — every source with fallback
# ─────────────────────────────────────────────────────────────

def collect_bookmaker_odds() -> None:
    try:
        from netrattler_odds_harvester import collect_live_all, persist_odds
        rows = collect_live_all(TODAY)
        result = persist_odds(rows, "netrattler_odds_snapshot.json")
        log(f"Odds sources: raw={len(rows)} odds_history={result.get('odds_history', 0)} data_lake={result.get('data_lake', 0)}")
    except Exception as exc:
        log(f"Odds sources failed: {str(exc)[:180]} — harvester continues", "WARN")


# ─────────────────────────────────────────────────────────────
# LOCAL SUMMARY
# ─────────────────────────────────────────────────────────────

def write_local_summary() -> None:
    summary = {
        "collected_at": NOW,
        "env": {
            "SUPABASE_URL": bool(SUPABASE_URL),
            "SUPABASE_KEY": bool(SUPABASE_KEY),
            "GITHUB_TOKEN": bool(GITHUB_TOKEN),
            "ENABLE_SOCCERDATA": os.getenv("ENABLE_SOCCERDATA", "1"),
        },
        "sources": KNOWN_SOURCES,
        "github_queries": GITHUB_QUERIES,
    }
    with open("netrattler_all_source_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log("lokal gespeichert: netrattler_all_source_summary.json")


# ─────────────────────────────────────────────────────────────
# V30 Source Hub addon
# ─────────────────────────────────────────────────────────────
def run_source_hub_v30() -> None:
    try:
        from netrattler_source_hub import write_summary, persist_source_health
        write_summary("netrattler_source_hub_summary.json")
        saved = persist_source_health(SUPABASE_URL, SUPABASE_KEY)
        log(f"V30 Source Hub health saved={saved}")
    except Exception as exc:
        log(f"V30 Source Hub addon failed: {str(exc)[:120]}", "WARN")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main() -> int:
    log("=" * 70)
    log("NETRATTLER ALL SOURCE HARVESTER startet")
    log("=" * 70)

    if not SUPABASE_URL or not SUPABASE_KEY:
        log("SUPABASE_URL/SUPABASE_KEY fehlen — Script läuft, aber Supabase Inserts schlagen fehl.", "WARN")

    # Discovery/registry work stays sequential because it updates shared source state.
    for name, fn in [("known_sources", collect_known_sources), ("github_discovery", collect_github_discovery)]:
        log(f"--- {name} ---")
        try:
            fn()
        except Exception as e:
            log(f"{name} HARD FAIL: {str(e)[:240]}", "ERROR")

    # Independent historical/public feeds are IO-bound; running them concurrently avoids
    # adding every network timeout serially. Each collector already has its own error guard.
    parallel_jobs = [
        ("football_data_uk", collect_football_data_uk),
        ("statsbomb_open_data", collect_statsbomb_open_data),
        ("openfootball", collect_openfootball),
        ("openligadb", collect_openligadb),
        ("thesportsdb", collect_thesportsdb),
    ]
    try:
        workers = max(1, min(6, int(os.getenv("HARVEST_PARALLEL_WORKERS", "4"))))
    except Exception:
        workers = 4
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in parallel_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                fut.result()
            except Exception as e:
                log(f"{name} HARD FAIL: {str(e)[:240]}", "ERROR")

    # soccerdata is optional/heavy and can have process/global caches: keep it isolated.
    log("--- soccerdata_all_adapters ---")
    try:
        collect_soccerdata_optional()
    except Exception as e:
        log(f"soccerdata_all_adapters HARD FAIL: {str(e)[:240]}", "ERROR")

    # Bookmaker collection has its own dedicated Odds Harvester workflow. Do not pay
    # the same Playwright cost here unless explicitly requested.
    if os.getenv("ALL_SOURCE_INCLUDE_ODDS", "false").lower() in {"1", "true", "yes", "on"}:
        log("--- bookmaker_odds_all_fallbacks ---")
        try:
            collect_bookmaker_odds()
        except Exception as e:
            log(f"bookmaker_odds_all_fallbacks HARD FAIL: {str(e)[:240]}", "ERROR")
    else:
        log("Bookmaker odds übersprungen — eigener Odds-Harvester ist aktiv")

    write_local_summary()
    run_source_hub_v30()
    log("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from concurrent.futures import ThreadPoolExecutor, as_completed
