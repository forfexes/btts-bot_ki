#!/usr/bin/env python3
"""
NETRATTLER Player Stats Scraper V13
27 Quellen: StatsBomb + FotMob + Understat + ESPN + TheStatsAPI + Football-Data.co.uk
+ Football-Data.org + FPL API + FPL Core Insights + OpenLigaDB + ClubElo + martj42
+ Sportmonks + ScoutingStats + Oddspedia + FootyMetrics + PhysioRoom + Forebet
+ xgabora CSV + openfootball JSON + WM2026 Dataset + jfjelstul WM DB
+ Referee DB + Open-Meteo Wetter + SofaScore + FBref + Pinnacle Props
Graceful: jede Quelle crasht nur für sich, nie den ganzen Scraper.
"""

import os, re, time, json, argparse, csv, io
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests

# ============================================================
# CONFIG
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

THESTATSAPI_KEY = os.getenv("THESTATSAPI_KEY", "")
SPORTMONKS_KEY  = os.getenv("SPORTMONKS_API_KEY", os.getenv("SPORTMONKS_KEY", ""))
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", os.getenv("APIFOOTBALL_KEY", ""))

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.7",
    "Referer": "https://www.google.com/",
})

def log(x): print(x, flush=True)
def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone.utc).date().isoformat()
def yesterday(): return (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()

def si(x, d=0):
    try: return int(float(str(x).replace(",", ".")))
    except: return d

def sf(x, d=0.0):
    try: return float(str(x).replace(",", "."))
    except: return d

def clean(s): return re.sub(r"\s+", " ", str(s or "")).strip()

def safe_get(url, params=None, headers=None, timeout=20):
    try:
        r = HTTP.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code == 403: log(f"  🚫 403: {url[:80]}"); return None
        if r.status_code == 429: log(f"  ⏳ 429 Rate Limit: {url[:80]}"); return None
        if not r.ok: log(f"  ⚠️ {r.status_code}: {url[:80]}"); return None
        return r
    except Exception as e:
        log(f"  ❌ {url[:60]}: {e}"); return None

def jget(url, params=None, headers=None):
    r = safe_get(url, params=params, headers=headers)
    if not r: return None
    try: return r.json()
    except: return None

# ============================================================
# SUPABASE
# ============================================================
def _dedupe_for_conflict(rows: List[Dict], conflict: str) -> List[Dict]:
    """Postgres kann innerhalb eines UPSERT-Kommandos nicht 2x denselben Conflict-Key updaten."""
    if not rows or not conflict:
        return rows
    keys = [k.strip() for k in conflict.split(",") if k.strip()]
    if not keys:
        return rows

    # Compatibility: alte Referee-Rows nutzen referee_name, neue Tabellen oft referee.
    if any("referee" in k for k in keys):
        for r in rows:
            if r.get("referee_name") and not r.get("referee"):
                r["referee"] = r.get("referee_name")
            if r.get("referee") and not r.get("referee_name"):
                r["referee_name"] = r.get("referee")

    seen = {}
    passthrough = []
    for r in rows:
        vals = []
        complete = True
        for k in keys:
            v = r.get(k)
            if v is None or str(v) == "":
                complete = False
                break
            vals.append(str(v))
        if not complete:
            passthrough.append(r)
            continue
        seen[tuple(vals)] = r  # last row wins
    return list(seen.values()) + passthrough


def upsert(table: str, rows: List[Dict], conflict: str = "") -> int:
    if not rows: return 0
    if not SUPABASE_URL or not SUPABASE_KEY:
        log(f"  ⚠️ Supabase nicht konfiguriert"); return 0

    rows = _dedupe_for_conflict(rows, conflict)

    total = 0
    h = dict(SB_HEADERS)
    h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    url = f"{SUPABASE_URL}/rest/v1/{table}" + (f"?on_conflict={conflict}" if conflict else "")
    for i in range(0, len(rows), 250):
        chunk = rows[i:i+250]
        chunk = _dedupe_for_conflict(chunk, conflict)
        try:
            r = HTTP.post(url, headers=h, json=chunk, timeout=45)
            if not r.ok:
                log(f"  ⚠️ UPSERT {table} {r.status_code}: {r.text[:350]}")
                continue
            total += len(chunk)
        except Exception as e:
            log(f"  ⚠️ UPSERT {table}: {e}")
    return total

def sb_get(table: str, params: Dict) -> List[Dict]:
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        r = HTTP.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=params, timeout=35)
        return r.json() if r.ok else []
    except: return []

def health(source, status, rows=0, msg=""):
    upsert("source_health", [{
        "source": source, "status": status, "rows": rows,
        "message": str(msg)[:400], "checked_at": now()
    }], "source")

# ============================================================
# HELPER: Player Match Row Template
# ============================================================
def player_row(player_name, team_name, match_id, match_date, home_team, away_team, source, **kwargs):
    row = {
        "player_name": clean(player_name),
        "team_name": clean(team_name),
        "match_id": str(match_id),
        "match_date": str(match_date) if match_date else "",
        "home_team": clean(home_team),
        "away_team": clean(away_team),
        "minutes": 0, "shots": 0, "sot": 0, "goals": 0, "assists": 0,
        "passes": 0, "tackles": 0, "fouls_committed": 0, "fouls_won": 0,
        "cards": 0, "corners": 0, "xg": 0.0, "xa": 0.0,
        "source": source, "updated_at": now()
    }
    row.update(kwargs)
    return row

# ============================================================
# 1. STATSBOMB OPEN DATA
# ============================================================
def statsbomb_rows(max_matches=120):
    log("📦 1. StatsBomb Open Data...")
    base = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    rows = []
    try:
        comps = jget(base + "/competitions.json") or []
    except Exception as e:
        log(f"  ❌ StatsBomb: {e}"); health("statsbomb", "error", 0, str(e)); return rows

    # Alle verfügbaren Competitions laden (nicht nur top 8)
    target_keywords = ["world cup", "euro", "copa america", "champions league",
                       "bundesliga", "serie a", "ligue 1", "premier league", "la liga",
                       "fa women", "nwsl", "women"]
    target_comps = [c for c in comps if any(x in str(c.get("competition_name","")).lower() for x in target_keywords)]
    log(f"  StatsBomb: {len(target_comps)} Competitions gefunden")

    seen = 0
    for c in target_comps:
        if seen >= max_matches: break
        try:
            matches = jget(f"{base}/matches/{c['competition_id']}/{c['season_id']}.json") or []
        except: continue
        for m in matches:
            if seen >= max_matches: break
            mid = m.get("match_id")
            try:
                events = jget(f"{base}/events/{mid}.json") or []
            except: continue
            seen += 1
            per = {}
            home = (m.get("home_team") or {}).get("home_team_name", "")
            away = (m.get("away_team") or {}).get("away_team_name", "")
            md = str(m.get("match_date") or "")
            for e in events:
                pname = (e.get("player") or {}).get("name")
                if not pname: continue
                p = per.setdefault(pname, player_row(
                    pname, (e.get("team") or {}).get("name", ""),
                    f"statsbomb_{mid}", md, home, away, "statsbomb_open_data"
                ))
                t = (e.get("type") or {}).get("name", "")
                if t == "Shot":
                    p["shots"] += 1
                    out = ((e.get("shot") or {}).get("outcome") or {}).get("name", "")
                    if out in ("Goal", "Saved", "Saved To Post"): p["sot"] += 1
                    if out == "Goal": p["goals"] += 1
                    p["xg"] = round(p["xg"] + sf((e.get("shot") or {}).get("statsbomb_xg", 0)), 4)
                elif t == "Pass":
                    p["passes"] += 1
                    if (e.get("pass") or {}).get("goal_assist"): p["assists"] += 1
                    if ((e.get("pass") or {}).get("type") or {}).get("name") == "Corner": p["corners"] += 1
                elif t == "Foul Committed":
                    p["fouls_committed"] += 1
                    if ((e.get("foul_committed") or {}).get("card") or {}).get("name"): p["cards"] += 1
                elif t == "Foul Won": p["fouls_won"] += 1
                elif t in ("Duel", "Block", "Interception", "Ball Recovery"): p["tackles"] += 1
            rows.extend(per.values())

    health("statsbomb", "ok", len(rows), f"matches={seen}")
    log(f"  ✅ StatsBomb: {len(rows)} Rows aus {seen} Spielen")
    return rows

