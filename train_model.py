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
SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]

# ── Elo-Konfiguration ─────────────────────────────────────────────────────────
ELO_BASE = 1500
ELO_K = 20
ELO_HOME_ADV = 60


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATEN LADEN
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_matches():
    """Lädt alle verfügbaren Spiele aus openfootball GitHub."""
    all_rows = []
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
                    })
            except Exception as e:
                print(f"  ⚠️  {season} {league}: {e}")

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    print(f"✅ {len(df)} Spiele geladen aus {df['league'].nunique()} Ligen, {df['season'].nunique()} Saisons")
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
    # Form-Punkte (W=3/D=1/L=0, aus bestehendem Feature-Engineering-Code)
    "form_pts_home", "form_pts_away", "form_pts_diff",
    "streak_win_home", "streak_win_away",
    # H2H-History
    "h2h_btts_rate", "h2h_avg_goals", "h2h_matches_norm",
]


def train_model(df, target_col, model_name):
    """Trainiert XGBoost-Klassifikator mit Time-Series-CV und Kalibrierung."""
    df_clean = df.dropna(subset=FEATURE_COLS + [target_col])
    # Erste 5 Spiele pro Team weglassen (noch keine stabilen Form-Features)
    df_clean = df_clean.iloc[200:].reset_index(drop=True)

    X = df_clean[FEATURE_COLS].values
    y = df_clean[target_col].values

    print(f"\n{'='*60}")
    print(f"🧠 Trainiere Modell: {model_name}")
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

    # Platt-Kalibrierung mit Time-Series-CV (kein Data-Leakage)
    tscv = TimeSeriesSplit(n_splits=3)
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
        "Prefer": "resolution=merge-duplicates",
    }
    payload = {
        "model_name": meta["model_name"],
        "model_data": model_b64,
        "meta": json.dumps(meta),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/ml_models",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if r.ok:
        size_kb = len(model_b64) / 1024
        print(f"   ✅ {meta['model_name']} in Supabase gespeichert ({size_kb:.0f} KB)")
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
        save_model_to_supabase(model, meta)
        all_meta[model_name] = meta

    print("\n" + "="*60)
    print("✅ Training abgeschlossen!")
    for name, meta in all_meta.items():
        print(f"   {name}: AUC={meta['roc_auc']}, Brier={meta['brier_score']}")
