#!/usr/bin/env python3
"""
NETRATTLER V14 — Supabase Data Importer

Imports football data into the correct Supabase tables:

1) ClubElo API/CSV                  -> team_elo_history
2) football-data.co.uk CSV          -> football_historical_matches, odds_history, league_*_features
3) FPL API                          -> player_profiles
4) openfootball JSON/TXT-compatible -> football_historical_matches
5) EXTRA_CSV_URLS JSON env          -> generic raw CSV source health + optional simple match import

Designed to run in GitHub Actions.
"""

import os
import re
import io
import csv
import json
import time
import math
import hashlib
from datetime import datetime, timezone, date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import pandas as pd


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
CHUNK_SIZE = int(os.environ.get("IMPORT_CHUNK_SIZE", "500"))
TIMEOUT = int(os.environ.get("IMPORT_TIMEOUT", "60"))
MAX_ROWS_PER_SOURCE = int(os.environ.get("MAX_ROWS_PER_SOURCE", "0"))  # 0 = no limit
IMPORT_SOURCES = [x.strip().lower() for x in os.environ.get("IMPORT_SOURCES", "all").split(",") if x.strip()]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

FD_LEAGUES = {
    "E0": ("England", "Premier League"),
    "E1": ("England", "Championship"),
    "E2": ("England", "League One"),
    "E3": ("England", "League Two"),
    "SC0": ("Scotland", "Premiership"),
    "D1": ("Germany", "Bundesliga"),
    "D2": ("Germany", "2. Bundesliga"),
    "I1": ("Italy", "Serie A"),
    "I2": ("Italy", "Serie B"),
    "SP1": ("Spain", "La Liga"),
    "SP2": ("Spain", "Segunda Division"),
    "F1": ("France", "Ligue 1"),
    "F2": ("France", "Ligue 2"),
    "N1": ("Netherlands", "Eredivisie"),
    "B1": ("Belgium", "Jupiler Pro League"),
    "P1": ("Portugal", "Primeira Liga"),
    "T1": ("Turkey", "Super Lig"),
    "G1": ("Greece", "Super League"),
}

DEFAULT_FD_SEASONS = os.environ.get("FD_SEASONS", "2526,2425,2324").split(",")
DEFAULT_FD_CODES = os.environ.get("FD_CODES", ",".join(FD_LEAGUES.keys())).split(",")

