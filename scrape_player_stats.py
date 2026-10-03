#!/usr/bin/env python3
"""
NETRATTLER - scrape_player_stats.py — V36H VERIFIED DAILY
=====================================
Täglich nach Spielende:
1. Match-Ergebnisse von ESPN + TheSportsDB + OpenFootball → Supabase match_results
2. Player Stats von FBref/FotMob/SofaScore/StatsBomb/soccerdata/GitHub datasets → Supabase player_match_stats

Läuft täglich 02:00 UTC via scrape_player_stats.yml
"""

import argparse, csv, gzip, io, json, os, re, time, hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                 or os.environ.get("SUPABASE_KEY", ""))
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_GROUP_STATS") or os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


USE_SOFASCORE = os.environ.get("USE_SOFASCORE", "true").lower() in ("1", "true", "yes", "on")
USE_FOTMOB = os.environ.get("USE_FOTMOB", "true").lower() in ("1", "true", "yes", "on")
USE_STATSBOMB = os.environ.get("USE_STATSBOMB", "true").lower() in ("1", "true", "yes", "on")
USE_FBREF = os.environ.get("USE_FBREF", "true").lower() in ("1", "true", "yes", "on")
USE_SOCCERDATA = os.environ.get("USE_SOCCERDATA", "false").lower() in ("1", "true", "yes", "on")
SOURCE_MAX_EVENTS = int(os.environ.get("SOURCE_MAX_EVENTS", "80"))
SOURCE_SLEEP = float(os.environ.get("SOURCE_SLEEP", "0.35"))

USE_GITHUB_OPEN_SOURCES = os.environ.get("USE_GITHUB_OPEN_SOURCES", "true").lower() in ("1", "true", "yes", "on")
USE_ODDSHARVESTER_STYLE = os.environ.get("USE_ODDSHARVESTER_STYLE", "true").lower() in ("1", "true", "yes", "on")
GITHUB_SOURCE_MAX_FILES = int(os.environ.get("GITHUB_SOURCE_MAX_FILES", "120"))
GITHUB_SOURCE_TIMEOUT = int(os.environ.get("GITHUB_SOURCE_TIMEOUT", "25"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ENABLE_REEP_IDENTITY = os.environ.get("ENABLE_REEP_IDENTITY", "true").lower() in ("1", "true", "yes", "on")
REEP_MAX_ROWS = int(os.environ.get("REEP_MAX_ROWS", "600000"))
IDENTITY_REFERENCE_HEALTHCHECK = os.environ.get(
    "IDENTITY_REFERENCE_HEALTHCHECK", "false"
).lower() in ("1", "true", "yes", "on")
REEP_CACHE_DAYS = int(os.environ.get("REEP_CACHE_DAYS", "7"))
CACHE_DIR = Path(os.environ.get("NETRATTLER_CACHE_DIR", ".netrattler_cache"))
REEP_CACHE_FILE = CACHE_DIR / "reep_identity_map.json.gz"
_IDENTITY_NAME_TO_ID: Dict[str, str] = {}


def _norm_entity_name(value: Any) -> str:
    value = str(value or "").lower().strip()
    value = re.sub(r"[^a-z0-9à-ž]+", " ", value, flags=re.I)
    return " ".join(value.split())



def _playwright_get(url: str, timeout_ms: int = 60000) -> Optional[str]:
    """Letzter Browser-Fallback für blockierte HTML-/JSON-Endpunkte."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                extra_http_headers={
                    "Accept": HEADERS["Accept"],
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
            body = page.locator("body").inner_text(timeout=10000)
            html = page.content()
            status = response.status if response else 0
            browser.close()
            if status and status >= 400:
                return None
            # JSON-Endpunkte werden im Browser meist als Body-Text angezeigt.
            stripped = body.strip()
            if stripped.startswith(("{", "[")):
                return stripped
            return html
    except Exception as exc:
        print(f"  ⚠️  Playwright Fallback: {str(exc)[:120]}")
        return None


def _fetch_text(url: str, *, params: Optional[dict] = None,
                timeout: int = 20, allow_playwright: bool = True) -> Optional[str]:
    """curl_cffi (TLS-Impersonation) → requests → cloudscraper → Playwright."""
    # 0) 🚀 curl_cffi zuerst — umgeht SofaScore/FBref TLS-Block (403)
    try:
        from curl_cffi import requests as _creq
        full_url = requests.Request("GET", url, params=params).prepare().url
        r = _creq.get(full_url, impersonate="chrome", timeout=timeout)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass

    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.ok and r.text:
            return r.text
        first_status = r.status_code
    except Exception:
        first_status = 0

    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        r = scraper.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.ok and r.text:
            return r.text
        second_status = r.status_code
    except Exception:
        second_status = 0

    if allow_playwright:
        full_url = requests.Request("GET", url, params=params).prepare().url
        value = _playwright_get(full_url)
        if value:
            return value

    print(f"  ⚠️  Quelle nicht erreichbar: {url[:70]} ({first_status}/{second_status})")
    return None


def _fetch_json(url: str, *, params: Optional[dict] = None,
                timeout: int = 20, allow_playwright: bool = True) -> Optional[Any]:
    raw = _fetch_text(
        url, params=params, timeout=timeout, allow_playwright=allow_playwright
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        # Browser-HTML kann JSON in <pre> enthalten.
        match = re.search(r"<pre[^>]*>(.*?)</pre>", raw, re.I | re.S)
        if match:
            import html as _html
            try:
                return json.loads(_html.unescape(match.group(1)))
            except Exception:
                return None
        return None


# ── Supabase ──────────────────────────────────────────────────────────────────

def _dedupe_rows(rows: list, conflict: str = None) -> list:
    if not rows:
        return []
    valid = [row for row in rows if isinstance(row, dict)]
    if not conflict:
        return valid

    keys = [x.strip() for x in conflict.split(",") if x.strip()]
    unique, passthrough = {}, []
    for row in valid:
        values = tuple(str(row.get(key) or "").strip() for key in keys)
        if any(not value for value in values):
            passthrough.append(row)
        else:
            unique[values] = row
    return list(unique.values()) + passthrough


def _rows_by_keyset(rows: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """PostgREST bulk inserts require identical object keys inside one request."""
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, dict):
            groups[tuple(sorted(row.keys()))].append(row)
    return list(groups.values())


def _sb_post(table: str, rows: list, conflict: str = None, *,
             base_url: str = None, api_key: str = None) -> int:
    """Key-homogeneous batch upsert with a last-resort single-row fallback."""
    base_url = base_url or SUPABASE_URL
    api_key = api_key or SUPABASE_KEY
    if not rows or not base_url or not api_key:
        return 0

    clean_rows = _dedupe_rows(rows, conflict)
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    params = {"on_conflict": conflict} if conflict else {}
    endpoint = f"{base_url.rstrip('/')}/rest/v1/{table}"
    total = 0
    group_count = 0

    for same_keys in _rows_by_keyset(clean_rows):
        group_count += 1
        for i in range(0, len(same_keys), 500):
            chunk = same_keys[i:i + 500]
            try:
                response = requests.post(
                    endpoint, headers=headers, params=params, json=chunk, timeout=90
                )
            except requests.RequestException as exc:
                print(f"  ⚠️  Supabase {table}: {exc}")
                continue

            if response.ok:
                total += len(chunk)
                continue

            print(
                f"  ⚠️  Supabase {table} {response.status_code}: "
                f"{response.text[:300]}"
            )
            # Keep the run useful if one source has a schema-specific row.
            for row in chunk:
                try:
                    one = requests.post(
                        endpoint, headers=headers, params=params, json=[row], timeout=30
                    )
                    if one.ok:
                        total += 1
                    else:
                        print(
                            f"     ❌ {row.get('source')} / {row.get('event_id')} / "
                            f"{row.get('player_id')} / {row.get('stat_name')}: "
                            f"{one.status_code} {one.text[:140]}"
                        )
                except requests.RequestException:
                    continue

    if group_count > 1:
        print(f"  ℹ️  Supabase {table}: {group_count} homogene Key-Gruppen")
    return total



# ── Zweite Datenbank: Spieler-Historie L20 (breites Format) ─────────────────
PLAYERS_DB_URL = (os.environ.get("SUPABASE_PLAYERS_URL") or "").strip()
PLAYERS_DB_KEY = (os.environ.get("SUPABASE_PLAYERS_SERVICE_KEY") or "").strip()
PLAYER_LOG_KEEP_GAMES = int(os.environ.get("PLAYER_LOG_KEEP_GAMES", "20"))
_WIDE_STATS = (
    "minutes", "shots", "sot", "goals", "assists", "fouls_committed",
    "fouls_won", "tackles", "yellow_cards", "red_cards", "saves",
    "offsides", "passes", "xg", "xa",
)


def _long_to_wide(rows: list) -> list:
    """EAV-Rows -> eine Zeile pro Spieler+Spiel. Nur EINE Quelle (fotmob bevorzugt),
    weil Event-IDs je Quelle verschieden sind und Spiele sonst doppelt zählen."""
    by_source: Dict[str, list] = {}
    for r in rows:
        if r.get("stat_name") in _WIDE_STATS and r.get("stat_value") is not None:
            by_source.setdefault(str(r.get("source")), []).append(r)
    src = "fotmob" if by_source.get("fotmob") else next(iter(by_source), None)
    if not src:
        return []
    wide: Dict[tuple, Dict[str, Any]] = {}
    for r in by_source[src]:
        name = str(r.get("player_name") or "").strip()
        if not name or name == "Unknown":
            continue
        key = f"{_norm_entity_name(name)}|{_norm_entity_name(r.get('team') or '')}"
        ev = str(r.get("event_id"))
        rec = wide.setdefault((key, ev), {
            "player_key": key, "event_id": ev, "source": src,
            "player_id": r.get("player_id"), "player_name": name,
            "team": r.get("team"), "league": r.get("league"),
            "home_team": r.get("home_team"), "away_team": r.get("away_team"),
            "match_date": str(r.get("match_date") or "")[:10] or None,
        })
        rec[r["stat_name"]] = r["stat_value"]
    out = list(wide.values())
    for rec in out:  # alle Spalten gesetzt -> homogene Keys fuer PostgREST
        for st in _WIDE_STATS:
            rec.setdefault(st, None)
    return out


def write_player_game_log(rows: list) -> int:
    """Schreibt breite Spieler-Spiel-Zeilen in die zweite DB und kappt auf L20 Spiele."""
    if not PLAYERS_DB_URL or not PLAYERS_DB_KEY:
        print("  ℹ️  Zweite DB (SUPABASE_PLAYERS_URL/_SERVICE_KEY) nicht gesetzt — übersprungen")
        return 0
    wide = _long_to_wide(rows)
    saved = _sb_post("player_game_log", wide, conflict="player_key,event_id",
                     base_url=PLAYERS_DB_URL, api_key=PLAYERS_DB_KEY)
    try:
        r = requests.post(
            f"{PLAYERS_DB_URL.rstrip('/')}/rest/v1/rpc/prune_player_game_log",
            headers={"apikey": PLAYERS_DB_KEY, "Authorization": f"Bearer {PLAYERS_DB_KEY}",
                     "Content-Type": "application/json"},
            json={"keep_games": PLAYER_LOG_KEEP_GAMES}, timeout=120,
        )
        print(f"  🧹 player_game_log L{PLAYER_LOG_KEEP_GAMES}-Prune: "
              f"{'ok, gelöscht=' + r.text.strip() if r.ok else 'HTTP ' + str(r.status_code)}")
    except requests.RequestException as exc:
        print(f"  ⚠️ player_game_log Prune: {str(exc)[:120]}")
    print(f"  💾 player_game_log: {saved} Spieler-Spiel-Zeilen")
    return saved

def prune_player_history_l15() -> bool:
    """Keep detailed raw EAV rows only for each player's latest 15 distinct matches.

    Season/365d aggregates live separately; this function only controls detailed
    match history growth. It is best-effort so a cleanup outage never breaks the
    daily collector.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    # RPC is installed separately in Supabase. Keeping the call here makes L15
    # retention automatic as soon as the DB has enough room to accept cleanup.
    endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/netrattler_prune_player_history_l15"
    try:
        r = requests.post(endpoint, headers=headers, json={}, timeout=120)
        if r.ok:
            print("  🧹 L15 player-history retention applied")
            return True
        print(f"  ⚠️ L15 retention unavailable {r.status_code}: {r.text[:180]}")
    except requests.RequestException as exc:
        print(f"  ⚠️ L15 retention deferred: {str(exc)[:160]}")
    return False


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                  timeout=15)


# ══════════════════════════════════════════════════════════════════════════════
# 1. MATCH RESULTS (ESPN + TheSportsDB + OpenFootball)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_espn_results(date_str: str) -> List[Dict]:
    """ESPN Scoreboard — bestätigt funktionierend auf GitHub Actions."""
    results = []
    espn_date = date_str.replace("-", "")
    urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={espn_date}",
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={espn_date}",
    ]
    for url in urls:
        try:
            time.sleep(2)  # Rate limit
            r = requests.get(url, headers=HEADERS, timeout=12)
            if not r.ok:
                continue
            for ev in r.json().get("events", []):
                comp = ev.get("competitions", [{}])[0]
                if not comp.get("status", {}).get("type", {}).get("completed"):
                    continue
                teams = {t["homeAway"]: t for t in comp.get("competitors", [])}
                h = teams.get("home", {})
                a = teams.get("away", {})
                hs = h.get("score")
                as_ = a.get("score")
                if hs is None or as_ is None:
                    continue
                ev_id = str(comp.get("id", ev.get("id", "")))
                results.append({
                    "source": "espn",
                    "event_id": ev_id,
                    "match_date": date_str,
                    "home_team": h.get("team", {}).get("displayName", ""),
                    "away_team": a.get("team", {}).get("displayName", ""),
                    "home_score": int(hs),
                    "away_score": int(as_),
                    "ht_home": None,
                    "ht_away": None,
                    "league": (ev.get("season") or {}).get("slug", ""),
                    "country": "",
                    "status": "finished",
                })
        except Exception as e:
            print(f"  ⚠️  ESPN {url[-30:]}: {e}")
    print(f"  ✅ ESPN: {len(results)} Ergebnisse für {date_str}")
    return results


