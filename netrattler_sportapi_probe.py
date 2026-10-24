"""SportAPI (sportapi7, Sofascore data) probe: 3 requests, key never printed.
1) England scheduled events (a finished day) 2) pick a finished PL match 3) lineups with per-player stats."""
import os, json, datetime as dt, requests
KEY = os.getenv("RAPIDAPI_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
HOST = "sportapi7.p.rapidapi.com"
B = f"https://{HOST}"


def get(path):
    r = requests.get(B + path, headers={"x-rapidapi-key": KEY, "x-rapidapi-host": HOST}, timeout=30)
    try:
        body = r.json()
    except Exception:
        body = None
    return r, body


out = {"probe": "sportapi_probe", "key_present": bool(KEY)}
if KEY:
    day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    r, j = get(f"/api/v1/category/1/scheduled-events/{day}")
    evs = (j or {}).get("events") or []
    out["events"] = {"http": r.status_code, "n": len(evs), "day": day,
                     "limit": r.headers.get("x-ratelimit-requests-limit"), "left": r.headers.get("x-ratelimit-requests-remaining"),
                     "msg": str(j)[:120] if not evs else None}
    pick = None
    for e in evs:
        if (e.get("status") or {}).get("type") == "finished" and ((e.get("tournament") or {}).get("uniqueTournament") or {}).get("id") == 17:
            pick = e
            break
    if pick:
        out["event"] = f'{pick["homeTeam"]["name"]} - {pick["awayTeam"]["name"]}'
        r2, lu = get(f"/api/v1/event/{pick['id']}/lineups")
        players = []
        try:
            players = (lu["home"].get("players") or [])[:30]
        except Exception:
            pass
        keys = set()
        sample = None
        for p in players:
            st = p.get("statistics") or {}
            keys |= set(st)
            if st and not sample:
                sample = {"name": (p.get("player") or {}).get("name"), "stats": st}
        out["lineups"] = {"http": r2.status_code, "n_players": len(players), "stat_keys": sorted(keys), "sample": sample,
                          "left": r2.headers.get("x-ratelimit-requests-remaining")}
print(json.dumps(out)[:500])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
