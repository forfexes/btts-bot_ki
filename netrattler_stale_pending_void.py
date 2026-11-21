#!/usr/bin/env python3
"""Read-only audit of old NETRATTLER pending tips.

Missing a score, player statistic or a matching result feed is never proof
that the bookmaker settled a wager as VOID. This module deliberately makes
NO Supabase writes, even when an old workflow passes STALE_APPLY=1.
Only verified bookmaker cancellation/no-appearance rules are handled by
the separate evidence-based settlement pipeline.
""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}
STALE_DAYS = int(os.getenv("STALE_DAYS", "7"))
APPLY = os.getenv("STALE_APPLY", "0") == "1"


def cutoff_iso(now=None, days=STALE_DAYS):
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat()


def stale_filter(cutoff):
    return {"status": "eq.pending", "created_at": f"lt.{cutoff}"}


def run():
    if not SB or not SK:
        print("no supabase env")
        return 0
    flt = stale_filter(cutoff_iso())
    r = requests.get(f"{SB}/rest/v1/tips", headers=H, timeout=60,
                     params={**flt, "select": "tip_id,market,status,profit_units,created_at", "limit": "5000"})
    rows = r.json() if r.ok and isinstance(r.json(), list) else []
    print(f"stale pending tips (> {STALE_DAYS} days): {len(rows)} apply={APPLY}")
    if APPLY:
        print("STALE_APPLY ignored: blanket VOID is prohibited; audit only")
    # All such tips stay PENDING for subsequent source backfill. A missing
    # result cannot justify a bookmaker VOID or a fabricated zero-unit P/L.
    return len(rows)


if __name__ == "__main__":
    run()