def fetch_thesportsdb_results(date_str: str) -> List[Dict]:
    """TheSportsDB — bestätigt funktionierend auf GitHub Actions."""
    results = []
    try:
        time.sleep(2)  # Rate limit
        r = requests.get(
            "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
            params={"d": date_str, "s": "Soccer"},
            headers=HEADERS, timeout=15,
        )
        if r.ok:
            for ev in r.json().get("events") or []:
                hs = ev.get("intHomeScore")
                as_ = ev.get("intAwayScore")
                if hs is None or as_ is None:
                    continue
                results.append({
                    "source": "thesportsdb",
                    "event_id": str(ev.get("idEvent", "")),
                    "match_date": date_str,
                    "home_team": ev.get("strHomeTeam", ""),
                    "away_team": ev.get("strAwayTeam", ""),
                    "home_score": int(hs),
                    "away_score": int(as_),
                    "ht_home": None,
                    "ht_away": None,
                    "league": ev.get("strLeague", ""),
                    "country": ev.get("strCountry", ""),
                    "status": "finished",
                })
    except Exception as e:
        print(f"  ⚠️  TheSportsDB: {e}")
    print(f"  ✅ TheSportsDB: {len(results)} Ergebnisse für {date_str}")
    return results


def fetch_fifa_results(date_str: str) -> List[Dict]:
    """FIFA API — WM 2026 + andere FIFA-Turniere."""
    results = []
    try:
        time.sleep(2)
        # WM 2026 season ID
        r = requests.get(
            "https://api.fifa.com/api/v3/calendar/matches",
            params={"idseason": "2024", "idCompetition": "17", "language": "en",
                    "count": "500", "dateFrom": date_str, "dateTo": date_str},
            headers=HEADERS, timeout=12,
        )
        if r.ok:
            for m in r.json().get("Results", []):
                hs = m.get("HomeTeamScore")
                as_ = m.get("AwayTeamScore")
                if hs is None or as_ is None:
                    continue
                home = (m.get("HomeTeam") or {}).get("TeamName", [{}])[0].get("Description", "")
                away = (m.get("AwayTeam") or {}).get("TeamName", [{}])[0].get("Description", "")
                results.append({
                    "source": "fifa", "event_id": str(m.get("IdMatch", "")),
                    "match_date": date_str, "home_team": home, "away_team": away,
                    "home_score": int(hs), "away_score": int(as_),
                    "ht_home": None, "ht_away": None,
                    "league": "FIFA World Cup", "country": "", "status": "finished",
                })
        if results:
            print(f"  ✅ FIFA API: {len(results)} Ergebnisse für {date_str}")
    except Exception as e:
        print(f"  ⚠️  FIFA API: {str(e)[:60]}")
    return results


