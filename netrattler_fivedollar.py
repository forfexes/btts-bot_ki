"""5DollarFootballAPI adapter. Shadow-safe; requires FIVEDOLLAR_API_KEY."""
from __future__ import annotations
import os, requests
BASE="https://api.5dollarfootballapi.com/v1"
def _get(path,params=None):
    key=os.getenv("FIVEDOLLAR_API_KEY","").strip()
    if not key:return None
    r=requests.get(BASE+path,params=params or {},headers={"Authorization":f"Bearer {key}"},timeout=15); r.raise_for_status(); return r.json()
def fixtures(status=None,include="odds"):
    p={"include":include}
    if status:p["status"]=status
    return _get("/fixtures",p)
def fixture_odds(fixture_id,market=None,bookmakers="bet365"):
    p={"bookmakers":bookmakers}
    if market:p["market"]=market
    return _get(f"/fixtures/{fixture_id}/odds",p)
def odds_history(fixture_id,market):
    return _get(f"/fixtures/{fixture_id}/odds/history",{"market":market})