# ============================================================
# 2. FOTMOB (kein Key, beste kostenlose Quelle)
# ============================================================
def fotmob_rows_for_date(date_str):
    log(f"📦 2. FotMob {date_str}...")
    rows = []
    try:
        data = jget(f"https://www.fotmob.com/api/matches?date={date_str.replace('-','')}")
        if not data:
            # Fallback: neuerer FotMob Endpoint
            data = jget(f"https://www.fotmob.com/api/fixtures?date={date_str}")
        if not data: health("fotmob", "empty", 0, date_str); return rows
        leagues = data.get("leagues") or []
        for league in leagues:
            league_name = league.get("name", "")
            for match in (league.get("matches") or []):
                if match.get("status", {}).get("finished") != True: continue
                mid = match.get("id")
                if not mid: continue
                # Hole Match Details
                detail = jget(f"https://www.fotmob.com/api/matchDetails?matchId={mid}")
                if not detail: continue
                content = detail.get("content") or {}
                lineup = content.get("lineup") or {}
                home_name = (detail.get("general") or {}).get("homeTeam", {}).get("name", "")
                away_name = (detail.get("general") or {}).get("awayTeam", {}).get("name", "")
                match_date = (detail.get("general") or {}).get("matchTimeUTC", "")[:10]

                for side in ("homeTeam", "awayTeam"):
                    team_name = home_name if side == "homeTeam" else away_name
                    players = (lineup.get(side) or {}).get("players") or []
                    for pl_list in players:
                        if isinstance(pl_list, list):
                            player_items = pl_list
                        else:
                            player_items = [pl_list]
                        for pl in player_items:
                            if not isinstance(pl, dict): continue
                            name = pl.get("name", {})
                            if isinstance(name, dict):
                                pname = name.get("fullName") or name.get("lastName", "")
                            else:
                                pname = str(name)
                            if not pname: continue
                            stats = pl.get("stats") or []
                            stat_map = {}
                            for stat_group in stats:
                                for k, v in (stat_group.get("stats") or {}).items():
                                    stat_map[k.lower()] = v.get("value") if isinstance(v, dict) else v
                            rows.append(player_row(
                                pname, team_name, f"fotmob_{mid}", match_date,
                                home_name, away_name, "fotmob",
                                minutes=si(stat_map.get("minutes played", stat_map.get("minutesplayed", 0))),
                                goals=si(stat_map.get("goals", 0)),
                                assists=si(stat_map.get("assists", 0)),
                                shots=si(stat_map.get("shots", stat_map.get("total shots", 0))),
                                sot=si(stat_map.get("shots on target", 0)),
                                tackles=si(stat_map.get("tackles", 0)),
                                fouls_committed=si(stat_map.get("fouls committed", stat_map.get("fouls", 0))),
                                cards=si(stat_map.get("yellow cards", 0)) + si(stat_map.get("red cards", 0)),
                                passes=si(stat_map.get("passes", stat_map.get("accurate passes", 0))),
                                xg=sf(stat_map.get("expected goals (xg)", stat_map.get("xg", 0))),
                                xa=sf(stat_map.get("expected assists (xa)", stat_map.get("xa", 0))),
                            ))
                time.sleep(0.3)
    except Exception as e:
        log(f"  ❌ FotMob: {e}")
        health("fotmob", "error", 0, str(e))
        return rows
    health("fotmob", "ok" if rows else "empty", len(rows), date_str)
    log(f"  ✅ FotMob: {len(rows)} Rows")
    return rows

# ============================================================
# 3. UNDERSTAT (xG/xA - Big 5 Ligen)
# ============================================================
def understat_rows(season=2024):
    log(f"📦 3. Understat xG/xA (Saison {season})...")
    rows = []
    leagues = ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1", "RFPL"]
    for league in leagues:
        try:
            r = safe_get(f"https://understat.com/league/{league}/{season}")
            if not r: continue
            # Extrahiere JSON aus HTML
            matches = re.findall(r"var datesData\s*=\s*JSON\.parse\('(.+?)'\)", r.text)
            if not matches: continue
            data = json.loads(matches[0].encode().decode('unicode_escape'))
            for match in data[:50]:  # letzte 50 Spiele
                if match.get("isResult") != True: continue
                mid = match.get("id")
                home = match.get("h", {}).get("title", "")
                away = match.get("a", {}).get("title", "")
                md = match.get("datetime", "")[:10]
                # Hole Player Stats für dieses Spiel
                pdata = jget(f"https://understat.com/match/{mid}")
                # Understat gibt HTML zurück, parse rostersData
                if not pdata:
                    # Versuche direkte Anfrage
                    pr = safe_get(f"https://understat.com/match/{mid}")
                    if not pr: continue
                    roster_matches = re.findall(r"var rostersData\s*=\s*JSON\.parse\('(.+?)'\)", pr.text)
                    if not roster_matches: continue
                    roster = json.loads(roster_matches[0].encode().decode('unicode_escape'))
                    for side in ("h", "a"):
                        team_name = home if side == "h" else away
                        for pid, pl in (roster.get(side) or {}).items():
                            pname = pl.get("player", "")
                            if not pname: continue
                            rows.append(player_row(
                                pname, team_name, f"understat_{mid}", md,
                                home, away, "understat",
                                minutes=si(pl.get("time", 0)),
                                shots=si(pl.get("shots", 0)),
                                goals=si(pl.get("goals", 0)),
                                assists=si(pl.get("assists", 0)),
                                xg=sf(pl.get("xG", 0)),
                                xa=sf(pl.get("xA", 0)),
                                fouls_committed=si(pl.get("yellow_card", 0)),
                                cards=si(pl.get("yellow_card", 0)) + si(pl.get("red_card", 0)),
                            ))
                    time.sleep(2.0)
        except Exception as e:
            log(f"  ⚠️ Understat {league}: {e}")
        time.sleep(3.0)
    health("understat", "ok" if rows else "blocked_or_empty", len(rows), f"season={season}")
    log(f"  ✅ Understat: {len(rows)} Rows")
    return rows