def fetch_weltfussball_results(home_team: str, away_team: str, date_str: str) -> Optional[Dict]:
    """Weltfussball.de — sehr statisch, gut für historische Daten."""
    try:
        time.sleep(2)
        # Suche via Weltfussball Spielplan
        year = date_str[:4]
        for league_path in ["bundesliga", "premier-league", "la-liga-primera-division"]:
            r = requests.get(
                f"https://www.weltfussball.de/spielplan/{league_path}-{int(year)-1}-{year[-2:]}/",
                headers=HEADERS, timeout=10,
            )
            if not r.ok:
                continue
            # Einfacher Textvergleich
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("table.standard_tabelle tr"):
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                match_date_cell = cells[0].get_text(strip=True)
                if date_str.replace("-", ".")[8:10] + "." + date_str[5:7] not in match_date_cell:
                    continue
                h = cells[2].get_text(strip=True)
                a = cells[4].get_text(strip=True)
                score_text = cells[3].get_text(strip=True)
                if ":" in score_text and h and a:
                    try:
                        hs, as_ = score_text.split(":")
                        return {
                            "source": "weltfussball", "event_id": f"wf_{h}_{a}_{date_str}",
                            "match_date": date_str, "home_team": h, "away_team": a,
                            "home_score": int(hs.strip()), "away_score": int(as_.strip()),
                            "ht_home": None, "ht_away": None,
                            "league": league_path, "country": "", "status": "finished",
                        }
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def fetch_openfootball_results(date_str: str) -> List[Dict]:
    """OpenFootball GitHub raw — immer erreichbar."""
    results = []
    year = date_str[:4]
    prev_year = str(int(year) - 1)
    season = f"{prev_year}-{year[-2:]}"

    leagues = [
        (f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/de.1.json", "Bundesliga"),
        (f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json", "Premier League"),
        (f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/es.1.json", "La Liga"),
        (f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/it.1.json", "Serie A"),
        (f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/fr.1.json", "Ligue 1"),
    ]
    for url, league_name in leagues:
        try:
            time.sleep(1)  # Rate limit
            r = requests.get(url, timeout=8)
            if not r.ok:
                continue
            for m in r.json().get("matches", []):
                if m.get("date") != date_str or not m.get("score"):
                    continue
                ft = m["score"].get("ft", [])
                ht = m["score"].get("ht", [])
                if len(ft) < 2:
                    continue
                key = f"{m.get('team1','')}_vs_{m.get('team2','')}_{date_str}"
                results.append({
                    "source": "openfootball",
                    "event_id": key,
                    "match_date": date_str,
                    "home_team": m.get("team1", ""),
                    "away_team": m.get("team2", ""),
                    "home_score": int(ft[0]),
                    "away_score": int(ft[1]),
                    "ht_home": int(ht[0]) if len(ht) >= 2 else None,
                    "ht_away": int(ht[1]) if len(ht) >= 2 else None,
                    "league": league_name,
                    "country": "",
                    "status": "finished",
                })
        except Exception:
            continue
    if results:
        print(f"  ✅ OpenFootball: {len(results)} Ergebnisse für {date_str}")
    return results


def scrape_results(date_str: str) -> int:
    """Holt Ergebnisse aus allen Quellen und speichert in match_results."""
    print(f"\n📅 Scrape Ergebnisse für {date_str}")
    all_results = []
    # Result sources are independent HTTP feeds. Parallel execution prevents one blocked
    # endpoint timeout from serially delaying every other source.
    result_jobs = [
        ("ESPN", lambda: fetch_espn_results(date_str)),
        ("TheSportsDB", lambda: fetch_thesportsdb_results(date_str)),
        ("OpenFootball", lambda: fetch_openfootball_results(date_str)),
        ("FIFA", lambda: fetch_fifa_results(date_str)),
        ("GitHub open results", lambda: fetch_github_open_source_results(date_str)),
        ("LiveScore API", lambda: fetch_livescore_api_results(date_str)),
    ]
    workers = max(1, min(6, int(os.environ.get("DAILY_RESULTS_PARALLEL_WORKERS", "4"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in result_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                all_results.extend(fut.result() or [])
            except Exception as exc:
                print(f"  ⚠️  {name}: {str(exc)[:100]}")

    # Deduplizieren (ESPN hat Vorrang weil vollständiger)
    seen = set()
    unique = []
    for r in all_results:
        key = r["event_id"]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    saved = _sb_post("match_results", unique, conflict="source,event_id")
    print(f"  💾 {saved} Ergebnisse in Supabase gespeichert")
    return saved



# ══════════════════════════════════════════════════════════════════════════════
# 1B. GITHUB / OPEN-SOURCE SOURCE HUB — ALL SOURCES V34 FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

GITHUB_OPEN_SOURCE_REPOS = [
    # Result / match repositories — JSON and Football.TXT
    ("openfootball", "football.json", "results"),
    ("openfootball", "worldcup.json", "results"),
    ("openfootball", "euro.json", "results"),
    ("openfootball", "worldcup", "results"),
    ("openfootball", "south-america", "results"),
    ("openfootball", "europe", "results"),
    ("openfootball", "champions-league", "results"),
    ("openfootball", "internationals", "results"),
    ("openfootball", "world", "results"),
    ("martj42", "international_results", "results"),

    # Identity / reference / player datasets
    ("openfootball", "players", "identity"),
    ("openfootball", "clubs", "identity"),
    ("withqwerty", "reep", "identity"),
    ("salimt", "football-datasets", "player_dataset"),
    ("eddwebster", "football_analytics", "catalog"),

    # Libraries / scraper adapters. These are executed by direct adapters below.
    ("probberechts", "soccerdata", "library"),
    ("davidrocha9", "fotmob-scraper", "library"),
    ("jordantete", "OddsHarvester", "odds"),
    ("Simatwa", "livescore-api", "live_api"),
]


def _github_api_json(url: str) -> Optional[Any]:
    headers = dict(HEADERS)
    headers["Accept"] = "application/vnd.github+json"
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        r = requests.get(url, headers=headers, timeout=GITHUB_SOURCE_TIMEOUT)
        if r.ok:
            return r.json()
        print(f"  ⚠️ GitHub API {r.status_code}: {url[:80]}")
    except Exception as exc:
        print(f"  ⚠️ GitHub API: {str(exc)[:100]}")
    return None


def _github_default_branch(owner: str, repo: str) -> Optional[str]:
    data = _github_api_json(f"https://api.github.com/repos/{owner}/{repo}")
    if isinstance(data, dict):
        return data.get("default_branch") or "master"
    return None


def _github_tree_files(owner: str, repo: str, max_files: int = None) -> List[str]:
    """List raw-eligible files from a GitHub repo. No token needed; fails soft on rate-limit."""
    if max_files is None:
        max_files = GITHUB_SOURCE_MAX_FILES
    branch = _github_default_branch(owner, repo) or "master"
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    data = _github_api_json(url)
    if not isinstance(data, dict) or "tree" not in data:
        return []
    candidates = []
    allowed = (".json", ".csv", ".tsv", ".parquet", ".ndjson", ".jsonl", ".txt")
    for item in data.get("tree", []):
        path = item.get("path") or ""
        if item.get("type") != "blob" or not path.lower().endswith(allowed):
            continue
        lower = path.lower()
        # Skip giant or irrelevant files first; still keep broad data folders.
        if any(skip in lower for skip in [".ipynb_checkpoints", "node_modules", "venv/", "docs/"]):
            continue
        candidates.append(path)
    # Prefer files likely to contain match/player data.
    def score(path: str) -> int:
        p = path.lower()
        s = 0
        for key in ["match", "result", "fixture", "game", "season", "events", "player", "club", "team", "data"]:
            if key in p:
                s += 3
        if p.endswith(".json"):
            s += 2
        if p.endswith(".csv"):
            s += 2
        if "readme" in p:
            s -= 10
        return -s
    candidates = sorted(candidates, key=score)
    return candidates[:max_files]


def _github_raw(owner: str, repo: str, path: str) -> Optional[str]:
    branch = _github_default_branch(owner, repo) or "master"
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    return _fetch_text(url, timeout=GITHUB_SOURCE_TIMEOUT, allow_playwright=False)


def _parse_score_pair(score_obj: Any):
    if isinstance(score_obj, dict):
        for key in ["ft", "fulltime", "full_time", "score"]:
            val = score_obj.get(key)
            if isinstance(val, list) and len(val) >= 2:
                return val[0], val[1]
            if isinstance(val, dict):
                h = val.get("home") or val.get("home_team") or val.get("team1")
                a = val.get("away") or val.get("away_team") or val.get("team2")
                if h is not None and a is not None:
                    return h, a
        h = score_obj.get("home") or score_obj.get("home_score") or score_obj.get("team1")
        a = score_obj.get("away") or score_obj.get("away_score") or score_obj.get("team2")
        if h is not None and a is not None:
            return h, a
    if isinstance(score_obj, list) and len(score_obj) >= 2:
        return score_obj[0], score_obj[1]
    return None, None


def _to_int_score(v):
    try:
        if v is None or v == "":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None


def _extract_matches_from_json(data: Any) -> List[Dict[str, Any]]:
    """Generic parser for openfootball-style JSON and simple match JSON lists."""
    if isinstance(data, dict):
        for key in ["matches", "games", "fixtures", "results", "rounds"]:
            val = data.get(key)
            if isinstance(val, list):
                if key == "rounds":
                    out = []
                    for r in val:
                        out.extend(_extract_matches_from_json(r))
                    return out
                return val
        return []
    if isinstance(data, list):
        # Flatten round containers.
        out = []
        for item in data:
            if isinstance(item, dict) and any(k in item for k in ["matches", "games", "fixtures"]):
                out.extend(_extract_matches_from_json(item))
            elif isinstance(item, dict):
                out.append(item)
        return out
    return []


def _github_match_to_result(m: Dict[str, Any], date_str: str, source: str, league: str = None) -> Optional[Dict[str, Any]]:
    mdate = str(m.get("date") or m.get("match_date") or m.get("utcDate") or m.get("game_date") or "")[:10]
    if not mdate or mdate != date_str:
        return None
    home = m.get("team1") or m.get("home") or m.get("home_team") or m.get("HomeTeam")
    away = m.get("team2") or m.get("away") or m.get("away_team") or m.get("AwayTeam")
    score_obj = m.get("score") or m.get("result") or m
    hg, ag = _parse_score_pair(score_obj)
    hg = _to_int_score(m.get("home_score") or m.get("FTHG") or hg)
    ag = _to_int_score(m.get("away_score") or m.get("FTAG") or ag)
    if not home or not away or hg is None or ag is None:
        return None
    ht = m.get("score", {}).get("ht", []) if isinstance(m.get("score"), dict) else []
    event_id = m.get("id") or m.get("match_id") or hashlib.md5(f"{source}|{date_str}|{home}|{away}".encode()).hexdigest()[:20]
    return {
        "source": source[:80],
        "event_id": str(event_id),
        "match_date": date_str,
        "league": league or m.get("league") or m.get("competition") or source,
        "home_team": str(home).strip(),
        "away_team": str(away).strip(),
        "home_score": hg,
        "away_score": ag,
        "ht_home": _to_int_score(ht[0]) if isinstance(ht, list) and len(ht) >= 2 else None,
        "ht_away": _to_int_score(ht[1]) if isinstance(ht, list) and len(ht) >= 2 else None,
    }


def _parse_csv_results(raw: str, date_str: str, source: str) -> List[Dict[str, Any]]:
    import csv, io
    out = []
    try:
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            rdate = _parse_any_date(row.get("date") or row.get("Date") or row.get("match_date"))
            # Football-data Date can be DD/MM/YY; keep generic but avoid false positives.
            if rdate != date_str:
                continue
            home = row.get("home_team") or row.get("home") or row.get("HomeTeam")
            away = row.get("away_team") or row.get("away") or row.get("AwayTeam")
            hg = _to_int_score(row.get("home_score") or row.get("FTHG") or row.get("home_goals"))
            ag = _to_int_score(row.get("away_score") or row.get("FTAG") or row.get("away_goals"))
            if home and away and hg is not None and ag is not None:
                eid = row.get("id") or row.get("match_id") or hashlib.md5(f"{source}|{date_str}|{home}|{away}".encode()).hexdigest()[:20]
                out.append({
                    "source": source[:80], "event_id": str(eid), "match_date": date_str,
                    "league": row.get("league") or row.get("competition") or source,
                    "home_team": home, "away_team": away,
                    "home_score": hg, "away_score": ag,
                    "ht_home": _to_int_score(row.get("HTHG") or row.get("ht_home")),
                    "ht_away": _to_int_score(row.get("HTAG") or row.get("ht_away")),
                })
    except Exception:
        return []
    return out



def _parse_any_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _football_txt_date_aliases(date_str: str) -> List[str]:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return [
        date_str,
        dt.strftime("%b/%d").replace("/0", "/"),
        dt.strftime("%b %d").replace(" 0", " "),
        dt.strftime("%d %b").lstrip("0"),
        dt.strftime("%a %b/%d").replace("/0", "/"),
        dt.strftime("%a %b %d").replace(" 0", " "),
    ]


def _parse_football_txt_results(raw: str, date_str: str, source: str, league: str) -> List[Dict[str, Any]]:
    """Parse common Football.TXT score lines, including date lines followed by matches."""
    rows: List[Dict[str, Any]] = []
    aliases = [a.lower() for a in _football_txt_date_aliases(date_str)]
    current_target_date = False
    score_re = re.compile(
        r"^\s*(?:\(\d+\)\s*)?(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+)?"
        r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[/. ]\d{1,2}\s+)?"
        r"(?:\d{1,2}:\d{2}\s+)?(?P<home>.+?)\s+(?P<h>\d+)\s*[-–:]\s*(?P<a>\d+)"
        r"(?:\s+(?:a\.e\.t\.|pen\.|pens\.))?(?:\s*\([^)]*\))?\s+(?P<away>.+?)"
        r"(?:\s+@\s+.*)?$", re.I,
    )
    for raw_line in raw.splitlines():
        line = re.sub(r"\s+#.*$", "", raw_line).strip()
        if not line:
            continue
        low = line.lower()
        if any(alias in low for alias in aliases):
            current_target_date = True
        elif re.match(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", line, re.I) or re.match(
            r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[/. ]\d{1,2}\b", line, re.I
        ):
            current_target_date = any(alias in low for alias in aliases)
        m = score_re.match(line)
        if not m:
            continue
        # A match line can carry its own date alias; otherwise use the previous date heading.
        if not current_target_date and not any(alias in low for alias in aliases):
            continue
        home = re.sub(r"\s+", " ", m.group("home")).strip(" |-•")
        away = re.sub(r"\s+", " ", m.group("away")).strip(" |-•")
        if len(home) < 2 or len(away) < 2:
            continue
        event_id = hashlib.sha1(f"{source}|{date_str}|{home}|{away}".encode()).hexdigest()[:24]
        rows.append({
            "source": source[:80], "event_id": event_id, "match_date": date_str,
            "league": league, "home_team": home, "away_team": away,
            "home_score": int(m.group("h")), "away_score": int(m.group("a")),
            "ht_home": None, "ht_away": None,
        })
    return rows


def _load_reep_identity_index() -> int:
    """Load canonical REEP IDs with a persistent GitHub Actions cache."""
    global _IDENTITY_NAME_TO_ID
    if _IDENTITY_NAME_TO_ID or not ENABLE_REEP_IDENTITY:
        return len(_IDENTITY_NAME_TO_ID)

    try:
        max_age = max(1, REEP_CACHE_DAYS) * 86400
        if (
            REEP_CACHE_FILE.exists()
            and time.time() - REEP_CACHE_FILE.stat().st_mtime <= max_age
        ):
            with gzip.open(REEP_CACHE_FILE, "rt", encoding="utf-8") as handle:
                cached = json.load(handle)
            if isinstance(cached, dict):
                _IDENTITY_NAME_TO_ID = {
                    str(key): str(value) for key, value in cached.items()
                    if key and value
                }
                print(
                    f"  ✅ REEP canonical identities (Cache): "
                    f"{len(_IDENTITY_NAME_TO_ID)}"
                )
                return len(_IDENTITY_NAME_TO_ID)
    except Exception as exc:
        print(f"  ⚠️ REEP Cache ignoriert: {str(exc)[:100]}")

    urls = [
        "https://raw.githubusercontent.com/withqwerty/reep/main/data/people.csv",
        "https://raw.githubusercontent.com/withqwerty/reep/main/data/names.csv",
    ]
    for url in urls:
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=90) as response:
                if not response.ok:
                    continue
                lines = (
                    line.decode("utf-8", errors="replace")
                    for line in response.iter_lines() if line
                )
                reader = csv.DictReader(lines)
                for index, row in enumerate(reader):
                    if index >= REEP_MAX_ROWS:
                        break
                    rid = row.get("reep_id") or row.get("id")
                    names = [row.get("name"), row.get("full_name"), row.get("alias")]
                    if not rid:
                        continue
                    for name in names:
                        key = _norm_entity_name(name)
                        if key:
                            _IDENTITY_NAME_TO_ID.setdefault(key, str(rid))
            if _IDENTITY_NAME_TO_ID:
                break
        except Exception as exc:
            print(f"  ⚠️ REEP identity: {str(exc)[:100]}")

    if _IDENTITY_NAME_TO_ID:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = REEP_CACHE_FILE.with_suffix(".tmp.gz")
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as handle:
                json.dump(_IDENTITY_NAME_TO_ID, handle, ensure_ascii=False)
            os.replace(tmp, REEP_CACHE_FILE)
        except Exception as exc:
            print(f"  ⚠️ REEP Cache konnte nicht gespeichert werden: {str(exc)[:80]}")

    print(
        f"  {'✅' if _IDENTITY_NAME_TO_ID else '⚪'} "
        f"REEP canonical identities: {len(_IDENTITY_NAME_TO_ID)}"
    )
    return len(_IDENTITY_NAME_TO_ID)


def fetch_github_open_source_results(date_str: str) -> List[Dict[str, Any]]:
    """All free GitHub result sources that can provide real match results."""
    if not USE_GITHUB_OPEN_SOURCES:
        return []
    rows: List[Dict[str, Any]] = []
    for owner, repo, kind in GITHUB_OPEN_SOURCE_REPOS:
        if kind not in {"results"}:
            continue
        label = f"github:{owner}/{repo}"
        try:
            files = _github_tree_files(owner, repo)
            hit = 0
            for path in files:
                lower = path.lower()
                # Date/year filter keeps runtime sane but still broad.
                if date_str[:4] not in lower and not any(k in lower for k in ["match", "result", "fixture", "season", "worldcup", "cup", "league"]):
                    continue
                raw = _github_raw(owner, repo, path)
                if not raw:
                    continue
                parsed = []
                if lower.endswith((".json", ".ndjson", ".jsonl")):
                    try:
                        if lower.endswith((".ndjson", ".jsonl")):
                            data = [json.loads(x) for x in raw.splitlines() if x.strip().startswith("{")]
                        else:
                            data = json.loads(raw)
                        for m in _extract_matches_from_json(data):
                            r = _github_match_to_result(m, date_str, label, league=repo)
                            if r:
                                parsed.append(r)
                    except Exception:
                        parsed = []
                elif lower.endswith((".csv", ".tsv")):
                    parsed = _parse_csv_results(raw, date_str, label)
                elif lower.endswith(".txt"):
                    # Football.TXT repositories contain many historical seasons. A bare
                    # "Sep 17" heading is not enough to prove it belongs to target year.
                    # Require explicit target-year evidence in the file path/content before
                    # assigning target date; this prevents old matches being written as today.
                    target_year = date_str[:4]
                    year_evidence = target_year in lower or target_year in raw
                    if year_evidence:
                        parsed = _parse_football_txt_results(raw, date_str, label, repo)
                    else:
                        parsed = []
                if parsed:
                    rows.extend(parsed)
                    hit += len(parsed)
                if hit >= SOURCE_MAX_EVENTS:
                    break
                time.sleep(SOURCE_SLEEP)
            print(f"  {'✅' if hit else '⚪'} {label}: {hit}")
        except Exception as e:
            print(f"  ⚠️  {label}: {str(e)[:100]}")
    return rows


def fetch_livescore_api_results(date_str: str) -> List[Dict[str, Any]]:
    """Simatwa/livescore-api style: only if user provides a free/non-paid endpoint/key."""
    endpoint = os.environ.get("LIVESCORE_API_ENDPOINT", "").strip()
    key = os.environ.get("LIVESCORE_API_KEY", "").strip()
    if not endpoint:
        print("  ⚪ Simatwa/livescore-api: kein freier Endpoint gesetzt")
        return []
    try:
        params = {"date": date_str}
        if key:
            params["key"] = key
        data = _fetch_json(endpoint, params=params, timeout=25, allow_playwright=False)
        matches = _extract_matches_from_json(data)
        out = []
        for m in matches:
            r = _github_match_to_result(m, date_str, "livescore_api", league=m.get("league"))
            if r:
                out.append(r)
        print(f"  {'✅' if out else '⚪'} Simatwa/livescore-api endpoint: {len(out)}")
        return out
    except Exception as e:
        print(f"  ⚠️  Simatwa/livescore-api: {str(e)[:100]}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 2. PLAYER STATS (FBref via Playwright + StatsBomb GitHub)
# ══════════════════════════════════════════════════════════════════════════════

_SB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
_SB_LEAGUE_MAP = {
    "Bundesliga": (9, 281), "La Liga": (11, 90), "Ligue 1": (7, 235),
    "FIFA World Cup": (43, 106), "WM 2026": (43, 106),
    "Copa America": (223, 282), "UEFA Euro": (55, 282),
}


def _make_stat_row(source, event_id, player_id, player_name, stat_name, stat_value,
                   team=None, league=None, home_team=None, away_team=None, match_date=None):
    return {
        "source": source, "event_id": str(event_id),
        "player_id": str(player_id) if player_id else _IDENTITY_NAME_TO_ID.get(_norm_entity_name(player_name)),
        "player_name": player_name or "Unknown",
        "team": team, "league": league,
        "home_team": home_team, "away_team": away_team,
        "match_date": match_date,
        "stat_name": stat_name,
        "stat_value": float(stat_value) if isinstance(stat_value, (int, float)) else None,
        "stat_text": None if isinstance(stat_value, (int, float)) else str(stat_value),
        "raw": {},
    }


def scrape_statsbomb_league(league_name: str) -> List[Dict]:
    """
    StatsBomb Open Data. Aggregiert Ereignisse zuerst pro Spieler/Spiel.
    Dadurch wird aus 5 Schuss-Events wirklich stat_value=5 statt fünf kollidierenden Rows.
    """
    comp = _SB_LEAGUE_MAP.get(league_name)
    if not comp:
        return []

    comp_id, season_id = comp
    rows = []
    matches = _fetch_json(
        f"{_SB_BASE}/matches/{comp_id}/{season_id}.json",
        allow_playwright=False,
    )
    if not isinstance(matches, list):
        return []

    for match in matches[-8:]:
        mid = match.get("match_id")
        home = (match.get("home_team") or {}).get("home_team_name", "")
        away = (match.get("away_team") or {}).get("away_team_name", "")
        mdate = match.get("match_date", "")
        events = _fetch_json(f"{_SB_BASE}/events/{mid}.json", allow_playwright=False)
        if not isinstance(events, list):
            continue

        totals = defaultdict(lambda: defaultdict(float))
        meta = {}

        for ev in events:
            player_obj = ev.get("player") or {}
            player = player_obj.get("name", "")
            pid = player_obj.get("id", "")
            team = (ev.get("team") or {}).get("name", "")
            if not player:
                continue

            key = (str(pid or player), player)
            meta[key] = team
            ev_type = (ev.get("type") or {}).get("name", "")

            if ev_type == "Shot":
                totals[key]["totalShots"] += 1
                shot = ev.get("shot") or {}
                outcome = (shot.get("outcome") or {}).get("name", "")
                totals[key]["xg"] += float(shot.get("statsbomb_xg") or 0)
                if outcome in ("Goal", "Saved", "Saved To Post"):
                    totals[key]["shotsOnTarget"] += 1
                if outcome == "Goal":
                    totals[key]["goals"] += 1
            elif ev_type == "Pass":
                totals[key]["passes"] += 1
                p = ev.get("pass") or {}
                if p.get("goal_assist"):
                    totals[key]["goalAssist"] += 1
                if p.get("shot_assist"):
                    totals[key]["keyPasses"] += 1
            elif ev_type == "Foul Committed":
                totals[key]["foulsCommitted"] += 1
                card = ((ev.get("foul_committed") or {}).get("card") or {}).get("name", "")
                if "Yellow" in card:
                    totals[key]["yellowCards"] += 1
                if "Red" in card:
                    totals[key]["redCards"] += 1
            elif ev_type == "Foul Won":
                totals[key]["foulsWon"] += 1
            elif ev_type in ("Duel", "Ball Recovery"):
                totals[key]["duels"] += 1
            elif ev_type == "Interception":
                totals[key]["interceptions"] += 1
            elif ev_type == "Clearance":
                totals[key]["clearances"] += 1
            elif ev_type == "Offside":
                totals[key]["offsides"] += 1
            elif ev_type == "Goal Keeper":
                gk_type = ((ev.get("goalkeeper") or {}).get("type") or {}).get("name", "")
                if gk_type in ("Shot Saved", "Shot Saved To Post", "Penalty Saved"):
                    totals[key]["saves"] += 1
            elif ev_type == "Bad Behaviour":
                card = ((ev.get("bad_behaviour") or {}).get("card") or {}).get("name", "")
                if "Yellow" in card:
                    totals[key]["yellowCards"] += 1
                if "Red" in card:
                    totals[key]["redCards"] += 1

        for (pid, player), stat_map in totals.items():
            for stat_name, stat_value in stat_map.items():
                rows.append(_make_stat_row(
                    "statsbomb", mid, pid, player, stat_name, stat_value,
                    team=meta.get((pid, player), ""), league=league_name,
                    home_team=home, away_team=away, match_date=mdate,
                ))
        time.sleep(SOURCE_SLEEP)

    return rows



_STAT_ALIASES = {
    "minutesplayed": "minutes",
    "minutes": "minutes",
    "totalshots": "shots",
    "shots": "shots",
    "shotstotal": "shots",
    "shotsontarget": "sot",
    "ontargetscoringattempt": "sot",
    "goals": "goals",
    "goalassist": "assists",
    "assists": "assists",
    "accuratepass": "passes",
    "accuratepasses": "passes",
    "totalpass": "passes",
    "passes": "passes",
    "tackles": "tackles",
    "totaltackle": "tackles",
    "wontackles": "tackles",
    "tackleswon": "tackles",
    "tacklesucceeded": "tackles",
    "interceptions": "interceptions",
    "clearance": "clearances",
    "clearances": "clearances",
    "fouls": "fouls_committed",
    "foulscommitted": "fouls_committed",
    "wasfouled": "fouls_won",
    "foulswon": "fouls_won",
    "yellowcards": "yellow_cards",
    "yellowcard": "yellow_cards",
    "redcards": "red_cards",
    "redcard": "red_cards",
    "saves": "saves",
    "keepersaves": "saves",
    "offsides": "offsides",
    "keypass": "key_passes",
    "keypasses": "key_passes",
    "duelwon": "duels_won",
    "duelswon": "duels_won",
    "totalduel": "duels",
    "duels": "duels",
    "touches": "touches",
    "xg": "xg",
    "expectedgoals": "xg",
    "xa": "xa",
    "expectedassists": "xa",
    "ontargetscoringatt": "sot",
    "totalpass": "passes",
    "accuratepass": "passes",
    "totalduel": "duels",
    "woncontest": "duels_won",
    "poss won contest": "duels_won",
    "fouls": "fouls_committed",
    "wasfouled": "fouls_won",
    "saves": "saves",
}



def _card_rows_from_events(events: Any, *, source: str, event_id: Any,
                           home: str, away: str, league: str,
                           match_date: str) -> List[Dict]:
    """Karten stehen bei FotMob/SofaScore in den Match-Events, nicht in den Spieler-Stats."""
    counts: Dict[Any, Dict[str, Any]] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("type") or ev.get("incidentType") or "").lower()
        if kind != "card":
            continue
        raw_card = str(ev.get("card") or ev.get("incidentClass") or "").lower().replace("_", "")
        if "yellowred" in raw_card or "secondyellow" in raw_card:
            stat_names = ["yellow_cards", "red_cards"]
        elif "red" in raw_card:
            stat_names = ["red_cards"]
        elif "yellow" in raw_card:
            stat_names = ["yellow_cards"]
        else:
            continue
        player = ev.get("player") if isinstance(ev.get("player"), dict) else {}
        pid = player.get("id") or ev.get("playerId")
        pname = (player.get("name") or ev.get("playerName") or ev.get("nameStr")
                 or player.get("shortName"))
        if not pname:
            continue
        is_home = ev.get("isHome")
        if is_home is None:
            is_home = ev.get("isHomeTeam")
        team = home if is_home else away
        key = pid or pname
        bucket = counts.setdefault(key, {"id": pid, "name": pname, "team": team, "stats": {}})
        for sn in stat_names:
            bucket["stats"][sn] = bucket["stats"].get(sn, 0) + 1
    rows: List[Dict] = []
    for b in counts.values():
        for sn, val in b["stats"].items():
            rows.append(_make_stat_row(
                source, event_id, b["id"] or b["name"], b["name"], sn, val,
                team=b["team"], league=league, home_team=home, away_team=away,
                match_date=match_date,
            ))
    return rows


def _stat_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in (
            "value", "statValue", "stat_value", "total", "count",
            "displayValue", "valueDisplay", "value_display",
        ):
            if key in value:
                parsed = _numeric(value.get(key))
                if parsed is not None:
                    return parsed
        return None
    if isinstance(value, list):
        for item in value:
            parsed = _numeric(item)
            if parsed is not None:
                return parsed
        return None
    raw = str(value).strip().replace("%", "")
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    raw = raw.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _flatten_stats(stats: Any) -> Dict[str, Any]:
    """Normalize current FotMob/SofaScore stat dictionaries and grouped stat lists."""
    output: Dict[str, Any] = {}

    if isinstance(stats, list):
        for item in stats:
            if not isinstance(item, dict):
                continue

            # Current FotMob groups:
            # {"title": "Top stats", "stats": {
            #   "Shots total": {"key": "totalShots", "stat": {"value": 4}}
            # }}
            group_stats = item.get("stats")
            if isinstance(group_stats, dict):
                output.update(_flatten_stats(group_stats))
                continue

            key = (
                item.get("key") or item.get("statKey") or item.get("name")
                or item.get("title") or item.get("label")
            )
            value = (
                item.get("stat") if "stat" in item else
                item.get("value") if "value" in item else
                item.get("statValue") if "statValue" in item else
                item.get("total")
            )
            if key is not None:
                numeric = _numeric(value)
                if numeric is not None:
                    output[str(key)] = numeric
            else:
                output.update(_flatten_stats(item))
        return output

    if not isinstance(stats, dict):
        return output

    # A single FotMob stat object:
    # {"key":"totalShots","stat":{"value":4,"total":5}}
    if stats.get("key") and ("stat" in stats or "value" in stats):
        numeric = _numeric(stats.get("stat") if "stat" in stats else stats.get("value"))
        if numeric is not None:
            output[str(stats.get("key"))] = numeric
        return output

    for label, value in stats.items():
        if isinstance(value, dict):
            inner_key = value.get("key") or value.get("statKey") or label
            if "stat" in value:
                numeric = _numeric(value.get("stat"))
                if numeric is not None:
                    output[str(inner_key)] = numeric
                    continue
            if "value" in value or "statValue" in value:
                numeric = _numeric(
                    value.get("value") if "value" in value else value.get("statValue")
                )
                if numeric is not None:
                    output[str(inner_key)] = numeric
                    continue

            nested = _flatten_stats(value)
            if nested:
                output.update(nested)
        elif isinstance(value, list):
            output.update(_flatten_stats(value))
        else:
            numeric = _numeric(value)
            if numeric is not None:
                output[str(label)] = numeric

    return output


def _fotmob_player_records(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Read FotMob content.playerStats, which is keyed by player id."""
    content = detail.get("content") or {}
    player_stats = content.get("playerStats") or {}
    records: List[Dict[str, Any]] = []

    if isinstance(player_stats, dict):
        for player_id, value in player_stats.items():
            if not isinstance(value, dict):
                continue
            stats = value.get("stats") or []
            if not stats:
                continue
            record = dict(value)
            record.setdefault("id", value.get("id") or player_id)
            record["stats"] = stats
            records.append(record)
    elif isinstance(player_stats, list):
        for value in player_stats:
            if isinstance(value, dict) and value.get("stats"):
                records.append(dict(value))

    return records


def _stats_to_rows(source: str, event_id: Any, player: dict, stats: dict,
                   *, team: str, league: str, home: str, away: str,
                   match_date: str) -> List[Dict]:
    player_id = player.get("id") or player.get("playerId") or player.get("uid")
    player_name = (
        player.get("name") or player.get("shortName") or
        player.get("displayName") or "Unknown"
    )
    result = []
    for raw_name, value in _flatten_stats(stats).items():
        stat_name = _STAT_ALIASES.get(_stat_key(raw_name))
        stat_value = _numeric(value)
        if not stat_name or stat_value is None:
            continue
        result.append(_make_stat_row(
            source, event_id, player_id or player_name, player_name,
            stat_name, stat_value, team=team, league=league,
            home_team=home, away_team=away, match_date=match_date,
        ))
    return result


def scrape_sofascore_date(date_str: str) -> List[Dict]:
    """
    SofaScore Tagesereignisse + fertige Lineup-Spielerstatistiken.
    Primär api.sofascore.com, danach www.sofascore.com und Browser-Fallback.
    """
    if not USE_SOFASCORE:
        return []

    schedule_paths = [
        f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
        f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
    ]

    data = None
    for url in schedule_paths:
        data = _fetch_json(url, timeout=25, allow_playwright=True)
        if isinstance(data, dict) and data.get("events"):
            break

    events = data.get("events", []) if isinstance(data, dict) else []
    rows = []
    if not events:
        print("  ⚠️  SofaScore: scheduled-events leer/blockiert "
              f"(Typ={type(data).__name__}) — Runner-IP vermutlich von Cloudflare geblockt")

    finished = [
        ev for ev in events
        if str((ev.get("status") or {}).get("type", "")).lower()
        in ("finished", "afterpenalties", "afterextratime")
    ][:SOURCE_MAX_EVENTS]

    for ev in finished:
        event_id = ev.get("id")
        detail = None
        for host in ("https://api.sofascore.com", "https://www.sofascore.com"):
            detail = _fetch_json(
                f"{host}/api/v1/event/{event_id}/lineups",
                timeout=20,
                allow_playwright=True,
            )
            if isinstance(detail, dict) and (
                detail.get("home") or detail.get("away")
            ):
                break

        if not isinstance(detail, dict):
            continue

        home = (ev.get("homeTeam") or {}).get("name", "")
        away = (ev.get("awayTeam") or {}).get("name", "")
        tournament = (
            ((ev.get("tournament") or {}).get("uniqueTournament") or {}).get("name", "")
            or (ev.get("tournament") or {}).get("name", "")
        )
        ts = ev.get("startTimestamp")
        mdate = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts else date_str
        )

        for side, team_name in (("home", home), ("away", away)):
            side_data = detail.get(side) or {}
            players = side_data.get("players") or []
            for entry in players:
                player = entry.get("player") or {}
                stats = entry.get("statistics") or {}
                rows.extend(_stats_to_rows(
                    "sofascore", event_id, player, stats,
                    team=team_name, league=tournament,
                    home=home, away=away, match_date=mdate,
                ))
        inc = _fetch_json(
            f"https://api.sofascore.com/api/v1/event/{event_id}/incidents",
            timeout=20, allow_playwright=False,
        )
        if isinstance(inc, dict):
            rows.extend(_card_rows_from_events(
                inc.get("incidents"), source="sofascore", event_id=event_id,
                home=home, away=away, league=tournament, match_date=mdate,
            ))
        time.sleep(SOURCE_SLEEP)

    print(f"  ✅ SofaScore: {len(rows)} Player-Stat-Rows aus {len(finished)} Spielen")
    return rows


def _walk_fotmob_players(node: Any):
    """Find FotMob player records across current and legacy response shapes."""
    if isinstance(node, dict):
        stats = (
            node.get("stats") or node.get("statistics")
            or node.get("playerStats")
        )
        player_obj = node.get("player") if isinstance(node.get("player"), dict) else node
        player_id = player_obj.get("id") or player_obj.get("playerId")
        player_name = (
            player_obj.get("name") or player_obj.get("displayName")
            or player_obj.get("shortName")
        )
        if stats and player_id and player_name:
            merged = dict(player_obj)
            merged["stats"] = stats
            merged["teamName"] = (
                node.get("teamName") or node.get("team")
                or player_obj.get("teamName") or player_obj.get("team")
            )
            yield merged
        for value in node.values():
            yield from _walk_fotmob_players(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_fotmob_players(value)


def scrape_fotmob_date(date_str: str) -> List[Dict]:
    """
    FotMob Tagesliste + Matchdetails.
    Probiert aktuelle /api/data/-Routen und ältere Fallback-Routen.
    """
    if not USE_FOTMOB:
        return []

    compact = date_str.replace("-", "")
    data = None
    match_endpoints = [
        ("https://www.fotmob.com/api/data/matches", {"date": compact}),
        ("https://www.fotmob.com/api/matches", {"date": compact}),
        ("https://www.fotmob.com/api/data/matches", {"date": date_str}),
    ]

    for url, params in match_endpoints:
        data = _fetch_json(
            url, params=params, timeout=25, allow_playwright=True
        )
        if isinstance(data, dict) and (
            data.get("leagues") or data.get("matches")
        ):
            break

    leagues = data.get("leagues", []) if isinstance(data, dict) else []
    matches = []

    if leagues:
        for league in leagues:
            league_name = league.get("name", "")
            for match in league.get("matches") or []:
                status_obj = match.get("status") or {}
                finished = (
                    status_obj.get("finished") is True
                    or str(status_obj.get("finished", "")).lower() in ("true", "1")
                    or str(status_obj.get("statusId", "")).lower() in ("6", "finished")
                )
                if finished:
                    matches.append((league_name, match))
    elif isinstance(data, dict):
        for match in data.get("matches") or []:
            matches.append((str(match.get("leagueName") or ""), match))

    matches = matches[:SOURCE_MAX_EVENTS]
    rows = []
    details_ok = 0
    details_with_player_stats = 0

    for league_name, match in matches:
        match_id = match.get("id") or match.get("matchId")
        if not match_id:
            continue

        detail = None
        detail_endpoints = [
            ("https://www.fotmob.com/api/data/matchDetails", {"matchId": match_id}),
            ("https://www.fotmob.com/api/matchDetails", {"matchId": match_id}),
            ("https://www.fotmob.com/api/data/matchDetails", {"matchId": match_id, "ccode3": "USA"}),
        ]

        for url, params in detail_endpoints:
            detail = _fetch_json(
                url, params=params, timeout=25, allow_playwright=True
            )
            if isinstance(detail, dict) and (
                detail.get("content") or detail.get("general")
            ):
                break

        if not isinstance(detail, dict):
            continue
        details_ok += 1
        if _fotmob_player_records(detail):
            details_with_player_stats += 1

        general = detail.get("general") or {}
        home = (
            (general.get("homeTeam") or {}).get("name")
            or (match.get("home") or {}).get("name")
            or match.get("homeName")
            or ""
        )
        away = (
            (general.get("awayTeam") or {}).get("name")
            or (match.get("away") or {}).get("name")
            or match.get("awayName")
            or ""
        )

        seen = set()
        direct_records = _fotmob_player_records(detail)
        player_objects = direct_records or list(
            _walk_fotmob_players(detail.get("content") or detail)
        )
        for obj in player_objects:
            player = {
                "id": obj.get("id") or obj.get("playerId"),
                "name": (
                    obj.get("name") or obj.get("displayName")
                    or obj.get("shortName")
                ),
            }
            stats = obj.get("stats") or obj.get("statistics") or {}
            if not player["name"] or not stats:
                continue

            team_name = obj.get("teamName") or obj.get("team") or ""
            dedupe_key = (
                str(player["id"] or player["name"]),
                json.dumps(stats, sort_keys=True, default=str),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rows.extend(_stats_to_rows(
                "fotmob", match_id, player, stats,
                team=str(team_name), league=league_name,
                home=home, away=away, match_date=date_str,
            ))
        try:
            facts = (detail.get("content") or {}).get("matchFacts") or {}
            ev_list = (facts.get("events") or {}).get("events") or []
            rows.extend(_card_rows_from_events(
                ev_list, source="fotmob", event_id=match_id, home=home,
                away=away, league=league_name, match_date=date_str,
            ))
        except Exception as exc:
            print(f"  ⚠️  FotMob Karten: {str(exc)[:80]}")
        time.sleep(SOURCE_SLEEP)

    print(
        f"  {'✅' if rows else '⚪'} FotMob: {len(rows)} Player-Stat-Rows "
        f"aus {len(matches)} Spielen | Details={details_ok} "
        f"| mit PlayerStats={details_with_player_stats}"
    )
    return rows


def scrape_soccerdata_fallback(date_str: str) -> List[Dict]:
    """
    Optionaler Open-Source-Fallback. Nutzt soccerdata/Understat für Top-5-Ligen.
    Nur Daten des gewünschten Datums werden übernommen.
    """
    if not USE_SOCCERDATA:
        print("  ℹ️  soccerdata deaktiviert (USE_SOCCERDATA=false) — spart Laufzeit")
        return []
    try:
        import soccerdata as sd
    except Exception:
        print("  ℹ️  soccerdata nicht verfügbar — nächster Fallback")
        return []

    year = int(date_str[:4])
    season = year if int(date_str[5:7]) >= 7 else year - 1
    league_map = {
        "ENG-Premier League": "Premier League",
        "ESP-La Liga": "La Liga",
        "GER-Bundesliga": "Bundesliga",
        "ITA-Serie A": "Serie A",
        "FRA-Ligue 1": "Ligue 1",
    }
    rows = []

    for league_id, league_name in league_map.items():
        try:
            reader = sd.Understat(
                leagues=league_id, seasons=season, no_cache=True, no_store=True
            )
            schedule = reader.read_schedule(force_cache=False)
            if schedule is None or schedule.empty:
                continue

            # Index/Spalten flexibel behandeln.
            frame = schedule.reset_index()
            date_col = next(
                (c for c in frame.columns if str(c).lower() in ("date", "game_date")),
                None,
            )
            id_col = next(
                (c for c in frame.columns if "game_id" in str(c).lower()
                 or "match_id" in str(c).lower()),
                None,
            )
            if date_col is None or id_col is None:
                continue

            frame[date_col] = frame[date_col].astype(str).str[:10]
            ids = frame.loc[frame[date_col] == date_str, id_col].tolist()
            for match_id in ids[:10]:
                df = reader.read_player_match_stats(match_id=match_id)
                if df is None or df.empty:
                    continue
                for _, record in df.reset_index().iterrows():
                    d = record.to_dict()
                    player_name = str(
                        d.get("player") or d.get("player_name") or d.get("player_id") or ""
                    )
                    if not player_name:
                        continue
                    player = {"id": d.get("player_id") or player_name, "name": player_name}
                    normalized = {
                        "minutes": d.get("minutes"),
                        "shots": d.get("shots"),
                        "goals": d.get("goals"),
                        "assists": d.get("assists"),
                        "xG": d.get("xG") or d.get("xg"),
                        "xA": d.get("xA") or d.get("xa"),
                    }
                    rows.extend(_stats_to_rows(
                        "understat_soccerdata", match_id, player, normalized,
                        team=str(d.get("team") or ""), league=league_name,
                        home=str(d.get("home_team") or ""),
                        away=str(d.get("away_team") or ""), match_date=date_str,
                    ))
        except Exception as exc:
            print(f"  ⚠️  soccerdata {league_name}: {str(exc)[:100]}")

    print(f"  ✅ soccerdata/Understat: {len(rows)} Player-Stat-Rows")
    return rows

def scrape_fbref_csv() -> List[Dict]:
    """FBref CSV-Downloads — leichtgewichtig, kein Playwright nötig."""
    rows = []
    csv_urls = [
        ("https://fbref.com/en/comps/20/shooting/Bundesliga-Stats", "Bundesliga", "shooting"),
        ("https://fbref.com/en/comps/9/shooting/Premier-League-Stats", "Premier League", "shooting"),
        ("https://fbref.com/en/comps/12/shooting/La-Liga-Stats", "La Liga", "shooting"),
    ]
    for url, league, stat_type in csv_urls:
        try:
            time.sleep(4)  # FBref Rate Limit: max 20 Req/Min
            r = requests.get(url, headers=HEADERS, timeout=15)
            if not r.ok:
                continue
            # Tabelle aus HTML parsen
            import pandas as _pd
            from io import StringIO as _SI
            tables = _pd.read_html(_SI(r.text))
            for df in tables:
                if df.empty:
                    continue
                # Spalten normalisieren
                df.columns = ['_'.join(str(c) for c in col).strip() if isinstance(col, tuple)
                              else str(col) for col in df.columns]
                # Spielernamen-Spalte finden
                player_col = next((c for c in df.columns if 'Player' in c or 'player' in c), None)
                if not player_col:
                    continue
                for _, row in df.iterrows():
                    player = str(row.get(player_col, "")).strip()
                    if not player or player == "Player":
                        continue
                    team_col = next((c for c in df.columns if 'Squad' in c or 'team' in c.lower()), None)
                    team = str(row.get(team_col, "")) if team_col else ""
                    for stat in ["Gls", "Sh", "SoT", "npxG", "xG", "Ast"]:
                        val_col = next((c for c in df.columns if stat in c), None)
                        if val_col and row.get(val_col) is not None:
                            try:
                                rows.append(_make_stat_row(
                                    "fbref_csv", f"fbref_{player}_{stat}",
                                    None, player, stat.lower(), float(row[val_col]),
                                    team=team, league=league
                                ))
                            except (ValueError, TypeError):
                                pass
                break  # Erste valide Tabelle reicht
            print(f"  ✅ FBref CSV {league}: {len(rows)} Rows")
        except Exception as e:
            print(f"  ⚠️  FBref CSV {league}: {str(e)[:60]}")
    return rows


def scrape_fbref_playwright(league: str = "Big5") -> List[Dict]:
    """
    FBref: requests → cloudscraper → Playwright. Parst auch auskommentierte Tabellen.
    FBref liefert Saisonwerte; Quelle bleibt als fbref_season gekennzeichnet.
    """
    if not USE_FBREF:
        return []

    urls = {
        "Big5": "https://fbref.com/en/comps/Big5/shooting/players/Big-5-European-Leagues-Stats",
        "Bundesliga": "https://fbref.com/en/comps/20/shooting/Bundesliga-Stats",
    }
    url = urls.get(league, urls["Big5"])
    raw = _fetch_text(url, timeout=25, allow_playwright=True)
    if not raw:
        return []

    raw = raw.replace("<!--", "").replace("-->", "")
    rows = []
    try:
        import pandas as pd
        from io import StringIO
        tables = pd.read_html(StringIO(raw))
    except Exception as exc:
        print(f"  ⚠️  FBref Parse: {str(exc)[:100]}")
        return []

    stat_candidates = {
        "Sh": "totalShots",
        "SoT": "shotsOnTarget",
        "Gls": "goals",
        "Ast": "goalAssist",
        "xG": "xg",
        "npxG": "npxg",
    }

    for df in tables:
        if df.empty:
            continue
        df.columns = [
            "_".join(str(x) for x in col).strip() if isinstance(col, tuple)
            else str(col)
            for col in df.columns
        ]
        player_col = next((c for c in df.columns if c.endswith("_Player") or c == "Player"), None)
        if not player_col:
            continue
        team_col = next((c for c in df.columns if c.endswith("_Squad") or c == "Squad"), None)

        for _, rec in df.iterrows():
            player_name = str(rec.get(player_col, "")).strip()
            if not player_name or player_name == "Player":
                continue
            team = str(rec.get(team_col, "")).strip() if team_col else ""
            player_id = hashlib.sha1(player_name.encode("utf-8")).hexdigest()[:16]

            for token, normalized in stat_candidates.items():
                col = next(
                    (c for c in df.columns
                     if c.endswith(f"_{token}") or c == token),
                    None,
                )
                if not col:
                    continue
                value = _numeric(rec.get(col))
                if value is None:
                    continue
                rows.append(_make_stat_row(
                    "fbref_season", f"fbref_{league}_{player_id}", player_id,
                    player_name, normalized, value, team=team, league=league,
                    match_date=datetime.now(timezone.utc).date().isoformat(),
                ))
        if rows:
            break

    print(f"  ✅ FBref Fallback-Kette: {len(rows)} Saison-Stat-Rows")
    return rows



# ══════════════════════════════════════════════════════════════════════════════
# 2B. GITHUB PLAYER DATASETS / IDENTITY MAPS — ALL SOURCES V34 FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

def _parse_generic_player_csv(raw: str, source: str, date_str: str = None) -> List[Dict[str, Any]]:
    import csv, io
    rows = []
    try:
        reader = csv.DictReader(io.StringIO(raw))
        for i, row in enumerate(reader):
            if i > SOURCE_MAX_EVENTS * 100:
                break
            player = row.get("player_name") or row.get("player") or row.get("name") or row.get("Player")
            team = row.get("team") or row.get("squad") or row.get("club") or row.get("Team")
            if not player:
                continue
            event_id = row.get("match_id") or row.get("event_id") or row.get("fixture_id") or f"{source}_dataset_{i}"
            match_date = (row.get("date") or row.get("match_date") or date_str or str(datetime.now(timezone.utc).date()))[:10]
            league = row.get("league") or row.get("competition") or source
            stat_aliases = {
                "minutes": ["minutes", "Min", "mins"],
                "shots": ["shots", "Sh", "total_shots"],
                "sot": ["sot", "SoT", "shots_on_target"],
                "goals": ["goals", "Gls", "goal"],
                "assists": ["assists", "Ast", "assist"],
                "passes": ["passes", "Passes", "passes_completed"],
                "tackles": ["tackles", "Tkl", "tackle"],
                "fouls_committed": ["fouls_committed", "Fls", "fouls"],
                "fouls_won": ["fouls_won", "Fld", "fouled"],
                "cards": ["cards", "yellow_cards", "YC"],
                "corners": ["corners", "corner_kicks"],
            }
            for stat, names in stat_aliases.items():
                val = None
                for n in names:
                    if n in row and row.get(n) not in (None, ""):
                        val = _numeric(row.get(n))
                        break
                if val is not None:
                    rows.append(_make_stat_row(
                        source=source, event_id=event_id,
                        player_id=row.get("player_id") or row.get("id") or player,
                        player_name=player, stat_name=stat, stat_value=val,
                        team=team, league=league, match_date=match_date,
                    ))
    except Exception:
        return []
    return rows


def scrape_github_player_datasets(date_str: str) -> List[Dict[str, Any]]:
    """salimt/football-datasets + eddwebster curated data if accessible as raw CSV/JSON."""
    if not USE_GITHUB_OPEN_SOURCES:
        return []
    all_rows = []
    for owner, repo, kind in GITHUB_OPEN_SOURCE_REPOS:
        if kind not in {"player_dataset"}:
            continue
        label = f"github:{owner}/{repo}"
        count = 0
        try:
            files = _github_tree_files(owner, repo, max_files=max(40, GITHUB_SOURCE_MAX_FILES // 2))
            for path in files:
                lower = path.lower()
                if not lower.endswith((".csv", ".json", ".ndjson")):
                    continue
                if not any(k in lower for k in ["player", "stat", "performance", "match", "appearance", "data"]):
                    continue
                raw = _github_raw(owner, repo, path)
                if not raw:
                    continue
                rows = []
                if lower.endswith(".csv"):
                    rows = _parse_generic_player_csv(raw, label, date_str)
                elif lower.endswith((".json", ".ndjson")):
                    # JSON player dataset fallback: convert flat dict list to CSV-like parser by mapping manually.
                    try:
                        data = [json.loads(x) for x in raw.splitlines() if x.strip().startswith("{")] if lower.endswith(".ndjson") else json.loads(raw)
                        if isinstance(data, dict):
                            for k in ["players", "data", "rows", "stats"]:
                                if isinstance(data.get(k), list):
                                    data = data[k]
                                    break
                        if isinstance(data, list):
                            import csv, io
                            if data and isinstance(data[0], dict):
                                out = io.StringIO()
                                writer = csv.DictWriter(out, fieldnames=sorted({kk for rr in data[:2000] if isinstance(rr, dict) for kk in rr.keys()}))
                                writer.writeheader(); writer.writerows([rr for rr in data[:2000] if isinstance(rr, dict)])
                                rows = _parse_generic_player_csv(out.getvalue(), label, date_str)
                    except Exception:
                        rows = []
                if rows:
                    all_rows.extend(rows)
                    count += len(rows)
                if count >= SOURCE_MAX_EVENTS * 20:
                    break
                time.sleep(SOURCE_SLEEP)
            print(f"  {'✅' if count else '⚪'} {label} player dataset: {count}")
        except Exception as e:
            print(f"  ⚠️  {label} player dataset: {str(e)[:100]}")
    return all_rows


def fetch_identity_maps_for_normalization() -> int:
    """Load the useful REEP map; reference-only repo scans belong to source learning."""
    if not USE_GITHUB_OPEN_SOURCES:
        return 0
    total = _load_reep_identity_index()
    if not IDENTITY_REFERENCE_HEALTHCHECK:
        print("  ℹ️  OpenFootball identity health-check im Daily-Run übersprungen")
        return total

    for owner, repo, kind in GITHUB_OPEN_SOURCE_REPOS:
        if kind != "identity" or repo == "reep":
            continue
        label = f"github:{owner}/{repo}"
        count = 0
        try:
            files = _github_tree_files(owner, repo, max_files=80)
            for path in files:
                if not path.lower().endswith(
                    (".csv", ".json", ".ndjson", ".jsonl", ".txt")
                ):
                    continue
                raw = _github_raw(owner, repo, path)
                if raw:
                    count += max(1, raw.count("\n"))
                if count >= 100000:
                    break
            total += count
            print(f"  {'✅' if count else '⚪'} {label} identity/reference rows: {count}")
        except Exception as exc:
            print(f"  ⚠️  {label} identity map: {str(exc)[:100]}")
    return total


def scrape_oddsharvester_style(date_str: str) -> int:
    """Run the real odds collector. Odds go to odds_history, not player_match_stats."""
    if not USE_ODDSHARVESTER_STYLE:
        return 0
    try:
        from netrattler_odds_harvester import collect_live_all, persist_odds
        rows = collect_live_all(date_str)
        saved = persist_odds(rows, "netrattler_odds_snapshot.json")
        count = saved.get("odds_history", 0) or saved.get("data_lake", 0) or saved.get("local", 0)
        print(f"  {'✅' if count else '⚪'} OddsHarvester/Bet365/other bookies: {count}")
        return int(count)
    except Exception as exc:
        print(f"  ⚠️ Odds collector: {str(exc)[:120]} — separate odds workflow remains fallback")
        return 0


def scrape_player_stats(date_str: str) -> int:
    """Multi-Source Player-Data Engine mit unabhängigen Fallbacks."""
    print(f"\n📊 Scrape Player Stats für {date_str}")
    all_rows: List[Dict] = []
    source_counts = {}

    def add_source(name: str, fn):
        try:
            rows = fn() or []
        except Exception as exc:
            print(f"  ⚠️  {name}: {str(exc)[:120]}")
            rows = []
        all_rows.extend(rows)
        source_counts[name] = len(rows)

    # Identitätsquellen zuerst laden/loggen: sie liefern Mapping, keine Stat-Rows.
    identity_count = fetch_identity_maps_for_normalization()
    source_counts["openfootball/players + clubs + REEP identity"] = identity_count
    if USE_ODDSHARVESTER_STYLE:
        source_counts["OddsHarvester + Bet365 + other bookies"] = scrape_oddsharvester_style(date_str)
    else:
        source_counts["OddsHarvester + Bet365 + other bookies"] = 0
        print("  ℹ️  Odds im Player-Stats-Lauf deaktiviert — eigener Odds-Schritt folgt")

    # Aktuelle Matchdaten zuerst. SofaScore/FotMob sind unabhängig und normalerweise
    # der teuerste Teil des Daily-Runs, daher parallel statt seriell.
    current_jobs = [
        ("SofaScore", lambda: scrape_sofascore_date(date_str)),
        ("FotMob direct API / davidrocha9-fotmob-scraper fallback", lambda: scrape_fotmob_date(date_str)),
    ]
    current_workers = max(1, min(2, int(os.environ.get("DAILY_STATS_PARALLEL_WORKERS", "2"))))
    with ThreadPoolExecutor(max_workers=current_workers) as pool:
        futures = {pool.submit(fn): name for name, fn in current_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                rows = fut.result() or []
            except Exception as exc:
                print(f"  ⚠️  {name}: {str(exc)[:120]}")
                rows = []
            all_rows.extend(rows)
            source_counts[name] = len(rows)

    # GitHub Player Dataset + research catalog. salimt supplies data; eddwebster is source discovery/catalog.
    add_source("GitHub player dataset: salimt/football-datasets", lambda: scrape_github_player_datasets(date_str))
    source_counts["eddwebster/football_analytics catalog"] = 1

    # Historisches Open Data als Modell-/Fallbackbasis
    if USE_STATSBOMB:
        for league in ["Bundesliga", "La Liga", "FIFA World Cup", "Copa America"]:
            add_source(
                f"StatsBomb {league}",
                lambda league=league: scrape_statsbomb_league(league),
            )

    # Saisonwerte und Open-Source-Library als letzte Fallbacks
    add_source("FBref", lambda: scrape_fbref_playwright("Big5"))
    add_source("probberechts/soccerdata", lambda: scrape_soccerdata_fallback(date_str))

    clean = _dedupe_rows(
        all_rows, "source,event_id,player_id,stat_name"
    )
    saved = _sb_post(
        "player_match_stats",
        clean,
        conflict="source,event_id,player_id,stat_name",
    )

    write_player_game_log(clean)

    print("  ── Quellenübersicht ──")
    for name, count in source_counts.items():
        icon = "✅" if count else "⚪"
        print(f"  {icon} {name}: {count}")
    print(f"  🧹 {len(all_rows)} Roh-Rows → {len(clean)} eindeutige Rows")
    print(f"  💾 {saved} Player-Stat-Rows gespeichert/aktualisiert")
    return saved


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",      default=None, help="Datum YYYY-MM-DD")
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--results-only", action="store_true", help="Nur Ergebnisse, keine Player Stats")
    parser.add_argument("--stats-only",   action="store_true", help="Nur Player Stats")
    parser.add_argument("--days", type=int, default=1,
                        help="Backfill: Player Stats für die letzten N Tage (ab gestern rückwärts)")
    parser.add_argument("--source",    choices=["sofascore", "fotmob", "statsbomb", "github", "odds", "auto"], default="auto")
    parser.add_argument("--event-id",  default=None)
    parser.add_argument("--match-id",  default=None)
    parser.add_argument("--output",    default=None)
    args = parser.parse_args()

    # Datum bestimmen
    if args.yesterday or not args.date:
        date_str = str((datetime.now(timezone.utc) - timedelta(days=1)).date())
    else:
        date_str = args.date

    print(f"🚀 NETRATTLER Scraper — {date_str}")

    if args.days and args.days > 1:
        # Backfill: nur Player Stats, älteste zuerst (neueste Werte gewinnen beim Upsert/Prune).
        base = datetime.fromisoformat(date_str).date()
        total = 0
        for offset in range(args.days - 1, -1, -1):
            day = str(base - timedelta(days=offset))
            try:
                total += scrape_player_stats(day)
            except Exception as exc:
                print(f"  ⚠️  Backfill {day}: {str(exc)[:120]}")
        send_telegram(
            f"📊 <b>NETRATTLER Backfill</b>\n\n"
            f"{args.days} Tage bis <b>{date_str}</b>\nPlayer Stats: <b>{total}</b>"
        )
        print(f"\n✅ Backfill fertig — {total} Stats")
        return

    results_saved = 0
    stats_saved = 0

    if not args.stats_only:
        results_saved = scrape_results(date_str)

    if not args.results_only:
        stats_saved = scrape_player_stats(date_str)

    report = (
        f"📊 <b>NETRATTLER Scraper</b>\n\n"
        f"Datum: <b>{date_str}</b>\n"
        f"Ergebnisse: <b>{results_saved}</b>\n"
        f"Player Stats: <b>{stats_saved}</b>"
    )
    if stats_saved:
        prune_player_history_l15()
    send_telegram(report)
    print(f"\n✅ Fertig — {results_saved} Ergebnisse, {stats_saved} Stats")


if __name__ == "__main__":
    main()
