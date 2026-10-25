#!/usr/bin/env python3
"""Read-only The Odds API v4 key diagnosis; no odds/Telegram/DB requests."""
import os
import requests

BASE = "https://api.the-odds-api.com/v4/sports/"

def diagnose(keys, get=requests.get):
    results = []
    for index, key in enumerate(dict.fromkeys(k.strip() for k in keys.split(",") if k.strip()), 1):
        try:
            response = get(BASE, params={"apiKey": key}, timeout=12)
            payload = response.json() if response.ok else []
            sports = [s["key"] for s in payload if isinstance(s, dict) and str(s.get("key", "")).startswith("soccer_")] if isinstance(payload, list) else []
            result = {"key_number": index, "status": response.status_code, "soccer_leagues": len(sports), "soccer_sample": sports[:5], "remaining": response.headers.get("x-requests-remaining"), "used": response.headers.get("x-requests-used")}
            results.append(result)
        except requests.RequestException as exc:
            results.append({"key_number": index, "error_type": type(exc).__name__})
    return results

def main():
    raw = os.getenv("ODDS_API_KEYS") or os.getenv("ODDS_API_KEY") or ""
    keys = list(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip()))
    print("Configured unique keys:", len(keys))
    for result in diagnose(",".join(keys)):
        print("Diagnostic:", result)

if __name__ == "__main__":
    main()
