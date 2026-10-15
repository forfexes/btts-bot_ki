#!/usr/bin/env python3
"""Read-only BetClone platform-family probe. A rendered site is NOT proof of usable odds."""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

SITES = {
    "altenar": ("rabona", "https://rabona.com/"),
    "betconstruct": ("vbet", "https://www.vbet.com/"),
    "betby": ("betfury", "https://betfury.com/"),
    "delasport": ("grandwin", "https://grandwin.bet/"),
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NETRATTLER-SourceAudit/1.0)",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
}
BLOCK = re.compile(r"captcha|cloudflare|access denied|just a moment|attention required|geoblock", re.I)


def count_structured_odds(value, depth=0):
    """Only structured, labelled numeric prices count; plain HTML/marketing claims do not."""
    if depth > 12:
        return 0
    if isinstance(value, list):
        return sum(count_structured_odds(v, depth + 1) for v in value[:300])
    if not isinstance(value, dict):
        return 0
    keys = {str(k).lower().replace("_", "") for k in value}
    price_keys = {"odds", "decimalodds", "price"}
    label_keys = {"selection", "selectionid", "outcome", "outcomeid", "market", "marketid", "name", "label"}
    count = 0
    if keys & price_keys and keys & label_keys:
        for k, v in value.items():
            if str(k).lower().replace("_", "") in price_keys:
                try:
                    if 1.01 <= float(v) <= 1000:
                        count = 1
                        break
                except (TypeError, ValueError):
                    pass
    return count + sum(count_structured_odds(v, depth + 1) for v in value.values() if isinstance(v, (dict, list)))


def probe_one(family, brand, url, timeout=12):
    result = {"platform": family, "brand": brand, "url": url, "http": 0,
              "status": "unverified", "blocked": False, "content_type": "",
              "bytes": 0, "odds_rows": 0}
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        result["http"] = response.status_code
        result["bytes"] = len(response.content)
        result["content_type"] = response.headers.get("Content-Type", "").split(";")[0].lower()
        result["final_host"] = urlparse(response.url).hostname
        body = response.text[:16000]
        result["blocked"] = response.status_code in (401, 403, 407, 429, 451) or bool(BLOCK.search(body[:3000]))
        if result["blocked"]:
            result["status"] = "blocked_or_restricted"
        elif response.status_code != 200:
            result["status"] = "http_error"
        elif "json" in result["content_type"]:
            try:
                result["odds_rows"] = count_structured_odds(response.json())
                result["status"] = "structured_odds" if result["odds_rows"] else "json_without_verified_odds"
            except (ValueError, TypeError):
                result["status"] = "invalid_json"
        elif "html" in result["content_type"]:
            result["status"] = "javascript_shell" if re.search(
                r"enable JavaScript|<div id=[\"'](?:root|app)[\"']", body, re.I
            ) else "html_only"
        else:
            result["status"] = "unsupported_content"
    except requests.RequestException as exc:
        result["status"] = "network_error"
        result["error_type"] = type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--output", default="netrattler_betclone_probe_summary.json")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(probe_one, family, *info, args.timeout): family
                for family, info in SITES.items()}
        results = {jobs[f]: f.result() for f in as_completed(jobs)}
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "public_homepage_read_only_no_automatic_integration",
              "sources": results,
              "verified_structured_odds_platforms": sum(
                  item["status"] == "structured_odds" for item in results.values())}
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, sort_keys=True)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