# ============================================================
# 4. ESPN API (kostenlos, kein Key)
# ============================================================
def espn_rows_for_date(date_str):
    log(f"📦 4. ESPN {date_str}...")
    rows = []
    leagues_espn = [
        ("eng.1", "Premier League"), ("esp.1", "La Liga"), ("ger.1", "Bundesliga"),
        ("ita.1", "Serie A"), ("fra.1", "Ligue 1"), ("uefa.champions", "UCL"),
        ("usa.1", "MLS"), ("mex.1", "Liga MX"), ("ned.1", "Eredivisie"),
        ("por.1", "Primeira Liga"), ("sco.1", "Scottish Premiership"),
    ]
    d = date_str.replace("-", "")
    for league_id, league_name in leagues_espn:
        try:
            data = jget(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/scoreboard?dates={d}")
            if not data: continue
            for event in (data.get("events") or []):
                comps = event.get("competitions") or []
                for comp in comps:
                    if comp.get("status", {}).get("type", {}).get("completed") != True: continue
                    mid = comp.get("id", "")
                    teams = comp.get("competitors") or []
                    home_team = next((t.get("team", {}).get("name", "") for t in teams if t.get("homeAway") == "home"), "")
                    away_team = next((t.get("team", {}).get("name", "") for t in teams if t.get("homeAway") == "away"), "")
                    # Hole Player Stats
                    pdata = jget(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/summary?event={mid}")
                    if not pdata: continue
                    for roster_side in (pdata.get("rosters") or []):
                        team_name = (roster_side.get("team") or {}).get("name", "")
                        for player in (roster_side.get("roster") or []):
                            pname = (player.get("athlete") or {}).get("displayName", "")
                            if not pname: continue
                            stats = {}
                            for sg in (player.get("stats") or []):
                                stats[sg.get("name", "").lower()] = sg.get("value", 0)
                            rows.append(player_row(
                                pname, team_name, f"espn_{mid}", date_str,
                                home_team, away_team, "espn",
                                minutes=si(stats.get("minutesplayed", stats.get("minutes", 0))),
                                goals=si(stats.get("goals", 0)),
                                assists=si(stats.get("assists", 0)),
                                shots=si(stats.get("shots", stats.get("totalshots", 0))),
                                sot=si(stats.get("shotsontarget", 0)),
                                tackles=si(stats.get("tackles", 0)),
                                fouls_committed=si(stats.get("foulscommitted", stats.get("fouls", 0))),
                                cards=si(stats.get("yellowcards", 0)) + si(stats.get("redcards", 0)),
                            ))
            time.sleep(0.5)
        except Exception as e:
            log(f"  ⚠️ ESPN {league_name}: {e}")
    health("espn", "ok" if rows else "empty", len(rows), date_str)
    log(f"  ✅ ESPN: {len(rows)} Rows")
    return rows

# ============================================================
# 5. FOOTBALL-DATA.CO.UK (Team Stats + Schiedsrichter)
# ============================================================
FDCOUK_LEAGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "SP1": "La Liga", "SP2": "La Liga 2",
    "D1": "Bundesliga", "D2": "2. Bundesliga",
    "I1": "Serie A", "I2": "Serie B",
    "F1": "Ligue 1", "F2": "Ligue 2",
    "N1": "Eredivisie", "P1": "Primeira Liga",
    "SC0": "Scottish Premiership", "B1": "Pro League",
    "G1": "Super League Greece", "T1": "Süper Lig",
}

def fdcouk_rows(season="2425"):
    log(f"📦 5. Football-Data.co.uk (Team Stats + Referee)...")
    team_rows = []
    referee_rows = []
    for code, name in FDCOUK_LEAGUES.items():
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        r = safe_get(url, timeout=15)
        if not r: continue
        try:
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                if not row.get("HomeTeam") or not row.get("Date"): continue
                # Team-Stats Zeile (Heim)
                team_rows.append({
                    "match_id": f"fdcouk_{code}_{row.get('Date','')}_{row.get('HomeTeam','')}",
                    "match_date": row.get("Date", ""),
                    "home_team": row.get("HomeTeam", ""),
                    "away_team": row.get("AwayTeam", ""),
                    "league": name,
                    "hs": si(row.get("HS", 0)), "as": si(row.get("AS", 0)),
                    "hst": si(row.get("HST", 0)), "ast": si(row.get("AST", 0)),
                    "hc": si(row.get("HC", 0)), "ac": si(row.get("AC", 0)),
                    "hf": si(row.get("HF", 0)), "af": si(row.get("AF", 0)),
                    "hy": si(row.get("HY", 0)), "ay": si(row.get("AY", 0)),
                    "hr": si(row.get("HR", 0)), "ar": si(row.get("AR", 0)),
                    "fthg": si(row.get("FTHG", 0)), "ftag": si(row.get("FTAG", 0)),
                    "hthg": si(row.get("HTHG", 0)), "htag": si(row.get("HTAG", 0)),
                    "ftr": row.get("FTR", ""), "htr": row.get("HTR", ""),
                    "referee": row.get("Referee", ""),
                    "attendance": si(row.get("Attendance", 0)),
                    "source": "fdcouk", "updated_at": now()
                })
                # Schiedsrichter-Row
                ref = row.get("Referee", "")
                if ref:
                    referee_rows.append({
                        "referee_name": clean(ref),
                        "match_date": row.get("Date", ""),
                        "home_team": row.get("HomeTeam", ""),
                        "away_team": row.get("AwayTeam", ""),
                        "league": name,
                        "total_yellow": si(row.get("HY", 0)) + si(row.get("AY", 0)),
                        "total_red": si(row.get("HR", 0)) + si(row.get("AR", 0)),
                        "total_fouls": si(row.get("HF", 0)) + si(row.get("AF", 0)),
                        "source": "fdcouk", "updated_at": now()
                    })
        except Exception as e:
            log(f"  ⚠️ FD.co.uk {code}: {e}")
        time.sleep(0.5)

    saved_teams = upsert("team_match_stats", team_rows, "match_id") if team_rows else 0
    saved_refs = upsert("referee_stats", referee_rows, "referee_name,match_date,home_team") if referee_rows else 0
    health("fdcouk", "ok" if team_rows else "empty", len(team_rows), f"refs={len(referee_rows)}")
    log(f"  ✅ FD.co.uk: {len(team_rows)} Team-Rows, {len(referee_rows)} Referee-Rows")
    return team_rows

# ============================================================
# 6. FPL API (Fantasy Premier League - detaillierte PL Stats)
# ============================================================
def fpl_rows():
    log("📦 6. FPL API (Premier League Player Stats)...")
    rows = []
    try:
        bootstrap = jget("https://fantasy.premierleague.com/api/bootstrap-static/")
        if not bootstrap: return rows
        players = bootstrap.get("elements") or []
        teams = {t["id"]: t["name"] for t in (bootstrap.get("teams") or [])}
        for pl in players:
            pname = f"{pl.get('first_name', '')} {pl.get('second_name', '')}".strip()
            team_name = teams.get(pl.get("team"), "")
            rows.append(player_row(
                pname, team_name, f"fpl_{pl.get('id')}", today(),
                "", "", "fpl_api",
                goals=si(pl.get("goals_scored", 0)),
                assists=si(pl.get("assists", 0)),
                minutes=si(pl.get("minutes", 0)),
                shots=si(pl.get("shots", 0)),
                cards=si(pl.get("yellow_cards", 0)) + si(pl.get("red_cards", 0)),
                fouls_committed=si(pl.get("penalties_missed", 0)),
            ))
    except Exception as e:
        log(f"  ❌ FPL: {e}")
    health("fpl_api", "ok" if rows else "empty", len(rows))
    log(f"  ✅ FPL: {len(rows)} Spieler")
    return rows

# ============================================================
# 7. FPL CORE INSIGHTS (Tackles, Blocks, Interceptions, Clearances)
# ============================================================
def fpl_core_rows():
    log("📦 7. FPL Core Insights (Defensive Stats)...")
    rows = []
    try:
        base = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/2025-2026"
        data = jget(f"{base}/playerstats.json")
        if not data and isinstance(data, type(None)):
            # Versuche CSV
            r = safe_get(f"{base}/playerstats.csv")
            if r:
                reader = csv.DictReader(io.StringIO(r.text))
                for row in reader:
                    pname = row.get("web_name") or row.get("player_name", "")
                    if not pname: continue
                    rows.append(player_row(
                        pname, row.get("team", ""), f"fpl_core_{row.get('id',pname)}",
                        today(), "", "", "fpl_core",
                        minutes=si(row.get("minutes", 0)),
                        goals=si(row.get("goals_scored", 0)),
                        assists=si(row.get("assists", 0)),
                        tackles=si(row.get("tackles", 0)),
                        cards=si(row.get("yellow_cards", 0)) + si(row.get("red_cards", 0)),
                    ))
    except Exception as e:
        log(f"  ⚠️ FPL Core: {e}")
    health("fpl_core", "ok" if rows else "empty", len(rows))
    log(f"  ✅ FPL Core: {len(rows)} Rows")
    return rows

# ============================================================
# 8. THESTATSAPI (xG, Lineups, Player Stats)
# ============================================================
def thestatsapi_rows_for_date(date_str):
    if not THESTATSAPI_KEY:
        log("📦 8. TheStatsAPI: kein Key"); return []
    log(f"📦 8. TheStatsAPI {date_str}...")
    rows = []
    try:
        h = {"X-Auth-Token": THESTATSAPI_KEY}
        data = jget("https://api.thestatsapi.com/v1/football/matches",
                    params={"date": date_str}, headers=h)
        if not data: return rows
        for match in (data.get("data") or data if isinstance(data, list) else []):
            mid = match.get("id", "")
            home = match.get("homeTeam", {}).get("name", "")
            away = match.get("awayTeam", {}).get("name", "")
            md = match.get("date", "")[:10]
            # Player Stats
            pdata = jget(f"https://api.thestatsapi.com/v1/football/matches/{mid}/players",
                        headers=h)
            if not pdata: continue
            for side in ("homeTeamPlayers", "awayTeamPlayers"):
                team = home if "home" in side.lower() else away
                for pl in (pdata.get(side) or []):
                    pname = pl.get("name", "")
                    if not pname: continue
                    st = pl.get("stats") or {}
                    rows.append(player_row(
                        pname, team, f"tsa_{mid}", md, home, away, "thestatsapi",
                        minutes=si(st.get("minutesPlayed", 0)),
                        goals=si(st.get("goals", 0)),
                        assists=si(st.get("assists", 0)),
                        shots=si(st.get("shots", 0)),
                        sot=si(st.get("shotsOnTarget", 0)),
                        xg=sf(st.get("xG", 0)),
                        xa=sf(st.get("xA", 0)),
                        tackles=si(st.get("tackles", 0)),
                        fouls_committed=si(st.get("foulsCommitted", 0)),
                        cards=si(st.get("yellowCards", 0)) + si(st.get("redCards", 0)),
                    ))
    except Exception as e:
        log(f"  ⚠️ TheStatsAPI: {e}")
    health("thestatsapi", "ok" if rows else "empty", len(rows), date_str)
    log(f"  ✅ TheStatsAPI: {len(rows)} Rows")
    return rows

# ============================================================
# 9. FOOTBALL-DATA.ORG (Free Tier - 10 Ligen + UCL)
# ============================================================
def football_data_org_rows(api_keys_str=""):
    log("📦 9. Football-Data.org...")
    rows = []
    keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    if not keys:
        keys_env = os.getenv("FOOTBALL_DATA_API_KEYS", os.getenv("FOOTBALL_DATA_API_KEY", ""))
        keys = [k.strip() for k in keys_env.split(",") if k.strip()]
    if not keys: log("  ⚠️ Kein Key für football-data.org"); return rows

    key = keys[0]
    competitions = ["PL", "BL1", "SA", "PD", "FL1", "CL", "PPL", "DED", "BSA"]
    for comp in competitions:
        try:
            data = jget(
                f"https://api.football-data.org/v4/competitions/{comp}/matches",
                params={"status": "FINISHED", "limit": 10},
                headers={"X-Auth-Token": key}
            )
            if not data: continue
            for match in (data.get("matches") or [])[:5]:
                mid = match.get("id", "")
                home = (match.get("homeTeam") or {}).get("name", "")
                away = (match.get("awayTeam") or {}).get("name", "")
                md = (match.get("utcDate") or "")[:10]
                # Hole Lineups
                mdata = jget(
                    f"https://api.football-data.org/v4/matches/{mid}",
                    headers={"X-Auth-Token": key}
                )
                if not mdata: continue
                for side in ("homeTeam", "awayTeam"):
                    team = home if side == "homeTeam" else away
                    lineup = (mdata.get(side) or {}).get("lineup") or []
                    for pl in lineup:
                        pname = pl.get("name", "")
                        if not pname: continue
                        rows.append(player_row(
                            pname, team, f"fdorg_{mid}", md, home, away, "football_data_org"
                        ))
                time.sleep(3.0)
        except Exception as e:
            log(f"  ⚠️ FD.org {comp}: {e}")
        time.sleep(2.0)  # Extra Sleep für Rate Limit
    health("football_data_org", "ok" if rows else "empty", len(rows))
    log(f"  ✅ Football-Data.org: {len(rows)} Rows")
    return rows

# ============================================================
# 10. OPENLIGADB (Bundesliga, kein Key)
# ============================================================
def openligadb_rows(league="bl1", season=2024):
    log(f"📦 10. OpenLigaDB {league} {season}...")
    rows = []
    try:
        matches = jget(f"https://api.openligadb.de/getmatchdata/{league}/{season}") or []
        for match in matches:
            if match.get("matchIsFinished") != True: continue
            mid = match.get("matchID", "")
            home = (match.get("team1") or {}).get("teamName", "")
            away = (match.get("team2") or {}).get("teamName", "")
            md = (match.get("matchDateTimeUTC") or "")[:10]
            # Tore als Events
            for goal in (match.get("goals") or []):
                scorer = goal.get("goalGetterName", "")
                if scorer:
                    rows.append(player_row(
                        scorer, "", f"openligadb_{mid}", md, home, away, "openligadb",
                        goals=1
                    ))
    except Exception as e:
        log(f"  ❌ OpenLigaDB: {e}")
    health("openligadb", "ok" if rows else "empty", len(rows))
    log(f"  ✅ OpenLigaDB: {len(rows)} Rows")
    return rows

# ============================================================
# 11. CLUBELO (Elo Ratings → team_elo Tabelle)
# ============================================================
def clubelo_rows():
    log("📦 11. ClubElo Ratings...")
    rows = []
    try:
        r = safe_get("http://api.clubelo.com/" + today())
        if not r: return rows
        for line in r.text.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) < 5: continue
            rows.append({
                "team_name": clean(parts[1]),
                "elo": sf(parts[4]),
                "rank": si(parts[0]),
                "country": parts[2],
                "league": parts[3],
                "date": today(),
                "source": "clubelo",
                "updated_at": now()
            })
    except Exception as e:
        log(f"  ❌ ClubElo: {e}")
    saved = upsert("team_elo", rows, "team_name,date") if rows else 0
    health("clubelo", "ok" if rows else "empty", len(rows))
    log(f"  ✅ ClubElo: {len(rows)} Teams")
    return rows

