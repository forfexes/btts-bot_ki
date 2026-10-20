"""Read-only: which 1xBet-platform mirrors answer the public LineFeed, and does any expose group names."""
import os, json, requests
H = {"User-Agent": "NETRATTLER-PublicSourceAudit/2.0", "Accept": "application/json"}
DOMAINS = ["megapari.com", "betandyou.com", "allyspin.com", "5gringos.com", "westace.com", "5gcasino.com",
           "spinbara.com", "posido.com", "wazamba.com", "amunra.com", "bankonbet.com", "powbet.com",
           "ivibet.com", "betify.com"]
def get(u, p=None):
    try:
        r = requests.get(u, params=p, headers=H, timeout=12)
        try: return r.status_code, r.json()
        except Exception: return r.status_code, None
    except Exception as e:
        return type(e).__name__, None
out = {"probe": "1x_clone", "rows": []}
for d in DOMAINS:
    host = "https://" + d
    st, js = get(host + "/service-api/LineFeed/Get1x2_VZip", {"sports": "1", "count": "5", "lng": "en", "mode": "4", "country": "1", "getEmpty": "true"})
    games = (js or {}).get("Value") or [] if isinstance(js, dict) else []
    row = {"d": d, "http": st, "games": len(games)}
    if games:
        st2, gj = get(host + "/service-api/LineFeed/GetGameZip", {"id": str(games[0]["I"]), "lng": "en", "GroupEvents": "true", "grMode": "2"})
        v = (gj or {}).get("Value") or {} if isinstance(gj, dict) else {}
        ge = (v.get("GE") or [{}])[0]
        row["group_keys"] = sorted(ge.keys())
        row["sg"] = [s.get("TG") for s in (v.get("SG") or [])][:6]
    out["rows"].append(row)
print(json.dumps(out)[:3000])
url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
if url and key:
    print(requests.post(url + "/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, json={"info": out}, timeout=30).status_code)
