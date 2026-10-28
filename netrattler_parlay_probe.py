"""Probe: ParlayAPI - gibt es Fussball-Spielerprops (Tackles/Fouls/Shots) fuer Top-5-Ligen? Nur lesende Abrufe, Key (falls vorhanden) wird nie ausgegeben."""
import os, re, json, collections, requests

KEY = os.getenv("PARLAYAPI_KEY", "")
BASE = "https://parlay-api.com"
H = {"X-API-Key": KEY} if KEY else {}
WORDS = re.compile(r"tackle|foul|shot|card", re.I)


def get(path, **params):
    try:
        r = requests.get(BASE + path, headers=H, params=params, timeout=30)
        try:
            data = r.json()
        except Exception:
            data = r.text[:200]
        return r.status_code, data
    except Exception as exc:
        return type(exc).__name__, None


def main():
    out = {"probe": "parlay_probe", "has_key": bool(KEY)}
    st, d = get("/v1/markets")
    out["markets_status"] = st
    txt = json.dumps(d)[:200000] if d is not None else ""
    out["market_hits"] = sorted(set(m.lower() for m in re.findall(r"[A-Za-z_]*(?:tackle|foul|shot|card)[A-Za-z_]*", txt, re.I)))[:60]
    st, d = get("/v1/sports")
    out["sports_status"] = st
    keys = []
    if isinstance(d, (list, dict)):
        items = d if isinstance(d, list) else d.get("data") or d.get("sports") or []
        keys = [x.get("key") if isinstance(x, dict) else str(x) for x in items]
    out["soccer_keys"] = [k for k in keys if k and str(k).startswith("soccer")][:80]
    out["n_keys"] = len(keys)
    if KEY:
        tgt = [k for k in out["soccer_keys"] if any(t in k for t in ("epl", "spain_la_liga", "germany_bundesliga", "italy_serie_a", "france_ligue_one"))][:3]
        out["props"] = {}
        for k in tgt:
            st, d = get(f"/v1/sports/{k}/props", regions="eu,uk,us")
            txt = json.dumps(d) if d is not None else ""
            mk = collections.Counter(re.findall(r'"(?:market|key|market_key)"\s*:\s*"([a-z0-9_]+)"', txt))
            out["props"][k] = {"status": st, "bytes": len(txt), "markets": dict(mk.most_common(40)), "head": txt[:300].replace(KEY, "<key>")}
    print(json.dumps(out)[:3000]); post(out)


def post(info):
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/"); k = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and k:
        try:
            requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": info},
                          headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        except Exception:
            pass


if __name__ == "__main__":
    main()
