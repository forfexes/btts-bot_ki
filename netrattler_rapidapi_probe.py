"""RapidAPI 'free-api-live-football-data' probe: 2 requests only, key never printed.
Host/paths are from memory of the public listing, so we only record what comes back."""
import os, json, requests
KEY = os.getenv("RAPIDAPI_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
HOST = os.getenv("RAPIDAPI_HOST", "free-api-live-football-data.p.rapidapi.com")


def shape(o, d=0):
    if d > 3:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:12]}
    if isinstance(o, list):
        return [shape(o[0], d + 1), "<%d>" % len(o)] if o else []
    return str(o)[:40]


out = {"probe": "rapidapi_probe", "key_present": bool(KEY), "host": HOST}
if KEY:
    for name, path, q in (("root", "/", {}), ("matches_by_date", "/football-get-matches-by-date", {"date": "20261023"})):
        r = requests.get(f"https://{HOST}{path}", headers={"x-rapidapi-key": KEY, "x-rapidapi-host": HOST}, params=q, timeout=30)
        try:
            body = r.json()
        except Exception:
            body = r.text[:200]
        out[name] = {"http": r.status_code, "shape": shape(body), "limit_left": r.headers.get("x-ratelimit-requests-remaining")}
print(json.dumps(out)[:400])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