# ============================================================
# 12. MARTJ42 (Länderspiele Historical)
# ============================================================
def martj42_rows():
    log("📦 12. martj42 International Results...")
    rows = []
    try:
        data = jget("https://raw.githubusercontent.com/martj42/international_results/master/results.csv")
        if not data:
            r = safe_get("https://raw.githubusercontent.com/martj42/international_results/master/results.csv")
            if not r: return rows
            reader = csv.DictReader(io.StringIO(r.text))
            recent = []
            for row in reader:
                recent.append(row)
            # Nur letzte 2 Jahre
            cutoff = (datetime.now(timezone.utc) - timedelta(days=730)).date().isoformat()
            for row in recent:
                if row.get("date", "") < cutoff: continue
                mid = f"martj42_{row.get('date','')}_{row.get('home_team','')}_{row.get('away_team','')}"
                rows.append({
                    "match_id": mid,
                    "match_date": row.get("date", ""),
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "home_score": si(row.get("home_score", 0)),
                    "away_score": si(row.get("away_score", 0)),
                    "tournament": row.get("tournament", ""),
                    "neutral": row.get("neutral", ""),
                    "source": "martj42", "updated_at": now()
                })
    except Exception as e:
        log(f"  ❌ martj42: {e}")
    saved = upsert("international_results", rows, "match_id") if rows else 0
    health("martj42", "ok" if rows else "empty", len(rows))
    log(f"  ✅ martj42: {len(rows)} Länderspiele")
    return rows

