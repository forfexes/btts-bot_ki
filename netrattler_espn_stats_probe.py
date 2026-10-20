"""Read-only: ESPN public site API per-player match stats (the source soccerdata uses)."""
import os, json, requests
B = "https://site.api.espn.com/apis/site/v2/sports/soccer"
out = {"probe": "espn_stats"}
sb = requests.get(f"{B}/eng.1/scoreboard", params={"dates": "20261018"}, timeout=20)
out["scoreboard_http"] = sb.status_code
evs = [e for e in (sb.json().get("events") or []) if e["status"]["type"].get("completed")] if sb.ok else []
out["completed"] = len(evs)
if evs:
    s = requests.get(f"{B}/eng.1/summary", params={"event": evs[0]["id"]}, timeout=20)
    out["summary_http"] = s.status_code
    js = s.json() if s.ok else {}
    ros = js.get("rosters") or []
    out["teams"] = len(ros)
    if ros:
        p = (ros[0].get("roster") or [{}])[0]
        out["player"] = (p.get("athlete") or {}).get("displayName")
        out["stats"] = {x.get("name"): x.get("value") for x in p.get("stats") or []}
        out["players"] = sum(len(r.get("roster") or []) for r in ros)
print(json.dumps(out)[:3000])
url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
if url and key:
    print(requests.post(url + "/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, json={"info": out}, timeout=30).status_code)
