#!/usr/bin/env python3
"""Retention fuer odds_history: Live-Quoten aelter als N Tage (Standard 20) loeschen.

Historische Quelle football_data_co_uk bleibt unangetastet (Trainingsdaten).
Loescht tageweise, damit REST-Requests nicht in Timeouts laufen.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import requests

RETENTION_DAYS = int(os.getenv("NETRATTLER_ODDS_RETENTION_DAYS", "20"))
LIVE_SOURCES = ("kambi", "pinnacle", "bwin", "1xbet_platform", "matchbook",
                "football_data", "espn", "altenar_platform", "the_odds_api")


def cutoff(today: date | None = None, days: int = RETENTION_DAYS) -> str:
    return ((today or date.today()) - timedelta(days=days)).isoformat()


def main() -> int:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not url or not key:
        print("SUPABASE credentials fehlen")
        return 1
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "return=minimal"}
    limit = cutoff()
    sources = ",".join(LIVE_SOURCES)
    deleted_days = 0
    for offset in range(RETENTION_DAYS + 1, RETENTION_DAYS + 61):
        day = (date.today() - timedelta(days=offset)).isoformat()
        r = requests.delete(
            f"{url}/rest/v1/odds_history", headers=headers, timeout=60,
            params={"match_date": f"eq.{day}", "source": f"in.({sources})"},
        )
        if r.status_code not in (200, 204):
            print(f"{day}: HTTP {r.status_code} {r.text[:120]}")
            continue
        deleted_days += 1
    print(f"retention: Tage vor {limit} bereinigt (geprueft {deleted_days})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
