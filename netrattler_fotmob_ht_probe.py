"""Probe FotMob matchDetails half-time representation for a few finished matches (read-only)."""
import json, os, time
import requests
import netrattler_fotmob_results as fr

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}
rows = requests.get(f"{SB}/rest/v1/match_results", headers=H, timeout=20, params={
    "source": "eq.fotmob", "match_date": "gte.2026-10-10", "select": "event_id,home_team,away_team,home_score,away_score,ht_home,ht_away",
    "home_score": "gte.2", "order": "match_date.desc", "limit": "6"}).json()
out = {"probe": "fotmob_ht_probe", "samples": []}
for r in rows:
    d = None
    for url in ("https://www.fotmob.com/api/data/matchDetails", "https://www.fotmob.com/api/matchDetails"):
        d = fr._fetch_json(url, {"matchId": r["event_id"]})
        if isinstance(d, dict) and d.get("content"):
            break
    if not isinstance(d, dict):
        out["samples"].append({"row": r, "detail": None}); continue
    facts = (d.get("content") or {}).get("matchFacts") or {}
    evs = (facts.get("events") or {}).get("events") or []
    header = d.get("header") or {}
    out["samples"].append({
        "row": r,
        "header_teams": [{k: t.get(k) for k in ("name", "score")} for t in header.get("teams") or []],
        "status_keys": sorted((header.get("status") or {}).keys())[:30],
        "halfs": (header.get("status") or {}).get("halfs"),
        "n_events": len(evs),
        "event_types": sorted({str(e.get("type")) for e in evs if isinstance(e, dict)}),
        "events": [{k: e.get(k) for k in ("type", "time", "overloadTime", "homeScore", "awayScore", "newScore", "isHome", "halfStrKey", "halfStrShort")} for e in evs if isinstance(e, dict) and str(e.get("type")).lower() in ("goal", "half")][:14],
        "parser_ht": fr.halftime_from_detail(d),
        "top_keys_facts": sorted(facts.keys())[:20],
    })
    time.sleep(0.3)
s = json.dumps(out, default=str)[:60000]
print(s[:4000])
requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20, headers={**H, "Content-Type": "application/json"}, json={"info": json.loads(s)})
