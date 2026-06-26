#!/usr/bin/env python3
"""
NETRATTLER Player Stats Scraper V10
===================================
Schneller, kostenloser Scraper/Updater:
- StatsBomb Open Data als stabile Basis
- baut einfache Spieler-Profile für Scoring/Props
- speichert optional in Supabase player_avg_stats
- wenn Tabelle fehlt: kein Crash, nur Warnung

Ziel: täglicher Rebuild, nicht im Main Bot Run.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def log(msg):
    print(msg, flush=True)


def sb_upsert(table: str, rows: List[Dict[str, Any]], conflict: str = "player_name") -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    headers = dict(HEADERS_SB)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}"
    r = requests.post(url, headers=headers, json=rows, timeout=40)
    if not r.ok:
        log(f"⚠️ Supabase {table} skip: {r.status_code} {r.text[:180]}")
        return 0
    return len(rows)


def load_json(url: str):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return r.json()


def build_statsbomb_profiles(max_matches: int = 60) -> List[Dict[str, Any]]:
    base = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    comps = load_json(f"{base}/competitions.json")

    # Priorität: neuere große Turniere
    wanted = []
    for c in comps:
        cname = str(c.get("competition_name", "")).lower()
        season = str(c.get("season_name", ""))
        if any(x in cname for x in ["world cup", "euro", "copa america"]):
            wanted.append(c)

    profiles: Dict[str, Dict[str, Any]] = {}
    matches_seen = 0

    for c in wanted[:6]:
        if matches_seen >= max_matches:
            break
        cid = c["competition_id"]
        sid = c["season_id"]
        try:
            matches = load_json(f"{base}/matches/{cid}/{sid}.json")
        except Exception:
            continue

        for m in matches[:20]:
            if matches_seen >= max_matches:
                break
            mid = m.get("match_id")
            try:
                events = load_json(f"{base}/events/{mid}.json")
            except Exception:
                continue

            matches_seen += 1
            for e in events:
                player = (e.get("player") or {}).get("name")
                if not player:
                    continue
                p = profiles.setdefault(player, {
                    "player_name": player,
                    "team_name": (e.get("team") or {}).get("name", ""),
                    "shots": 0,
                    "sot": 0,
                    "passes": 0,
                    "fouls_committed": 0,
                    "fouls_won": 0,
                    "cards": 0,
                    "tackles": 0,
                    "events": 0,
                })
                p["events"] += 1
                et = (e.get("type") or {}).get("name", "")
                if et == "Shot":
                    p["shots"] += 1
                    outcome = ((e.get("shot") or {}).get("outcome") or {}).get("name", "")
                    if outcome in ("Goal", "Saved", "Saved To Post"):
                        p["sot"] += 1
                elif et == "Pass":
                    p["passes"] += 1
                elif et == "Foul Committed":
                    p["fouls_committed"] += 1
                    card = ((e.get("foul_committed") or {}).get("card") or {}).get("name", "")
                    if card:
                        p["cards"] += 1
                elif et == "Foul Won":
                    p["fouls_won"] += 1
                elif et in ("Duel", "Block", "Interception"):
                    p["tackles"] += 1

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for p in profiles.values():
        ev = max(1, p["events"])
        rows.append({
            "player_name": p["player_name"],
            "team_name": p["team_name"],
            "shots_avg": round(p["shots"] / ev * 90, 3),
            "sot_avg": round(p["sot"] / ev * 90, 3),
            "passes_avg": round(p["passes"] / ev * 90, 3),
            "fouls_committed_avg": round(p["fouls_committed"] / ev * 90, 3),
            "fouls_won_avg": round(p["fouls_won"] / ev * 90, 3),
            "cards_avg": round(p["cards"] / ev * 90, 3),
            "tackles_avg": round(p["tackles"] / ev * 90, 3),
            "sample_events": ev,
            "source": "statsbomb_open_data",
            "updated_at": now,
        })

    rows.sort(key=lambda x: x["sample_events"], reverse=True)
    return rows[:1500]


def main():
    log("📊 NETRATTLER Player Stats Scraper V10 startet")
    rows = build_statsbomb_profiles(max_matches=int(os.getenv("STATSBOMB_MAX_MATCHES", "60")))
    log(f"📦 Player Profiles gebaut: {len(rows)}")
    saved = sb_upsert("player_avg_stats", rows, conflict="player_name")
    log(f"✅ Supabase gespeichert: {saved}")
    log("Fertig")


if __name__ == "__main__":
    main()
