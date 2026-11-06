#!/usr/bin/env python3
"""Read-only: trace WHY fetch_1xbet_player_props returns 0 rows in production.
Uses the bot's own _get_json (same transport) on real fixtures; writes probe '1x_fetch_diag'."""
import os, time, json, requests
from collections import Counter
import netrattler_prop_sources as ps

def post(info):
    u=(os.getenv("SUPABASE_URL") or "").rstrip("/"); k=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if u and k:
        requests.post(f"{u}/rest/v1/netrattler_card_diag",timeout=15,headers={"apikey":k,"Authorization":f"Bearer {k}","Content-Type":"application/json"},json={"info":info})

def main():
    out={"probe":"1x_fetch_diag","hosts":{}}
    stages=Counter(); samples=[]
    for host in ps._1X_HOSTS[:3]:
        d=ps._get_json(f"{host}/service-api/LineFeed/Get1x2_VZip",params={"sports":1,"count":500,"lng":"en","mode":4,"country":1})
        vals=(d or {}).get("Value") or []
        out["hosts"][host]={"list_ok":bool(d),"n":len(vals)}
        if not vals: continue
        for g in vals[:400]:
            if len(samples)>=10: break
            if float(g.get("S") or 0)<=time.time(): continue
            eid=g.get("I") or g.get("CI")
            gz=ps._get_json(f"{host}/service-api/LineFeed/GetGameZip",params={"id":eid,"lng":"en","cfview":0,"grMode":4,"country":1,"isSubGames":"true","GroupEvents":"true"})
            v=(gz or {}).get("Value") or {}
            sgs=[(s.get("TG"),str(s.get("PN") or ""),s.get("I")) for s in v.get("SG") or []]
            ps_sg=[s for s in sgs if s[0]=="Players' stats"]
            row={"m":f"{g.get('O1')} v {g.get('O2')}","gz":bool(gz),"n_sg":len(sgs),"ps_sg":len(ps_sg)}
            if ps_sg:
                sub=ps._get_json(f"{host}/service-api/LineFeed/GetGameZip",params={"id":ps_sg[0][2],"lng":"en","GroupEvents":"true","grMode":2})
                sv=(sub or {}).get("Value") or {}
                from netrattler_1x_verified_props import decode_player_props
                row["sub_ok"]=bool(sub); row["sub_TG"]=sv.get("TG"); row["sub_ge"]=len(sv.get("GE") or [])
                row["teams_eq"]=(sv.get("O1"),sv.get("O2"))==(v.get("O1"),v.get("O2"))
                row["decoded"]=len(decode_player_props(v,sv))
            samples.append(row)
        if samples: break
    out["samples"]=samples
    variants={}
    h="https://22bet.com"
    for name,prm in {"count2000":{"sports":1,"count":2000,"lng":"en","mode":4,"country":1},
                     "nomode":{"sports":1,"count":2000,"lng":"en","country":1},
                     "mode1":{"sports":1,"count":2000,"lng":"en","mode":1,"country":1},
                     "gr":{"sports":1,"count":2000,"lng":"en","mode":4,"country":1,"getEmpty":"true","partner":1}}.items():
        d=ps._get_json(f"{h}/service-api/LineFeed/Get1x2_VZip",params=prm)
        variants[name]=len((d or {}).get("Value") or [])
    ch=ps._get_json(f"{h}/service-api/LineFeed/GetChampsZip",params={"sport":1,"lng":"en","country":1,"virtualSports":"true","groupChamps":"true"})
    cv=(ch or {}).get("Value") or []
    variants["champs"]=len(cv)
    if cv:
        c0=cv[0]; variants["champ_keys"]=list(c0.keys())[:12]
        cid=c0.get("LI") or c0.get("I")
        d=ps._get_json(f"{h}/service-api/LineFeed/Get1x2_VZip",params={"sports":1,"champs":cid,"count":200,"lng":"en","mode":4,"country":1})
        variants["by_champ_n"]=len((d or {}).get("Value") or [])
    out["variants"]=variants
    from netrattler_identity_hub import normalize_team_name as nt
    out["norm"]={x:nt(x) for x in ["Borussia Dortmund","Dortmund","RasenBallsport Leipzig","RB Leipzig","1. FSV Mainz 05","Mainz","Bayern Munich","Bayern München","Elversberg","SV Elversberg","Leeds United","Leeds"]}
    post(out); print(json.dumps(out)[:1500])

if __name__=="__main__": main()
