#!/usr/bin/env python3
"""Load ONE public 22bet football page in a normal headless browser and list
which JSON/JS files the page itself fetches that contain bet-group names
(e.g. 'Fouls', 'Tackles'), so the numeric group ids in the LineFeed can be
mapped from the operator's own dictionary. Read-only; records only URL
path, size and short matched snippets. No login, no bypass."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import requests

START = "https://22bet.com/line/football"
WORDS = re.compile(r"(Fouls?|Tackles?|Shots on target|Players' stats)", re.I)


def main() -> int:
    from playwright.sync_api import sync_playwright
    found, seen = [], 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(accept_downloads=False)
        page = ctx.new_page()

        def on_resp(resp):
            nonlocal seen
            if seen > 400 or len(found) >= 25:
                return
            ct = (resp.headers.get("content-type") or "").lower()
            if not any(t in ct for t in ("json", "javascript", "text/plain")):
                return
            seen += 1
            try:
                body = resp.text()
            except Exception:
                return
            hits = WORDS.findall(body[:3_000_000])
            if len(hits) >= 3:
                p = urlparse(resp.url)
                snips = []
                for m in list(WORDS.finditer(body))[:4]:
                    snips.append(body[max(0, m.start() - 70): m.end() + 70])
                found.append({"host": p.hostname, "path": p.path[:160], "bytes": len(body),
                              "hits": len(hits), "snips": snips})

        page.on("response", on_resp)
        status = None
        try:
            nav = page.goto(START, wait_until="domcontentloaded", timeout=25000)
            status = nav.status if nav else None
            page.wait_for_timeout(5000)
            # open the first listed match (public link on the same site)
            hrefs = page.locator("a[href*='/line/football/']").evaluate_all(
                "a => a.map(x => x.getAttribute('href')).filter(h => h.split('/').length > 5).slice(0,3)")
            if hrefs:
                page.goto("https://22bet.com" + hrefs[0] if hrefs[0].startswith("/") else hrefs[0],
                          wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(6000)
        except Exception as exc:
            status = f"error {type(exc).__name__}"
        b.close()
    out = {"probe": "x1_dict_browser_probe", "status": status, "inspected": seen, "found": found}
    print(json.dumps(out, indent=2, ensure_ascii=False)[:6000])
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": out})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
