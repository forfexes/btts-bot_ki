"""Shape probe for footballdata.io (free plan, 1,000 req/month): ~8 requests, no key output.
Stores structure only (keys, a few sample values) in diag probe 'footballdata_io_probe'."""
import os
import json
import requests

BASE = "https://footballdata.io/api/v1"
KEY = os.getenv("FOOTBALLDATA_IO_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""


def shape(o, d=0):
    if d > 4:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:22]}
    if isinstance(o, list):
        return [shape(o[0], d + 1), "<%d>" % len(o)] if o else []
    return str(o)[:30]


def get(path):
    r = requests.get(BASE + path, headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"}, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = None
    return r.status_code, j


def first_list(j):
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        for v in j.values():
            if isinstance(v, list) and v:
                return v
            if isinstance(v, dict):
                x = first_list(v)
                if x:
                    return x
    return []


def main():
    out = {"probe": "footballdata_io_probe", "key_present": bool(KEY)}
    if KEY:
        for name, path in (("usage", "/account/usage"), ("fixtures_today", "/fixtures/today"), ("results", "/fixtures/results")):
            st, j = get(path)
            out[name] = {"http": st, "shape": shape(j)}
        st, j = get("/fixtures/results")
        items = first_list(j)
        mid = None
        if items and isinstance(items[0], dict):
            mid = items[0].get("id") or items[0].get("match_id")
        out["match_id_found"] = bool(mid)
        if mid:
            for name, path in (("match_stats", f"/matches/{mid}/stats"), ("match_odds", f"/matches/{mid}/odds")):
                st, j = get(path)
                out[name] = {"http": st, "shape": shape(j)}
    print(json.dumps(out)[:600])
    if SB and SK:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20, json={"info": out},
                      headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
