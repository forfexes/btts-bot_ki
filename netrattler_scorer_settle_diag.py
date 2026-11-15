#!/usr/bin/env python3
"""Read-only: warum bleiben Torschuetzen-Tipps offen? Probe 'scorer_settle_diag'."""
import os, json, requests, unicodedata, re
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
AK=next((k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n",",").split(",") if k.strip()),"")
def get(p,q): return requests.get("https://v3.football.api-sports.io"+p,params=q,headers={"x-apisports-key":AK},timeout=30).json()
n=lambda s:re.sub(r"[^a-z]","",unicodedata.normalize("NFKD",str(s or "").lower()).encode("ascii","ignore").decode())
tips=requests.get(f"{U}/rest/v1/tips",headers=H,params={"select":"date,match,player_name","market":"eq.scorer","status":"eq.pending","date":"gte.2026-11-12"},timeout=30).json()
out={"probe":"scorer_settle_diag","rows":[]}
cache={}
for t in tips:
    h,a=(t["match"].split(" vs ")+[""])[:2]; found=None
    for day in (t["date"],):
        if day not in cache: cache[day]=get("/fixtures",{"date":day}).get("response") or []
        for f in cache[day]:
            fh,fa=f["teams"]["home"]["name"],f["teams"]["away"]["name"]
            if n(h)[:5]==n(fh)[:5] and n(a)[:5]==n(fa)[:5]: found=f
    if not found: out["rows"].append([t["player_name"],t["match"],"fixture_not_found"]); continue
    st=found["fixture"]["status"]["short"]
    ps=get("/fixtures/players",{"fixture":found["fixture"]["id"]}).get("response") or []
    hit=None
    for team in ps:
        for p in team.get("players") or []:
            pn=p["player"]["name"]
            if n(pn).endswith(n(t["player_name"].split()[-1])) or n(t["player_name"].split()[-1]) in n(pn):
                s=(p.get("statistics") or [{}])[0]; hit=[pn,(s.get("games") or {}).get("minutes"),(s.get("goals") or {}).get("total")]
    out["rows"].append([t["player_name"],t["match"],st,hit])
print(json.dumps(out)[:3500])
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
