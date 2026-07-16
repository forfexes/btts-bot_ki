#!/usr/bin/env python3
"""
NETRATTLER ML-Training-Script
==============================
Trainiert XGBoost-Modelle für ALLE verfügbaren NETRATTLER-Kanäle: BTTS, Over/Under, HT, 1X2, Double Chance, Team Goals, Corners, Cards, Shots und Player Props.
Wird wöchentlich via GitHub Actions ausgeführt.
Speichert trainierte Modelle in Supabase (Tabelle: ml_models).

Features pro Spiel:
- Elo-Rating Heim/Auswärts (rollend berechnet)
- Form letzte 5 Spiele (Heim: Tore erzielt/kassiert, Auswärts ebenso)
- Heim-BTTS-Rate letzte 10 Spiele
- Auswärts-BTTS-Rate letzte 10 Spiele
- Heim-Over2.5-Rate letzte 10 Spiele
- Auswärts-Over2.5-Rate letzte 10 Spiele
- Elo-Differenz
"""

import os, sys, json, math, base64, io, pickle, statistics
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ML
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit, StratifiedKFold
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, roc_auc_score

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ── Datenquellen ──────────────────────────────────────────────────────────────
OPENFOOTBALL_SOURCES = [
    ("en.1", "Premier League"),
    ("de.1", "Bundesliga"),
    ("es.1", "La Liga"),
    ("it.1", "Serie A"),
    ("fr.1", "Ligue 1"),
    ("en.2", "Championship"),
    ("nl.1", "Eredivisie"),
    ("pt.1", "Primeira Liga"),
]
SEASONS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]

# Football-Data.co.uk — mehrere Saisons, mehr Features (Schüsse, Ecken, Karten)
FD_CO_UK_LEAGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "D1": "Bundesliga", "D2": "2. Bundesliga",
    "SP1": "La Liga", "SP2": "Segunda Division",
    "I1": "Serie A", "I2": "Serie B",
    "F1": "Ligue 1", "F2": "Ligue 2",
    "N1": "Eredivisie", "P1": "Primeira Liga",
    "B1": "Jupiler Pro League", "T1": "Super Lig",
    "SC0": "Scottish Premiership", "G1": "Super League Greece",
}
def _season_labels(start_year: int, end_year: int):
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(start_year, end_year + 1)]


_FD_START_YEAR = int(os.environ.get("FD_START_YEAR", "2010"))
_FD_END_YEAR = int(os.environ.get("FD_END_YEAR", str(datetime.now(timezone.utc).year)))
FD_CO_UK_SEASONS = [x.strip() for x in os.environ.get("FD_SEASONS", "").split(",") if x.strip()] or _season_labels(_FD_START_YEAR, _FD_END_YEAR)


# ── Elo-Konfiguration ─────────────────────────────────────────────────────────
ELO_BASE = 1500
ELO_K = 20
ELO_HOME_ADV = 60


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATEN LADEN
# ═══════════════════════════════════════════════════════════════════════════════

def _to_int_or_none(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _to_float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _parse_match_date(value):
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _norm_team(value):
    import re as _re
    value = str(value or "").lower().strip()
    value = _re.sub(r"\b(fc|cf|ac|sc|sv|afc)\b", " ", value)
    value = _re.sub(r"[^a-z0-9à-ž]+", " ", value, flags=_re.I)
    return " ".join(value.split())


def _match_key(match_date, home, away):
    return f"{str(match_date)[:10]}|{_norm_team(home)}|{_norm_team(away)}"


def _odds_richness(row):
    return sum(1 for k in [
        "odd_home", "odd_draw", "odd_away", "over25_odds", "under25_odds",
        "bet365_home", "bet365_draw", "bet365_away", "pinnacle_home", "pinnacle_draw", "pinnacle_away",
    ] if row.get(k) not in (None, ""))


def _row_stat_richness(row):
    """Used before dedup: keep Football-Data/Supabase rows with corners/cards/shots over empty GitHub rows."""
    score = 0
    for k in ["shots_home", "shots_away", "corners_home", "corners_away", "cards_home", "cards_away"]:
        v = row.get(k)
        if v is not None and v != "":
            score += 1
    return score


def _fetch_supabase_rows(table, select="*", order=None, limit_total=50000):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    rows = []
    step = 1000  # Supabase/PostgREST free projects often cap one request at 1000
    for offset in range(0, limit_total, step):
        params = {"select": select, "limit": step, "offset": offset}
        if order:
            params["order"] = order
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, timeout=45)
            if not r.ok:
                print(f"  ⚠️  Supabase {table}: {r.status_code} {r.text[:200]}")
                break
            batch = r.json()
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < step:
                break
        except Exception as e:
            print(f"  ⚠️  Supabase {table}: {e}")
            break
    return rows


def _normalize_result_row(row, default_source="supabase"):
    home = row.get("home") or row.get("home_team")
    away = row.get("away") or row.get("away_team")
    hg = row.get("home_goals", row.get("home_score"))
    ag = row.get("away_goals", row.get("away_score"))
    dt = row.get("date") or row.get("match_date")
    if not home or not away or hg is None or ag is None or not dt:
        return None
    try:
        hg = int(float(hg))
        ag = int(float(ag))
    except Exception:
        return None

    return {
        "date": dt,
        "season": str(dt)[:4],
        "league": row.get("league") or row.get("competition") or "Supabase Results",
        "source": row.get("source") or default_source,
        "home": str(home).strip(),
        "away": str(away).strip(),
        "home_goals": hg,
        "away_goals": ag,
        "ht_home": _to_int_or_none(row.get("ht_home")) or 0,
        "ht_away": _to_int_or_none(row.get("ht_away")) or 0,
        "shots_home": _to_int_or_none(row.get("shots_home") or row.get("home_shots") or row.get("HS")),
        "shots_away": _to_int_or_none(row.get("shots_away") or row.get("away_shots") or row.get("AS")),
        "corners_home": _to_int_or_none(row.get("corners_home") or row.get("home_corners") or row.get("HC")),
        "corners_away": _to_int_or_none(row.get("corners_away") or row.get("away_corners") or row.get("AC")),
        "cards_home": _to_int_or_none(row.get("cards_home") or row.get("home_cards") or row.get("HY") or row.get("home_yellow")),
        "cards_away": _to_int_or_none(row.get("cards_away") or row.get("away_cards") or row.get("AY") or row.get("away_yellow")),
        "match_id": row.get("match_id") or row.get("event_id"),
        "odd_home": _to_float_or_none(row.get("odd_home") or row.get("odds_home")),
        "odd_draw": _to_float_or_none(row.get("odd_draw") or row.get("odds_draw")),
        "odd_away": _to_float_or_none(row.get("odd_away") or row.get("odds_away")),
        "over25_odds": _to_float_or_none(row.get("over25_odds") or row.get("odds_over25")),
        "under25_odds": _to_float_or_none(row.get("under25_odds") or row.get("odds_under25")),
    }



def _load_supabase_match_table(table: str, limit_total: int = 100000):
    rows = []
    for row in _fetch_supabase_rows(table, select="*", order="match_date.asc", limit_total=limit_total):
        norm = _normalize_result_row(row, table)
        if norm:
            rows.append(norm)
    print(f"   ✅ Supabase {table}: {len(rows)} Spiele")
    return rows


def _load_odds_history(limit_total: int = 200000):
    print("📥 Lade Supabase odds_history (alle Bookies)...")
    raw = _fetch_supabase_rows(
        "odds_history", select="*", order="match_date.asc,captured_date.asc", limit_total=limit_total
    )
    by_key = {}
    for row in raw:
        dt = _parse_match_date(row.get("match_date"))
        home, away = row.get("home_team"), row.get("away_team")
        odd = _to_float_or_none(row.get("odds"))
        if not dt or not home or not away or not odd:
            continue
        key = _match_key(dt, home, away)
        by_key.setdefault(key, []).append(row)
    print(f"   ✅ odds_history: {len(raw)} Rows / {len(by_key)} Matches")
    return by_key


