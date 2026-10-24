"""Which past dates can the free API-Football key read? 1 request per date, stores count + errors."""
import os, json, datetime as dt, requests
KEYS = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
out = {"probe": "apifootball_dates", "dates": {}}
if KEYS:
    for back in (1, 2, 3, 4, 6, 8):
        d = (dt.date.today() - dt.timedelta(days=back)).isoformat()
        r = requests.get("https://v3.football.api-sports.io/fixtures", headers={"x-apisports-key": KEYS[0]}, params={"date": d}, timeout=30)
        j = r.json() if r.ok else {}
        out["dates"][d] = {"http": r.status_code, "n": len(j.get("response") or []), "errors": j.get("errors")}
print(json.dumps(out)[:500])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