# ============================================================
# 13. XGABORA CSV (475k Spiele, 42 Ligen, 2000-2025)
# ============================================================
def xgabora_rows():
    log("📦 13. xgabora Club Football Match Data 2000-2025...")
    rows = []
    try:
        # Hauptdatensatz: Repo hat je nach Version andere Pfade/Dateinamen.
        urls = [
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv",
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/matches.csv",
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/Matches.csv",
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/matches.csv",
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/master/data/Matches.csv",
            "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/master/data/matches.csv",
        ]
        r = None
        for _url in urls:
            r = safe_get(_url, timeout=90)
            if r:
                break
        if not r:
            health("xgabora", "empty", 0); return rows
        reader = csv.DictReader(io.StringIO(r.text))
        # Nur letzte 3 Jahre für Team Stats
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1095)).date().isoformat()
        for row in reader:
            md = row.get("date", row.get("Date", ""))
            if md and md < cutoff: continue
            home = row.get("home_team", row.get("HomeTeam", ""))
            away = row.get("away_team", row.get("AwayTeam", ""))
            if not home or not away: continue
            rows.append({
                "match_id": f"xgabora_{md}_{home}_{away}",
                "match_date": md,
                "home_team": clean(home),
                "away_team": clean(away),
                "league": row.get("league", row.get("Div", "")),
                "country": row.get("country", ""),
                "fthg": si(row.get("fthg", row.get("FTHG", 0))),
                "ftag": si(row.get("ftag", row.get("FTAG", 0))),
                "hthg": si(row.get("hthg", row.get("HTHG", 0))),
                "htag": si(row.get("htag", row.get("HTAG", 0))),
                "home_shots": si(row.get("hs", row.get("HS", 0))),
                "away_shots": si(row.get("as_", row.get("as", row.get("AS", 0)))),
                "home_sot": si(row.get("hst", row.get("HST", 0))),
                "away_sot": si(row.get("ast", row.get("AST", 0))),
                "home_corners": si(row.get("hc", row.get("HC", 0))),
                "away_corners": si(row.get("ac", row.get("AC", 0))),
                "home_fouls": si(row.get("hf", row.get("HF", 0))),
                "away_fouls": si(row.get("af", row.get("AF", 0))),
                "home_yellow": si(row.get("hy", row.get("HY", 0))),
                "away_yellow": si(row.get("ay", row.get("AY", 0))),
                "home_red": si(row.get("hr", row.get("HR", 0))),
                "away_red": si(row.get("ar", row.get("AR", 0))),
                "home_elo": sf(row.get("home_elo", row.get("HomeElo", 0))),
                "away_elo": sf(row.get("away_elo", row.get("AwayElo", 0))),
                "source": "xgabora", "updated_at": now()
            })
    except Exception as e:
        log(f"  ❌ xgabora: {e}")
    saved = upsert("team_match_stats", rows, "match_id") if rows else 0
    health("xgabora", "ok" if rows else "empty", len(rows))
    log(f"  ✅ xgabora: {len(rows)} Spiele")
    return rows

# ============================================================
# 14. OPENFOOTBALL JSON (aktuelle Saison + WM 2026 live)
# ============================================================
def openfootball_rows():
    log("📦 14. openfootball JSON (aktuelle Saison + WM 2026)...")
    rows = []
    sources = [
        ("https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json", "WM 2026"),
        ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json", "Premier League 25/26"),
        ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/de.1.json", "Bundesliga 25/26"),
        ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/es.1.json", "La Liga 25/26"),
        ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/it.1.json", "Serie A 25/26"),
        ("https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/fr.1.json", "Ligue 1 25/26"),
    ]

    def _extract_matches(data):
        if isinstance(data, dict):
            if isinstance(data.get("matches"), list):
                return data.get("matches") or []
            if isinstance(data.get("rounds"), list):
                out = []
                for rnd in data.get("rounds") or []:
                    if isinstance(rnd, dict):
                        out.extend(rnd.get("matches") or [])
                return out
            return []
        if isinstance(data, list):
            out = []
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("matches"), list):
                    out.extend(item.get("matches") or [])
                elif isinstance(item, dict):
                    out.append(item)
            return out
        return []

    def _team_name(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return x.get("name") or x.get("team") or ""
        return ""

    def _score_ft(score):
        if isinstance(score, dict):
            ft = score.get("ft") or score.get("fulltime") or score.get("full_time")
            if isinstance(ft, list) and len(ft) >= 2:
                return si(ft[0]), si(ft[1])
            if isinstance(ft, dict):
                return si(ft.get("home")), si(ft.get("away"))
            if "home" in score and "away" in score:
                return si(score.get("home")), si(score.get("away"))
        if isinstance(score, list) and len(score) >= 2:
            return si(score[0]), si(score[1])
        return None, None

    for url, league_name in sources:
        try:
            data = jget(url)
            if not data:
                continue
            matches = _extract_matches(data)
            for match in matches:
                if not isinstance(match, dict):
                    continue
                h_name = _team_name(match.get("team1") or match.get("home") or match.get("home_team"))
                a_name = _team_name(match.get("team2") or match.get("away") or match.get("away_team"))
                md = match.get("date", "")
                hg, ag = _score_ft(match.get("score") or {})
                goals = match.get("goals") or []

                # Manche openfootball Dateien liefern nur Resultate, keine Goal-Events.
                # Dann wenigstens Team-Goal-Pseudo-Rows erzeugen, damit aktuelle Ergebnisse nicht verloren gehen.
                if goals:
                    for goal in goals:
                        if not isinstance(goal, dict):
                            continue
                        scorer = goal.get("name") or goal.get("player") or ""
                        team = goal.get("team") or ""
                        if scorer:
                            rows.append(player_row(
                                scorer, team, f"openfootball_{league_name}_{md}_{h_name}",
                                md, h_name, a_name, "openfootball",
                                goals=1
                            ))
                elif hg is not None or ag is not None:
                    if hg:
                        rows.append(player_row(
                            f"{h_name} team goals", h_name, f"openfootball_{league_name}_{md}_{h_name}",
                            md, h_name, a_name, "openfootball", goals=hg
                        ))
                    if ag:
                        rows.append(player_row(
                            f"{a_name} team goals", a_name, f"openfootball_{league_name}_{md}_{a_name}",
                            md, h_name, a_name, "openfootball", goals=ag
                        ))
        except Exception as e:
            log(f"  ⚠️ openfootball {league_name}: {e}")
    health("openfootball", "ok" if rows else "empty", len(rows))
    log(f"  ✅ openfootball: {len(rows)} Goal-Events")
    return rows

# ============================================================
# 15. WM 2026 DATASET (täglich aktualisiert, Schiedsrichter, xG)
# ============================================================
def wm2026_rows():
    log("📦 15. WM 2026 Dataset (GitHub)...")
    rows = []
    ref_rows = []
    try:
        base = "https://raw.githubusercontent.com/mominullptr/FIFA-World-Cup-2026-Dataset/main"
        # Match Events (Goals, Cards, Assists)
        r = safe_get(f"{base}/match_events.csv")
        if r:
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                pname = row.get("player_name", "")
                if not pname: continue
                event_type = row.get("event_type", "").lower()
                rows.append(player_row(
                    pname, row.get("team_name", ""),
                    f"wm2026_{row.get('match_id', '')}",
                    row.get("date", ""), row.get("home_team", ""),
                    row.get("away_team", ""), "wm2026_dataset",
                    goals=1 if "goal" in event_type else 0,
                    assists=1 if "assist" in event_type else 0,
                    cards=1 if "card" in event_type else 0,
                ))

        # Match Team Stats (Shots, Corners, Fouls, xG)
        r2 = safe_get(f"{base}/match_team_stats.csv")
        if r2:
            reader2 = csv.DictReader(io.StringIO(r2.text))
            team_stats = []
            for row in reader2:
                team_stats.append({
                    "match_id": f"wm2026_{row.get('match_id','')}_{row.get('team_name','')}",
                    "match_date": row.get("date", ""),
                    "team_name": row.get("team_name", ""),
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "shots": si(row.get("shots", 0)),
                    "shots_on_target": si(row.get("shots_on_target", 0)),
                    "corners": si(row.get("corners", 0)),
                    "fouls": si(row.get("fouls", 0)),
                    "xg": sf(row.get("xg", 0)),
                    "source": "wm2026", "updated_at": now()
                })
            if team_stats:
                upsert("team_match_stats", team_stats, "match_id")

        # Schiedsrichter-Daten
        r3 = safe_get(f"{base}/matches_detailed.csv")
        if r3:
            reader3 = csv.DictReader(io.StringIO(r3.text))
            for row in reader3:
                ref = row.get("referee_name", "")
                if not ref: continue
                ref_rows.append({
                    "referee_name": clean(ref),
                    "match_date": row.get("date", ""),
                    "home_team": row.get("home_team_name", ""),
                    "away_team": row.get("away_team_name", ""),
                    "league": "FIFA World Cup 2026",
                    "source": "wm2026", "updated_at": now()
                })

    except Exception as e:
        log(f"  ❌ WM2026: {e}")

    if ref_rows:
        upsert("referee_stats", ref_rows, "referee_name,match_date,home_team")
    health("wm2026", "ok" if rows else "empty", len(rows))
    log(f"  ✅ WM2026: {len(rows)} Events, {len(ref_rows)} Referee-Rows")
    return rows

# ============================================================
# 16. JFJELSTUL WM REFEREE DATABASE (1930-2022)
# ============================================================
def jfjelstul_referee_rows():
    log("📦 16. jfjelstul WM Referee Database...")
    rows = []
    try:
        base = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv"
        r = safe_get(f"{base}/referees.csv")
        if r:
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                rows.append({
                    "referee_name": clean(row.get("referee_name", "")),
                    "country": row.get("country_name", ""),
                    "confederation": row.get("confederation_id", ""),
                    "source": "jfjelstul_worldcup",
                    "updated_at": now()
                })
        if rows:
            upsert("referee_stats", rows, "referee_name,match_date,home_team")
    except Exception as e:
        log(f"  ⚠️ jfjelstul: {e}")
    health("jfjelstul_wc", "ok" if rows else "empty", len(rows))
    log(f"  ✅ jfjelstul WC Referees: {len(rows)}")
    return rows

# ============================================================
# 17. PHYSIOROOM (Verletzungen Premier League)
# ============================================================
def physioroom_rows():
    log("📦 17. PhysioRoom (Verletzungen)...")
    rows = []
    try:
        r = safe_get("https://www.physioroom.com/news/english_premier_league/epl_injury_table.php")
        if not r: return rows
        # Parse HTML Table
        table_match = re.search(r'<table[^>]*class="[^"]*injury[^"]*"[^>]*>(.*?)</table>', r.text, re.S|re.I)
        if not table_match:
            table_match = re.search(r'<table[^>]*>(.*?)</table>', r.text, re.S|re.I)
        if table_match:
            for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.S|re.I):
                cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S|re.I)
                cells = [re.sub(r'<.*?>', '', c).strip() for c in cells]
                if len(cells) >= 3:
                    rows.append({
                        "player_name": clean(cells[0]),
                        "team_name": clean(cells[1]) if len(cells) > 1 else "",
                        "injury_type": clean(cells[2]) if len(cells) > 2 else "",
                        "return_date": clean(cells[3]) if len(cells) > 3 else "",
                        "source": "physioroom", "updated_at": now()
                    })
        if rows:
            upsert("player_injuries", rows, "player_name,team_name")
    except Exception as e:
        log(f"  ⚠️ PhysioRoom: {e}")
    health("physioroom", "ok" if rows else "empty", len(rows))
    log(f"  ✅ PhysioRoom: {len(rows)} Verletzungen")
    return rows

