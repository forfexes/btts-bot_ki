#!/usr/bin/env python3
"""Read-only: which (group,type) pairs exist in the Players' stats sub-game that the strict decoder does not know,
plus operator dictionary snippets for saves/tackles/etc. Writes probe '1x_player_markets'."""
import os, re, time, json, requests
from collections import defaultdict
import netrattler_prop_sources as ps
from netrattler_1x_verified_props import MARKETS

KEYS = ["Saves", "Tackles", "Fouls Committed By", "Shots Over", "Offsides", "Assists", "Interceptions", "Shots Off", "Passes"]

def post(info):
    u=(os.getenv("SUPABASE_URL") or "").rstrip("/"); k=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if u and k:
        requests.post(f"{u}/rest/v1/netrattler_card_diag",timeout=20,headers={"apikey":k,"Authorization":f"Bearer {k}","Content-Type":"application/json"},json={"info":info})

def main():
    out={"probe":"1x_player_markets"}
    h="https://22bet.com"
    d=ps._get_json(f"{h}/service-api/LineFeed/Get1x2_VZip",params={"sports":1,"count":500,"lng":"en","mode":4,"country":1})
    games=[g for g in (d or {}).get("Value") or [] if float(g.get("S") or 0)>time.time()]
    obs=defaultdict(lambda:{"n":0,"c":[],"p":set(),"pl":set()})
    done=0
    for g in games:
        if done>=6: break
        gz=ps._get_json(f"{h}/service-api/LineFeed/GetGameZip",params={"id":g.get("I"),"lng":"en","cfview":0,"grMode":4,"country":1,"isSubGames":"true","GroupEvents":"true"})
        v=(gz or {}).get("Value") or {}
        for sg in v.get("SG") or []:
            if sg.get("TG")=="Players' stats" and not str(sg.get("PN") or "").strip():
                sub=ps._get_json(f"{h}/service-api/LineFeed/GetGameZip",params={"id":sg.get("I"),"lng":"en","GroupEvents":"true","grMode":2})
                sv=(sub or {}).get("Value") or {}
                for grp in sv.get("GE") or []:
                    for row in grp.get("E") or []:
                        for ev in (row if isinstance(row,list) else [row]):
                            if not isinstance(ev,dict): continue
                            key=(grp.get("G"),ev.get("T"))
                            if key in MARKETS: continue
                            o=obs[key]; o["n"]+=1
                            if len(o["c"])<4: o["c"].append(ev.get("C"))
                            if ev.get("P") is not None and len(o["p"])<6: o["p"].add(ev.get("P"))
                            if len(o["pl"])<2: o["pl"].add(str((ev.get("PL") or {}).get("N")))
                done+=1
                break
    out["unknown_pairs"]=sorted(([list(k),v["n"],v["c"],sorted(v["p"]),sorted(v["pl"])] for k,v in obs.items()),key=lambda x:-x[1])[:60]
    try:
        txt=requests.get("https://v2l.traincdn.com/genfiles/cms/betstemplates/betsNames_full_en.js",timeout=30).text
        out["dict_len"]=len(txt); snip={}
        names={}
        for m in re.finditer(r'"(\d+)":\{"IdG":"(\d+)","N":"([^"]*)"',txt):
            names[int(m.group(1))]=(m.group(2),m.group(3))
        out["names"]=[[k[0],k[1],names.get(k[1],("?","?"))[0],names.get(k[1],("?","?"))[1][:70],v["n"],v["c"][:2],sorted(v["p"])[:4]] for k,v in sorted(obs.items(),key=lambda kv:-kv[1]["n"])[:70]]
        for k in KEYS:
            snip[k]=[txt[max(0,m.start()-120):m.end()+80].replace("\n"," ") for m in list(re.finditer(re.escape(k),txt))[:5]]
        out["dict"]=snip
    except Exception as e:
        out["dict_err"]=str(e)[:100]
    post(out); print(json.dumps(out)[:1200])
if __name__=="__main__": main()
