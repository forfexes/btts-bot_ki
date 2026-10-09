#!/usr/bin/env python3
"""Network smoke-test for keyless NETRATTLER bookmaker/aggregator sources.

No tips, no writes, no synthetic odds. It only reports whether public endpoints
return usable football event payloads from a GitHub Actions runner.
"""
from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict

import requests

import netrattler_prop_sources as ps

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
TIMEOUT = 10

PIN_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_KEY = os.getenv("PINNACLE_GUEST_KEY", "")


def _result(source: str, ok: bool, **extra: Any) -> Dict[str, Any]:
    return {"source": source, "ok": bool(ok), **extra}


def probe_pinnacle() -> Dict[str, Any]:
    try:
        r = requests.get(
            f"{PIN_BASE}/sports/29/matchups",
            headers={**H, "x-api-key": PIN_KEY, "Referer": "https://www.pinnacle.com/", "Origin": "https://www.pinnacle.com"},
            params={"withSpecials": "false", "brandId": "0"}, timeout=TIMEOUT,
        )
        rows = r.json() if r.ok else []
        matches = [x for x in rows if isinstance(x, dict) and x.get("type") == "matchup"] if isinstance(rows, list) else []
        return _result("pinnacle_guest", r.ok and bool(matches), status=r.status_code, matches=len(matches))
    except Exception as exc:
        return _result("pinnacle_guest", False, error=type(exc).__name__)


def probe_kambi(brand: str) -> Dict[str, Any]:
    for host in ps._KAMBI_HOSTS:
        try:
            data = ps._get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"}, timeout=TIMEOUT,
            )
            events = data.get("events") or [] if isinstance(data, dict) else []
            if events:
                return _result(f"kambi_{brand}", True, host=host, events=len(events))
        except Exception:
            continue
    return _result(f"kambi_{brand}", False, events=0)


def probe_1xbet(host: str) -> Dict[str, Any]:
    try:
        data = ps._get_json(
            f"{host}/LineFeed/Get1x2_VZip",
            params={"sports": 1, "count": 300, "lng": "en", "mode": 4, "country": 1}, timeout=TIMEOUT,
        )
        rows = data.get("Value") or [] if isinstance(data, dict) else []
        return _result(f"1xbet:{host}", bool(rows), events=len(rows))
    except Exception as exc:
        return _result(f"1xbet:{host}", False, error=type(exc).__name__)


def probe_oddspedia() -> Dict[str, Any]:
    for host in ("https://oddspedia.com", "https://www.oddspedia.com"):
        try:
            data = ps._get_json(
                f"{host}/api/v1/getMatchList",
                params={"sport": "football", "type": "upcoming", "language": "en"}, timeout=TIMEOUT,
            )
            if not isinstance(data, dict):
                continue
            raw = data.get("data") or {}
            rows = raw.get("matchList") if isinstance(raw, dict) else raw
            if isinstance(rows, dict):
                rows = rows.get("matches") or []
            rows = rows if isinstance(rows, list) else []
            if rows:
                return _result("oddspedia", True, host=host, events=len(rows))
        except Exception:
            continue
    return _result("oddspedia", False, events=0)


def main() -> int:
    results = [probe_pinnacle()]
    for brand in ("ub", "bs", "888", "nb"):
        results.append(probe_kambi(brand))
    for host in ("https://1xbet.com", "https://ind.1xbet.com", "https://melbet.com"):
        results.append(probe_1xbet(host))
    results.append(probe_oddspedia())

    payload = {"captured_at": datetime.now(timezone.utc).isoformat(), "results": results}
    with open("netrattler_quote_source_probe.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    for row in results:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    ok = sum(bool(x.get("ok")) for x in results)
    print(f"KEYLESS QUOTE SOURCES: {ok}/{len(results)} reachable with event payloads", flush=True)
    # Diagnostic probe itself should not fail the workflow because one source can
    # legitimately block a cloud IP. A zero result is still useful evidence.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
