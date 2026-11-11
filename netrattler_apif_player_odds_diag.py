#!/usr/bin/env python3
"""Read-only: which player/card/foul/tackle markets does API-Football actually quote for upcoming fixtures? Writes probe 'apif_player_odds'."""
import os, json, requests
from datetime import date, timedelta
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
AK=next((k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n",",").split(",") if k.strip()),"")
AH={"x-apisports-key":AK}
WORDS=("player","card","foul","tackle","shot","booked","assist","scorer","save","offside","corner")
def get(path,params):
    r=requests.get("https://v3.football.api-sports.io"+path,params=params,headers=AH,timeout=30); return r.json()
out={"probe":"apif_player_odds","key":bool(AK)}
cat=get("/odds/bets",{}).get("response") or []
out["catalogue"]=[ [b.get("id"),b.get("name")] for b in cat if any(w in str(b.get("name","")).lower() for w in WORDS)][:60]
fx=[]
for i in (0,1):
    fx+= (get("/fixtures",{"date":str(date.today()+timedelta(days=i))}).get("response") or [])
from netrattler_apifootball_players import PRIORITY
fx=[f for f in fx if f["fixture"]["status"]["short"]=="NS"]
fx=[f for f in fx if (f.get("league") or {}).get("id") in PRIORITY]+[f for f in fx if (f.get("league") or {}).get("id") not in PRIORITY][:10]
seen={}; checked=0
for f in fx[:70]:
    js=get("/odds",{"fixture":f["fixture"]["id"]}); checked+=1
    for it in js.get("response") or []:
        for bk in it.get("bookmakers") or []:
            for bet in bk.get("bets") or []:
                nm=str(bet.get("name",""))
                if any(w in nm.lower() for w in WORDS):
                    s=seen.setdefault(nm,{"fixtures":set(),"books":set(),"n":0})
                    s["fixtures"].add(f["fixture"]["id"]); s["books"].add(bk.get("name")); s["n"]+=len(bet.get("values") or [])
out["fixtures_ns"]=len(fx); out["checked"]=checked
out["markets"]=[{"name":k,"fixtures":len(v["fixtures"]),"books":sorted(x for x in v["books"] if x)[:5],"values":v["n"]} for k,v in sorted(seen.items(),key=lambda kv:-len(kv[1]["fixtures"]))][:40]
print(json.dumps(out)[:3000])
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
