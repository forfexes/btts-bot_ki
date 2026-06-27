#!/usr/bin/env python3
import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from supabase_client import SupabaseRest

BASE = "https://fbref.com"
SLEEP_SECONDS = float(os.getenv("FBREF_SLEEP_SECONDS", "8"))
MAX_LEAGUES_ENV = int(os.getenv("FBREF_MAX_LEAGUES", "0") or "0")
ONLY_LEAGUES = [x.strip().lower() for x in os.getenv("FBREF_ONLY_LEAGUES", "").split(",") if x.strip()]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TABLES = {
    "standard": "stats_standard",
    "shooting": "stats_shooting",
    "passing": "stats_passing",
    "pass_types": "stats_passing_types",
    "gca": "stats_gca",
    "defense": "stats_defense",
    "possession": "stats_possession",
    "playing_time": "stats_playing_time",
    "misc": "stats_misc",
}

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def safe_col(x: str) -> str:
    x = str(x).strip()
    x = re.sub(r"\s+", "_", x)
    x = x.replace("%", "pct").replace("/", "_per_").replace("+", "plus")
    return x

def get_html(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=35)
            if r.status_code == 429:
                wait = SLEEP_SECONDS * attempt * 2
                log(f"429 Rate Limit – warte {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code == 403:
                raise RuntimeError("403 Forbidden. Auf GitHub Actions später erneut testen.")
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(SLEEP_SECONDS * attempt)
    raise RuntimeError(f"Download fehlgeschlagen: {url} – {last}")

def get_all_leagues() -> List[Dict[str, str]]:
    html = get_html(f"{BASE}/en/comps/")
    soup = BeautifulSoup(html, "html.parser")
    leagues = {}

    for a in soup.select('a[href*="/en/comps/"]'):
        href = a.get("href", "")
        m = re.match(r"^/en/comps/(\d+)/([^/]+)$", href)
        if not m:
            continue
        league_id, slug = m.group(1), m.group(2)
        name = a.get_text(" ", strip=True)
        if not name or len(name) < 3:
            continue
        leagues[league_id] = {
            "league_id": league_id,
            "league_name": name,
            "slug": slug,
            "url": f"{BASE}/en/comps/{league_id}/stats/{slug}-Stats",
        }

    result = list(leagues.values())
    result.sort(key=lambda x: x["league_name"])
    return result

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [safe_col(c[-1]) for c in df.columns]
    else:
        df.columns = [safe_col(c) for c in df.columns]

    if "Rk" in df.columns:
        df = df[df["Rk"].astype(str).str.lower() != "rk"]

    df = df.loc[:, ~df.columns.duplicated()].copy()
    return df

def scrape_league_tables(league: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = []
    url = league["url"]
    season = datetime.now(timezone.utc).strftime("%Y")
    scraped_at = datetime.now(timezone.utc).isoformat()

    for table_name, table_id in TABLES.items():
        try:
            log(f"  Tabelle {table_name}")
            dfs = pd.read_html(url, attrs={"id": table_id})
            if not dfs:
                continue
            df = clean_dataframe(dfs[0])

            for _, row in df.iterrows():
                raw = {}
                for k, v in row.to_dict().items():
                    if pd.isna(v):
                        raw[k] = None
                    else:
                        raw[k] = v.item() if hasattr(v, "item") else v

                player = str(raw.get("Player") or raw.get("player") or "").strip()
                squad = str(raw.get("Squad") or raw.get("squad") or "").strip()
                if not player or player.lower() == "player":
                    continue

                minutes = raw.get("Min") or raw.get("minutes") or raw.get("Playing_Time_Min")
                try:
                    minutes = float(str(minutes).replace(",", ""))
                except Exception:
                    minutes = None

                rows.append({
                    "scraped_at": scraped_at,
                    "season": season,
                    "league_id": league["league_id"],
                    "league_name": league["league_name"],
                    "table_name": table_name,
                    "player": player,
                    "squad": squad,
                    "nation": str(raw.get("Nation") or "").strip(),
                    "position": str(raw.get("Pos") or "").strip(),
                    "age": str(raw.get("Age") or "").strip(),
                    "minutes": minutes,
                    "raw": raw,
                })
        except ValueError:
            log(f"  - {table_name}: nicht vorhanden")
        except Exception as e:
            log(f"  ! {table_name}: Fehler {str(e)[:120]}")
        time.sleep(1.0)

    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-leagues", type=int, default=MAX_LEAGUES_ENV)
    parser.add_argument("--only", type=str, default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    only = ONLY_LEAGUES[:]
    if args.only:
        only += [x.strip().lower() for x in args.only.split(",") if x.strip()]

    log("Hole FBref Liga-Index")
    leagues = get_all_leagues()
    log(f"Gefundene Ligen: {len(leagues)}")

    if only:
        leagues = [l for l in leagues if any(x in l["league_name"].lower() for x in only)]
        log(f"Gefilterte Ligen: {len(leagues)}")

    if args.max_leagues and args.max_leagues > 0:
        leagues = leagues[:args.max_leagues]

    supa = None if args.dry_run else SupabaseRest()

    total = 0
    for i, league in enumerate(leagues, 1):
        log(f"[{i}/{len(leagues)}] Scrape {league['league_name']}")
        try:
            rows = scrape_league_tables(league)
            log(f"  Spielerzeilen: {len(rows)}")
            if rows and supa:
                saved = supa.upsert(
                    "fbref_player_stats",
                    rows,
                    on_conflict="season,league_id,table_name,player,squad",
                    batch_size=400,
                )
                log(f"  Supabase gespeichert: {saved}")
                total += saved
        except Exception as e:
            log(f"  FEHLER Liga {league['league_name']}: {e}")
        time.sleep(SLEEP_SECONDS)

    log(f"Fertig. Gesamt gespeichert: {total}")

if __name__ == "__main__":
    main()
