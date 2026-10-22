"""Check each API_FOOTBALL_KEYS entry against /status. Never prints/stores key values (only index + quota)."""
import os
import json
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""


def main():
    keys = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or os.getenv("API_FOOTBALL_KEY") or "").split(",") if k.strip()]
    res = []
    for i, k in enumerate(keys):
        try:
            r = requests.get("https://v3.football.api-sports.io/status", headers={"x-apisports-key": k}, timeout=25)
            j = r.json() if r.ok else {}
            resp = j.get("response") or {}
            if isinstance(resp, list):
                resp = {}
            req = resp.get("requests") or {}
            res.append({"i": i, "http": r.status_code, "errors": j.get("errors") if j.get("errors") else None,
                        "plan": (resp.get("subscription") or {}).get("plan"), "active": (resp.get("subscription") or {}).get("active"),
                        "used_today": req.get("current"), "limit_day": req.get("limit_day")})
        except Exception as e:
            res.append({"i": i, "error": type(e).__name__})
    info = {"probe": "apifootball_check", "n_keys": len(keys), "keys": res}
    print(json.dumps(info))
    if SB and KEY:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20, json={"info": info},
                      headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
