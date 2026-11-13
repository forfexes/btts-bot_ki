#!/usr/bin/env python3
"""Read-only: wie sieht API-Football die offenen Tipps vom 12.11.? Schreibt probe 'apif_result_diag'."""
import os, json, requests
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
AK=next((k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n",",").split(",") if k.strip()),"")
def get(p,q): return requests.get("https://v3.football.api-sports.io"+p,params=q,headers={"x-apisports-key":AK},timeout=30).json()
DAY=os.getenv("DIAG_DAY","2026-11-12")
NEEDLES=["tritones","purepechas","h20","fasil","kenema","kirkos","nifas","arba","oruba","muscat","atletico nacional","once caldas","albania","finland","italy","france","curacao","panama"]
out={"probe":"apif_result_diag","day":DAY,"key":bool(AK),"hits":[],"events":{}}
fx=get("/fixtures",{"date":DAY}).get("response") or []
out["total_fixtures"]=len(fx)
for f in fx:
    names=(f["teams"]["home"]["name"]+" | "+f["teams"]["away"]["name"]).lower()
    if any(n in names for n in NEEDLES):
        out["hits"].append([f["fixture"]["id"],f["teams"]["home"]["name"],f["teams"]["away"]["name"],f["fixture"]["status"]["short"],f["goals"]["home"],f["goals"]["away"],f["league"]["name"]])
        if f["fixture"]["status"]["short"]=="FT" and any(n in names for n in ("albania","italy")):
            ev=get("/fixtures/events",{"fixture":f["fixture"]["id"]}).get("response") or []
            out["events"][str(f["fixture"]["id"])]=[[e["time"]["elapsed"],e["team"]["name"],(e.get("player") or {}).get("name"),e["type"],e["detail"]] for e in ev if e["type"]=="Goal"]
print(json.dumps(out)[:3000])
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