DEFAULT_OPENFOOTBALL_URLS = [
    # Keep configurable. Many openfootball repos differ by folder names; failures are logged, not fatal.
    "https://raw.githubusercontent.com/openfootball/england/master/2024-25/1-premierleague.json",
    "https://raw.githubusercontent.com/openfootball/deutschland/master/2024-25/1-bundesliga.json",
    "https://raw.githubusercontent.com/openfootball/italy/master/2024-25/1-seriea.json",
    "https://raw.githubusercontent.com/openfootball/espana/master/2024-25/1-liga.json",
    "https://raw.githubusercontent.com/openfootball/france/master/2024-25/1-ligue1.json",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def enabled(name: str) -> bool:
    return "all" in IMPORT_SOURCES or name.lower() in IMPORT_SOURCES


def clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def to_float(v: Any) -> Optional[float]:
    v = clean(v)
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def to_int(v: Any) -> Optional[int]:
    f = to_float(v)
    return None if f is None else int(f)


def to_date(v: Any) -> Optional[str]:
    v = clean(v)
    if v is None:
        return None
    try:
        dt = pd.to_datetime(v, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            return None
        return dt.date().isoformat()
    except Exception:
        return None


def slug(s: Any) -> str:
    s = str(clean(s) or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60] or "na"


def season_from_fd_code(code: str) -> str:
    code = str(code)
    if len(code) == 4 and code.isdigit():
        return f"20{code[:2]}/20{code[2:]}"
    return code


def match_id(source: str, league: Any, match_date: Any, home: Any, away: Any) -> str:
    base = f"{source}|{league}|{match_date}|{home}|{away}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{slug(source)}_{slug(league)}_{match_date or 'nodate'}_{slug(home)}_{slug(away)}_{h}"[:180]


def rest_upsert(table: str, rows: List[Dict[str, Any]], conflict: str) -> int:
    if not rows:
        return 0
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY missing")
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}"
    ok = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        r = requests.post(url, headers=HEADERS, data=json.dumps(chunk, default=str), timeout=TIMEOUT)
        if r.status_code not in (200, 201, 204):
            log(f"⚠️ UPSERT {table} {r.status_code}: {r.text[:700]}")
        else:
            ok += len(chunk)
        time.sleep(0.05)
    return ok


def health(source: str, status: str, rows: int, message: str) -> None:
    row = {
        "source": source,
        "status": status,
        "rows": rows,
        "message": message[:800],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        rest_upsert("football_import_health", [row], "source")
    except Exception as e:
        log(f"⚠️ health football_import_health failed: {e}")
    try:
        rest_upsert("source_health", [row], "source")
    except Exception:
        pass


def import_clubelo() -> int:
    src = "clubelo"
    today = os.environ.get("CLUBELO_DATE", date.today().isoformat())
    urls = [
        os.environ.get("CLUBELO_URL", ""),
        f"https://api.clubelo.com/{today}",
        f"http://api.clubelo.com/{today}",
    ]
    urls = [u for u in urls if u]
    for url in urls:
        try:
            log(f"📦 ClubElo: {url}")
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code != 200 or not r.text.strip():
                log(f"  ⚠️ ClubElo HTTP {r.status_code}")
                continue
            df = pd.read_csv(io.StringIO(r.text))
            rows = []
            for raw in df.to_dict(orient="records"):
                team = clean(raw.get("Club") or raw.get("Team"))
                if not team:
                    continue
                rows.append({
                    "source": src,
                    "rating_date": today,
                    "team_name": team,
                    "country": clean(raw.get("Country")),
                    "rank": to_int(raw.get("Rank")),
                    "level": clean(raw.get("Level")),
                    "elo": to_float(raw.get("Elo")),
                    "from_date": to_date(raw.get("From")),
                    "to_date": to_date(raw.get("To")),
                    "raw": {k: clean(v) for k, v in raw.items()},
                })
                if MAX_ROWS_PER_SOURCE and len(rows) >= MAX_ROWS_PER_SOURCE:
                    break
            ok = rest_upsert("team_elo_history", rows, "source,rating_date,team_name")
            health(src, "ok", ok, f"ClubElo imported from {url}")
            log(f"  ✅ ClubElo: {ok} Teams")
            return ok
        except Exception as e:
            log(f"  ⚠️ ClubElo error: {e}")
    health(src, "error", 0, "all ClubElo URLs failed")
    return 0


def fd_row_to_match(raw: Dict[str, Any], season_code: str, code: str, country: str, league: str) -> Dict[str, Any]:
    d = to_date(raw.get("Date"))
    home = clean(raw.get("HomeTeam"))
    away = clean(raw.get("AwayTeam"))
    hg = to_int(raw.get("FTHG"))
    ag = to_int(raw.get("FTAG"))
    total = None if hg is None or ag is None else hg + ag
    hy = to_float(raw.get("HY"))
    ay = to_float(raw.get("AY"))
    hr = to_float(raw.get("HR"))
    ar = to_float(raw.get("AR"))
    hc = to_float(raw.get("HC"))
    ac = to_float(raw.get("AC"))
    hf = to_float(raw.get("HF"))
    af = to_float(raw.get("AF"))
    hs = to_float(raw.get("HS"))
    a_s = to_float(raw.get("AS"))
    hst = to_float(raw.get("HST"))
    ast = to_float(raw.get("AST"))
    return {
        "source": "football_data_co_uk",
        "match_id": match_id("fdcouk", f"{season_code}_{code}", d, home, away),
        "match_date": d,
        "season": season_from_fd_code(season_code),
        "country": country,
        "league": league,
        "division": code,
        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "result": clean(raw.get("FTR")),
        "ht_home_goals": to_int(raw.get("HTHG")),
        "ht_away_goals": to_int(raw.get("HTAG")),
        "ht_result": clean(raw.get("HTR")),
        "total_goals": total,
        "btts": None if hg is None or ag is None else bool(hg > 0 and ag > 0),
        "over_25_hit": None if total is None else bool(total > 2.5),
        "home_shots": hs,
        "away_shots": a_s,
        "home_sot": hst,
        "away_sot": ast,
        "home_fouls": hf,
        "away_fouls": af,
        "home_corners": hc,
        "away_corners": ac,
        "home_yellow": hy,
        "away_yellow": ay,
        "home_red": hr,
        "away_red": ar,
        "referee": clean(raw.get("Referee")),
        "odd_home": to_float(raw.get("B365H") or raw.get("AvgH") or raw.get("MaxH")),
        "odd_draw": to_float(raw.get("B365D") or raw.get("AvgD") or raw.get("MaxD")),
        "odd_away": to_float(raw.get("B365A") or raw.get("AvgA") or raw.get("MaxA")),
        "over25_odds": to_float(raw.get("B365>2.5") or raw.get("Avg>2.5") or raw.get("Max>2.5")),
        "under25_odds": to_float(raw.get("B365<2.5") or raw.get("Avg<2.5") or raw.get("Max<2.5")),
        "raw": {k: clean(v) for k, v in raw.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def odds_rows_from_match(m: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    cap_date = date.today().isoformat()
    mid = m["match_id"]
    base = {
        "source": "football_data_co_uk",
        "match_id": mid,
        "home_team": m.get("home_team"),
        "away_team": m.get("away_team"),
        "match_date": m.get("match_date"),
        "captured_date": cap_date,
    }
    for selection, odds in [("home", m.get("odd_home")), ("draw", m.get("odd_draw")), ("away", m.get("odd_away"))]:
        if odds:
            rows.append({**base, "market": "1x2", "bookmaker": "football-data.co.uk", "selection": selection, "odds": odds, "raw": {}})
    for selection, odds in [("over_2_5", m.get("over25_odds")), ("under_2_5", m.get("under25_odds"))]:
        if odds:
            rows.append({**base, "market": "totals_2_5", "bookmaker": "football-data.co.uk", "selection": selection, "odds": odds, "raw": {}})
    return rows


def build_league_features(matches: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not matches:
        return [], [], []
    df = pd.DataFrame(matches)
    if df.empty:
        return [], [], []
    for col in [
        "total_goals", "home_goals", "away_goals", "btts", "over_25_hit",
        "home_yellow", "away_yellow", "home_red", "away_red",
        "home_corners", "away_corners",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    rows_goal, rows_cards, rows_corners = [], [], []
    now = datetime.now(timezone.utc).isoformat()
    for (league, season), g in df.groupby(["league", "season"], dropna=True):
        n = int(len(g))
        if n == 0:
            continue
        result = g["result"].fillna("")
        rows_goal.append({
            "source": "football_data_co_uk",
            "league": str(league),
            "season": str(season),
            "matches": n,
            "goals_pg": float(g["total_goals"].mean()) if g["total_goals"].notna().any() else None,
            "home_goals_pg": float(g["home_goals"].mean()) if g["home_goals"].notna().any() else None,
            "away_goals_pg": float(g["away_goals"].mean()) if g["away_goals"].notna().any() else None,
            "btts_rate": float(g["btts"].mean()) if g["btts"].notna().any() else None,
            "over25_rate": float(g["over_25_hit"].mean()) if g["over_25_hit"].notna().any() else None,
            "home_win_rate": float(result.eq("H").mean()),
            "draw_rate": float(result.eq("D").mean()),
            "away_win_rate": float(result.eq("A").mean()),
            "updated_at": now,
        })
        total_y = g["home_yellow"].fillna(0) + g["away_yellow"].fillna(0)
        total_r = g["home_red"].fillna(0) + g["away_red"].fillna(0)
        if total_y.sum() or total_r.sum():
            rows_cards.append({
                "source": "football_data_co_uk",
                "league": str(league),
                "season": str(season),
                "matches": n,
                "yellow_cards_pg": float(total_y.mean()),
                "red_cards_pg": float(total_r.mean()),
                "total_cards_pg": float((total_y + total_r).mean()),
                "home_yellow_pg": float(g["home_yellow"].mean()) if g["home_yellow"].notna().any() else None,
                "away_yellow_pg": float(g["away_yellow"].mean()) if g["away_yellow"].notna().any() else None,
                "updated_at": now,
            })
        total_c = g["home_corners"].fillna(0) + g["away_corners"].fillna(0)
        if total_c.sum():
            rows_corners.append({
                "source": "football_data_co_uk",
                "league": str(league),
                "season": str(season),
                "matches": n,
                "corners_pg": float(total_c.mean()),
                "home_corners_pg": float(g["home_corners"].mean()) if g["home_corners"].notna().any() else None,
                "away_corners_pg": float(g["away_corners"].mean()) if g["away_corners"].notna().any() else None,
                "updated_at": now,
            })
    return rows_goal, rows_cards, rows_corners


def import_football_data_co_uk() -> int:
    total = 0
    all_matches = []
    for season in [s.strip() for s in DEFAULT_FD_SEASONS if s.strip()]:
        for code in [c.strip() for c in DEFAULT_FD_CODES if c.strip()]:
            country, league = FD_LEAGUES.get(code, ("Unknown", code))
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
            try:
                log(f"📦 FD.co.uk {season} {code}...")
                r = requests.get(url, timeout=TIMEOUT)
                if r.status_code != 200 or not r.text.strip():
                    log(f"  ⚠️ HTTP {r.status_code}")
                    continue
                df = pd.read_csv(io.StringIO(r.text))
                if df.empty:
                    continue
                rows = []
                odds = []
                for raw in df.to_dict(orient="records"):
                    if not clean(raw.get("HomeTeam")) or not clean(raw.get("AwayTeam")):
                        continue
                    m = fd_row_to_match(raw, season, code, country, league)
                    rows.append(m)
                    odds.extend(odds_rows_from_match(m))
                    if MAX_ROWS_PER_SOURCE and len(rows) >= MAX_ROWS_PER_SOURCE:
                        break
                ok = rest_upsert("football_historical_matches", rows, "source,match_id")
                rest_upsert("odds_history", odds, "source,match_id,market,bookmaker,captured_date,selection")
                total += ok
                all_matches.extend(rows)
                log(f"  ✅ {league}: {ok} Matches")
            except Exception as e:
                log(f"  ⚠️ FD.co.uk {season} {code}: {e}")
    goals, cards, corners = build_league_features(all_matches)
    g = rest_upsert("league_goal_features", goals, "source,league,season")
    c = rest_upsert("league_cards_features", cards, "source,league,season")
    co = rest_upsert("league_corners_features", corners, "source,league,season")
    health("football_data_co_uk", "ok" if total else "warn", total, f"matches={total}, goal_features={g}, card_features={c}, corner_features={co}")
    log(f"✅ FD.co.uk total: {total} Matches | features g/c/corners {g}/{c}/{co}")
    return total


def import_fpl_profiles() -> int:
    src = "fpl_api"
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    try:
        log("📦 FPL player profiles...")
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            health(src, "warn", 0, f"HTTP {r.status_code}")
            return 0
        data = r.json()
        teams = {t.get("id"): t.get("name") for t in data.get("teams", [])}
        pos = {e.get("id"): e.get("singular_name_short") for e in data.get("element_types", [])}
        rows = []
        for p in data.get("elements", []):
            pid = str(p.get("id"))
            rows.append({
                "source": src,
                "player_id": pid,
                "player_name": clean(p.get("web_name") or f"{p.get('first_name','')} {p.get('second_name','')}"),
                "first_name": clean(p.get("first_name")),
                "last_name": clean(p.get("second_name")),
                "team_name": clean(teams.get(p.get("team"))),
                "position": clean(pos.get(p.get("element_type"))),
                "nationality": None,
                "birth_date": None,
                "age": None,
                "height_cm": None,
                "weight_kg": None,
                "preferred_foot": None,
                "shirt_number": None,
                "raw": p,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        ok = rest_upsert("player_profiles", rows, "source,player_id")
        health(src, "ok", ok, "FPL player profiles imported")
        log(f"  ✅ FPL profiles: {ok}")
        return ok
    except Exception as e:
        health(src, "error", 0, str(e))
        log(f"  ⚠️ FPL error: {e}")
        return 0


def openfootball_matches_from_json(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, dict):
        matches = obj.get("matches") or obj.get("rounds") or []
        if obj.get("rounds"):
            matches = []
            for rnd in obj.get("rounds", []):
                matches.extend(rnd.get("matches", []) or [])
        league = clean(obj.get("name") or obj.get("league") or obj.get("title") or "openfootball")
    elif isinstance(obj, list):
        matches = obj
        league = "openfootball"
    else:
        return []
    out = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        date_str = to_date(m.get("date"))
        t1 = m.get("team1") or m.get("home_team") or m.get("home")
        t2 = m.get("team2") or m.get("away_team") or m.get("away")
        if isinstance(t1, dict):
            t1 = t1.get("name")
        if isinstance(t2, dict):
            t2 = t2.get("name")
        score = m.get("score") or {}
        ft = score.get("ft") if isinstance(score, dict) else None
        hg = ag = None
        if isinstance(ft, list) and len(ft) >= 2:
            hg, ag = to_int(ft[0]), to_int(ft[1])
        elif isinstance(score, dict):
            hg, ag = to_int(score.get("home")), to_int(score.get("away"))
        if not clean(t1) or not clean(t2):
            continue
        total = None if hg is None or ag is None else hg + ag
        out.append({
            "source": "openfootball",
            "match_id": match_id("openfootball", league, date_str, t1, t2),
            "match_date": date_str,
            "season": None,
            "country": None,
            "league": league,
            "division": league,
            "home_team": clean(t1),
            "away_team": clean(t2),
            "home_goals": hg,
            "away_goals": ag,
            "result": "H" if hg is not None and ag is not None and hg > ag else ("A" if hg is not None and ag is not None and ag > hg else ("D" if hg is not None and ag is not None else None)),
            "total_goals": total,
            "btts": None if hg is None or ag is None else bool(hg > 0 and ag > 0),
            "over_25_hit": None if total is None else bool(total > 2.5),
            "raw": m,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def import_openfootball() -> int:
    urls_env = os.environ.get("OPENFOOTBALL_URLS", "")
    urls = [u.strip() for u in urls_env.split(",") if u.strip()] if urls_env else DEFAULT_OPENFOOTBALL_URLS
    total = 0
    for url in urls:
        try:
            log(f"📦 openfootball: {url}")
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                log(f"  ⚠️ HTTP {r.status_code}")
                continue
            data = r.json()
            rows = openfootball_matches_from_json(data)
            if MAX_ROWS_PER_SOURCE:
                rows = rows[:MAX_ROWS_PER_SOURCE]
            ok = rest_upsert("football_historical_matches", rows, "source,match_id")
            total += ok
            log(f"  ✅ openfootball rows: {ok}")
        except Exception as e:
            log(f"  ⚠️ openfootball error: {e}")
    health("openfootball", "ok" if total else "warn", total, "openfootball json import")
    return total


def import_extra_csv_urls() -> int:
    """
    EXTRA_CSV_URLS format:
    [
      {"source":"my_csv","url":"https://...csv","type":"football_matches"}
    ]
    Currently supports type=football_matches with columns similar to HomeTeam/AwayTeam/FTHG/FTAG.
    """
    raw = os.environ.get("EXTRA_CSV_URLS", "").strip()
    if not raw:
        health("extra_csv", "skipped", 0, "EXTRA_CSV_URLS empty")
        return 0
    try:
        cfgs = json.loads(raw)
    except Exception as e:
        health("extra_csv", "error", 0, f"invalid JSON: {e}")
        return 0
    total = 0
    for cfg in cfgs if isinstance(cfgs, list) else []:
        source = cfg.get("source") or "extra_csv"
        url = cfg.get("url")
        typ = cfg.get("type") or "football_matches"
        if not url:
            continue
        try:
            log(f"📦 Extra CSV {source}: {url}")
            df = pd.read_csv(url)
            rows = []
            if typ == "football_matches":
                for raw_row in df.to_dict(orient="records"):
                    d = to_date(raw_row.get("Date") or raw_row.get("match_date"))
                    home = clean(raw_row.get("HomeTeam") or raw_row.get("home_team") or raw_row.get("Home"))
                    away = clean(raw_row.get("AwayTeam") or raw_row.get("away_team") or raw_row.get("Away"))
                    if not home or not away:
                        continue
                    hg = to_int(raw_row.get("FTHG") or raw_row.get("home_goals"))
                    ag = to_int(raw_row.get("FTAG") or raw_row.get("away_goals"))
                    total_goals = None if hg is None or ag is None else hg + ag
                    rows.append({
                        "source": source,
                        "match_id": match_id(source, cfg.get("league") or "extra", d, home, away),
                        "match_date": d,
                        "league": clean(cfg.get("league") or raw_row.get("League") or raw_row.get("league")),
                        "division": clean(raw_row.get("Div") or raw_row.get("division")),
                        "home_team": home,
                        "away_team": away,
                        "home_goals": hg,
                        "away_goals": ag,
                        "total_goals": total_goals,
                        "btts": None if hg is None or ag is None else bool(hg > 0 and ag > 0),
                        "over_25_hit": None if total_goals is None else bool(total_goals > 2.5),
                        "raw": {k: clean(v) for k, v in raw_row.items()},
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
                    if MAX_ROWS_PER_SOURCE and len(rows) >= MAX_ROWS_PER_SOURCE:
                        break
                ok = rest_upsert("football_historical_matches", rows, "source,match_id")
                total += ok
                health(source, "ok", ok, f"extra csv football_matches imported from {url}")
        except Exception as e:
            health(source, "error", 0, str(e))
            log(f"  ⚠️ Extra CSV error {source}: {e}")
    return total


def main() -> None:
    log("=" * 60)
    log("NETRATTLER V14 — Supabase Data Importer")
    log("=" * 60)
    log(f"Sources: {IMPORT_SOURCES}")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY fehlt")

    total = 0
    if enabled("clubelo"):
        total += import_clubelo()
    if enabled("fdcouk") or enabled("football-data"):
        total += import_football_data_co_uk()
    if enabled("fpl"):
        total += import_fpl_profiles()
    if enabled("openfootball"):
        total += import_openfootball()
    if enabled("extra_csv"):
        total += import_extra_csv_urls()

    log("=" * 60)
    log(f"✅ V14 Import fertig. Gesamt importierte/upsertete Rows ca.: {total}")
    log("=" * 60)


if __name__ == "__main__":
    main()
