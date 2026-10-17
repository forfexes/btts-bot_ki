"""Schema probe: Smarkets public API (events -> markets -> contracts -> quotes). Read-only, bounded."""
import json, os
import requests

B = "https://api.smarkets.com/v3"
H = {"User-Agent": "Mozilla/5.0 NETRATTLER-research/1.0", "Accept": "application/json"}
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
out = {"probe": "smarkets_probe"}
g = lambda path, **p: requests.get(B + path, headers=H, params=p, timeout=25)
ev = g("/events/", type="football_match", state="upcoming", limit=200, sort="start_datetime,id")
evs = ev.json().get("events", [])
out["events"] = len(evs)
out["event_sample"] = evs[:2]
out["pagination"] = ev.json().get("pagination")
e = evs[0]
mk = g(f"/events/{e['id']}/markets/").json().get("markets", [])
want = [m for m in mk if str(m.get("market_type", {}).get("name") if isinstance(m.get("market_type"), dict) else m.get("market_type")) in ("BTTS", "OVER_UNDER", "WINNER_3_WAY", "FIRST_HALF_OVER_UNDER", "BTTS_FIRST_HALF")]
out["market_sample"] = want[:4] or mk[:4]
ids = ",".join(str(m["id"]) for m in want[:6])
if ids:
    out["contracts"] = g(f"/markets/{ids}/contracts/").json()
    out["quotes"] = g(f"/markets/{ids}/quotes/").json()
    out["last_prices"] = g(f"/markets/{ids}/last_executed_prices/").json()
s = json.dumps(out, default=str)[:60000]
print(s[:6000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                  json={"info": json.loads(s) if s.endswith("}") else {"probe": "smarkets_probe", "truncated": s[:50000]}})