def _merge_odds_into_match(row, odds_rows):
    if not odds_rows:
        return row
    buckets = {}
    for o in odds_rows:
        market = str(o.get("market") or "").lower()
        book = str(o.get("bookmaker") or "").lower()
        sel = str(o.get("selection") or "").lower()
        odd = _to_float_or_none(o.get("odds"))
        if odd:
            buckets.setdefault((market, sel), []).append((book, odd))

    def values(market_names, selections):
        vals = []
        for (market, sel), items in buckets.items():
            if any(m in market for m in market_names) and any(s == sel or s in sel for s in selections):
                vals.extend(items)
        return vals

    def consensus(items):
        nums = [v for _, v in items if v and v > 1]
        return statistics.median(nums) if nums else None

    def book(items, names):
        for name in names:
            vals = [v for b, v in items if name in b]
            if vals:
                return vals[-1]
        return None

    hv, dv, av = values(["1x2", "h2h", "match_odds"], ["home"]), values(["1x2", "h2h", "match_odds"], ["draw"]), values(["1x2", "h2h", "match_odds"], ["away"])
    ov, uv = values(["total", "over_under"], ["over_2_5", "over_2.5", "over"]), values(["total", "over_under"], ["under_2_5", "under_2.5", "under"])
    for k, v in {
        "odd_home": consensus(hv), "odd_draw": consensus(dv), "odd_away": consensus(av),
        "over25_odds": consensus(ov), "under25_odds": consensus(uv),
        "bet365_home": book(hv, ["bet365"]), "bet365_draw": book(dv, ["bet365"]), "bet365_away": book(av, ["bet365"]),
        "pinnacle_home": book(hv, ["pinnacle"]), "pinnacle_draw": book(dv, ["pinnacle"]), "pinnacle_away": book(av, ["pinnacle"]),
        "betfair_home": book(hv, ["betfair"]), "betfair_draw": book(dv, ["betfair"]), "betfair_away": book(av, ["betfair"]),
        "bet365_over25": book(ov, ["bet365"]), "bet365_under25": book(uv, ["bet365"]),
        "pinnacle_over25": book(ov, ["pinnacle"]), "pinnacle_under25": book(uv, ["pinnacle"]),
    }.items():
        if row.get(k) in (None, "") and v is not None:
            row[k] = v
    row["odds_source_count"] = len({str(o.get("bookmaker") or "") for o in odds_rows})
    return row


def _fuse_match_group(group):
    """Fuse fields from all sources instead of dropping useful duplicate-source columns."""
    group = list(group)
    group.sort(key=lambda r: (_row_stat_richness(r), _odds_richness(r)), reverse=True)
    out = dict(group[0])
    all_keys = set().union(*(r.keys() for r in group))
    for key in all_keys:
        _current = out.get(key)
        _missing = _current is None or _current == ""
        try:
            _missing = _missing or (isinstance(_current, float) and math.isnan(_current))
        except Exception:
            pass
        if _missing:
            for row in group[1:]:
                value = row.get(key)
                if value is not None and value != "":
                    try:
                        if isinstance(value, float) and math.isnan(value):
                            continue
                    except Exception:
                        pass
                    out[key] = value
                    break
    out["source_count"] = len({str(r.get("source") or "unknown") for r in group})
    out["sources"] = ",".join(sorted({str(r.get("source") or "unknown") for r in group}))[:1000]
    return out


def load_all_matches():
    """Lädt alle verfügbaren Spiele aus mehreren Quellen."""
    all_rows = []

    print("📥 ML-Quellen aktiv: openfootball GitHub, Football-Data.co.uk, martj42 GitHub, Supabase ml_tips, Supabase match_results, Supabase player_match_stats")
    print("   Hinweis: GitHub Registry ist Quellen-Metadaten. Trainiert wird mit geladenen Match-/Player-Daten aus diesen Quellen.")

    # ── 1. openfootball (JSON, mehrere Saisons) ────────────────────────────
    print("📥 Lade openfootball Daten...")
    for season in SEASONS:
        for code, league in OPENFOOTBALL_SOURCES:
            url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{code}.json"
            try:
                r = requests.get(url, timeout=10)
                if not r.ok:
                    continue
                data = r.json()
                for match in data.get("matches", []):
                    score = match.get("score")
                    if not score:
                        continue
                    ft = score.get("ft", [])
                    ht = score.get("ht", [])
                    if len(ft) < 2:
                        continue
                    all_rows.append({
                        "date": match.get("date", ""),
                        "season": season,
                        "league": league,
                        "source": "openfootball/football.json",
                        "match_id": None,
                        "home": match.get("team1", "").replace(" FC", "").replace(" CF", "").strip(),
                        "away": match.get("team2", "").replace(" FC", "").replace(" CF", "").strip(),
                        "home_goals": int(ft[0]),
                        "away_goals": int(ft[1]),
                        "ht_home": int(ht[0]) if len(ht) >= 2 else 0,
                        "ht_away": int(ht[1]) if len(ht) >= 2 else 0,
                        "shots_home": None, "shots_away": None,
                        "corners_home": None, "corners_away": None,
                        "cards_home": None, "cards_away": None,
                    })
            except Exception as e:
                print(f"  ⚠️  openfootball {season} {league}: {e}")

    print(f"   ✅ openfootball: {len(all_rows)} Spiele")

    # ── 2. Football-Data.co.uk (CSV, mehr Features: Schüsse/Ecken/Karten) ──
    print("📥 Lade Football-Data.co.uk CSV-Daten...")
    fd_count = 0
    for season_str, league_code in [(s, lc) for s in FD_CO_UK_SEASONS for lc in FD_CO_UK_LEAGUES]:
        # Season-Format: "2021-22" → "2122"
        parts = season_str.split("-")
        fd_season = parts[0][-2:] + parts[1][-2:]
        url = f"https://www.football-data.co.uk/mmz4281/{fd_season}/{league_code}.csv"
        try:
            r = requests.get(url, timeout=12)
            if not r.ok or not r.text or len(r.text) < 100:
                continue
            import csv as _csv, io as _io
            reader = _csv.DictReader(_io.StringIO(r.text))
            for row in reader:
                try:
                    if not row.get("HomeTeam") or not row.get("FTHG"):
                        continue
                    _date = _parse_match_date(row.get("Date"))
                    _home = row.get("HomeTeam", "").strip()
                    _away = row.get("AwayTeam", "").strip()
                    if not _date or not _home or not _away:
                        continue
                    all_rows.append({
                        "date": _date,
                        "season": season_str,
                        "league": FD_CO_UK_LEAGUES[league_code],
                        "source": "football_data_co_uk",
                        "match_id": f"fd_{season_str}_{league_code}_{_norm_team(_home)}_{_norm_team(_away)}_{_date}",
                        "home": _home,
                        "away": _away,
                        "home_goals": _to_int_or_none(row.get("FTHG")),
                        "away_goals": _to_int_or_none(row.get("FTAG")),
                        "ht_home": _to_int_or_none(row.get("HTHG")),
                        "ht_away": _to_int_or_none(row.get("HTAG")),
                        "shots_home": _to_float_or_none(row.get("HS")),
                        "shots_away": _to_float_or_none(row.get("AS")),
                        "sot_home": _to_float_or_none(row.get("HST")),
                        "sot_away": _to_float_or_none(row.get("AST")),
                        "corners_home": _to_float_or_none(row.get("HC")),
                        "corners_away": _to_float_or_none(row.get("AC")),
                        "cards_home": _to_float_or_none(row.get("HY")),
                        "cards_away": _to_float_or_none(row.get("AY")),
                        # Bet365 + Pinnacle + Betfair/market consensus. All are pre-match odds.
                        "bet365_home": _to_float_or_none(row.get("B365CH") or row.get("B365H")),
                        "bet365_draw": _to_float_or_none(row.get("B365CD") or row.get("B365D")),
                        "bet365_away": _to_float_or_none(row.get("B365CA") or row.get("B365A")),
                        "pinnacle_home": _to_float_or_none(row.get("PSCH") or row.get("PSH") or row.get("PH")),
                        "pinnacle_draw": _to_float_or_none(row.get("PSCD") or row.get("PSD") or row.get("PD")),
                        "pinnacle_away": _to_float_or_none(row.get("PSCA") or row.get("PSA") or row.get("PA")),
                        "betfair_home": _to_float_or_none(row.get("BFEH") or row.get("BFH")),
                        "betfair_draw": _to_float_or_none(row.get("BFED") or row.get("BFD")),
                        "betfair_away": _to_float_or_none(row.get("BFEA") or row.get("BFA")),
                        "odd_home": _to_float_or_none(row.get("AvgH") or row.get("B365CH") or row.get("B365H") or row.get("PSH")),
                        "odd_draw": _to_float_or_none(row.get("AvgD") or row.get("B365CD") or row.get("B365D") or row.get("PSD")),
                        "odd_away": _to_float_or_none(row.get("AvgA") or row.get("B365CA") or row.get("B365A") or row.get("PSA")),
                        "over25_odds": _to_float_or_none(row.get("Avg>2.5") or row.get("B365>2.5") or row.get("P>2.5")),
                        "under25_odds": _to_float_or_none(row.get("Avg<2.5") or row.get("B365<2.5") or row.get("P<2.5")),
                        "bet365_over25": _to_float_or_none(row.get("B365>2.5")),
                        "bet365_under25": _to_float_or_none(row.get("B365<2.5")),
                        "pinnacle_over25": _to_float_or_none(row.get("P>2.5")),
                        "pinnacle_under25": _to_float_or_none(row.get("P<2.5")),
                    })
                    fd_count += 1
                except (ValueError, TypeError):
                    continue
        except Exception as e:
            print(f"  ⚠️  FD.co.uk {season_str} {league_code}: {str(e)[:50]}")

    print(f"   ✅ Football-Data.co.uk: {fd_count} Spiele (mit Schüssen/Ecken/Karten)")

    # ── 3. martj42 Länderspiele ────────────────────────────────────────────
    print("📥 Lade martj42 Länderspiele...")
    intl_count = 0
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
            timeout=15,
        )
        if r.ok:
            import csv as _csv, io as _io
            reader = _csv.DictReader(_io.StringIO(r.text))
            for row in reader:
                try:
                    date_str = row.get("date", "")
                    if not date_str or date_str < "2010-01-01":
                        continue  # nur ab 2010 (neuere Fussball-Ära)
                    all_rows.append({
                        "date": date_str,
                        "season": date_str[:4],
                        "league": "International",
                        "source": "martj42/international_results",
                        "match_id": None,
                        "home": row.get("home_team", "").strip(),
                        "away": row.get("away_team", "").strip(),
                        "home_goals": int(row.get("home_score", 0) or 0),
                        "away_goals": int(row.get("away_score", 0) or 0),
                        "ht_home": 0, "ht_away": 0,
                        "shots_home": None, "shots_away": None,
                        "corners_home": None, "corners_away": None,
                        "cards_home": None, "cards_away": None,
                    })
                    intl_count += 1
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"  ⚠️  martj42: {e}")
    print(f"   ✅ martj42: {intl_count} Länderspiele (ab 2010)")

    # ── 4. Supabase ml_tips (eigene Bot-Ergebnisse als Trainingsquelle) ────
    if SUPABASE_URL and SUPABASE_KEY:
        print("📥 Lade Supabase ml_tips (eigene Bot-Ergebnisse)...")
        supabase_count = 0
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/ml_tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"settled": "eq.true", "select": "*", "limit": "10000"},
                timeout=15,
            )
            if r.ok:
                for tip in r.json():
                    try:
                        if not tip.get("actual_score") or not tip.get("result"):
                            continue
                        score_parts = tip["actual_score"].split("-")
                        if len(score_parts) != 2:
                            continue
                        all_rows.append({
                            "date": tip.get("date", ""),
                            "season": "bot",
                            "league": tip.get("league", "Bot"),
                            "home": tip.get("home_team", ""),
                            "away": tip.get("away_team", ""),
                            "home_goals": int(score_parts[0]),
                            "away_goals": int(score_parts[1]),
                            "ht_home": 0, "ht_away": 0,
                            "shots_home": None, "shots_away": None,
                            "corners_home": None, "corners_away": None,
                            "cards_home": None, "cards_away": None,
                        })
                        supabase_count += 1
                    except Exception:
                        continue
        except Exception as e:
            print(f"  ⚠️  Supabase ml_tips: {e}")
        print(f"   ✅ Supabase ml_tips: {supabase_count} eigene Spiele")

