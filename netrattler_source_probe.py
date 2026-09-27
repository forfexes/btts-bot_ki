#!/usr/bin/env python3
"""NETRATTLER public-source probe.

Conservative source-health checker: no CAPTCHA/Cloudflare bypass, no login automation,
no synthetic odds. Playwright/Chromium is optional and only renders normal public pages.
This module is diagnostic/shadow-only and does not feed production picks.
"""
from __future__ import annotations
import json, os, time
import requests

UA = "NETRATTLER-SourceProbe/1.1 (+https://github.com/forfexes/btts-bot_ki)"
TIMEOUT = int(os.getenv("NETRATTLER_SOURCE_PROBE_TIMEOUT", "20"))

SOURCES = {
    "soccerstats": "https://www.soccerstats.com/",
    "besoccer": "https://www.besoccer.com/",
    "aiscore": "https://www.aiscore.com/",
    "sofascore": "https://www.sofascore.com/",
    "fotmob": "https://www.fotmob.com/",
    "understat": "https://understat.com/",
    "forebet": "https://www.forebet.com/",
    "betmines": "https://betmines.com/",
    # Odds comparison/public bookmaker pages. Probe-only until a parser has
    # demonstrated exact event/market/selection mapping in CI.
    "oddsportal": "https://www.oddsportal.com/football/",
    "betexplorer": "https://www.betexplorer.com/football/",
    "flashscore": "https://www.flashscore.com/football/",
}

def request_probe(name, url):
    started=time.monotonic()
    try:
        r=requests.get(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=TIMEOUT,allow_redirects=True)
        return {"source":name,"mode":"requests","ok":r.ok,"status":r.status_code,"final_url":r.url,"bytes":len(r.content),"elapsed_s":round(time.monotonic()-started,2)}
    except Exception as e:
        return {"source":name,"mode":"requests","ok":False,"error":type(e).__name__,"detail":str(e)[:180],"elapsed_s":round(time.monotonic()-started,2)}

def browser_probe(name,url):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"source":name,"mode":"playwright","ok":False,"error":"playwright_unavailable","detail":str(e)[:120]}
    started=time.monotonic()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(user_agent=UA)
            resp=page.goto(url,wait_until="domcontentloaded",timeout=TIMEOUT*1000)
            title=page.title()
            html=page.content()
            browser.close()
        return {"source":name,"mode":"playwright","ok":bool(resp and resp.ok),"status":resp.status if resp else None,"title":title[:100],"bytes":len(html.encode()),"elapsed_s":round(time.monotonic()-started,2)}
    except Exception as e:
        return {"source":name,"mode":"playwright","ok":False,"error":type(e).__name__,"detail":str(e)[:180],"elapsed_s":round(time.monotonic()-started,2)}

def main():
    browser=os.getenv("NETRATTLER_SOURCE_PROBE_BROWSER","0")=="1"
    out=[]
    for name,url in SOURCES.items():
        row=request_probe(name,url); out.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
        if browser and not row.get("ok"):
            brow=browser_probe(name,url); out.append(brow); print(json.dumps(brow,ensure_ascii=False),flush=True)
        time.sleep(1)
    with open("netrattler_source_probe.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
if __name__=="__main__": main()
