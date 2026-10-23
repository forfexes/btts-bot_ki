#!/usr/bin/env python3
"""Void tips that stayed pending for more than STALE_DAYS because no result exists in any source.

Why: a tip whose match was postponed, mis-dated or played in a league no source covers can never be
settled; leaving it 'pending' forever distorts counts.  'void' stakes nothing, adds no profit and keeps the row.
DB only (no Telegram edit).  Originals are copied once into tips_stale_void_backup (created by DDL step if missing).
Default is dry-run; set STALE_APPLY=1 to write."""
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
    if not rows or not APPLY:
        return len(rows)
    ids = [x["tip_id"] for x in rows]
    done = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        inlist = "in.(" + ",".join('"' + c.replace('"', "") + '"' for c in chunk) + ")"
        # backup first (idempotent upsert on tip_id)
        full = requests.get(f"{SB}/rest/v1/tips", headers=H, timeout=60, params={"tip_id": inlist, "select": "*"})
        # Never change a tip without a complete, verified rollback copy.
        if not full.ok:
            print("backup source fetch failed, skipping chunk", full.status_code)
            continue
        try:
            backup_rows = full.json()
        except ValueError:
            print("backup source response invalid, skipping chunk")
            continue
        if (not isinstance(backup_rows, list)
                or len(backup_rows) != len(chunk)
                or {row.get("tip_id") for row in backup_rows if isinstance(row, dict)} != set(chunk)):
            print("backup source incomplete, skipping chunk")
            continue
        b = requests.post(f"{SB}/rest/v1/tips_stale_void_backup", timeout=60,
                          headers={**H, "Prefer": "resolution=merge-duplicates,return=minimal"},
                          params={"on_conflict": "tip_id"}, json=backup_rows)
        if not b.ok:
            print("backup failed, skipping chunk", b.status_code, b.text[:120])
            continue
        u = requests.patch(f"{SB}/rest/v1/tips", headers={**H, "Prefer": "return=minimal"}, timeout=60,
                           params={"tip_id": inlist, "status": "eq.pending"},
                           json={"status": "void", "profit_units": 0})
        done += len(chunk) if u.ok else 0
    print(f"voided: {done}")
    return done


if __name__ == "__main__":
    run()