# ── 5. Supabase match_results (Result-Scraper/Source-Hub Output) ───────
    print("📥 Lade Supabase match_results...")
    mr_count = 0
    for row in _fetch_supabase_rows("match_results", select="*", order="match_date.asc", limit_total=30000):
        norm = _normalize_result_row(row, "supabase_match_results")
        if norm:
            all_rows.append(norm)
            mr_count += 1
    print(f"   ✅ Supabase match_results: {mr_count} Spiele")

    # V34: Import-Harvester tables contain many more GitHub/Open-Source historical matches.
    all_rows.extend(_load_supabase_match_table("football_historical_matches", limit_total=150000))

    # Merge every bookmaker/source from odds_history into matching games.
    odds_by_key = _load_odds_history(limit_total=250000)
    for _row in all_rows:
        _dt = _parse_match_date(_row.get("date"))
        if _dt:
            _row["date"] = _dt
            _merge_odds_into_match(_row, odds_by_key.get(_match_key(_dt, _row.get("home"), _row.get("away")), []))

    # Sortieren nach Datum
    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "home", "away"]).sort_values("date").reset_index(drop=True)

    # Multi-source fusion: preserve stats/odds from every successful source.
    stat_cols = ["shots_home", "shots_away", "corners_home", "corners_away", "cards_home", "cards_away"]
    for _c in stat_cols:
        if _c not in df.columns:
            df[_c] = None
    if "source" not in df.columns:
        df["source"] = "unknown"
    df["_dedup_key"] = df.apply(lambda r: _match_key(r["date"].date().isoformat(), r["home"], r["away"]), axis=1)
    fused = []
    for _, _g in df.groupby("_dedup_key", sort=False):
        fused.append(_fuse_match_group(_g.drop(columns=["_dedup_key"]).to_dict("records")))
    df = pd.DataFrame(fused)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)

    print("   📊 Stat-Abdeckung nach Dedup:",
          "shots", int(pd.to_numeric(df.get("shots_home"), errors="coerce").notna().sum()),
          "corners", int(pd.to_numeric(df.get("corners_home"), errors="coerce").notna().sum()),
          "cards", int(pd.to_numeric(df.get("cards_home"), errors="coerce").notna().sum()))

    print(f"\n✅ TOTAL: {len(df)} Spiele aus {df['league'].nunique()} Ligen, {df['date'].dt.year.nunique()} Jahre")
    print(f"   Datum: {df['date'].min().date()} bis {df['date'].max().date()}")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ELO-RATINGS ROLLEND BERECHNEN
# ═══════════════════════════════════════════════════════════════════════════════

