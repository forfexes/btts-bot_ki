#!/usr/bin/env python3
"""Read-only: fehlen Wappen/Spielerfotos fuer die Tipps der letzten 2 Tage? Probe 'asset_diag'."""
import os, json, requests
from datetime import date, timedelta
U=(os.getenv("SUPABASE_URL") or "").rstrip("/"); K=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H={"apikey":K,"Authorization":f"Bearer {K}","Content-Type":"application/json"}
since=(date.today()-timedelta(days=2)).isoformat()
rows=requests.get(f"{U}/rest/v1/tips",headers=H,params={"select":"match,market,player_name,player_team","date":f"gte.{since}","limit":300},timeout=30).json()
import netrattler_stats_match_cards as c
teams=set(); players=set()
for r in rows:
    if " vs " in (r.get("match") or ""):
        a,b=r["match"].split(" vs ",1); teams|={a.strip(),b.strip()}
    if r.get("player_name"): players.add((r["player_name"],r.get("player_team") or ""))
out={"probe":"asset_diag","teams":len(teams),"players":len(players),"no_crest":[],"no_photo":[]}
for t in sorted(teams):
    try: ok=bool(c._badge_bytes(t))
    except Exception: ok=False
    if not ok: out["no_crest"].append(t)
for n,t in sorted(players)[:40]:
    try: ok=bool(c._player_photo(n,t))
    except Exception: ok=False
    if not ok: out["no_photo"].append([n,t])
print(json.dumps(out)[:3000])
requests.post(f"{U}/rest/v1/netrattler_card_diag",headers=H,json={"info":out},timeout=20)