# ============================================================
# 18. OPEN-METEO (Wetter für Stadien)
# ============================================================
STADIUMS = {
    "London": (51.5074, -0.1278), "Manchester": (53.4808, -2.2426),
    "Munich": (48.1374, 11.5755), "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3851, 2.1734), "Milan": (45.4654, 9.1859),
    "Paris": (48.8566, 2.3522), "Amsterdam": (52.3676, 4.9041),
    "Dortmund": (51.5134, 7.4653), "Rome": (41.9028, 12.4964),
    "Lisbon": (38.7223, -9.1393), "Porto": (41.1579, -8.6291),
    "Glasgow": (55.8642, -4.2518), "Brussels": (50.8503, 4.3517),
    "Vienna": (48.2082, 16.3738), "Zurich": (47.3769, 8.5417),
}

def openmeteo_rows():
    log("📦 18. Open-Meteo Wetter...")
    rows = []
    try:
        for city, (lat, lon) in STADIUMS.items():
            data = jget(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                    "forecast_days": 3, "timezone": "auto"
                }
            )
            if not data: continue
            daily = data.get("daily") or {}
            times = daily.get("time") or []
            for i, d in enumerate(times):
                rows.append({
                    "city": city, "date": d,
                    "temp_max": sf((daily.get("temperature_2m_max") or [0])[i] if i < len(daily.get("temperature_2m_max") or []) else 0),
                    "temp_min": sf((daily.get("temperature_2m_min") or [0])[i] if i < len(daily.get("temperature_2m_min") or []) else 0),
                    "precipitation": sf((daily.get("precipitation_sum") or [0])[i] if i < len(daily.get("precipitation_sum") or []) else 0),
                    "wind_max": sf((daily.get("windspeed_10m_max") or [0])[i] if i < len(daily.get("windspeed_10m_max") or []) else 0),
                    "source": "open_meteo", "updated_at": now()
                })
            time.sleep(0.2)
    except Exception as e:
        log(f"  ⚠️ Open-Meteo: {e}")
    saved = upsert("weather_forecast", rows, "city,date") if rows else 0
    health("open_meteo", "ok" if rows else "empty", len(rows))
    log(f"  ✅ Open-Meteo: {len(rows)} Wetter-Rows")
    return rows

# ============================================================
# 19. SOFASCORE (Player Stats per Datum)
# ============================================================
def sofascore_rows_for_date(date_str, max_events=30):
    log(f"📦 19. SofaScore {date_str}...")
    rows = []
    try:
        data = jget(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}")
        if not data: health("sofascore", "blocked", 0, date_str); return rows
        events = data.get("events") or []
        fin = [e for e in events if (e.get("status") or {}).get("type", "").lower() in
               ("finished", "afterpenalties", "afterextra")]
        log(f"  SofaScore: {len(fin)} beendete Spiele")
        for ev in fin[:max_events]:
            eid = ev.get("id")
            if not eid: continue
            lineups = jget(f"https://api.sofascore.com/api/v1/event/{eid}/lineups")
            if not lineups: continue
            evdata = jget(f"https://api.sofascore.com/api/v1/event/{eid}") or {}
            event = evdata.get("event", {})
            home = (event.get("homeTeam") or {}).get("name", "")
            away = (event.get("awayTeam") or {}).get("name", "")
            ts = event.get("startTimestamp")
            md = datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else date_str
            for side in ("home", "away"):
                team = home if side == "home" else away
                for item in ((lineups.get(side) or {}).get("players") or []):
                    pl = item.get("player") or {}
                    st = item.get("statistics") or {}
                    pname = pl.get("name") or pl.get("shortName", "")
                    if not pname: continue
                    rows.append(player_row(
                        pname, team, f"sofascore_{eid}", md, home, away, "sofascore",
                        minutes=si(st.get("minutesPlayed") or st.get("minutes", 0)),
                        shots=si(st.get("totalShots") or st.get("shots", 0)),
                        sot=si(st.get("shotsOnTarget", 0)),
                        goals=si(st.get("goals", 0)),
                        assists=si(st.get("goalAssist") or st.get("assists", 0)),
                        passes=si(st.get("totalPass") or st.get("passes", 0)),
                        tackles=si(st.get("totalTackle") or st.get("tackles", 0)),
                        fouls_committed=si(st.get("fouls") or st.get("foulsCommitted", 0)),
                        fouls_won=si(st.get("wasFouled") or st.get("foulsWon", 0)),
                        cards=si(st.get("yellowCards", 0)) + si(st.get("redCards", 0)),
                        xg=sf(st.get("expectedGoals", st.get("xg", 0))),
                        xa=sf(st.get("expectedAssists", st.get("xa", 0))),
                    ))
            time.sleep(0.3)
    except Exception as e:
        log(f"  ⚠️ SofaScore: {e}")
    health("sofascore", "ok" if rows else "empty", len(rows), date_str)
    log(f"  ✅ SofaScore: {len(rows)} Rows")
    return rows

