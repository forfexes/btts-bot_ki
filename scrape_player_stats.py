#!/usr/bin/env python3
import os
import json
import time
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", "")

TABLE_NAME = "player_match_stats"


def log(msg):
    print(msg, flush=True)


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception:
        pass


def supabase_upsert(rows):
    if not rows:
        log("⚠️ Keine Rows zum Speichern")
        return 0

    if not SUPABASE_URL or not SUPABASE_KEY:
        log("❌ SUPABASE_URL oder SUPABASE_KEY fehlt")
        return 0

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?on_conflict=source,event_id,player_id,stat_name"

    total = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        r = requests.post(url, headers=headers, json=chunk, timeout=40)

        if r.ok:
            total += len(chunk)
            log(f"✅ Supabase gespeichert: {len(chunk)} Rows")
        else:
            log(f"❌ Supabase Fehler {r.status_code}: {r.text[:500]}")

    return total


def make_row(comp):
    event_id = f"{comp.get('competition_id')}_{comp.get('season_id')}"
    league = comp.get("competition_name")
    season = comp.get("season_name")

    return {
        "source": "statsbomb_open",
        "event_id": str(event_id),
        "player_id": "competition_record",
        "player_name": "COMPETITION_RECORD",
        "team": None,
        "league": league,
        "home_team": None,
        "away_team": None,
        "match_date": datetime.now(timezone.utc).isoformat(),
        "stat_name": "competition_available",
        "stat_value": 1,
        "stat_text": season,
        "raw": comp,
    }


def main():
    log("📊 NETRATTLER Player Stats TEST startet")
    log("Quelle: StatsBomb Open Data")
    log(f"SUPABASE_URL vorhanden: {'JA' if SUPABASE_URL else 'NEIN'}")
    log(f"SUPABASE_KEY vorhanden: {'JA' if SUPABASE_KEY else 'NEIN'}")

    url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json"

    try:
        r = requests.get(url, timeout=30)
        log(f"[GET] {r.status_code} {url}")

        if not r.ok:
            log("❌ StatsBomb konnte nicht geladen werden")
            return

        data = r.json()
    except Exception as e:
        log(f"❌ Download Fehler: {e}")
        return

    rows = [make_row(comp) for comp in data]
    log(f"📦 Rows gebaut: {len(rows)}")

    saved = supabase_upsert(rows)

    msg = (
        f"📊 <b>NETRATTLER Player Stats TEST</b>\n\n"
        f"Quelle: <b>StatsBomb Open Data</b>\n"
        f"Rows gebaut: <b>{len(rows)}</b>\n"
        f"Rows gespeichert: <b>{saved}</b>"
    )

    log(msg)
    send_telegram(msg)


if __name__ == "__main__":
    main()
