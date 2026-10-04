"""Probe: welche Odds-/Stats-Seiten sind vom GitHub-Runner ohne API-Key erreichbar?"""
import re, sys, requests
try:
    import netrattler_health as H
except Exception:
    H = None
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en"}
URLS = [
 "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
]
def _espn_note(t):
    import json
    try:
        ev = json.loads(t)["events"][0]
        comp = ev["competitions"][0]
        o = dict((comp.get("odds") or [{}])[0]); o.pop("link", None)
        return "ODDS=" + json.dumps(o)[:900]
    except Exception as e:
        return "parse " + str(e)[:100]
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=20)
        t = r.text or ""
        odd = len(re.findall(r'"(?:odds|price|decimal)"', t))
        print(f"{r.status_code} len={len(t):>8} oddsWords={odd:>4} {u}", flush=True)
        if H: H.record("source_probe3", u[:90], len(t), odd, note=_espn_note(t), ok=(r.status_code==200 and len(t)>2000))
    except Exception as e:
        print(f"ERR {type(e).__name__} {u}", flush=True)
        if H: H.record("source_probe2", u[:90], 0, 0, note=f"ERR {type(e).__name__} {str(e)[:120]}", ok=False)