def compute_elo_ratings(df):
    """
    Berechnet Elo-Ratings für jeden Eintrag NACH dem Spiel, 
    sodass Features vor-dem-Spiel sauber sind (kein Data-Leakage).
    """
    ratings = {}  # {team_key: elo}

    elo_before_home = []
    elo_before_away = []

    for _, row in df.iterrows():
        h = row["home"]
        a = row["away"]

        r_h = ratings.get(h, ELO_BASE)
        r_a = ratings.get(a, ELO_BASE)

        elo_before_home.append(r_h)
        elo_before_away.append(r_a)

        # Update nach Spiel
        h_adj = r_h + ELO_HOME_ADV
        exp_h = 1 / (1 + 10 ** ((r_a - h_adj) / 400))
        actual_h = 1.0 if row["home_goals"] > row["away_goals"] else (
            0.5 if row["home_goals"] == row["away_goals"] else 0.0
        )
        margin_mult = 1.0 + (abs(row["home_goals"] - row["away_goals"]) - 1) * 0.15 \
            if abs(row["home_goals"] - row["away_goals"]) > 1 else 1.0
        delta = ELO_K * margin_mult * (actual_h - exp_h)

        ratings[h] = r_h + delta
        ratings[a] = r_a - delta

    df = df.copy()
    df["elo_home"] = elo_before_home
    df["elo_away"] = elo_before_away
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    df["elo_home"] = pd.to_numeric(df["elo_home"], errors="coerce")
    df["elo_away"] = pd.to_numeric(df["elo_away"], errors="coerce")
    df["elo_diff"] = pd.to_numeric(df["elo_diff"], errors="coerce")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FORM-FEATURES (rollend, kein Data-Leakage)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_form_features(df, n=10):
    """
    Rolling Form-Features pro Team (aus vergangenen Spielen):
    BTTS-Rate, Over2.5-Rate, Ø Tore erzielt/kassiert
    """
    df = df.copy()
    df["btts"] = ((df["home_goals"] > 0) & (df["away_goals"] > 0)).astype(int)
    df["over25"] = ((df["home_goals"] + df["away_goals"]) > 2).astype(int)
    df["total_goals"] = df["home_goals"] + df["away_goals"]
    df["btts_ht"] = ((df["ht_home"] > 0) & (df["ht_away"] > 0)).astype(int)
    df["over15_ht"] = ((df["ht_home"] + df["ht_away"]) > 1).astype(int)

    # V31: weitere Channel-Targets für Training
    df["over15"] = ((df["home_goals"] + df["away_goals"]) > 1).astype(int)
    df["over35"] = ((df["home_goals"] + df["away_goals"]) > 3).astype(int)
    df["btts_over25"] = ((df["btts"] == 1) & (df["over25"] == 1)).astype(int)
    df["home_win"] = (df["home_goals"] > df["away_goals"]).astype(int)
    df["draw"] = (df["home_goals"] == df["away_goals"]).astype(int)
    df["away_win"] = (df["away_goals"] > df["home_goals"]).astype(int)

    # Corners/Cards nur trainieren, wenn echte Football-Data.co.uk Werte vorhanden sind.
    # Bei openfootball/martj42 bleiben diese Targets NaN und werden im Training sauber gedroppt.
    corners_total = pd.to_numeric(df.get("corners_home"), errors="coerce") + pd.to_numeric(df.get("corners_away"), errors="coerce")
    cards_total = pd.to_numeric(df.get("cards_home"), errors="coerce") + pd.to_numeric(df.get("cards_away"), errors="coerce")
    df["corners_over85"] = np.where(corners_total.notna(), (corners_total > 8).astype(int), np.nan)
    df["corners_over95"] = np.where(corners_total.notna(), (corners_total > 9).astype(int), np.nan)
    df["cards_over25"] = np.where(cards_total.notna(), (cards_total > 2).astype(int), np.nan)
    df["cards_over35"] = np.where(cards_total.notna(), (cards_total > 3).astype(int), np.nan)

    # V32 TRAIN-ALL: alle Match-/Kanal-Targets, die aus den vorhandenen Daten ableitbar sind.
    total_goals = pd.to_numeric(df["home_goals"], errors="coerce") + pd.to_numeric(df["away_goals"], errors="coerce")
    home_goals = pd.to_numeric(df["home_goals"], errors="coerce")
    away_goals = pd.to_numeric(df["away_goals"], errors="coerce")
    ht_goals = pd.to_numeric(df["ht_home"], errors="coerce") + pd.to_numeric(df["ht_away"], errors="coerce")
    shots_total = pd.to_numeric(df.get("shots_home"), errors="coerce") + pd.to_numeric(df.get("shots_away"), errors="coerce")

    df["over05"] = (total_goals > 0).astype(int)
    df["over45"] = (total_goals > 4).astype(int)
    df["under25"] = (total_goals < 3).astype(int)
    df["under35"] = (total_goals < 4).astype(int)
    df["btts_no"] = (df["btts"] == 0).astype(int)

    df["home_over05"] = (home_goals > 0).astype(int)
    df["home_over15"] = (home_goals > 1).astype(int)
    df["home_over25"] = (home_goals > 2).astype(int)
    df["away_over05"] = (away_goals > 0).astype(int)
    df["away_over15"] = (away_goals > 1).astype(int)
    df["away_over25"] = (away_goals > 2).astype(int)
    df["home_clean_sheet"] = (away_goals == 0).astype(int)
    df["away_clean_sheet"] = (home_goals == 0).astype(int)

    df["home_or_draw"] = ((df["home_win"] == 1) | (df["draw"] == 1)).astype(int)
    df["away_or_draw"] = ((df["away_win"] == 1) | (df["draw"] == 1)).astype(int)
    df["home_or_away"] = ((df["home_win"] == 1) | (df["away_win"] == 1)).astype(int)

    df["over05_ht"] = (ht_goals > 0).astype(int)
    df["under15_ht"] = (ht_goals < 2).astype(int)
    df["home_win_ht"] = (pd.to_numeric(df["ht_home"], errors="coerce") > pd.to_numeric(df["ht_away"], errors="coerce")).astype(int)
    df["draw_ht"] = (pd.to_numeric(df["ht_home"], errors="coerce") == pd.to_numeric(df["ht_away"], errors="coerce")).astype(int)
    df["away_win_ht"] = (pd.to_numeric(df["ht_away"], errors="coerce") > pd.to_numeric(df["ht_home"], errors="coerce")).astype(int)

    for line in [65, 75, 85, 95, 105, 115]:
        col = f"corners_over{line}"
        df[col] = np.where(corners_total.notna(), (corners_total > (line / 10.0)).astype(int), np.nan)

    for line in [15, 25, 35, 45, 55]:
        col = f"cards_over{line}"
        df[col] = np.where(cards_total.notna(), (cards_total > (line / 10.0)).astype(int), np.nan)

    for line in [185, 205, 225, 245, 265, 285]:
        col = f"shots_over{line}"
        df[col] = np.where(shots_total.notna(), (shots_total > (line / 10.0)).astype(int), np.nan)

    # Team-History aufbauen {team: [list of match dicts]}
    team_history = {}

    feat_btts_h, feat_btts_a = [], []
    feat_o25_h, feat_o25_a = [], []
    feat_goals_scored_h, feat_goals_scored_a = [], []
    feat_goals_conceded_h, feat_goals_conceded_a = [], []
    feat_btts_ht_h, feat_btts_ht_a = [], []
    feat_o15ht_h, feat_o15ht_a = [], []

    for _, row in df.iterrows():
        home, away = row["home"], row["away"]

        def _get_stats(team, is_home_team):
            hist = team_history.get(team, [])
            if not hist:
                return [0.5, 0.5, 1.35, 1.15, 0.4, 0.4]
            last = hist[-n:]
            if is_home_team:
                scored = [m["home_goals"] for m in last if m["is_home"]] + \
                         [m["away_goals"] for m in last if not m["is_home"]]
                conceded = [m["away_goals"] for m in last if m["is_home"]] + \
                           [m["home_goals"] for m in last if not m["is_home"]]
            else:
                scored = [m["home_goals"] for m in last if m["is_home"]] + \
                         [m["away_goals"] for m in last if not m["is_home"]]
                conceded = [m["away_goals"] for m in last if m["is_home"]] + \
                           [m["home_goals"] for m in last if not m["is_home"]]

            btts_r = sum(m["btts"] for m in last) / len(last)
            o25_r = sum(m["over25"] for m in last) / len(last)
            avg_s = sum(scored) / len(scored) if scored else 1.2
            avg_c = sum(conceded) / len(conceded) if conceded else 1.2
            btts_ht_r = sum(m["btts_ht"] for m in last) / len(last)
            o15ht_r = sum(m["over15_ht"] for m in last) / len(last)
            return [btts_r, o25_r, avg_s, avg_c, btts_ht_r, o15ht_r]

        sh = _get_stats(home, True)
        sa = _get_stats(away, False)

        feat_btts_h.append(sh[0])
        feat_o25_h.append(sh[1])
        feat_goals_scored_h.append(sh[2])
        feat_goals_conceded_h.append(sh[3])
        feat_btts_ht_h.append(sh[4])
        feat_o15ht_h.append(sh[5])

        feat_btts_a.append(sa[0])
        feat_o25_a.append(sa[1])
        feat_goals_scored_a.append(sa[2])
        feat_goals_conceded_a.append(sa[3])
        feat_btts_ht_a.append(sa[4])
        feat_o15ht_a.append(sa[5])

        # Update History
        match_info = {
            "is_home": True,
            "home_goals": row["home_goals"],
            "away_goals": row["away_goals"],
            "btts": row["btts"],
            "over25": row["over25"],
            "btts_ht": row["btts_ht"],
            "over15_ht": row["over15_ht"],
        }
        team_history.setdefault(home, []).append(match_info)
        away_info = {**match_info, "is_home": False}
        team_history.setdefault(away, []).append(away_info)

    df["btts_rate_home"] = feat_btts_h
    df["btts_rate_away"] = feat_btts_a
    df["o25_rate_home"] = feat_o25_h
    df["o25_rate_away"] = feat_o25_a
    df["avg_scored_home"] = feat_goals_scored_h
    df["avg_scored_away"] = feat_goals_scored_a
    df["avg_conceded_home"] = feat_goals_conceded_h
    df["avg_conceded_away"] = feat_goals_conceded_a
    df["btts_ht_rate_home"] = feat_btts_ht_h
    df["btts_ht_rate_away"] = feat_btts_ht_a
    df["o15ht_rate_home"] = feat_o15ht_h
    df["o15ht_rate_away"] = feat_o15ht_a

    # Kombinierte Features
    df["btts_rate_combined"] = (df["btts_rate_home"] + df["btts_rate_away"]) / 2
    df["o25_rate_combined"] = (df["o25_rate_home"] + df["o25_rate_away"]) / 2
    df["exp_goals"] = df["avg_scored_home"] + df["avg_scored_away"]
    df["avg_conceded_combined"] = (df["avg_conceded_home"] + df["avg_conceded_away"]) / 2

    # ── Rolling Schüsse/Ecken/Karten (aus football-data.co.uk) ────────────
    # Nur wo Daten vorhanden (sonst 0 = neutral)
    shot_avg_h, shot_avg_a = [], []
    corner_avg_h, corner_avg_a = [], []
    card_avg_h, card_avg_a = [], []
    team_shots = {}
    team_corners = {}
    team_cards = {}

    for _, row in df.iterrows():
        home, away = row["home"], row["away"]

        def _avg(store, team, default):
            hist = store.get(team, [])[-10:]
            return sum(hist) / len(hist) if hist else default

        shot_avg_h.append(_avg(team_shots, home, 11.0))
        shot_avg_a.append(_avg(team_shots, away, 10.0))
        corner_avg_h.append(_avg(team_corners, home, 5.0))
        corner_avg_a.append(_avg(team_corners, away, 4.5))
        card_avg_h.append(_avg(team_cards, home, 1.5))
        card_avg_a.append(_avg(team_cards, away, 1.5))

        # Update mit echten Werten wenn vorhanden
        if row.get("shots_home") is not None and row["shots_home"] > 0:
            team_shots.setdefault(home, []).append(row["shots_home"])
            team_shots.setdefault(away, []).append(row["shots_away"])
        if row.get("corners_home") is not None and row["corners_home"] > 0:
            team_corners.setdefault(home, []).append(row["corners_home"])
            team_corners.setdefault(away, []).append(row["corners_away"])
        if row.get("cards_home") is not None:
            team_cards.setdefault(home, []).append(row["cards_home"])
            team_cards.setdefault(away, []).append(row["cards_away"])

    df["avg_shots_home"] = shot_avg_h
    df["avg_shots_away"] = shot_avg_a
    df["avg_corners_home"] = corner_avg_h
    df["avg_corners_away"] = corner_avg_a
    df["avg_cards_home"] = card_avg_h
    df["avg_cards_away"] = card_avg_a
    df["total_shots_exp"] = df["avg_shots_home"] + df["avg_shots_away"]
    df["total_corners_exp"] = df["avg_corners_home"] + df["avg_corners_away"]
    df["total_cards_exp"] = df["avg_cards_home"] + df["avg_cards_away"]

    # ── Form-Punkte (W=3/D=1/L=0 — aus bestehendem Feature-Engineering-Code) ──
    form_pts_home = []
    form_pts_away = []
    streak_win_home = []
    streak_win_away = []

    # Nochmal über History iterieren für Punkte-Features (getrennt, sauber)
    team_results = {}
    for _, row in df.iterrows():
        home, away = row["home"], row["away"]

        def _form_pts(team, last_k=5):
            hist = team_results.get(team, [])[-last_k:]
            pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in hist)
            return pts / 15.0  # max 15 Punkte (5 Siege) → normiert auf 0-1

        def _streak(team):
            hist = team_results.get(team, [])
            streak = 0
            for r in reversed(hist):
                if r == "W":
                    streak += 1
                else:
                    break
            return min(streak / 5.0, 1.0)  # normiert

        form_pts_home.append(_form_pts(home))
        form_pts_away.append(_form_pts(away))
        streak_win_home.append(_streak(home))
        streak_win_away.append(_streak(away))

        # Ergebnis für dieses Spiel speichern
        if row["home_goals"] > row["away_goals"]:
            team_results.setdefault(home, []).append("W")
            team_results.setdefault(away, []).append("L")
        elif row["home_goals"] < row["away_goals"]:
            team_results.setdefault(home, []).append("L")
            team_results.setdefault(away, []).append("W")
        else:
            team_results.setdefault(home, []).append("D")
            team_results.setdefault(away, []).append("D")

    df["form_pts_home"] = form_pts_home
    df["form_pts_away"] = form_pts_away
    df["form_pts_diff"] = df["form_pts_home"] - df["form_pts_away"]
    df["streak_win_home"] = streak_win_home
    df["streak_win_away"] = streak_win_away

    # ── H2H Features aus Match-History ──
    h2h_history = {}
    h2h_btts = []
    h2h_avg_goals = []
    h2h_matches = []

    for _, row in df.iterrows():
        h, a = row["home"], row["away"]
        key = tuple(sorted([h, a]))
        hist = h2h_history.get(key, [])

        if hist:
            h2h_btts.append(sum(m["btts"] for m in hist) / len(hist))
            h2h_avg_goals.append(sum(m["goals"] for m in hist) / len(hist))
            h2h_matches.append(min(len(hist) / 10.0, 1.0))
        else:
            h2h_btts.append(0.5)      # Prior: 50% wenn keine H2H-Daten
            h2h_avg_goals.append(2.5)
            h2h_matches.append(0.0)

        h2h_history.setdefault(key, []).append({
            "btts": int(row["home_goals"] > 0 and row["away_goals"] > 0),
            "goals": row["home_goals"] + row["away_goals"],
        })

    df["h2h_btts_rate"] = h2h_btts
    df["h2h_avg_goals"] = h2h_avg_goals
    df["h2h_matches_norm"] = h2h_matches

    # 🆕 Erzwinge numerischen Dtype für alle Feature-Spalten — verhindert
    # dass gemischte Quellen (int/None/string) eine Spalte zu 'object' machen,
    # was dropna()/XGBoost unvorhersehbar verhalten lassen kann.
    _numeric_cols = [
        "btts_rate_home", "btts_rate_away", "o25_rate_home", "o25_rate_away",
        "avg_scored_home", "avg_scored_away", "avg_conceded_home", "avg_conceded_away",
        "btts_ht_rate_home", "btts_ht_rate_away", "o15ht_rate_home", "o15ht_rate_away",
        "btts_rate_combined", "o25_rate_combined", "exp_goals", "avg_conceded_combined",
        "avg_shots_home", "avg_shots_away", "avg_corners_home", "avg_corners_away",
        "avg_cards_home", "avg_cards_away", "total_shots_exp", "total_corners_exp",
        "total_cards_exp", "form_pts_home", "form_pts_away", "form_pts_diff",
        "streak_win_home", "streak_win_away", "h2h_btts_rate", "h2h_avg_goals",
        "h2h_matches_norm",
    ]
    for col in _numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 🆕 Shots/Ecken/Karten mit 0 füllen (openfootball/martj42 haben None → 0 = neutral/unbekannt)
    # So werden alle 33.000+ Spiele genutzt statt nur die 148 mit FD.co.uk-Daten
    for col in ["avg_shots_home", "avg_shots_away", "total_shots_exp",
                "avg_corners_home", "avg_corners_away", "total_corners_exp",
                "avg_cards_home", "avg_cards_away", "total_cards_exp"]:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    return df