# ============================================================
# 20. FBREF (wenn nicht geblockt)
# ============================================================
FBREF_URLS = [
    ("https://fbref.com/en/comps/9/stats/Premier-League-Stats", "Premier League"),
    ("https://fbref.com/en/comps/20/stats/Bundesliga-Stats", "Bundesliga"),
    ("https://fbref.com/en/comps/12/stats/La-Liga-Stats", "La Liga"),
    ("https://fbref.com/en/comps/11/stats/Serie-A-Stats", "Serie A"),
    ("https://fbref.com/en/comps/13/stats/Ligue-1-Stats", "Ligue 1"),
    ("https://fbref.com/en/comps/8/stats/Champions-League-Stats", "UCL"),
    ("https://fbref.com/en/comps/14/stats/Primera-Division-Argentina-Stats", "Argentina"),
    ("https://fbref.com/en/comps/24/stats/Serie-A-Stats", "Brazil"),
]

def fbref_rows():
    log("📦 20. FBref (wenn nicht geblockt)...")
    rows = []
    for url, league_name in FBREF_URLS:
        r = safe_get(url, timeout=25)
        if not r: time.sleep(7); continue
        try:
            html = r.text
            html = re.sub(r"<br\s*/?>", " ", html)
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S|re.I):
                if 'data-stat="player"' not in tr: continue
                cells = {}
                for stat, val in re.findall(r'data-stat="([^"]+)"[^>]*>(.*?)</t[dh]>', tr, re.S|re.I):
                    cells[stat] = re.sub(r"<.*?>", "", val).strip()
                pname = cells.get("player", "")
                if not pname or pname.lower() == "player": continue
                rows.append(player_row(
                    pname, cells.get("team") or cells.get("squad", ""),
                    "fbref_season", "", "", "", "fbref",
                    minutes=si(cells.get("minutes", 0)),
                    shots=si(cells.get("shots_total", 0)),
                    sot=si(cells.get("shots_on_target", 0)),
                    goals=si(cells.get("goals", 0)),
                    assists=si(cells.get("assists", 0)),
                    passes=si(cells.get("passes_completed", 0)),
                    tackles=si(cells.get("tackles", 0)),
                    cards=si(cells.get("cards_yellow", 0)) + si(cells.get("cards_red", 0)),
                    xg=sf(cells.get("xg", 0)),
                    xa=sf(cells.get("xa", 0)),
                ))
            log(f"  FBref {league_name}: {len(rows)} Spieler")
        except Exception as e:
            log(f"  ⚠️ FBref {league_name}: {e}")
        time.sleep(7)
    health("fbref", "ok" if rows else "blocked_or_empty", len(rows))
    log(f"  ✅ FBref total: {len(rows)} Rows")
    return rows

# ============================================================
# 21. SPORTMONKS (Dänemark + Schottland, Free Key)
# ============================================================
def sportmonks_rows_for_date(date_str):
    if not SPORTMONKS_KEY: log("📦 21. Sportmonks: kein Key"); return []
    log(f"📦 21. Sportmonks {date_str}...")
    rows = []
    try:
        data = jget(
            f"https://api.sportmonks.com/v3/football/fixtures/date/{date_str}",
            params={"api_token": SPORTMONKS_KEY, "include": "lineups;scores"}
        )
        for fixture in (data or {}).get("data") or []:
            mid = fixture.get("id", "")
            home = (fixture.get("localTeam") or {}).get("data", {}).get("name", "")
            away = (fixture.get("visitorTeam") or {}).get("data", {}).get("name", "")
            md = (fixture.get("time") or {}).get("starting_at", {}).get("date", date_str)
            for pl in (fixture.get("lineup") or {}).get("data") or []:
                pname = (pl.get("player") or {}).get("data", {}).get("display_name", "")
                team = home if pl.get("team_id") == fixture.get("localteam_id") else away
                if pname:
                    rows.append(player_row(
                        pname, team, f"sportmonks_{mid}", md, home, away, "sportmonks"
                    ))
    except Exception as e:
        log(f"  ⚠️ Sportmonks: {e}")
    health("sportmonks", "ok" if rows else "empty", len(rows), date_str)
    log(f"  ✅ Sportmonks: {len(rows)} Rows")
    return rows

# ============================================================
# 22. PINNACLE PROPS (aus Bot-Logik)
# ============================================================
def pinnacle_props_rows():
    log("📦 22. Pinnacle Player Props...")
    rows = []
    try:
        r = safe_get(
            "https://guest.api.arcadia.pinnacle.com/0.1/leagues/1980/markets/straight",
            headers={"X-Device-UUID": "v1.1234567890", "Content-Type": "application/json"}
        )
        if not r: return rows
        data = r.json()
        for market in (data or [])[:200]:
            desc = market.get("description", "")
            parts = market.get("participants") or []
            odds = market.get("prices") or []
            if not desc or len(parts) < 1: continue
            for i, part in enumerate(parts[:2]):
                pname = part.get("name", "")
                if not pname: continue
                price = next((p.get("price", 0) for p in odds if p.get("participantId") == part.get("id")), 0)
                rows.append({
                    "player_name": clean(pname),
                    "market": clean(desc),
                    "odds": sf(price),
                    "source": "pinnacle_props",
                    "updated_at": now()
                })
    except Exception as e:
        log(f"  ⚠️ Pinnacle Props: {e}")
    health("pinnacle_props", "ok" if rows else "empty", len(rows))
    log(f"  ✅ Pinnacle Props: {len(rows)} Props")
    return rows

