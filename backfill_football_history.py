#!/usr/bin/env python3
"""
NETRATTLER V13 — 475K Football History Backfill

Imports the big historical xgabora dataset into Supabase:
- football_historical_matches
- football_team_history_features
- football_history_source_health

Data source:
- xgabora/Club-Football-Match-Data-2000-2025
  raw Matches.csv + EloRatings.csv support.
"""

import os
import re
import sys
import json
import time
import math
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests
import pandas as pd


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
CHUNK_SIZE = int(os.environ.get("HISTORY_CHUNK_SIZE", "500"))
READ_CHUNK_SIZE = int(os.environ.get("HISTORY_READ_CHUNK_SIZE", "25000"))
MAX_ROWS = int(os.environ.get("HISTORY_MAX_ROWS", "0"))  # 0 = all
REQUEST_TIMEOUT = int(os.environ.get("HISTORY_REQUEST_TIMEOUT", "60"))
SLEEP_BETWEEN_CHUNKS = float(os.environ.get("HISTORY_SLEEP_BETWEEN_CHUNKS", "0.10"))

XGABORA_MATCHES_URL = os.environ.get(
    "XGABORA_MATCHES_URL",
    "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv",
)
XGABORA_ELO_URL = os.environ.get(
    "XGABORA_ELO_URL",
    "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/EloRatings.csv",
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

COUNTRY_BY_PREFIX = {
    "ARG": "Argentina", "AUT": "Austria", "BEL": "Belgium", "BRA": "Brazil",
    "CHN": "China", "DNK": "Denmark", "ENG": "England", "FIN": "Finland",
    "FRA": "France", "GER": "Germany", "GRC": "Greece", "ITA": "Italy",
    "JPN": "Japan", "MEX": "Mexico", "NLD": "Netherlands", "NOR": "Norway",
    "POL": "Poland", "PRT": "Portugal", "ROU": "Romania", "RUS": "Russia",
    "SCO": "Scotland", "ESP": "Spain", "SWE": "Sweden", "SWZ": "Switzerland",
    "TUR": "Turkey", "USA": "USA",
    "E": "England", "D": "Germany", "I": "Italy", "SP": "Spain", "F": "France",
    "N": "Netherlands", "P": "Portugal", "SC": "Scotland", "B": "Belgium",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    log(f"❌ {msg}")
    sys.exit(1)


def clean_value(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


def to_int(v: Any) -> Optional[int]:
    v = clean_value(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def to_float(v: Any) -> Optional[float]:
    v = clean_value(v)
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def to_date(v: Any) -> Optional[str]:
    v = clean_value(v)
    if v is None:
        return None
    try:
        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date().isoformat()
    except Exception:
        return None


def slug(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80]


def division_country(div: Optional[str]) -> Optional[str]:
    if not div:
        return None
    d = str(div).strip()
    for prefix in sorted(COUNTRY_BY_PREFIX.keys(), key=len, reverse=True):
        if d.upper().startswith(prefix.upper()):
            return COUNTRY_BY_PREFIX[prefix]
    return None


def season_from_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        y = int(date_str[:4])
        m = int(date_str[5:7])
        if m >= 7:
            return f"{y}/{str(y+1)[-2:]}"
        return f"{y-1}/{str(y)[-2:]}"
    except Exception:
        return None


def match_key(source: str, division: Any, date: Any, home: Any, away: Any) -> str:
    base = f"{source}|{clean_value(division)}|{to_date(date)}|{clean_value(home)}|{clean_value(away)}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:14]
    return f"{slug(str(clean_value(division) or 'na'))}_{to_date(date) or 'no-date'}_{slug(str(clean_value(home) or 'home'))}_{slug(str(clean_value(away) or 'away'))}_{h}"[:180]


def rest_upsert(table: str, rows: List[Dict[str, Any]], conflict: str) -> int:
    if not rows:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}"
    ok = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        r = requests.post(url, headers=HEADERS, data=json.dumps(chunk), timeout=REQUEST_TIMEOUT)
        if r.status_code not in (200, 201, 204):
            log(f"⚠️ UPSERT {table} {r.status_code}: {r.text[:500]}")
        else:
            ok += len(chunk)
        if SLEEP_BETWEEN_CHUNKS:
            time.sleep(SLEEP_BETWEEN_CHUNKS)
    return ok


def health(source: str, status: str, rows: int, message: str) -> None:
    row = {
        "source": source,
        "status": status,
        "rows": rows,
        "message": message[:500],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        rest_upsert("football_history_source_health", [row], "source")
    except Exception as e:
        log(f"⚠️ health error: {e}")


def map_match_row(row: Dict[str, Any]) -> Dict[str, Any]:
    date = to_date(row.get("MatchDate") or row.get("Date"))
    div = clean_value(row.get("Division") or row.get("Div"))
    home = clean_value(row.get("HomeTeam") or row.get("Home"))
    away = clean_value(row.get("AwayTeam") or row.get("Away"))

    hg = to_int(row.get("FTHome") or row.get("FTHG"))
    ag = to_int(row.get("FTAway") or row.get("FTAG"))
    hhg = to_int(row.get("HTHome") or row.get("HTHG"))
    hag = to_int(row.get("HTAway") or row.get("HTAG"))

    home_y = to_float(row.get("HomeYellow") or row.get("HY"))
    away_y = to_float(row.get("AwayYellow") or row.get("AY"))
    home_r = to_float(row.get("HomeRed") or row.get("HR"))
    away_r = to_float(row.get("AwayRed") or row.get("AR"))
    home_corners = to_float(row.get("HomeCorners") or row.get("HC"))
    away_corners = to_float(row.get("AwayCorners") or row.get("AC"))
    home_fouls = to_float(row.get("HomeFouls") or row.get("HF"))
    away_fouls = to_float(row.get("AwayFouls") or row.get("AF"))

    total_goals = None if hg is None or ag is None else hg + ag
    home_cards = (home_y or 0) + (home_r or 0) if home_y is not None or home_r is not None else None
    away_cards = (away_y or 0) + (away_r or 0) if away_y is not None or away_r is not None else None

    out = {
        "source": "xgabora_475k",
        "match_id": match_key("xgabora_475k", div, date, home, away),
        "match_date": date,
        "match_time": clean_value(row.get("MatchTime") or row.get("Time")),
        "season": season_from_date(date),
        "division": div,
        "league": div,
        "country": division_country(div),

        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "result": clean_value(row.get("FTResult") or row.get("FTR")),
        "ht_home_goals": hhg,
        "ht_away_goals": hag,
        "ht_result": clean_value(row.get("HTResult") or row.get("HTR")),

        "home_elo": to_float(row.get("HomeElo")),
        "away_elo": to_float(row.get("AwayElo")),
        "elo_diff": None,
        "form3_home": to_float(row.get("Form3Home")),
        "form5_home": to_float(row.get("Form5Home")),
        "form3_away": to_float(row.get("Form3Away")),
        "form5_away": to_float(row.get("Form5Away")),

        "home_shots": to_float(row.get("HomeShots") or row.get("HS")),
        "away_shots": to_float(row.get("AwayShots") or row.get("AS")),
        "home_sot": to_float(row.get("HomeTarget") or row.get("HST")),
        "away_sot": to_float(row.get("AwayTarget") or row.get("AST")),
        "home_fouls": home_fouls,
        "away_fouls": away_fouls,
        "home_corners": home_corners,
        "away_corners": away_corners,
        "home_yellow": home_y,
        "away_yellow": away_y,
        "home_red": home_r,
        "away_red": away_r,

        "odd_home": to_float(row.get("OddHome") or row.get("B365H")),
        "odd_draw": to_float(row.get("OddDraw") or row.get("B365D")),
        "odd_away": to_float(row.get("OddAway") or row.get("B365A")),
        "max_home": to_float(row.get("MaxHome") or row.get("MaxH")),
        "max_draw": to_float(row.get("MaxDraw") or row.get("MaxD")),
        "max_away": to_float(row.get("MaxAway") or row.get("MaxA")),
        "over25": to_float(row.get("Over25") or row.get("B365>2.5")),
        "under25": to_float(row.get("Under25") or row.get("B365<2.5")),
        "max_over25": to_float(row.get("MaxOver25") or row.get("Max>2.5")),
        "max_under25": to_float(row.get("MaxUnder25") or row.get("Max<2.5")),

        "total_goals": total_goals,
        "btts": None if hg is None or ag is None else bool(hg > 0 and ag > 0),
        "over_25_hit": None if total_goals is None else bool(total_goals > 2.5),
        "home_cards": home_cards,
        "away_cards": away_cards,
        "total_cards": None if home_cards is None and away_cards is None else (home_cards or 0) + (away_cards or 0),
        "total_corners": None if home_corners is None and away_corners is None else (home_corners or 0) + (away_corners or 0),
        "total_fouls": None if home_fouls is None and away_fouls is None else (home_fouls or 0) + (away_fouls or 0),
        "raw": {k: clean_value(v) for k, v in row.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if out["home_elo"] is not None and out["away_elo"] is not None:
        out["elo_diff"] = out["home_elo"] - out["away_elo"]
    return out


def build_feature_rows(matches: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build team features from a pandas DataFrame of normalized historical rows."""
    if matches.empty:
        return []

    rows = []
    home = pd.DataFrame({
        "team_name": matches["home_team"],
        "division": matches["division"],
        "match_date": matches["match_date"],
        "goals_for": matches["home_goals"],
        "goals_against": matches["away_goals"],
        "shots_for": matches["home_shots"],
        "shots_against": matches["away_shots"],
        "sot_for": matches["home_sot"],
        "sot_against": matches["away_sot"],
        "fouls_for": matches["home_fouls"],
        "fouls_against": matches["away_fouls"],
        "corners_for": matches["home_corners"],
        "corners_against": matches["away_corners"],
        "yellow_cards": matches["home_yellow"],
        "red_cards": matches["home_red"],
        "total_cards": matches["home_cards"],
        "btts": matches["btts"],
        "over25": matches["over_25_hit"],
        "win_home": matches["result"].eq("H"),
        "win_away": False,
        "draw": matches["result"].eq("D"),
        "elo": matches["home_elo"],
        "form3": matches["form3_home"],
        "form5": matches["form5_home"],
    })
    away = pd.DataFrame({
        "team_name": matches["away_team"],
        "division": matches["division"],
        "match_date": matches["match_date"],
        "goals_for": matches["away_goals"],
        "goals_against": matches["home_goals"],
        "shots_for": matches["away_shots"],
        "shots_against": matches["home_shots"],
        "sot_for": matches["away_sot"],
        "sot_against": matches["home_sot"],
        "fouls_for": matches["away_fouls"],
        "fouls_against": matches["home_fouls"],
        "corners_for": matches["away_corners"],
        "corners_against": matches["home_corners"],
        "yellow_cards": matches["away_yellow"],
        "red_cards": matches["away_red"],
        "total_cards": matches["away_cards"],
        "btts": matches["btts"],
        "over25": matches["over_25_hit"],
        "win_home": False,
        "win_away": matches["result"].eq("A"),
        "draw": matches["result"].eq("D"),
        "elo": matches["away_elo"],
        "form3": matches["form3_away"],
        "form5": matches["form5_away"],
    })
    both = pd.concat([home, away], ignore_index=True)
    both = both.dropna(subset=["team_name", "division"])

    metric_cols = [
        "goals_for", "goals_against", "shots_for", "shots_against", "sot_for", "sot_against",
        "fouls_for", "fouls_against", "corners_for", "corners_against",
        "yellow_cards", "red_cards", "total_cards", "btts", "over25",
        "win_home", "win_away", "draw", "elo", "form3", "form5",
    ]
    for col in metric_cols:
        both[col] = pd.to_numeric(both[col], errors="coerce")

    grouped = both.groupby(["team_name", "division"], dropna=True)
    now = datetime.now(timezone.utc).isoformat()
    for (team, div), g in grouped:
        n = int(len(g))
        if n <= 0:
            continue
        row = {
            "team_name": str(team),
            "division": str(div),
            "source": "xgabora_475k",
            "matches": n,
            "last_match_date": str(pd.to_datetime(g["match_date"], errors="coerce").max().date()) if not g["match_date"].isna().all() else None,
            "goals_for_pg": float(g["goals_for"].mean()) if g["goals_for"].notna().any() else None,
            "goals_against_pg": float(g["goals_against"].mean()) if g["goals_against"].notna().any() else None,
            "shots_for_pg": float(g["shots_for"].mean()) if g["shots_for"].notna().any() else None,
            "shots_against_pg": float(g["shots_against"].mean()) if g["shots_against"].notna().any() else None,
            "sot_for_pg": float(g["sot_for"].mean()) if g["sot_for"].notna().any() else None,
            "sot_against_pg": float(g["sot_against"].mean()) if g["sot_against"].notna().any() else None,
            "fouls_for_pg": float(g["fouls_for"].mean()) if g["fouls_for"].notna().any() else None,
            "fouls_against_pg": float(g["fouls_against"].mean()) if g["fouls_against"].notna().any() else None,
            "corners_for_pg": float(g["corners_for"].mean()) if g["corners_for"].notna().any() else None,
            "corners_against_pg": float(g["corners_against"].mean()) if g["corners_against"].notna().any() else None,
            "yellow_cards_pg": float(g["yellow_cards"].mean()) if g["yellow_cards"].notna().any() else None,
            "red_cards_pg": float(g["red_cards"].mean()) if g["red_cards"].notna().any() else None,
            "total_cards_pg": float(g["total_cards"].mean()) if g["total_cards"].notna().any() else None,
            "btts_rate": float(g["btts"].mean()) if g["btts"].notna().any() else None,
            "over25_rate": float(g["over25"].mean()) if g["over25"].notna().any() else None,
            "home_win_rate": float(g["win_home"].mean()) if g["win_home"].notna().any() else None,
            "away_win_rate": float(g["win_away"].mean()) if g["win_away"].notna().any() else None,
            "draw_rate": float(g["draw"].mean()) if g["draw"].notna().any() else None,
            "avg_elo": float(g["elo"].mean()) if g["elo"].notna().any() else None,
            "avg_form3": float(g["form3"].mean()) if g["form3"].notna().any() else None,
            "avg_form5": float(g["form5"].mean()) if g["form5"].notna().any() else None,
            "updated_at": now,
        }
        rows.append(row)
    return rows


def import_xgabora_matches() -> int:
    log("📦 475K History: xgabora Matches.csv laden...")
    imported = 0
    feature_frames = []

    try:
        chunks = pd.read_csv(XGABORA_MATCHES_URL, chunksize=READ_CHUNK_SIZE, low_memory=False)
    except Exception as e:
        health("xgabora_475k", "error", 0, f"CSV load failed: {e}")
        raise

    for idx, df in enumerate(chunks, 1):
        if MAX_ROWS and imported >= MAX_ROWS:
            break
        if MAX_ROWS:
            remaining = MAX_ROWS - imported
            df = df.head(max(0, remaining))

        records = []
        normalized_for_features = []
        for raw in df.to_dict(orient="records"):
            mapped = map_match_row(raw)
            records.append(mapped)
            normalized_for_features.append(mapped)

        ok = rest_upsert("football_historical_matches", records, "source,match_id")
        imported += ok
        feature_frames.append(pd.DataFrame(normalized_for_features))

        log(f"  ✅ Chunk {idx}: {ok} gespeichert | total {imported}")
        if len(df) == 0:
            break
        if MAX_ROWS and imported >= MAX_ROWS:
            break

    if feature_frames:
        log("🔄 Berechne team history features...")
        all_norm = pd.concat(feature_frames, ignore_index=True)
        features = build_feature_rows(all_norm)
        feat_ok = rest_upsert("football_team_history_features", features, "team_name,division,source")
        log(f"  ✅ Team Features gespeichert: {feat_ok}")

    health("xgabora_475k", "ok", imported, "Matches imported and features rebuilt")
    return imported


def import_xgabora_elo_health_only() -> int:
    """Tracks Elo source availability. Full Elo snapshots are already in match rows via HomeElo/AwayElo."""
    try:
        r = requests.get(XGABORA_ELO_URL, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            lines = max(0, len(r.text.splitlines()) - 1)
            health("xgabora_elo", "ok", lines, "EloRatings.csv reachable; match-level Elo imported via Matches.csv")
            log(f"✅ EloRatings erreichbar: ca. {lines} Zeilen")
            return lines
        health("xgabora_elo", "warn", 0, f"HTTP {r.status_code}")
        log(f"⚠️ EloRatings HTTP {r.status_code}")
        return 0
    except Exception as e:
        health("xgabora_elo", "error", 0, str(e))
        log(f"⚠️ EloRatings Fehler: {e}")
        return 0


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        fail("SUPABASE_URL oder SUPABASE_KEY fehlt")

    log("=" * 60)
    log("NETRATTLER V13 — 475K Football History Backfill")
    log("=" * 60)
    log(f"Matches URL: {XGABORA_MATCHES_URL}")
    log(f"MAX_ROWS: {'ALL' if MAX_ROWS == 0 else MAX_ROWS}")
    log(f"READ_CHUNK_SIZE: {READ_CHUNK_SIZE} | UPSERT_CHUNK_SIZE: {CHUNK_SIZE}")

    start = time.time()
    rows = import_xgabora_matches()
    import_xgabora_elo_health_only()

    elapsed = time.time() - start
    log("=" * 60)
    log(f"✅ Fertig: {rows} historical matches importiert in {elapsed/60:.1f} min")
    log("Nächster Schritt: Main Bot kann diese Tabellen für BTTS/Over/Cards/Corners Features nutzen.")
    log("=" * 60)


if __name__ == "__main__":
    main()
