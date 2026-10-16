#!/usr/bin/env python3
"""Bounded, read-only probe: do public aggregator pages show odds when rendered in a plain
headless browser (no stealth, no fingerprint spoofing)? Writes counts only to netrattler_card_diag."""
import json, os, re, time
import requests
from playwright.sync_api import sync_playwright

PAGES = {
    "oddsportal_football": "https://www.oddsportal.com/matches/football/",
    "flashscore_football": "https://www.flashscore.com/football/",
    "sofascore_football": "https://www.sofascore.com/football",
}
BLOCK = re.compile(r"captcha|access denied|just a moment|attention required|are you a robot|unusual traffic", re.I)
DEC = re.compile(r"\b\d{1,2}\.\d{2}\b")


def main():
    out = {"probe": "browser_probe"}
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        for name, url in PAGES.items():
            res = {}
            try:
                ctx = br.new_context(locale="en-GB", viewport={"width": 1280, "height": 900})
                page = ctx.new_page()
                xhr = []
                page.on("response", lambda r: xhr.append((r.status, r.url.split("?")[0][-70:])) if r.request.resource_type in ("xhr", "fetch") else None)
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(9000)
                text = page.inner_text("body")
                res = {"http": resp.status if resp else 0, "title": page.title()[:60], "chars": len(text),
                       "blocked": bool(BLOCK.search(text[:4000])), "decimals": len(DEC.findall(text)),
                       "xhr_n": len(xhr), "xhr_non200": sum(1 for s, _ in xhr if s != 200),
                       "xhr_sample": [u for s, u in xhr if s == 200][:6]}
                ctx.close()
            except Exception as exc:
                res = {"err": f"{type(exc).__name__}: {str(exc)[:80]}"}
            out[name] = res
            print(name, json.dumps(res), flush=True)
        br.close()
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": out},
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
