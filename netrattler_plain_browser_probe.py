"""Read-only, plain (no stealth, no proxy) Chromium visits.
Part 1: status/title for domains that returned 403 to requests -> no workaround if still blocked.
Part 2: on 22bet (HTTP 200) load one football match page and list which JSON responses
contain market-name words (foul/tackle/...), to locate the public name dictionary for bet groups."""
import os, re, json, requests
from playwright.sync_api import sync_playwright

BLOCKED = ["allyspin.com", "5gringos.com", "westace.com", "spinbara.com", "posido.com", "wazamba.com",
           "amunra.com", "bankonbet.com", "powbet.com", "5gcasino.com", "ivibet.com", "betify.com"]
WORDS = ("foul", "tackle", "offside", "shots on target", "passes")

def main():
    out = {"probe": "plain_browser", "sites": [], "dict_hits": []}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for d in BLOCKED:
            pg = b.new_page()
            try:
                r = pg.goto("https://" + d + "/", timeout=20000, wait_until="domcontentloaded")
                out["sites"].append({"d": d, "status": r.status if r else None, "title": (pg.title() or "")[:60]})
            except Exception as e:
                out["sites"].append({"d": d, "error": type(e).__name__})
            pg.close()
        pg = b.new_page()
        seen = []
        def on_resp(resp):
            try:
                if "json" in (resp.headers.get("content-type") or "") and len(seen) < 80:
                    t = resp.text()
                    low = t.lower()
                    hits = [w for w in WORDS if w in low]
                    if hits:
                        seen.append({"url": re.sub(r"\?.*", "", resp.url)[:140], "bytes": len(t), "hits": hits,
                                     "sample": low[max(0, low.find(hits[0]) - 80): low.find(hits[0]) + 120]})
            except Exception:
                pass
        pg.on("response", on_resp)
        try:
            pg.goto("https://22bet.com/line/football", timeout=30000, wait_until="networkidle")
            link = pg.locator("a[href*='/line/football/']").nth(5)
            href = link.get_attribute("href")
            if href:
                pg.goto("https://22bet.com" + href if href.startswith("/") else href, timeout=30000, wait_until="networkidle")
            pg.wait_for_timeout(4000)
        except Exception as e:
            out["nav_error"] = type(e).__name__
        out["dict_hits"] = seen[:12]
        b.close()
    print(json.dumps(out)[:3500])
    url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if url and key:
        print(requests.post(url + "/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, json={"info": out}, timeout=30).status_code)

main()
