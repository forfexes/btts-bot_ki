"""Probe: do Pinnacle (public guest feed), Smarkets, Matchbook and the 22bet platform expose FINISHED-match
results we could use for settlement? Public endpoints only, read-only, bounded. Writes one diag row."""
import json, os
from datetime import date, timedelta
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
UA = {"User-Agent": "NETRATTLER-research/1.0", "Accept": "application/json"}
PIN = os.getenv("PINNACLE_BASE", "https://guest.api.arcadia.pinnacle.com/0.1")
PH = {**UA, "x-api-key": os.getenv("PINNACLE_GUEST_KEY", "")}
y = (date.today() - timedelta(days=1)).isoformat()
out = {"probe": "results_sources"}


def tryget(name, url, **kw):
    try:
        r = requests.get(url, timeout=25, **kw)
        body = r.text[:700]
        out[name] = {"http": r.status_code, "len": len(r.text), "head": body}
        try:
            return r.json()
        except Exception:
            return None
    except Exception as e:
        out[name] = {"err": str(e)[:150]}


# Pinnacle: sport 29 = soccer; look for any settled/results style fields
js = tryget("pin_matchups", f"{PIN}/sports/29/matchups", headers=PH, params={"brandId": "0"})
if isinstance(js, list) and js:
    m = js[0]
    out["pin_keys"] = sorted(m.keys())[:40]
    mid = m.get("id")
    for nm, path in (("pin_results", f"/matchups/{mid}/results"), ("pin_related", f"/matchups/{mid}/markets/related/straight"),
                     ("pin_settlements", f"/matchups/{mid}/settlements")):
        tryget(nm, PIN + path, headers=PH)

# Smarkets settled football
js = tryget("sm_settled", "https://api.smarkets.com/v3/events/", headers=UA,
            params={"type": "football_match", "state": "settled", "limit": 5, "sort": "start_datetime,id", "start_datetime_min": y + "T00:00:00Z"})
if isinstance(js, dict) and js.get("events"):
    e = js["events"][0]
    out["sm_event"] = {k: e.get(k) for k in ("id", "name", "state", "start_datetime")}
    mk = requests.get(f"https://api.smarkets.com/v3/events/{e['id']}/markets/", headers=UA, timeout=25).json().get("markets", [])[:3]
    out["sm_markets"] = [{k: m.get(k) for k in ("id", "name", "state")} for m in mk]
    if mk:
        c = requests.get(f"https://api.smarkets.com/v3/markets/{mk[0]['id']}/contracts/", headers=UA, timeout=25).json()
        out["sm_contracts"] = json.dumps(c)[:600]

# Matchbook closed events
tryget("mb_closed", "https://api.matchbook.com/edge/rest/events", headers=UA,
       params={"sport-ids": "15", "states": "closed", "per-page": 5, "after": f"{int(__import__('time').time()) - 86400}"})

# 22bet results feed candidates
for host in ("https://22bet.com",):
    tryget("x1_result_a", f"{host}/service-api/result/web/api/v2/champs", headers=UA,
           params={"dateFrom": y, "dateTo": y, "sportId": 1, "lng": "en"})
    tryget("x1_result_b", f"{host}/service-api/result/web/api/v1/results", headers=UA,
           params={"dateFrom": y, "dateTo": y, "sportId": 1, "lng": "en"})
    tryget("x1_result_c", f"{host}/service-api/LineFeed/GetChampsZip", headers=UA,
           params={"sport": 1, "lng": "en", "country": 1, "mode": 4})

print(json.dumps(out)[:6000])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}, json={"info": out})
