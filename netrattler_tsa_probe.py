#!/usr/bin/env python3
"""Probe TheStatsAPI v2 player odds (anytime goalscorer). Read-only; writes counts
(no keys, no player data) to netrattler_card_diag."""
import os, json, datetime as d, requests

BASE = "https://api.thestatsapi.com/api"
keys = [k.strip() for k in (os.getenv("THESTATSAPI_KEYS") or os.getenv("THESTATSAPI_KEY") or "").split(",") if k.strip()]
out = {"probe": "thestatsapi_v2", "keys": len(keys)}


def get(path, key, **params):
    r = requests.get(BASE + path, params=params, timeout=20, headers={"Authorization": f"Bearer {key}"})
    try:
        body = r.json()
    except Exception:
        body = {}
    return r.status_code, body


key = None
key_status = []
for _k in keys:
    _st, _b = get("/v2/football/matches", _k, per_page=1)
    key_status.append(f"{_st}:{(_b.get('error') or {}).get('code', 'ok') if isinstance(_b, dict) else ''}")
    if _st == 200 and key is None:
        key = _k
out["key_status"] = key_status
if key:
    today = d.date.today()
    matches = []
    for path in ("/v2/football/matches", "/football/matches"):
        st, body = get(path, key, date_from=str(today), date_to=str(today + d.timedelta(days=2)), per_page=50)
        out[f"list{path}"] = st
        if st == 200:
            data = body.get("data") or []
            matches = data if isinstance(data, list) else []
            break
        out[f"list_err{path}"] = str((body.get("error") or {}).get("code") or body)[:80]
    out["matches"] = len(matches)
    tried = ags = books = 0
    sample_books = set()
    for m in matches[:6]:
        mid = m.get("id") or m.get("match_id")
        if not mid:
            continue
        st, body = get(f"/v2/football/matches/{mid}/odds/players", key)
        tried += 1
        out.setdefault("odds_status", []).append(st)
        for b in ((body.get("data") or {}).get("bookmakers") or []):
            books += 1
            sample_books.add(str(b.get("bookmaker")))
            for mk in b.get("markets") or []:
                if mk.get("name") == "anytime_goalscorer":
                    ags += len(mk.get("players") or [])
    out.update({"odds_tried": tried, "bookmaker_blocks": books, "anytime_goalscorer_quotes": ags,
                "bookmakers": sorted(sample_books)})
print(json.dumps(out, indent=1))
url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
sk = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
if url and sk:
    requests.post(f"{url}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=15,
                  headers={"apikey": sk, "Authorization": f"Bearer {sk}", "Content-Type": "application/json"})
