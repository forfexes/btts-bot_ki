"""Odds-API.io probe (<=5 requests, key never printed): events, bookmakers, one event's odds incl. Bet365 market names."""
import os, json, requests
KEY = os.getenv("ODDSAPIIO_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
B = "https://api.odds-api.io/v3"


def get(path, **q):
    q["apiKey"] = KEY
    r = requests.get(B + path, params=q, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def shape(o, d=0):
    if d > 3:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:14]}
    if isinstance(o, list):
        return [shape(o[0], d + 1), "<%d>" % len(o)] if o else []
    return str(o)[:40]


out = {"probe": "oddsapiio_probe", "key_present": bool(KEY)}
if KEY:
    st, ev = get("/events", sport="football", status="pending")
    out["events"] = {"http": st, "shape": shape(ev)}
    lst = ev if isinstance(ev, list) else (ev or {}).get("data") if isinstance(ev, dict) else None
    eid = None
    for e in lst or []:
        ln = ((e.get("league") or {}).get("name") or "").lower()
        if any(t in ln for t in ("premier league", "la liga", "bundesliga", "serie a", "ligue 1", "champions league")) and "u19" not in ln and "u21" not in ln and "women" not in ln:
            eid = e.get("id")
            out["odds_event"] = f'{e.get("home")} - {e.get("away")} ({(e.get("league") or {}).get("name")})'
            break
    st, se = get("/events", sport="football", status="settled")
    sl = se if isinstance(se, list) else []
    out["settled"] = {"http": st, "n": len(sl), "dates": sorted({(x.get("date") or "")[:10] for x in sl if isinstance(x, dict)})[:12], "has_scores": bool(sl and sl[0].get("scores"))}
    st, bk = get("/bookmakers")
    out["bookmakers"] = {"http": st, "n": len(bk) if isinstance(bk, list) else None, "names": [b.get("name") if isinstance(b, dict) else b for b in (bk or [])][:40] if isinstance(bk, list) else shape(bk)}
    if eid:
        st, od = get("/odds", eventId=eid, bookmakers="Bet365")
        mk = []
        try:
            for bm, mkts in (od.get("bookmakers") or {}).items():
                mk = sorted({m.get("name") for m in mkts})[:80]
        except Exception:
            pass
        out["odds"] = {"http": st, "shape": shape(od), "markets": mk}
        try:
            first = next(iter((od.get("bookmakers") or {}).values()))
            out["odds"]["sample_market"] = shape(first[:2] if isinstance(first, list) else first)
        except Exception:
            pass
print(json.dumps(out)[:400])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
