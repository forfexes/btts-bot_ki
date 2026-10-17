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


FRONTEND = "https://hu-sb2frontend-altenar2.biahosted.com/api/widget"


def _coverage(payload) -> dict:
    """Bounded coverage summary: how many football events / complete 1X2
    markets / distinct kickoff days a public widget response contains."""
    if not isinstance(payload, dict):
        return {"events": 0}
    soccer = {s.get("id") for s in payload.get("sports") or []
              if isinstance(s, dict) and str(s.get("iconName") or "") == "soccer"}
    events = [e for e in payload.get("events") or [] if isinstance(e, dict)]
    football = [e for e in events if e.get("sportId") in soccer]
    days = sorted({str(e.get("startDate") or "")[:10] for e in football if e.get("startDate")})
    m1x2 = sum(1 for m in payload.get("markets") or []
               if isinstance(m, dict) and str(m.get("headerName") or "").strip() == "1X2")
    return {"events": len(events), "football": len(football), "markets_1x2": m1x2,
            "days": days[:10], "soccer_sport_ids": sorted(x for x in soccer if x is not None)[:3]}


def run_variants() -> list:
    """Same public endpoint/params the vegas.hu page itself uses, varying
    only eventCount/timePeriod/sportId to find the widest public listing."""
    base = dict(PARAMS)
    first = requests.get(ENDPOINT, params=base, headers=HEADERS, timeout=12)
    soccer_ids = []
    try:
        soccer_ids = _coverage(first.json()).get("soccer_sport_ids") or []
    except Exception:
        pass
    sport = str(soccer_ids[0]) if soccer_ids else "0"
    variants = [
        ("top_default", "GetTopEvents", {}),
        ("top_count50", "GetTopEvents", {"eventCount": "50"}),
        ("top_count500", "GetTopEvents", {"eventCount": "500"}),
        ("top_soccer", "GetTopEvents", {"sportId": sport}),
        ("top_soccer_tp1", "GetTopEvents", {"sportId": sport, "timePeriod": "1"}),
        ("top_soccer_tp2", "GetTopEvents", {"sportId": sport, "timePeriod": "2"}),
        ("top_soccer_tp3", "GetTopEvents", {"sportId": sport, "timePeriod": "3"}),
        ("upcoming_soccer", "GetUpcoming", {"sportId": sport, "eventCount": "200"}),
        ("events_soccer", "GetEvents", {"sportId": sport}),
        ("fav_champs", "GetFavouritesChamps", {}),
    ]
    out = []
    for name, path, extra in variants:
        row = {"variant": name, "path": path}
        try:
            r = requests.get(f"{FRONTEND}/{path}", params={**base, **extra}, headers=HEADERS, timeout=12)
            row["http"] = r.status_code
            if r.status_code == 200:
                try:
                    payload = r.json()
                    row.update(_coverage(payload))
                    if isinstance(payload, dict):
                        row["keys"] = sorted(payload.keys())[:20]
                        if path == "GetEvents":
                            # Bounded schema sample so a full-list adapter
                            # can map markets/odds (values truncated).
                            from collections import Counter
                            from netrattler_altenar_schema_probe import _truncate_deep
                            mk = [m for m in payload.get("markets") or [] if isinstance(m, dict)]
                            row["n_markets"] = len(mk)
                            row["n_odds"] = len(payload.get("odds") or [])
                            row["market_names"] = Counter(
                                str(m.get("name") or m.get("headerName") or "")[:40] for m in mk
                            ).most_common(12)
                            row["market_typeids"] = Counter(m.get("typeId") for m in mk).most_common(12)
                            row["sample_market"] = _truncate_deep(mk[0]) if mk else None
                            row["sample_odd"] = _truncate_deep((payload.get("odds") or [None])[0])
                            row["sample_event"] = _truncate_deep((payload.get("events") or [None])[0])
                            row["headers_sample"] = _truncate_deep((payload.get("headers") or [None])[:3])
                            row["page"], row["pageCount"] = payload.get("page"), payload.get("pageCount")
                    elif isinstance(payload, list):
                        row["list_len"] = len(payload)
                except Exception:
                    row["non_json"] = True
        except Exception as exc:
            row["error"] = type(exc).__name__
        out.append(row)
    return out


def main() -> int:
    if os.getenv("ALTENAR_PROBE_VARIANTS", "").lower() in {"1", "true", "yes"}:
        rows = run_variants()
        print(json.dumps(rows, indent=2)[:6000])
        url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
        if url and key:
            requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                          headers={"apikey": key, "Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json={"info": {"probe": "altenar_coverage_variants", "rows": rows}})
        return 0
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
