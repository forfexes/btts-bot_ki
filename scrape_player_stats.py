#!/usr/bin/env python3
"""
NETRATTLER - scrape_player_stats.py
=====================================
Täglich nach Spielende:
1. Match-Ergebnisse von ESPN + TheSportsDB + OpenFootball → Supabase match_results
2. Player Stats von FBref (Playwright) + StatsBomb → Supabase player_match_stats

Läuft täglich 02:00 UTC via scrape_player_stats.yml
"""

import argparse, json, os, re, time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
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


# ── Supabase ──────────────────────────────────────────────────────────────────

def _sb_post(table: str, rows: list, conflict: str = None) -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    params = {}
    if conflict:
        params["on_conflict"] = conflict
    total = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i+500]
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}",
                          headers=headers, params=params, json=chunk, timeout=30)
        if r.ok:
            total += len(chunk)
        else:
            print(f"  ⚠️  Supabase {table} {r.status_code}: {r.text[:100]}")
    return total


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
    all_results.extend(fetch_espn_results(date_str))
    all_results.extend(fetch_thesportsdb_results(date_str))
    all_results.extend(fetch_openfootball_results(date_str))
    all_results.extend(fetch_fifa_results(date_str))  # FIFA WM/Turniere

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
        "player_id": str(player_id) if player_id else None,
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
    """StatsBomb Open Data — immer erreichbar via GitHub raw."""
    comp = _SB_LEAGUE_MAP.get(league_name)
    if not comp:
        return []
    comp_id, season_id = comp
    rows = []
    try:
        r = requests.get(f"{_SB_BASE}/matches/{comp_id}/{season_id}.json", timeout=10)
        if not r.ok:
            return []
        matches = r.json()[-5:]  # letzte 5 Spiele
        for match in matches:
            mid = match.get("match_id")
            home = match.get("home_team", {}).get("home_team_name", "")
            away = match.get("away_team", {}).get("away_team_name", "")
            mdate = match.get("match_date", "")
            try:
                re2 = requests.get(f"{_SB_BASE}/events/{mid}.json", timeout=10)
                if not re2.ok:
                    continue
                for ev in re2.json():
                    ev_type = (ev.get("type") or {}).get("name", "")
                    player = (ev.get("player") or {}).get("name", "")
                    pid = (ev.get("player") or {}).get("id", "")
                    team = (ev.get("team") or {}).get("name", "")
                    if not player:
                        continue
                    if ev_type == "Shot":
                        outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
                        if outcome in ("Goal", "Saved", "Saved To Post"):
                            rows.append(_make_stat_row("statsbomb", mid, pid, player, "shotsOnTarget", 1,
                                                        team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                        if outcome == "Goal":
                            rows.append(_make_stat_row("statsbomb", mid, pid, player, "goals", 1,
                                                        team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                        rows.append(_make_stat_row("statsbomb", mid, pid, player, "totalShots", 1,
                                                    team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                    elif ev_type == "Foul Committed":
                        rows.append(_make_stat_row("statsbomb", mid, pid, player, "foulsCommitted", 1,
                                                    team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                    elif ev_type == "Bad Behaviour":
                        card = (ev.get("bad_behaviour") or {}).get("card", {}).get("name", "")
                        if "Yellow" in card:
                            rows.append(_make_stat_row("statsbomb", mid, pid, player, "yellowCards", 1,
                                                        team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                    elif ev_type == "Pass":
                        if (ev.get("pass") or {}).get("goal_assist"):
                            rows.append(_make_stat_row("statsbomb", mid, pid, player, "goalAssist", 1,
                                                        team=team, league=league_name, home_team=home, away_team=away, match_date=mdate))
                time.sleep(1)
            except Exception:
                continue
    except Exception as e:
        print(f"  ⚠️  StatsBomb {league_name}: {e}")
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
    """FBref Player Stats via Playwright — bestätigt auf GitHub Actions."""
    rows = []
    try:
        from playwright.sync_api import sync_playwright
        urls = {
            "Big5": "https://fbref.com/en/comps/Big5/shooting/players/Big-5-European-Leagues-Stats",
            "Bundesliga": "https://fbref.com/en/comps/20/shooting/Bundesliga-Stats",
        }
        url = urls.get(league, urls["Big5"])
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Chrome/122.0"})
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Tabelle parsen
            tables = page.query_selector_all("table.stats_table")
            for table in tables[:2]:
                rows_html = table.query_selector_all("tbody tr")
                for row_el in rows_html:
                    cells = row_el.query_selector_all("td, th")
                    if not cells:
                        continue
                    try:
                        player_el = row_el.query_selector("td[data-stat='player'] a")
                        if not player_el:
                            continue
                        player_name = player_el.inner_text().strip()
                        team_el = row_el.query_selector("td[data-stat='team_name']")
                        team = team_el.inner_text().strip() if team_el else ""

                        for stat_name in ["shots", "shots_on_target", "goals", "npxg", "xg"]:
                            el = row_el.query_selector(f"td[data-stat='{stat_name}']")
                            if el:
                                val = el.inner_text().strip()
                                try:
                                    rows.append(_make_stat_row(
                                        "fbref", f"fbref_{player_name}_{stat_name}",
                                        None, player_name, stat_name, float(val),
                                        team=team, league=league
                                    ))
                                except ValueError:
                                    pass
                    except Exception:
                        continue
            browser.close()
        print(f"  ✅ FBref Playwright: {len(rows)} Stat-Rows für {league}")
    except ImportError:
        print("  ⚠️  Playwright nicht installiert")
    except Exception as e:
        print(f"  ⚠️  FBref Playwright Error: {str(e)[:80]}")
    return rows


def scrape_player_stats(date_str: str) -> int:
    """Sammelt Player Stats aus StatsBomb + FBref."""
    print(f"\n📊 Scrape Player Stats für {date_str}")
    all_rows = []

    # StatsBomb (immer erreichbar)
    for league in ["Bundesliga", "La Liga", "FIFA World Cup", "Copa America"]:
        rows = scrape_statsbomb_league(league)
        all_rows.extend(rows)
        if rows:
            print(f"  ✅ StatsBomb {league}: {len(rows)} Rows")
        time.sleep(3)  # Rate limit zwischen Ligen

    # FBref via Playwright
    fbref_rows = scrape_fbref_playwright("Big5")
    all_rows.extend(fbref_rows)

    saved = _sb_post("player_match_stats", all_rows)
    print(f"  💾 {saved} Player-Stat-Rows gespeichert")
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
    parser.add_argument("--source",    choices=["sofascore", "fotmob", "statsbomb", "auto"], default="auto")
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
    send_telegram(report)
    print(f"\n✅ Fertig — {results_saved} Ergebnisse, {stats_saved} Stats")


if __name__ == "__main__":
    main()
