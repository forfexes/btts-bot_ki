#!/usr/bin/env python3
"""Bounded, read-only live football odds probe. No Telegram or DB writes."""
import os
import requests

BASE = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds/"

def probe(key, get=requests.get):
    if not key:
        return {"error": "missing_key"}
    try:
        response = get(BASE, params={"apiKey": key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=15)
        result = {"http_status": response.status_code, "remaining": response.headers.get("x-requests-remaining"), "used": response.headers.get("x-requests-used"), "last": response.headers.get("x-requests-last")}
        if response.ok:
            data = response.json()
            if isinstance(data, list):
                result.update({"events": len(data), "events_with_bookmakers": sum(bool(e.get("bookmakers")) for e in data if isinstance(e, dict)), "bookmaker_offers": sum(len(e.get("bookmakers") or []) for e in data if isinstance(e, dict))})
            else:
                result["response_shape"] = type(data).__name__
        else:
            result["error_type"] = "api_http_error"
        return result
    except (requests.RequestException, ValueError) as exc:
        return {"error_type": type(exc).__name__}

def main():
    raw = os.getenv("ODDS_API_KEYS") or os.getenv("ODDS_API_KEY") or ""
    keys = list(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip()))
    print("Available unique keys:", len(keys))
    if keys:
        print("One-key live EPL h2h probe:", probe(keys[0]))
    else:
        print("No API key configured")

if __name__ == "__main__":
    main()
