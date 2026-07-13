#!/usr/bin/env python3
"""
NETRATTLER ML-Training-Script
==============================
Trainiert XGBoost-Modelle für BTTS und Over2.5 aus openfootball-Daten.
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

import os, sys, json, math, base64, io, pickle
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ML
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
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
FD_CO_UK_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]


# ── Elo-Konfiguration ─────────────────────────────────────────────────────────
ELO_BASE = 1500
ELO_K = 20
ELO_HOME_ADV = 60


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATEN LADEN
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_matches():
    """Lädt alle verfügbaren Spiele aus mehreren Quellen."""
    all_rows = []

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
                    all_rows.append({
                        "date": row.get("Date", ""),
                        "season": season_str,
                        "league": FD_CO_UK_LEAGUES[league_code],
                        "home": row.get("HomeTeam", "").strip(),
                        "away": row.get("AwayTeam", "").strip(),
                        "home_goals": int(row.get("FTHG", 0) or 0),
                        "away_goals": int(row.get("FTAG", 0) or 0),
                        "ht_home": int(row.get("HTHG", 0) or 0),
                        "ht_away": int(row.get("HTAG", 0) or 0),
                        "shots_home": int(row.get("HS", 0) or 0),
                        "shots_away": int(row.get("AS", 0) or 0),
                        "corners_home": int(row.get("HC", 0) or 0),
                        "corners_away": int(row.get("AC", 0) or 0),
                        "cards_home": int(row.get("HY", 0) or 0),
                        "cards_away": int(row.get("AY", 0) or 0),
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

    # Sortieren nach Datum
    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "home", "away"]).sort_values("date").reset_index(drop=True)

    # Duplikate entfernen (same match from multiple sources)
    df["_dedup_key"] = df["home"].str.lower().str[:8] + "_" + df["away"].str.lower().str[:8] + "_" + df["date"].dt.strftime("%Y-%m-%d")
    df = df.drop_duplicates(subset=["_dedup_key"]).drop(columns=["_dedup_key"])
    df = df.reset_index(drop=True)

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
    # Schüsse/Ecken (nur football-data.co.uk — mit fillna 0 damit kein dropna-Problem)
    "avg_shots_home", "avg_shots_away", "total_shots_exp",
    "avg_corners_home", "avg_corners_away", "total_corners_exp",
    # Karten BEWUSST NICHT in FEATURE_COLS — 99.2% NaN (nur FD.co.uk, openfootball/martj42 haben keine)
    # Können später als Feature hinzukommen wenn Scraper player_match_stats befüllt ist
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

    # 🆕 Time-Series-CV Splits anpassen an Datensatzgrösse
    n_splits = min(3, max(2, len(X) // 500))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    calibrated = CalibratedClassifierCV(base_model, method="isotonic", cv=tscv)
    calibrated.fit(X, y)

    # Evaluierung auf letzten 20% (Out-of-Sample)
    split = int(len(X) * 0.8)
    X_eval, y_eval = X[split:], y[split:]
    proba = calibrated.predict_proba(X_eval)[:, 1]
    brier = brier_score_loss(y_eval, proba)
    auc = roc_auc_score(y_eval, proba)
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
# 6. HAUPTPROGRAMM
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧠 NETRATTLER ML-Training startet...")
    print(f"   Zeitstempel: {datetime.now(timezone.utc).isoformat()}")

    # Daten laden
    df = load_all_matches()

    # Features berechnen
    print("\n📊 Berechne Elo-Ratings...")
    df = compute_elo_ratings(df)
    print("📊 Berechne Form-Features...")
    df = compute_form_features(df)

    # Targets definieren
    targets = {
        "btts_model": "btts",
        "over25_model": "over25",
        "btts_ht_model": "btts_ht",
        "over15_ht_model": "over15_ht",
    }

    all_meta = {}
    for model_name, target_col in targets.items():
        model, meta = train_model(df, target_col, model_name)
        if model is None:
            print(f"   ⏭️  {model_name} übersprungen: {meta.get('reason', 'unbekannt')}")
            all_meta[model_name] = meta
            continue
        save_model_to_supabase(model, meta)
        all_meta[model_name] = meta

    print("\n" + "="*60)
    print("✅ Training abgeschlossen!")
    for name, meta in all_meta.items():
        if meta.get("skipped"):
            print(f"   {name}: ÜBERSPRUNGEN ({meta.get('reason')})")
        else:
            print(f"   {name}: AUC={meta['roc_auc']}, Brier={meta['brier_score']}")
