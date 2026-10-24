"""sportapi.ai: print the full structure of ONE lineup player (keys only) + events types for one match. 3 requests."""
import os, json, datetime as dt, requests
KEY = os.getenv("SPORTAPI_AI_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
B = "https://sportapi.ai/api"
H = {"X-Api-Key": KEY, "Accept": "application/json"}
out = {"probe": "sportapiai_probe2"}
if KEY:
    day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    fx = requests.get(f"{B}/fixtures/date/{day}", headers=H, timeout=25).json().get("data") or []
    pick = next((m for m in fx if m.get("status") == "FT" and m.get("league_name") == "Premier League"), None)
    if pick:
        lu = requests.get(f"{B}/fixtures/{pick['id']}/lineups", headers=H, timeout=25).json().get("data") or {}
        st = (lu.get("home") or {}).get("starters") or []
        out["starter0"] = st[0] if st else None
        out["starter_keys_union"] = sorted({k for p in st for k in p})
        ev = requests.get(f"{B}/fixtures/{pick['id']}/events", headers=H, timeout=25).json().get("data") or []
        out["event_types"] = sorted({e.get("event_type") for e in ev})
        out["event0"] = ev[0] if ev else None
print(json.dumps(out)[:600])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
