"""sportapi.ai probe (direct plan, 2000 req/day): finds the base URL among a few candidates (1 request each),
then reads one finished match's stats + lineups. Key never printed."""
import os, json, datetime as dt, requests
KEY = os.getenv("SPORTAPI_AI_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
BASES = ["https://api.sportapi.ai", "https://sportapi.ai/api/v1", "https://sportapi.ai/api", "https://api.sportapi.ai/v1", "https://sportapi.ai/v1"]


def shape(o, d=0):
    if d > 3:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:25]}
    if isinstance(o, list):
        return [shape(o[0], d + 1), "<%d>" % len(o)] if o else []
    return str(o)[:30]


def get(base, path):
    try:
        r = requests.get(base + path, headers={"X-Api-Key": KEY, "Accept": "application/json"}, timeout=25)
        try:
            j = r.json()
        except Exception:
            j = None
        return r, j
    except Exception as e:
        return None, {"err": type(e).__name__}


out = {"probe": "sportapiai_probe", "key_present": bool(KEY), "tries": {}}
if KEY:
    day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    base = None
    for b in BASES:
        r, j = get(b, f"/fixtures/date/{day}")
        out["tries"][b] = (r.status_code if r is not None else None)
        if r is not None and r.status_code == 200 and isinstance(j, dict) and j.get("success"):
            base, fx = b, j
            break
    out["base"] = base
    if base:
        data = fx.get("data") or []
        out["fixtures"] = {"n": len(data), "left": r.headers.get("x-ratelimit-remaining") or r.headers.get("X-RateLimit-Remaining")}
        pick = next((m for m in data if m.get("status") == "FT" and m.get("league_name") in ("Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1")), None) or next((m for m in data if m.get("status") == "FT"), None)
        if pick:
            out["match"] = f'{pick.get("home_team")} - {pick.get("away_team")} ({pick.get("league_name")})'
            for name, path in (("stats", f"/fixtures/{pick['id']}/stats"), ("lineups", f"/fixtures/{pick['id']}/lineups"), ("events", f"/fixtures/{pick['id']}/events")):
                r2, j2 = get(base, path)
                out[name] = {"http": r2.status_code if r2 is not None else None, "shape": shape(j2)}
        r3, j3 = get(base, "/players/stats")
        out["players_stats"] = {"http": r3.status_code if r3 is not None else None, "shape": shape(j3)}
print(json.dumps(out)[:500])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
