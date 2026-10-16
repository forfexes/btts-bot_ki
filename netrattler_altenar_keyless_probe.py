#!/usr/bin/env python3
"""Bounded test: is Altenar's public GetTopEvents widget endpoint reachable
with a plain keyless HTTP GET, like the existing 1xBet/bwin/matchbook
collectors in netrattler_keyless_odds.py, instead of a full browser session?

Observed via the already-audited public Vegas.hu homepage render (see
netrattler_altenar_schema_probe.py): the browser's own JS makes an
unauthenticated GET to

    https://hu-sb2frontend-altenar2.biahosted.com/api/widget/GetTopEvents
    ?culture=hu-HU&timezoneOffset=-300&integration=vegas.hu&deviceType=1
    &numFormat=hu-HU&countryCode=&eventCount=0&sportId=0&timePeriod=0

"integration=vegas.hu" is the operator's own public widget brand id (the
same kind of value already hardcoded for other brands elsewhere in this
project), not a credential. No bypass, no stealth, no auth header, no
cookies: a single plain GET with a descriptive User-Agent, exactly what
the public page's own browser already does unauthenticated.

This script ONLY reports reachability/shape diagnostics to
netrattler_card_diag (probe='altenar_keyless_probe'). It does not write to
odds_history and is not wired into any production path.
"""
from __future__ import annotations

import json
import os

import requests

from netrattler_altenar_schema_probe import describe_top_level_arrays, sniff

ENDPOINT = "https://hu-sb2frontend-altenar2.biahosted.com/api/widget/GetTopEvents"
PARAMS = {
    "culture": "hu-HU",
    "timezoneOffset": "-300",
    "integration": "vegas.hu",
    "deviceType": "1",
    "numFormat": "hu-HU",
    "countryCode": "",
    "eventCount": "0",
    "sportId": "0",
    "timePeriod": "0",
}
HEADERS = {
    "User-Agent": "NETRATTLER-PublicSourceAudit/2.0 (+https://github.com/forfexes/btts-bot_ki)",
    "Accept": "application/json",
    "Accept-Language": "en,en-US;q=0.8",
}


def run() -> dict:
    result = {"endpoint": ENDPOINT, "status": "not_checked"}
    try:
        r = requests.get(ENDPOINT, params=PARAMS, headers=HEADERS, timeout=12)
    except Exception as exc:
        result["status"] = "request_error"
        result["error_type"] = type(exc).__name__
        return result
    result["http"] = r.status_code
    result["bytes"] = len(r.content or b"")
    if r.status_code != 200:
        result["status"] = "http_error"
        return result
    try:
        payload = r.json()
    except Exception:
        result["status"] = "non_json_response"
        return result
    sniffed = sniff(payload)
    arrays = describe_top_level_arrays(payload)
    result["status"] = "ok_keyless_reachable" if (sniffed["shapes"] or arrays) else "ok_but_empty_payload"
    result["shapes"] = sniffed["shapes"]
    result["array_keys_present"] = sorted(arrays.keys())
    result["event_count"] = len(payload.get("events") or []) if isinstance(payload, dict) else None
    result["sample_event"] = arrays.get("events", [None])[0] if arrays.get("events") else None
    return result


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2)[:4000])
    SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/netrattler_card_diag", timeout=15,
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                json={"info": {"probe": "altenar_keyless_probe", **result}},
            )
        except Exception as exc:
            print("Supabase write failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
