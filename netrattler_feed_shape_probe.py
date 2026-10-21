"""Shape probe: plain GET of the two public JSON lists the sport pages load themselves.
Stores only structure + one small football sample (no secrets). Diag probe 'feed_shape'."""
import os, json, requests

URLS = {
    "gamdom_featured": "https://api.gamdom.onebittech.com/api/vaix/featured-matches",
    "gamdom_partidos": "https://api.gamdom.onebittech.com/api/partidos",
    "wild_matches": "https://sports.wild.io/api/v2/matches",
}


def shape(o, d=0):
    if d > 5:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:25]}
    if isinstance(o, list):
        return [shape(o[0], d + 1), "<%d>" % len(o)] if o else []
    return str(o)[:40]


def football(items):
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and "soccer" in json.dumps({k: it.get(k) for k in ("Deporte", "sport", "sport_name")}).lower():
            return it
    return None


def run():
    out = {"probe": "feed_shape", "res": {}}
    for name, u in URLS.items():
        try:
            r = requests.get(u, timeout=40, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            e = {"status": r.status_code, "bytes": len(r.content)}
            if r.ok:
                j = r.json()
                items = j.get("data") if isinstance(j, dict) else j
                fb = football(items)
                e["shape"] = shape(fb if fb else (items[0] if isinstance(items, list) and items else j))
                e["football_found"] = bool(fb)
                if fb:
                    mods = fb.get("Modalidades") or []
                    e["mod_names"] = [{k: str(m.get(k))[:40] for k in m if k != "Ofertas"} for m in mods[:6]]
                    e["n_mod"] = len(mods)
                    e["offers_sample"] = [(mods[0].get("Ofertas") or [])[:3]] if mods else []
            else:
                e["body"] = r.text[:120]
            out["res"][name] = e
        except Exception as ex:
            out["res"][name] = {"error": str(ex)[:150]}
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if base and key:
        requests.post(base + "/rest/v1/netrattler_card_diag", json={"info": out},
                      headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, timeout=30)
    print(json.dumps(out)[:500])


if __name__ == "__main__":
    run()
