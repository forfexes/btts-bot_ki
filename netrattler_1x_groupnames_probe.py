#!/usr/bin/env python3
"""Find the public dictionary that names 1xBet-family bet groups (G) /
event types (T), so player-prop groups can be mapped from evidence
instead of guessing. Read-only GETs of candidate public front-end files;
records only status, size and a few key/sample entries."""
from __future__ import annotations

import json
import os

import requests

HOST = "https://22bet.com"
HEADERS = {"User-Agent": "NETRATTLER-PublicSourceAudit/2.0 (+https://github.com/forfexes/btts-bot_ki)",
           "Accept": "application/json, */*"}
CANDIDATES = [
    "/service-api/LineFeed/GetGroupsZip?lng=en",
    "/service-api/LineFeed/GetEventsGroupsZip?lng=en",
    "/service-api/LineFeed/GetGroupsNames?lng=en",
    "/genfiles/cms/betstemplates/betsModelsEn.json",
    "/genfiles/cms/betstemplates/en.json",
    "/sys/LineFeed/GetGroups?lng=en",
    "/service-api/main-line-feed/v1/eventGroups?lng=en&ref=151",
    "/service-api/main-line-feed/v1/groups?lng=en&ref=151",
    "/service-api/LineFeed/GetTypesZip?lng=en",
]
INTEREST = (117, 118, 1156, 1158, 2468, 2470, 2487, 3091, 3093, 3095, 3097, 3241, 3243, 737, 765, 2728)


def main() -> int:
    out = []
    for path in CANDIDATES:
        row = {"path": path}
        try:
            r = requests.get(HOST + path, headers=HEADERS, timeout=15)
            row["http"], row["bytes"] = r.status_code, len(r.content or b"")
            row["ctype"] = r.headers.get("content-type", "")[:40]
            if r.status_code == 200:
                try:
                    js = r.json()
                    row["type"] = type(js).__name__
                    if isinstance(js, dict):
                        row["keys"] = list(js.keys())[:15]
                    text = json.dumps(js, ensure_ascii=False)
                    hits = {}
                    for gid in INTEREST:
                        i = text.find(f'"G": {gid},')
                        if i < 0:
                            i = text.find(f'"{gid}"')
                        if i >= 0:
                            hits[gid] = text[max(0, i - 80): i + 160]
                    row["interest_hits"] = hits
                    row["head"] = text[:400]
                except Exception:
                    row["head"] = r.text[:300]
        except Exception as exc:
            row["error"] = type(exc).__name__
        out.append(row)
    print(json.dumps(out, indent=2, ensure_ascii=False)[:6000])
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": {"probe": "x1_groupnames_probe", "rows": out}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