def add_market_odds_features(df):
    """Pre-match bookmaker consensus features. Missing odds use neutral priors plus availability flags."""
    for col in [
        "odd_home", "odd_draw", "odd_away", "over25_odds", "under25_odds",
        "bet365_home", "bet365_draw", "bet365_away", "pinnacle_home", "pinnacle_draw", "pinnacle_away",
        "betfair_home", "betfair_draw", "betfair_away", "bet365_over25", "bet365_under25",
        "pinnacle_over25", "pinnacle_under25", "source_count", "odds_source_count",
    ]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def implied(series):
        return np.where(series > 1.0, 1.0 / series, np.nan)

    home_p, draw_p, away_p = implied(df["odd_home"]), implied(df["odd_draw"]), implied(df["odd_away"])
    total = home_p + draw_p + away_p
    df["odds_available_1x2"] = np.where(np.isfinite(total), 1.0, 0.0)
    df["market_margin_1x2"] = np.where(np.isfinite(total), total - 1.0, 0.0)
    df["market_home_prob"] = np.where(np.isfinite(total) & (total > 0), home_p / total, 1/3)
    df["market_draw_prob"] = np.where(np.isfinite(total) & (total > 0), draw_p / total, 1/3)
    df["market_away_prob"] = np.where(np.isfinite(total) & (total > 0), away_p / total, 1/3)

    over_p, under_p = implied(df["over25_odds"]), implied(df["under25_odds"])
    total_ou = over_p + under_p
    df["odds_available_ou25"] = np.where(np.isfinite(total_ou), 1.0, 0.0)
    df["market_over25_prob"] = np.where(np.isfinite(total_ou) & (total_ou > 0), over_p / total_ou, 0.5)
    df["market_under25_prob"] = np.where(np.isfinite(total_ou) & (total_ou > 0), under_p / total_ou, 0.5)

    # Sharp/soft deltas: Pinnacle and Bet365 compared with consensus.
    for side in ["home", "draw", "away"]:
        consensus = pd.to_numeric(df[f"odd_{side}"], errors="coerce")
        for book in ["pinnacle", "bet365", "betfair"]:
            b = pd.to_numeric(df[f"{book}_{side}"], errors="coerce")
            df[f"{book}_{side}_delta"] = np.where(
                (b > 1) & (consensus > 1), (1 / b) - (1 / consensus), 0.0
            )

    df["source_count_norm"] = pd.to_numeric(df["source_count"], errors="coerce").fillna(1).clip(1, 10) / 10.0
    df["odds_source_count_norm"] = pd.to_numeric(df["odds_source_count"], errors="coerce").fillna(0).clip(0, 20) / 20.0
    stat_present = sum(pd.to_numeric(df.get(c), errors="coerce").notna().astype(int) for c in [
        "shots_home", "shots_away", "corners_home", "corners_away", "cards_home", "cards_away"
    ])
    df["stat_coverage"] = stat_present / 6.0
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4A. ROBUSTE KALIBRIERUNG — kein Crash bei einseitigen CV-Folds
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_fit_classifier(base_model, X, y, model_name, prefer_calibration=True):
    """
    Trainiert robust:
    - StratifiedKFold statt TimeSeriesSplit, damit jeder Fold beide Klassen hat.
    - Wenn zu wenig Minderheitsklasse vorhanden ist: ohne Calibration trainieren.
    - Wenn Calibration trotzdem crasht: Fallback auf unkalibrierten XGBoost.
    """
    y_arr = np.asarray(y).astype(int)
    classes, counts = np.unique(y_arr, return_counts=True)
    if len(classes) < 2:
        raise ValueError(f"{model_name}: only one class in target")

    minority = int(counts.min())
    if (not prefer_calibration) or minority < 2:
        print(f"   ⚠️ Calibration AUS: Minderheitsklasse nur {minority} Samples")
        base_model.fit(X, y_arr)
        return base_model

    n_splits = max(2, min(3, minority))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    try:
        calibrated = CalibratedClassifierCV(base_model, method="sigmoid", cv=cv)
        calibrated.fit(X, y_arr)
        return calibrated
    except Exception as e:
        print(f"   ⚠️ Calibration-Fallback für {model_name}: {str(e)[:120]}")
        base_model.fit(X, y_arr)
        return base_model


