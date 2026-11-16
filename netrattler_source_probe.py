#!/usr/bin/env python3
"""Read-only: fragt jede Datenquelle einmal ab, schreibt Probe 'source_audit' (kein Telegram)."""
import os, json, time, requests
from datetime import date
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
first=lambda n:next((k.strip() for k in (os.getenv(n) or "").replace("\n",",").split(",") if k.strip()),"")
D=date.today().isoformat(); out={"probe":"source_audit","day":D,"sources":{}}
def probe(name,fn):
    t=time.time()
    try:
        r=fn(); out["sources"][name]={"ok":bool(r[0]),"detail":str(r[1])[:90],"s":round(time.time()-t,1)}
    except Exception as e:
        out["sources"][name]={"ok":False,"detail":type(e).__name__+":"+str(e)[:70],"s":round(time.time()-t,1)}
def js(r,f): 
    try: return f(r.json())
    except Exception: return "nojson"
g=lambda u,**k: requests.get(u,timeout=15,**k)
def apif():
    r=g("https://v3.football.api-sports.io/fixtures",headers={"x-apisports-key":first("API_FOOTBALL_KEYS")},params={"date":D}); return r.ok,f"http={r.status_code} fixtures={js(r,lambda j:len(j.get('response') or []))}"
def fd():
    r=g("https://api.football-data.org/v4/matches",headers={"X-Auth-Token":first("FOOTBALL_DATA_API_KEYS")}); return r.ok,f"http={r.status_code} n={js(r,lambda j:len(j.get('matches') or []))}"
def sm():
    r=g(f"https://api.sportmonks.com/v3/football/fixtures/date/{D}",params={"api_token":first("SPORTMONKS_API_KEY")}); return r.ok,f"http={r.status_code} n={js(r,lambda j:len(j.get('data') or []))}"
def fs():
    r=g("https://api.football-data-api.com/todays-matches",params={"key":first("FOOTYSTATS_API_KEY"),"date":D}); return r.ok,f"http={r.status_code} n={js(r,lambda j:len(j.get('data') or []))}"
def allsp():
    r=g("https://apiv2.allsportsapi.com/football/",params={"met":"Fixtures","APIkey":first("ALLSPORTS_API_KEY"),"from":D,"to":D}); return r.ok,f"http={r.status_code} n={js(r,lambda j:len(j.get('result') or []))}"
def sdb():
    r=g("https://api.sportdb.dev/v1/football/fixtures",headers={"X-API-Key":first("SPORTDB_API_KEY")},params={"date":D}); return r.ok,f"http={r.status_code}"
def tsa():
    r=g("https://api.thestatsapi.com/v1/matches",headers={"Authorization":"Bearer "+first("THESTATSAPI_KEY")},params={"date":D,"per_page":5}); return r.ok,f"http={r.status_code}"
def odds():
    r=g("https://api.the-odds-api.com/v4/sports",params={"apiKey":first("ODDS_API_KEYS")}); return r.ok,f"http={r.status_code} left={r.headers.get('x-requests-remaining')}"
def pin():
    r=g("https://guest.api.arcadia.pinnacle.com/0.1/sports/29/matchups",headers={"X-API-Key":"CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"}); return r.ok,f"http={r.status_code} n={js(r,len)}"
def fm():
    r=g("https://www.fotmob.com/api/data/matches",params={"date":D.replace('-','')},headers={"User-Agent":"Mozilla/5.0"}); return r.ok,f"http={r.status_code} leagues={js(r,lambda j:len(j.get('leagues') or []))}"
def m42():
    r=g("https://raw.githubusercontent.com/martj42/international_results/master/results.csv"); return r.ok,f"http={r.status_code} lines={r.text.count(chr(10))}"
def fpl():
    r=g("https://fantasy.premierleague.com/api/bootstrap-static/"); return r.ok,f"http={r.status_code}"
def forebet():
    r=g("https://www.forebet.com/en/football-predictions",headers={"User-Agent":"Mozilla/5.0"}); return r.ok,f"http={r.status_code} bytes={len(r.content)}"
for n,f in [("api_football",apif),("football_data",fd),("sportmonks",sm),("footystats",fs),("allsports",allsp),("sportdb",sdb),("thestatsapi",tsa),("the_odds_api",odds),("pinnacle",pin),("fotmob",fm),("martj42",m42),("fpl",fpl),("forebet",forebet)]: probe(n,f)
print(json.dumps(out)[:3500])
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
