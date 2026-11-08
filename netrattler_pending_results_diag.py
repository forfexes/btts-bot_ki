#!/usr/bin/env python3
"""Read-only: for pending tips, check whether API-Football has a finished fixture. Writes probe 'pending_results'."""
import os, json, re, unicodedata, requests
from datetime import date
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
AK=next((k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n",",").split(",") if k.strip()),"")
def norm(s):
    s=unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]"," ",s)
def toks(s): return {t for t in norm(s).split() if len(t)>2 and t not in {"fc","cf","sc","club","the","de","ca","cd"}}
def hit(a,b):
    x,y=toks(a),toks(b); return bool(x and y and (x<=y or y<=x or len(x&y)>=max(1,min(len(x),len(y))-0) and len(x&y)>=1 and len(x&y)/min(len(x),len(y))>=.6))
rows=requests.get(f"{U}/rest/v1/tips",headers=H,params={"status":"eq.pending","date":f"lt.{date.today()}","select":"date,market,match","limit":"300"},timeout=30).json()
pairs={}
for r in rows:
    m=(r.get("match") or "").split(" / ")
    for part in m:
        if " vs " in part:
            h,a=part.split(" vs ",1); pairs.setdefault(r["date"],set()).add((h.strip(),a.strip()))
out={"probe":"pending_results","key":bool(AK),"days":{}}
fx_by_day={}
for d in sorted(pairs):
    for dd in (d,):
        try:
            resp=requests.get("https://v3.football.api-sports.io/fixtures",params={"date":dd},headers={"x-apisports-key":AK},timeout=30)
            js=resp.json(); fx_by_day[d]=js.get("response") or []; out["days"][d]={"http":resp.status_code,"fixtures":len(fx_by_day[d]),"errors":str(js.get("errors"))[:120]}
        except Exception as e:
            out["days"][d]={"err":type(e).__name__}
res=[]
for d,ps in pairs.items():
    for h,a in sorted(ps):
        f=[x for x in fx_by_day.get(d,[]) if hit(h,x["teams"]["home"]["name"]) and hit(a,x["teams"]["away"]["name"])]
        alt=[] if f else [(x["fixture"]["status"]["short"],x["teams"]["home"]["name"],x["teams"]["away"]["name"],x["league"]["name"]) for x in fx_by_day.get(d,[]) if (toks(h)&toks(x["teams"]["home"]["name"])) or (toks(a)&toks(x["teams"]["away"]["name"])) or (toks(h)&toks(x["teams"]["away"]["name"])) or (toks(a)&toks(x["teams"]["home"]["name"]))][:3]
        res.append([d,h,a,alt if not f else [(x["fixture"]["status"]["short"],x["teams"]["home"]["name"],x["teams"]["away"]["name"],x["goals"]["home"],x["goals"]["away"]) for x in f[:1]]])
out["matches"]=res
out["found"]=sum(1 for r in res if r[3]); out["total"]=len(res)
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
print(json.dumps(out)[:1200])