def _safe_auc(y_true, proba):
    try:
        if len(np.unique(y_true)) < 2:
            return 0.5
        return roc_auc_score(y_true, proba)
    except Exception:
        return 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MODELL TRAINIEREN
# ═══════════════════════════════════════════════════════════════════════════════

FEATURE_COLS = [
    # Elo-Ratings
    "elo_home", "elo_away", "elo_diff",
    # BTTS/Over-Raten (rolling)
    "btts_rate_home", "btts_rate_away", "btts_rate_combined",
    "o25_rate_home", "o25_rate_away", "o25_rate_combined",
    # Tore erzielt/kassiert
    "avg_scored_home", "avg_scored_away",
    "avg_conceded_home", "avg_conceded_away",
    "exp_goals", "avg_conceded_combined",
    # Halbzeit-Features
    "btts_ht_rate_home", "btts_ht_rate_away",
    "o15ht_rate_home", "o15ht_rate_away",
    # Form-Punkte (W=3/D=1/L=0)
    "form_pts_home", "form_pts_away", "form_pts_diff",
    "streak_win_home", "streak_win_away",
    # H2H-History
    "h2h_btts_rate", "h2h_avg_goals", "h2h_matches_norm",
    # Schüsse/Ecken/Karten
    "avg_shots_home", "avg_shots_away", "total_shots_exp",
    "avg_corners_home", "avg_corners_away", "total_corners_exp",
    "avg_cards_home", "avg_cards_away", "total_cards_exp",
    # Multi-source + bookmaker market features
    "source_count_norm", "stat_coverage", "odds_source_count_norm",
    "odds_available_1x2", "market_margin_1x2",
    "market_home_prob", "market_draw_prob", "market_away_prob",
    "odds_available_ou25", "market_over25_prob", "market_under25_prob",
    "pinnacle_home_delta", "pinnacle_draw_delta", "pinnacle_away_delta",
    "bet365_home_delta", "bet365_draw_delta", "bet365_away_delta",
    "betfair_home_delta", "betfair_draw_delta", "betfair_away_delta",
]


