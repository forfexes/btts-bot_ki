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


out = {"probe": "rapidapi_probe2", "key_present": bool(KEY), "host": HOST}
if KEY:
    for d in ("20261018", "20261017"):
        r = requests.get(f"https://{HOST}/football-get-matches-by-date", headers={"x-rapidapi-key": KEY, "x-rapidapi-host": HOST}, params={"date": d}, timeout=30)
        try:
            body = r.json()
        except Exception:
            body = {}
        ms = ((body.get("response") or {}).get("matches")) if isinstance(body, dict) else None
        ms = ms if isinstance(ms, list) else []
        out[d] = {"http": r.status_code, "n": len(ms), "sample": ms[0] if ms else str(body)[:200],
                  "limit_left": r.headers.get("x-ratelimit-requests-remaining"), "limit": r.headers.get("x-ratelimit-requests-limit")}
print(json.dumps(out)[:400])
if SB and SK:
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", json={"info": out}, timeout=20,
                  headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"})
