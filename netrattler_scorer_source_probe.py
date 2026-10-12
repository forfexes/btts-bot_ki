#!/usr/bin/env python3
"""Probe: can 22bet / Betfair / AiScore be reached from Actions and do they expose
goalscorer odds? Read-only; writes one diagnostic row to netrattler_card_diag."""
import json, os, re, requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "en"}
TARGETS = {
    "aiscore_home": "https://m.aiscore.com/football",
    "betfair_exchange": "https://www.betfair.com/exchange/plus/football",
    "betfair_api": "https://ero.betfair.com/www/sports/exchange/readonly/v1/bymarket?alt=json&marketIds=1.1",
    "22bet_home": "https://22bet.com/line/football",
    "22bet_feed": "https://22bet.com/LineFeed/GetChampsZip?sport=1&lng=en&country=1&partner=151&virtualSports=true&gr=151",
    "kambi_ub": "https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football.json?lang=en_GB&market=GB",
}
KW = re.compile(r"goal\s*-?\s*scorer|anytime|to score", re.I)


def probe(url):
    try:
        r = requests.get(url, headers=UA, timeout=15)
        t = r.text or ""
        return {"http": r.status_code, "bytes": len(t), "scorer_kw": bool(KW.search(t)),
                "blocked": bool(re.search(r"captcha|cloudflare|access denied|just a moment", t[:4000], re.I))}
    except Exception as exc:
        return {"err": type(exc).__name__}


def main():
    out = {k: probe(u) for k, u in TARGETS.items()}
    out["probe"] = "scorer_sources"
    print(json.dumps(out, indent=1))
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": out})


if __name__ == "__main__":
    main()
