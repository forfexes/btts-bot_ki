"""SockOdds soccer/player-prop adapter. Player props require statEntityID not all/home/away."""
from __future__ import annotations
import os, requests
BASE="https://api.sockodds.com/v2"
def _get(path,params=None):
    key=os.getenv("SOCKODDS_API_KEY","").strip()
    if not key:return None
    r=requests.get(BASE+path,params=params or {},headers={"x-api-key":key},timeout=20); r.raise_for_status(); return r.json()
def events(**params):
    params.setdefault("sportID","SOCCER"); params.setdefault("oddsAvailable","true")
    return _get("/events/",params)
def players(**params): return _get("/players/",params)
def markets(**params): return _get("/markets/",params)
def player_prop_rows(event):
    out=[]
    odds=(event or {}).get("odds") or {}
    items=odds.values() if isinstance(odds,dict) else odds
    for odd in items or []:
        if not isinstance(odd,dict):continue
        ent=str(odd.get("statEntityID") or "").strip()
        if not ent or ent.lower() in {"all","home","away"}:continue
        for book,v in (odd.get("byBookmaker") or {}).items():
            if not isinstance(v,dict) or v.get("available") is False:continue
            try:dec=float(v.get("decimal") or 0)
            except:continue
            if dec<=1.01:continue
            out.append({"event":event.get("eventID",""),"player_id":ent,"market":odd.get("marketName") or odd.get("oddID"),
                        "market_id":odd.get("oddID"),"line":v.get("line") or odd.get("line"),"odds":dec,
                        "bookmaker":book,"source":"sockodds","observed_at":v.get("updatedAt") or event.get("updatedAt") or ""})
    return out
