#!/usr/bin/env python3
"""Import open (CC-BY-4.0) Hugging Face closing-consensus datasets into Supabase
netrattler_closing_consensus. Benchmark/CLV/calibration only: these are de-vigged
multi-bookmaker consensus probabilities, NEVER a publishable tip quote (REAL_ODDS_ONLY)."""
import io
import math
import os
import sys

import pandas as pd
import requests

UA = {"User-Agent": "NETRATTLER-HF-Closing/1.0"}
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
# dataset -> (file, default league). Extra datasets via HF_CLOSING_DATASETS="id:file:league,..."
DATASETS = [
    ("minmaxxxer/premier-league-odds-2026-27", "premier_league_2026_27_odds.parquet", "Premier League"),
    ("minmaxxxer/premier-league-closing-odds-2025-26", "premier_league_2025_26_closing_odds.parquet", "Premier League"),
    ("minmaxxxer/laliga-serie-a-bundesliga-closing-odds-2025-26", "laliga_serie_a_bundesliga_2025_26_closing_odds.parquet", ""),
]
for extra in filter(None, (os.getenv("HF_CLOSING_DATASETS") or "").split(",")):
    parts = extra.split(":")
    if len(parts) >= 2:
        DATASETS.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))

NUM = ["open_home_prob", "open_draw_prob", "open_away_prob", "close_home_prob", "close_draw_prob", "close_away_prob",
       "open_over25_prob", "close_over25_prob", "open_btts_prob", "close_btts_prob", "close_ah_line_home", "close_ah_home_prob"]
INT = ["home_goals", "away_goals", "ht_home_goals", "ht_away_goals", "bookmakers"]


def _v(x, cast):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return cast(x)
    except Exception:
        return None


def rows_for(did, fname, league):
    r = requests.get(f"https://huggingface.co/datasets/{did}/resolve/main/{fname}", headers=UA, timeout=90)
    r.raise_for_status()
    df = pd.read_parquet(io.BytesIO(r.content))
    out = []
    for x in df.to_dict(orient="records"):
        if not x.get("match_id") or not x.get("home_team"):
            continue
        row = {"source": did, "match_id": str(x["match_id"]), "league": str(x.get("league") or league or ""),
               "season": str(x.get("season") or ""), "match_date": str(x.get("date_uk") or "")[:10] or None,
               "kickoff_utc": str(x.get("kickoff_utc") or "") or None,
               "home_team": str(x["home_team"]), "away_team": str(x.get("away_team") or "")}
        for c in NUM:
            row[c] = _v(x.get(c), float)
        for c in INT:
            row[c] = _v(x.get(c), int)
        out.append(row)
    return out


def main():
    if not SB or not KEY:
        print("SUPABASE fehlt")
        return 1
    hdr = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
           "Prefer": "resolution=merge-duplicates,return=minimal"}
    total, fails = 0, 0
    for did, fname, league in DATASETS:
        try:
            rows = rows_for(did, fname, league)
        except Exception as exc:
            print(f"{did}: {type(exc).__name__} {str(exc)[:120]}")
            fails += 1
            continue
        for i in range(0, len(rows), 500):
            resp = requests.post(f"{SB}/rest/v1/netrattler_closing_consensus?on_conflict=source,match_id",
                                 headers=hdr, json=rows[i:i + 500], timeout=60)
            if not resp.ok:
                print(f"{did}: HTTP {resp.status_code} {resp.text[:160]}")
                fails += 1
                break
        else:
            total += len(rows)
            print(f"{did}: {len(rows)} Spiele")
    print(f"fertig: {total} Spiele, {fails} Fehler")
    return 0 if total and not fails else 2


if __name__ == "__main__":
    sys.exit(main())
