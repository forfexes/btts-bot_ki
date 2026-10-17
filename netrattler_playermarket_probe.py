"""Bounded, read-only probe: which licensed APIs we already hold keys for expose soccer PLAYER-prop odds?

Counts only; writes one row to netrattler_card_diag. Uses documented public API endpoints with our own keys.
No evasion of any kind.
"""
import json, os
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
out = {"probe": "playermarket_probe"}


def first_key(name):
    v = os.getenv(name) or ""
    return v.split(",")[0].strip()


def get(url, **params):
    try:
        r = requests.get(url, params=params, timeout=25)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body, r.headers
    except Exception as e:
        return None, None, {"err": str(e)[:80]}


# 1) The Odds API: do soccer events list player markets?
k = first_key("ODDS_API_KEYS")
if k:
    code, sports, h = get("https://api.the-odds-api.com/v4/sports", apiKey=k)
    soccer = [s["key"] for s in (sports or []) if isinstance(s, dict) and str(s.get("key", "")).startswith("soccer_") and s.get("active")]
    out["odds_api"] = {"sports_http": code, "active_soccer_leagues": len(soccer), "remaining": h.get("x-requests-remaining") if hasattr(h, "get") else None}
    tried = []
    for sk in [x for x in soccer if x in ("soccer_epl", "soccer_germany_bundesliga", "soccer_spain_la_liga", "soccer_italy_serie_a", "soccer_uefa_champs_league")][:3]:
        c, evs, _ = get(f"https://api.the-odds-api.com/v4/sports/{sk}/events", apiKey=k)
        if not (isinstance(evs, list) and evs):
            tried.append({"sport": sk, "events_http": c, "events": 0}); continue
        eid = evs[0]["id"]
        c2, mk, _ = get(f"https://api.the-odds-api.com/v4/sports/{sk}/events/{eid}/markets", apiKey=k)
        keys = set()
        for bm in (mk or {}).get("bookmakers", []) if isinstance(mk, dict) else []:
            for m in bm.get("markets", []):
                keys.add(m.get("key"))
        tried.append({"sport": sk, "events": len(evs), "markets_http": c2, "market_keys": sorted(x for x in keys if x)[:60]})
    out["odds_api"]["tried"] = tried
else:
    out["odds_api"] = "no key"

# 2) API-Football (RapidAPI/direct): odds bets list
k2 = first_key("API_FOOTBALL_KEYS")
if k2:
    try:
        r = requests.get("https://v3.football.api-sports.io/odds/bets", headers={"x-apisports-key": k2}, timeout=25)
        bets = (r.json() or {}).get("response") or []
        names = [b.get("name") for b in bets if isinstance(b, dict)]
        out["api_football"] = {"http": r.status_code, "bets": len(names),
                               "player_like": [n for n in names if n and any(t in n.lower() for t in ("player", "shot", "foul", "tackle", "card", "scorer", "assist"))][:40]}
    except Exception as e:
        out["api_football"] = {"err": str(e)[:80]}
else:
    out["api_football"] = "no key"

print(json.dumps(out)[:3000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=15,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                  json={"info": out})