# ============================================================
# REBUILD: Berechne Durchschnitte + Hit Rates aus player_match_stats
# ============================================================
def rebuild(days_back=365):
    log(f"🔄 Rebuild player_avg_stats (letzte {days_back} Tage)...")
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
    rows = sb_get("player_match_stats", {
        "select": "*", "match_date": f"gte.{since}", "limit": "50000"
    })
    if not rows:
        log("  ⚠️ Keine player_match_stats"); return 0

    agg = {}
    for r in rows:
        p = clean(r.get("player_name", ""))
        # Filtere ungültige Namen
        if not p or len(p) < 2: continue
        if p.upper() == p and len(p) > 15: continue  # "COMPETITION_RECORD" etc
        if any(c.isdigit() for c in p) and len(p) < 4: continue
        a = agg.setdefault(p, {
            "player_name": p, "team_name": r.get("team_name") or "", "games": 0,
            "minutes": 0, "shots": 0, "sot": 0, "goals": 0, "assists": 0,
            "passes": 0, "tackles": 0, "fouls_committed": 0, "fouls_won": 0,
            "cards": 0, "corners": 0, "xg_total": 0.0, "xa_total": 0.0,
            "games_sot": 0, "games_shot": 0, "games_goal": 0,
            "games_assist": 0, "games_foul": 0, "games_card": 0,
            "games_tackle": 0,
        })
        a["games"] += 1
        for k in ("minutes", "shots", "sot", "goals", "assists", "passes",
                  "tackles", "fouls_committed", "fouls_won", "cards", "corners"):
            a[k] += sf(r.get(k, 0))
        a["xg_total"] += sf(r.get("xg", 0))
        a["xa_total"] += sf(r.get("xa", 0))
        # Hit Rate Counters
        if sf(r.get("sot", 0)) >= 1: a["games_sot"] += 1
        if sf(r.get("shots", 0)) >= 1: a["games_shot"] += 1
        if sf(r.get("goals", 0)) >= 1: a["games_goal"] += 1
        if sf(r.get("assists", 0)) >= 1: a["games_assist"] += 1
        if sf(r.get("fouls_committed", 0)) >= 1: a["games_foul"] += 1
        if sf(r.get("cards", 0)) >= 1: a["games_card"] += 1
        if sf(r.get("tackles", 0)) >= 1: a["games_tackle"] += 1

    out = []
    for p, a in agg.items():
        g = max(1, a["games"])
        minutes_avg = round(a["minutes"] / g, 2)
        shots_avg = round(a["shots"] / g, 3)
        sot_avg = round(a["sot"] / g, 3)
        goals_avg = round(a["goals"] / g, 3)
        assists_avg = round(a["assists"] / g, 3)
        passes_avg = round(a["passes"] / g, 3)
        tackles_avg = round(a["tackles"] / g, 3)
        fouls_committed_avg = round(a["fouls_committed"] / g, 3)
        fouls_won_avg = round(a["fouls_won"] / g, 3)
        cards_avg = round(a["cards"] / g, 3)
        corners_avg = round(a["corners"] / g, 3)
        xg_avg = round(a["xg_total"] / g, 4)
        xa_avg = round(a["xa_total"] / g, 4)

        out.append({
            "player_name": p,
            "stat_name": "avg",
            "stat_type": "player_average",
            "team_name": a["team_name"] or "",
            "team": a["team_name"] or "",
            "league": "",
            "position": "",
            "games": a["games"],

            # Compatibility columns for old and new bot versions
            "minutes": minutes_avg,
            "minutes_avg": minutes_avg,
            "shots": shots_avg,
            "shots_pg": shots_avg,
            "shots_avg": shots_avg,
            "sot": sot_avg,
            "sot_pg": sot_avg,
            "sot_avg": sot_avg,
            "goals": goals_avg,
            "goals_pg": goals_avg,
            "goals_avg": goals_avg,
            "assists": assists_avg,
            "assists_pg": assists_avg,
            "assists_avg": assists_avg,
            "passes": passes_avg,
            "passes_pg": passes_avg,
            "passes_avg": passes_avg,
            "tackles": tackles_avg,
            "tackles_pg": tackles_avg,
            "tackles_avg": tackles_avg,
            "fouls_committed": fouls_committed_avg,
            "fouls_committed_pg": fouls_committed_avg,
            "fouls_committed_avg": fouls_committed_avg,
            "fouls_won": fouls_won_avg,
            "fouls_won_pg": fouls_won_avg,
            "fouls_won_avg": fouls_won_avg,
            "cards": cards_avg,
            "cards_pg": cards_avg,
            "cards_avg": cards_avg,
            "corners": corners_avg,
            "corners_pg": corners_avg,
            "corners_avg": corners_avg,
            "xg": xg_avg,
            "xg_pg": xg_avg,
            "xg_avg": xg_avg,
            "xa": xa_avg,
            "xa_pg": xa_avg,
            "xa_avg": xa_avg,

            # Hit Rates (Wahrscheinlichkeit mind. 1x in einem Spiel)
            "hr_sot": round(a["games_sot"] / g, 3),
            "hr_shot": round(a["games_shot"] / g, 3),
            "hr_goal": round(a["games_goal"] / g, 3),
            "hr_assist": round(a["games_assist"] / g, 3),
            "hr_foul_committed": round(a["games_foul"] / g, 3),
            "hr_yc": round(a["games_card"] / g, 3),
            "hr_tackle": round(a["games_tackle"] / g, 3),
            "source": "rebuild_v13_multi_source",
            "updated_at": now()
        })

    saved = upsert("player_avg_stats", out, "player_name")
    log(f"  ✅ player_avg_stats: {saved} Spieler aktualisiert")
    return saved

# ============================================================
# MAIN
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="NETRATTLER Player Stats Scraper V13")
    ap.add_argument("--date", default="")
    ap.add_argument("--source", default="all")
    ap.add_argument("--rebuild-only", action="store_true")
    ap.add_argument("--days-back", type=int, default=365)
    ap.add_argument("--statsbomb-matches", type=int, default=int(os.getenv("STATSBOMB_MAX_MATCHES", "120")))
    ap.add_argument("--sofascore-events", type=int, default=int(os.getenv("SOFASCORE_MAX_EVENTS", "30")))
    args = ap.parse_args()

    target_date = args.date or yesterday()
    log(f"\n{'='*60}")
    log(f"NETRATTLER Player Stats Scraper V13")
    log(f"Datum: {target_date} | Quelle: {args.source}")
    log(f"{'='*60}\n")

    if args.rebuild_only:
        rebuild(args.days_back)
        return

    all_player_rows = []

    src = args.source.lower()

    # ── Quellen die immer laufen (kein Block-Risiko) ──
    if src in ("all", "statsbomb"):
        all_player_rows += statsbomb_rows(args.statsbomb_matches)

    if src in ("all", "fotmob"):
        all_player_rows += fotmob_rows_for_date(target_date)

    if src in ("all", "espn"):
        all_player_rows += espn_rows_for_date(target_date)

    if src in ("all", "fpl"):
        all_player_rows += fpl_rows()
        all_player_rows += fpl_core_rows()

    if src in ("all", "openligadb"):
        all_player_rows += openligadb_rows("bl1", 2024)
        all_player_rows += openligadb_rows("bl2", 2024)

    if src in ("all", "openfootball"):
        all_player_rows += openfootball_rows()

    if src in ("all", "wm2026"):
        all_player_rows += wm2026_rows()

    if src in ("all", "thestatsapi"):
        all_player_rows += thestatsapi_rows_for_date(target_date)

    if src in ("all", "fdorg"):
        all_player_rows += football_data_org_rows()

    if src in ("all", "sportmonks"):
        all_player_rows += sportmonks_rows_for_date(target_date)

    if src in ("all", "sofascore"):
        all_player_rows += sofascore_rows_for_date(target_date, args.sofascore_events)

    # ── Separat gespeicherte Quellen ──
    if src in ("all", "clubelo"):
        clubelo_rows()

    if src in ("all", "martj42"):
        martj42_rows()

    if src in ("all", "xgabora"):
        xgabora_rows()

    if src in ("all", "fdcouk"):
        fdcouk_rows()

    if src in ("all", "referee", "wm2026"):
        jfjelstul_referee_rows()

    if src in ("all", "injuries", "physioroom"):
        physioroom_rows()

    if src in ("all", "weather", "meteo"):
        openmeteo_rows()

    if src in ("all", "fbref"):
        all_player_rows += fbref_rows()

    if src in ("all", "understat"):
        all_player_rows += understat_rows(2024)

    if src in ("all", "pinnacle"):
        pinnacle_props_rows()

    # ── Dedup + Speichern ──
    if all_player_rows:
        dedup = {}
        for r in all_player_rows:
            key = (r.get("source", ""), r.get("match_id", ""), r.get("player_name", ""), r.get("team_name", ""))
            dedup[key] = r
        final = list(dedup.values())
        log(f"\n📦 Total Player Rows (nach Dedup): {len(final)}")
        saved = upsert("player_match_stats", final, "source,match_id,player_name")
        log(f"✅ player_match_stats gespeichert: {saved}")
    else:
        log("⚠️ Keine Player Rows gesammelt")

    # ── Rebuild Durchschnitte + Hit Rates ──
    rebuild(args.days_back)
    log("\n✅ V13 Scraper fertig!")

if __name__ == "__main__":
    main()
