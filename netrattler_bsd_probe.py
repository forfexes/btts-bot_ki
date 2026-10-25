"""Read-only Probe fuer BSD (sports.bzzoiro.com, Lizenz erlaubt Speichern/Analyse/KI-Nutzung).
Prueft Coverage (ohne Key) und, falls BSD_API_KEY gesetzt ist, Events/Odds/Spieler-Stats.
Wenige Requests, kein Umgehen von Limits. Schreibt nur eine Diagnosezeile."""
import os, requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
KEY = os.getenv("BSD_API_KEY") or ""
BASE = "https://sports.bzzoiro.com/api/v2"


def get(path, params=None, auth=True):
    h = {"Accept": "application/json"}
    if auth and KEY:
        h["Authorization"] = f"Token {KEY}"
    try:
        r = requests.get(BASE + path, params=params, headers=h, timeout=25)
        try:
            j = r.json()
        except Exception:
            j = None
        return r.status_code, j, dict(r.headers)
    except Exception as e:
        return type(e).__name__, None, {}


def keys_of(o, n=40):
    if isinstance(o, dict):
        return sorted(o.keys())[:n]
    if isinstance(o, list) and o and isinstance(o[0], dict):
        return sorted(o[0].keys())[:n]
    return []


def main():
    out = {"probe": "bsd", "has_key": bool(KEY)}
    st, j, _ = get("/coverage/", {"sport": "football"}, auth=False)
    out["coverage"] = {"http": st, "data": (j if isinstance(j, dict) else None)}
    if KEY:
        st, j, hd = get("/events/", {"limit": 5})
        res = (j or {}).get("results") if isinstance(j, dict) else j
        ev = {"http": st, "n": len(res or []), "keys": keys_of(res), "ratelimit": {k: v for k, v in hd.items() if "limit" in k.lower() or "remaining" in k.lower()}}
        out["events"] = ev
        eid = (res or [{}])[0].get("id") if res else None
        if eid:
            for sub in ("stats", "odds", "lineups", "incidents"):
                s2, j2, _ = get(f"/events/{eid}/{sub}/")
                out[sub] = {"http": s2, "keys": keys_of(j2 if not isinstance(j2, dict) else (j2.get("results") or j2))}
        s3, j3, _ = get("/odds/", {"limit": 3})
        out["odds_list"] = {"http": s3, "keys": keys_of((j3 or {}).get("results") if isinstance(j3, dict) else j3)}
        s4, j4, _ = get("/players/", {"limit": 2})
        out["players"] = {"http": s4, "keys": keys_of((j4 or {}).get("results") if isinstance(j4, dict) else j4)}
    print(out)
    if SB and SK:
        try:
            requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=15,
                          headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                          json={"info": out})
        except Exception:
            pass


if __name__ == "__main__":
    main()
