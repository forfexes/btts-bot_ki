#!/usr/bin/env python3
"""Free daily football match results research feed, never bookmaker odds.

Opt-in because open-matchday is marked non-commercial by its publisher.
Only uses a pinned public CSV URL. No secrets, no Telegram or DB writes.
"""
import csv
import io
import os
import requests

URL = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/ENG_1_premier-league/results_2627.csv"

def parse_csv(content):
    rows = []
    for row in csv.DictReader(io.StringIO(content)):
        if not row:
            continue
        rows.append({str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None})
    return rows

def collect():
    if os.getenv("ENABLE_OPEN_MATCHDAY", "false").lower() not in ("1", "true", "yes"):
        return []
    response = requests.get(URL, timeout=12, headers={"User-Agent": "NETRATTLER-SourceResearch/1.0"})
    response.raise_for_status()
    if len(response.content) > 4_000_000:
        raise ValueError("CSV too large")
    return parse_csv(response.text)

if __name__ == "__main__":
    import json
    try:
        rows = collect()
        print(json.dumps({"source": "open_matchday", "rows": len(rows), "fields": list(rows[0]) if rows else [], "odds": False}))
    except requests.RequestException as exc:
        print(json.dumps({"source": "open_matchday", "error": type(exc).__name__}))
