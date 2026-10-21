import os, json, traceback, requests

def post(info):
    u = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if u and key:
        requests.post(u + "/rest/v1/netrattler_card_diag", json={"info": info}, timeout=20,
                      headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})

try:
    import netrattler_keyless_odds as k
    rows = k.collect_gamdom_platform("")
    datekeys = {}
    for u in k.GAMDOM_FEEDS:
        js, _ = k._get(u)
        for ev in (js if isinstance(js, list) else []):
            if isinstance(ev, dict) and ev.get("Deporte") == "Soccer":
                datekeys[u[-12:]] = {a: str(b)[:40] for a, b in ev.items() if any(t in a.lower() for t in ("fecha", "hora", "inicio", "time", "date", "start"))}
                break
    mk = {}
    for r in rows:
        mk[r["market"]] = mk.get(r["market"], 0) + 1
    info = {"probe": "gamdom_probe", "rows": len(rows), "markets": mk, "diag": k.KEYLESS_DIAG.get("gamdom"),
            "datekeys": datekeys, "events": len({r["match_id"] for r in rows}),
            "sample": [{x: r.get(x) for x in ("home_team", "away_team", "commence_time", "market", "selection", "odds")} for r in rows[:4]]}
except Exception:
    info = {"probe": "gamdom_probe", "error": traceback.format_exc()[-900:]}
print(info)
post(info)