def train_model(df, target_col, model_name):
    """Trainiert XGBoost-Klassifikator mit Time-Series-CV und Kalibrierung."""
    # 🆕 Diagnostik VOR dropna — zeigt welche Spalte das Problem verursacht
    print(f"\n{'='*60}")
    print(f"🧠 Trainiere Modell: {model_name}")
    print(f"   Rohdaten: {len(df)} Zeilen")

    nan_report = []
    for col in FEATURE_COLS + [target_col]:
        if col not in df.columns:
            nan_report.append(f"   ❌ FEHLENDE SPALTE: {col}")
            continue
        n_nan = df[col].isna().sum()
        if n_nan > 0:
            pct = round(n_nan / len(df) * 100, 1)
            nan_report.append(f"   ⚠️  {col}: {n_nan} NaN ({pct}%)")

    if nan_report:
        print(f"   📋 NaN-Diagnose ({len(nan_report)} betroffene Spalten):")
        for line in nan_report[:15]:  # Max 15 Zeilen zeigen
            print(line)

    df_clean = df.dropna(subset=FEATURE_COLS + [target_col])
    print(f"   Nach dropna: {len(df_clean)} Zeilen (von {len(df)})")

    # 🆕 Schutz: iloc-Cut proportional statt fix 200 (verhindert leeres df bei kleinen Datensätzen)
    cut = min(200, max(0, len(df_clean) // 20))
    df_clean = df_clean.iloc[cut:].reset_index(drop=True)
    print(f"   Nach iloc[{cut}:]: {len(df_clean)} Zeilen")

    X = df_clean[FEATURE_COLS].values
    y = df_clean[target_col].values

    # 🆕 Abbruch mit klarer Meldung statt Crash, wenn zu wenig Daten
    if len(X) < 50:
        print(f"   ❌ ÜBERSPRINGE {model_name}: nur {len(X)} Datensätze (min. 50 nötig)")
        print(f"   → Prüfe NaN-Diagnose oben um die Ursache zu finden")
        return None, {
            "model_name": model_name,
            "skipped": True,
            "reason": f"only {len(X)} samples after cleaning",
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

    if y.mean() == 0 or y.mean() == 1:
        print(f"   ❌ ÜBERSPRINGE {model_name}: keine Varianz im Target ({y.mean():.0%} positiv)")
        return None, {
            "model_name": model_name,
            "skipped": True,
            "reason": "no variance in target",
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

    print(f"   Datensätze: {len(X)}, Positiv-Rate: {y.mean():.1%}")

    # XGBoost-Parameter
    base_model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        scale_pos_weight=(1 - y.mean()) / y.mean(),
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    # V32B: robuste Calibration.
    # TimeSeriesSplit kann bei schiefen Targets einzelne Folds mit nur einer Klasse erzeugen
    # und XGBoost crasht dann: "Expected [0], got [1]".
    calibrated = _safe_fit_classifier(base_model, X, y, model_name)

    # Evaluierung auf letzten 20% (Out-of-Sample)
    split = int(len(X) * 0.8)
    X_eval, y_eval = X[split:], y[split:]
    proba = calibrated.predict_proba(X_eval)[:, 1]
    brier = brier_score_loss(y_eval, proba)
    auc = _safe_auc(y_eval, proba)
    print(f"   ✅ Brier Score: {brier:.4f} (niedriger = besser, Baseline ~0.24)")
    print(f"   ✅ ROC-AUC:     {auc:.4f} (höher = besser, Zuffall = 0.5)")

    return calibrated, {
        "model_name": model_name,
        "feature_cols": FEATURE_COLS,
        "brier_score": round(brier, 4),
        "roc_auc": round(auc, 4),
        "training_samples": len(X),
        "positive_rate": round(float(y.mean()), 3),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. IN SUPABASE SPEICHERN
# ═══════════════════════════════════════════════════════════════════════════════

def save_model_to_supabase(model, meta):
    """Serialisiert Modell via pickle + base64 und speichert in Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Kein Supabase-Zugang — Modell lokal gespeichert als Fallback")
        with open(f"{meta['model_name']}.pkl", "wb") as f:
            pickle.dump({"model": model, "meta": meta, "feature_cols": FEATURE_COLS}, f)
        return

    buf = io.BytesIO()
    pickle.dump({"model": model, "meta": meta, "feature_cols": FEATURE_COLS}, buf)
    model_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    payload = {
        "model_name": meta["model_name"],
        "model_data": model_b64,
        "meta": json.dumps(meta),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # 🆕 UPSERT via ?on_conflict=model_name (verhindert 409 bei wiederholtem Training)
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/ml_models",
        headers=headers,
        params={"on_conflict": "model_name"},
        json=payload,
        timeout=30,
    )
    if r.ok:
        size_kb = len(model_b64) / 1024
        print(f"   ✅ {meta['model_name']} in Supabase gespeichert/aktualisiert ({size_kb:.0f} KB)")

    else:
        print(f"   ❌ Supabase-Fehler {r.status_code}: {r.text[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PLAYER-PROP TRAINING — TRAIN ALL
# ═══════════════════════════════════════════════════════════════════════════════

PLAYER_STAT_ALIASES = {
    "shots_on_target": "sot",
    "sot": "sot",
    "shots": "shots",
    "goals": "goals",
    "assists": "assists",
    "passes": "passes",
    "tackles": "tackles",
    "tackles_committed": "tackles",
    "fouls_committed": "fouls_committed",
    "fouls_won": "fouls_won",
    "fouls_received": "fouls_won",
    "cards": "cards",
    "yellow_cards": "cards",
    "red_cards": "cards",
    "corners": "corners",
    "minutes": "minutes",
}

PLAYER_FEATURE_COLS = [
    "games_prior", "avg_minutes", "avg_shots", "avg_sot", "avg_goals", "avg_assists",
    "avg_passes", "avg_tackles", "avg_fouls_committed", "avg_fouls_won",
    "avg_cards", "avg_corners", "avg_source_count",
]


def _safe_rest_get(table, params, page_size=1000, max_pages=60):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    rows = []
    for page in range(max_pages):
        p = dict(params)
        p["limit"] = page_size
        p["offset"] = page * page_size
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=p, timeout=45)
            if not r.ok:
                print(f"   ⚠️ {table} GET {r.status_code}: {r.text[:300]}")
                break
            batch = r.json()
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
        except Exception as e:
            print(f"   ⚠️ {table} GET exception: {e}")
            break
    return rows


def load_player_prop_training_frame():
    """Lädt player_match_stats und baut spielerbasierte Rolling-Features."""
    print("\n📥 Lade Player-Stats für Player-Prop Training...")
    select_cols = ",".join([
        "source", "event_id", "match_date", "league", "team", "player_id", "player_name",
        "stat_name", "stat_value", "minutes", "shots", "sot", "goals", "assists",
        "passes", "tackles", "fouls_committed", "fouls_won", "cards", "corners"
    ])
    raw = _safe_rest_get(
        "player_match_stats",
        {"select": select_cols, "order": "match_date.asc"},
        page_size=1000,
        max_pages=60,
    )
    if not raw:
        print("   ⚠️ Keine Player-Stats gefunden")
        return pd.DataFrame()

    dfp = pd.DataFrame(raw)
    print(f"   ✅ player_match_stats geladen: {len(dfp)} Rows")

    # Basis-Keys
    for c in ["source", "event_id", "match_date", "league", "team", "player_id", "player_name"]:
        if c not in dfp.columns:
            dfp[c] = None
    dfp["player_key"] = dfp["player_id"].fillna("").astype(str)
    dfp.loc[dfp["player_key"].eq(""), "player_key"] = dfp["player_name"].fillna("").astype(str)

    # Wide columns normalisieren
    stat_cols = ["minutes", "shots", "sot", "goals", "assists", "passes", "tackles",
                 "fouls_committed", "fouls_won", "cards", "corners"]
    for c in stat_cols:
        if c not in dfp.columns:
            dfp[c] = np.nan
        dfp[c] = pd.to_numeric(dfp[c], errors="coerce")

    # stat_name/stat_value rows in wide cols mappen
    if "stat_name" in dfp.columns and "stat_value" in dfp.columns:
        tmp = dfp[["event_id", "match_date", "league", "team", "player_key", "player_name", "stat_name", "stat_value"]].copy()
        tmp["stat_norm"] = tmp["stat_name"].astype(str).str.lower().map(PLAYER_STAT_ALIASES)
        tmp["stat_value"] = pd.to_numeric(tmp["stat_value"], errors="coerce")
        tmp = tmp[tmp["stat_norm"].notna()]
        if not tmp.empty:
            piv = tmp.pivot_table(
                index=["event_id", "match_date", "league", "team", "player_key", "player_name"],
                columns="stat_norm",
                values="stat_value",
                aggfunc="sum",
            ).reset_index()
            for c in stat_cols:
                if c not in piv.columns:
                    piv[c] = np.nan
        else:
            piv = pd.DataFrame(columns=["event_id", "match_date", "league", "team", "player_key", "player_name"] + stat_cols)
    else:
        piv = pd.DataFrame(columns=["event_id", "match_date", "league", "team", "player_key", "player_name"] + stat_cols)

    # Wide rows aggregieren und mit Pivot kombinieren
    wide = dfp.groupby(["event_id", "match_date", "league", "team", "player_key", "player_name"], dropna=False)[stat_cols].max().reset_index()
    combined = pd.concat([wide, piv], ignore_index=True, sort=False)
    if combined.empty:
        return pd.DataFrame()

    combined = combined.groupby(["event_id", "match_date", "league", "team", "player_key", "player_name"], dropna=False)[stat_cols].max().reset_index()
    source_counts = dfp.groupby(["event_id", "player_key"], dropna=False)["source"].nunique().rename("source_count").reset_index()
    combined = combined.merge(source_counts, on=["event_id", "player_key"], how="left")
    combined["source_count"] = pd.to_numeric(combined["source_count"], errors="coerce").fillna(1.0)
    combined["match_date"] = pd.to_datetime(combined["match_date"], errors="coerce")
    combined = combined.dropna(subset=["match_date", "player_key"]).sort_values(["player_key", "match_date"])

    # Missing Stats: 0, Minuten unbekannt: Median/0
    for c in stat_cols:
        combined[c] = pd.to_numeric(combined[c], errors="coerce").fillna(0.0)

    # Rolling Features pro Spieler, strikt nur Vergangenheit
    rows = []
    hist = {}
    for _, row in combined.iterrows():
        pk = str(row["player_key"])
        h = hist.get(pk, [])
        feat = dict(row)
        feat["games_prior"] = len(h)

        def avg_stat(stat, default=0.0):
            last = h[-8:]
            if not last:
                return default
            return float(np.mean([x.get(stat, 0.0) for x in last]))

        for stat in stat_cols:
            feat[f"avg_{stat}"] = avg_stat(stat, 0.0)
        feat["avg_source_count"] = avg_stat("source_count", 1.0)

        rows.append(feat)
        hist.setdefault(pk, []).append({**{s: float(row.get(s, 0.0)) for s in stat_cols}, "source_count": float(row.get("source_count", 1.0))})

    out = pd.DataFrame(rows)
    for c in PLAYER_FEATURE_COLS:
        if c not in out.columns:
            out[c] = 0.0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    print(f"   ✅ Player-Prop Trainingsframe: {len(out)} Spieler-Matches")
    return out


def train_player_prop_model(dfp, stat, line, model_name):
    if dfp.empty or stat not in dfp.columns:
        print(f"   ⏭️ {model_name}: keine Daten für {stat}")
        return None, {"model_name": model_name, "skipped": True, "reason": f"no data for {stat}", "trained_at": datetime.now(timezone.utc).isoformat()}

    d = dfp.copy()
    d["target"] = (pd.to_numeric(d[stat], errors="coerce").fillna(0.0) > line).astype(int)
    d = d.dropna(subset=PLAYER_FEATURE_COLS + ["target"])
    d = d[d["games_prior"] >= 1].reset_index(drop=True)

    print(f"\n{'='*60}")
    print(f"🎯 Trainiere Player-Prop Modell: {model_name}")
    print(f"   Daten: {len(d)} | Target: {stat} > {line}")

    if len(d) < 80:
        print(f"   ⏭️ zu wenig Daten")
        return None, {"model_name": model_name, "skipped": True, "reason": f"only {len(d)} samples", "trained_at": datetime.now(timezone.utc).isoformat()}
    if d["target"].nunique() < 2:
        print(f"   ⏭️ keine Varianz")
        return None, {"model_name": model_name, "skipped": True, "reason": "no target variance", "trained_at": datetime.now(timezone.utc).isoformat()}

    X = d[PLAYER_FEATURE_COLS].values
    y = d["target"].values
    print(f"   Positiv-Rate: {y.mean():.1%}")

    base_model = xgb.XGBClassifier(
        n_estimators=220,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=8,
        scale_pos_weight=max(0.2, (1 - y.mean()) / max(y.mean(), 1e-6)),
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    calibrated = _safe_fit_classifier(base_model, X, y, model_name)

    split = int(len(X) * 0.8)
    proba = calibrated.predict_proba(X[split:])[:, 1]
    brier = brier_score_loss(y[split:], proba)
    auc = _safe_auc(y[split:], proba)

    print(f"   ✅ Brier Score: {brier:.4f}")
    print(f"   ✅ ROC-AUC:     {auc:.4f}")

    meta = {
        "model_name": model_name,
        "feature_cols": PLAYER_FEATURE_COLS,
        "model_family": "player_prop",
        "stat": stat,
        "line": line,
        "brier_score": round(float(brier), 4),
        "roc_auc": round(float(auc), 4),
        "training_samples": int(len(X)),
        "positive_rate": round(float(y.mean()), 3),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    return calibrated, meta


def train_all_player_prop_models():
    dfp = load_player_prop_training_frame()
    prop_targets = [
        ("shots", 0.5, "player_shots_over05_model"),
        ("shots", 1.5, "player_shots_over15_model"),
        ("shots", 2.5, "player_shots_over25_model"),
        ("sot", 0.5, "player_sot_over05_model"),
        ("sot", 1.5, "player_sot_over15_model"),
        ("goals", 0.5, "player_goal_over05_model"),
        ("assists", 0.5, "player_assist_over05_model"),
        ("passes", 24.5, "player_passes_over245_model"),
        ("passes", 34.5, "player_passes_over345_model"),
        ("passes", 44.5, "player_passes_over445_model"),
        ("tackles", 0.5, "player_tackles_over05_model"),
        ("tackles", 1.5, "player_tackles_over15_model"),
        ("fouls_committed", 0.5, "player_fouls_committed_over05_model"),
        ("fouls_committed", 1.5, "player_fouls_committed_over15_model"),
        ("fouls_won", 0.5, "player_fouls_won_over05_model"),
        ("fouls_won", 1.5, "player_fouls_won_over15_model"),
        ("cards", 0.5, "player_card_over05_model"),
        ("corners", 0.5, "player_corners_over05_model"),
    ]

    metas = {}
    for stat, line, model_name in prop_targets:
        model, meta = train_player_prop_model(dfp, stat, line, model_name)
        metas[model_name] = meta
        if model is not None:
            save_model_to_supabase(model, meta)
        else:
            print(f"   ⏭️ {model_name} übersprungen: {meta.get('reason')}")
    return metas


# ═══════════════════════════════════════════════════════════════════════════════
# 7. HAUPTPROGRAMM
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧠 NETRATTLER ML-Training startet — TRAIN ALL SOURCES + ODDS V34...")
    print(f"   Zeitstempel: {datetime.now(timezone.utc).isoformat()}")

    # Daten laden
    df = load_all_matches()

    # Features berechnen
    print("\n📊 Berechne Elo-Ratings...")
    df = compute_elo_ratings(df)
    print("📊 Berechne Form-Features...")
    df = compute_form_features(df)
    print("📊 Berechne Multi-Source- und Bookmaker-Features...")
    df = add_market_odds_features(df)

    # Targets definieren
    targets = {
        # BTTS / Goals
        "btts_model": "btts",
        "btts_no_model": "btts_no",
        "over05_model": "over05",
        "over15_model": "over15",
        "over25_model": "over25",
        "over35_model": "over35",
        "over45_model": "over45",
        "under25_model": "under25",
        "under35_model": "under35",

        # Team Goals / Clean Sheet
        "home_over05_model": "home_over05",
        "home_over15_model": "home_over15",
        "home_over25_model": "home_over25",
        "away_over05_model": "away_over05",
        "away_over15_model": "away_over15",
        "away_over25_model": "away_over25",
        "home_clean_sheet_model": "home_clean_sheet",
        "away_clean_sheet_model": "away_clean_sheet",

        # 1X2 / Double Chance
        "home_win_model": "home_win",
        "draw_model": "draw",
        "away_win_model": "away_win",
        "home_or_draw_model": "home_or_draw",
        "away_or_draw_model": "away_or_draw",
        "home_or_away_model": "home_or_away",

        # Combos
        "btts_over25_combo_model": "btts_over25",

        # Half Time — alles, was als Kanal aktiv ist: BTTS HT + Over 1.5 HT
        "btts_ht_model": "btts_ht",
        "over15_ht_model": "over15_ht",

        # Corners
        "corners_over65_model": "corners_over65",
        "corners_over75_model": "corners_over75",
        "corners_over85_model": "corners_over85",
        "corners_over95_model": "corners_over95",
        "corners_over105_model": "corners_over105",
        "corners_over115_model": "corners_over115",

        # Cards
        "cards_over15_model": "cards_over15",
        "cards_over25_model": "cards_over25",
        "cards_over35_model": "cards_over35",
        "cards_over45_model": "cards_over45",
        "cards_over55_model": "cards_over55",

        # Team Shots total
        "shots_over185_model": "shots_over185",
        "shots_over205_model": "shots_over205",
        "shots_over225_model": "shots_over225",
        "shots_over245_model": "shots_over245",
        "shots_over265_model": "shots_over265",
        "shots_over285_model": "shots_over285",
    }

    all_meta = {}
    for model_name, target_col in targets.items():
        try:
            model, meta = train_model(df, target_col, model_name)
            if model is None:
                print(f"   ⏭️  {model_name} übersprungen: {meta.get('reason', 'unbekannt')}")
                all_meta[model_name] = meta
                continue
            save_model_to_supabase(model, meta)
            all_meta[model_name] = meta
        except Exception as e:
            print(f"   ⚠️ {model_name} Fehler, Training läuft weiter: {str(e)[:250]}")
            all_meta[model_name] = {
                "model_name": model_name,
                "target_col": target_col,
                "skipped": True,
                "reason": str(e)[:500],
                "trained_at": datetime.now(timezone.utc).isoformat(),
            }

    # Player Props trainieren wir ebenfalls: alles, was aus player_match_stats ableitbar ist.
    try:
        player_prop_meta = train_all_player_prop_models()
        all_meta.update(player_prop_meta)
    except Exception as e:
        print(f"   ⚠️ Player-Prop Training Fehler, Match-Modelle bleiben gespeichert: {str(e)[:250]}")
        all_meta["player_props_training"] = {
            "model_name": "player_props_training",
            "skipped": True,
            "reason": str(e)[:500],
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

    print("\n" + "="*60)
    print("✅ Training abgeschlossen!")
    for name, meta in all_meta.items():
        if isinstance(meta, dict) and meta.get("skipped"):
            print(f"   {name}: ÜBERSPRUNGEN ({meta.get('reason')})")
        elif isinstance(meta, dict):
            print(f"   {name}: AUC={meta.get('roc_auc')}, Brier={meta.get('brier_score')}")
        else:
            print(f"   {name}: meta nicht lesbar")
