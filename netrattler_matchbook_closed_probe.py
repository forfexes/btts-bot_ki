"""Probe: do closed Matchbook events expose settled runner outcomes (winner/loser)? Public API, read-only."""
import json, os, time
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
UA = {"User-Agent": "NETRATTLER-research/1.0", "Accept": "application/json"}
out = {"probe": "matchbook_closed"}
base = "https://api.matchbook.com/edge/rest/events"
combos = {
    "a": {"sport-ids": "15", "states": "closed", "per-page": 5, "after": int(time.time()) - 86400, "include-markets": "true", "include-runners": "true"},
    "b": {"sport-ids": "15", "states": "closed", "per-page": 5, "after": int(time.time()) - 86400, "include-prices": "false", "include-event-participants": "true", "exchange-type": "back-lay", "odds-type": "DECIMAL"},
}
for k, p in combos.items():
    try:
        r = requests.get(base, params=p, headers=UA, timeout=25)
        js = r.json() if r.ok else {}
        evs = js.get("events", [])
        e0 = evs[0] if evs else {}
        mk = (e0.get("markets") or [])[:2]
        out[k] = {"http": r.status_code, "events": len(evs), "total": js.get("total"), "event_keys": sorted(e0.keys()),
                  "markets": [{"name": m.get("name"), "status": m.get("status"),
                               "runners": [{"n": x.get("name"), "status": x.get("status"), "result": x.get("result"), "keys": sorted(x.keys())} for x in (m.get("runners") or [])[:3]]} for m in mk]}
    except Exception as e:
        out[k] = {"err": str(e)[:150]}
# direct event fetch
try:
    r = requests.get(base, params={"sport-ids": "15", "states": "closed", "per-page": 1, "after": int(time.time()) - 86400}, headers=UA, timeout=25)
    eid = r.json()["events"][0]["id"]
    r2 = requests.get(f"{base}/{eid}", params={"include-prices": "false"}, headers=UA, timeout=25)
    out["single"] = {"http": r2.status_code, "head": r2.text[:1500]}
    r3 = requests.get(f"{base}/{eid}/markets", params={"include-prices": "false"}, headers=UA, timeout=25)
    out["single_markets"] = {"http": r3.status_code, "head": r3.text[:2000]}
except Exception as e:
    out["single_err"] = str(e)[:150]
print(json.dumps(out)[:6000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}, json={"info": out})
