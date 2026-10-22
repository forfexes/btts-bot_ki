"""2-3 requests: can the free key read yesterday's fixtures + player stats (fouls/cards)?"""
import os, json, datetime as dt, requests
KEYS = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"x-apisports-key": KEYS[0]} if KEYS else {}
B = "https://v3.football.api-sports.io"


def g(p, **q):
    r = requests.get(B + p, headers=H, params=q, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


out = {"probe": "apifootball_players_probe"}
if KEYS:
    d = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    st, j = g("/fixtures", date=d)
    out["fixtures"] = {"http": st, "errors": j.get("errors"), "n": len(j.get("response") or [])}
    fin = [x for x in (j.get("response") or []) if x["fixture"]["status"]["short"] == "FT"]
    if fin:
        fid = fin[0]["fixture"]["id"]
        st, j2 = g("/fixtures/players", fixture=fid)
        out["players"] = {"http": st, "errors": j2.get("errors"), "teams": len(j2.get("response") or [])}
        try:
            p = j2["response"][0]["players"][0]
            out["sample"] = {"name_present": bool(p["player"]["name"]), "stat_keys": {k: list(v) if isinstance(v, dict) else v for k, v in p["statistics"][0].items() if k in ("games", "shots", "fouls", "cards")}}
        except Exception as e:
            out["sample_err"] = str(e)[:80]
print(json.dumps(out)[:500])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
