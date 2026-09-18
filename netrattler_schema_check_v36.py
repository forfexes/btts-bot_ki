#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from typing import List

import requests

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""

REQUIRED = [
    "netrattler_source_candidates",
    "netrattler_source_tests",
    "netrattler_odds_snapshots",
    "netrattler_clv_events",
    "netrattler_learning_events",
    "netrattler_learning_weights",
    "netrattler_calibration_bins",
    "netrattler_risk_state",
    "netrattler_policy_snapshots",
    "netrattler_model_registry",
    "netrattler_autolearn_models",
    "netrattler_builder_pair_models",
    "netrattler_exposure_ledger",
    "netrattler_coverage_watchdog",
    "netrattler_market_discovery",
]

def main() -> None:
    if not URL or not KEY:
        raise SystemExit("SUPABASE_URL oder SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY fehlt")

    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
    }
    missing: List[str] = []
    for table in REQUIRED:
        response = requests.get(
            f"{URL}/rest/v1/{table}",
            headers=headers,
            params={"select": "*", "limit": "1"},
            timeout=30,
        )
        if response.ok:
            print(f"SCHEMA OK {table}")
        else:
            print(f"SCHEMA FAIL {table}: {response.status_code} {response.text[:240]}")
            missing.append(table)

    if missing:
        print("MISSING TABLES:", ", ".join(missing))
        print("Run sql/netrattler_v37_self_maintenance_schema.sql in Supabase SQL Editor.")
        raise SystemExit(2)

    print(f"V37 SELF-MAINTENANCE SCHEMA CHECK OK tables={len(REQUIRED)}")

if __name__ == "__main__":
    main()
