#!/usr/bin/env python3
"""NETRATTLER public-source feature collector (shadow only).

Collects normal public football pages for later ML feature extraction. It never
creates odds, never bypasses CAPTCHA/Cloudflare/login controls, and never feeds
production picks directly. REAL_ODDS_ONLY remains owned by the production odds
pipeline.
"""
from __future__ import annotations
import json, os, re, time
from datetime import datetime, timezone
from urllib.parse import quote_plus
import requests

UA="NETRATTLER-PublicFeatures/1.0 (+https://github.com/forfexes/btts-bot_ki)"
TIMEOUT=int(os.getenv("NETRATTLER_PUBLIC_SOURCE_TIMEOUT","20"))
USE_BROWSER=os.getenv("NETRATTLER_PUBLIC_SOURCE_BROWSER","1")=="1"

SOURCES={
 "aiscore":"https://www.aiscore.com/",
 "besoccer":"https://www.besoccer.com/",
 "soccerstats":"https://www.soccerstats.com/",
 "understat":"https://understat.com/",
 "forebet":"https://www.forebet.com/",
 "betmines":"https://betmines.com/",
}

def fetch_public(url):
    try:
        r=requests.get(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=TIMEOUT,allow_redirects=True)
        if r.ok and len(r.text)>1000:
            return r.text,"requests",r.status_code
    except Exception:
        pass
    if not USE_BROWSER:
        return "","failed",None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True)
            page=b.new_page(user_agent=UA)
            resp=page.goto(url,wait_until="domcontentloaded",timeout=TIMEOUT*1000)
            html=page.content(); b.close()
            return html,"playwright",resp.status if resp else None
    except Exception:
        return "","failed",None

def text_features(html):
    txt=re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>"," ",html,flags=re.I)
    txt=re.sub(r"<[^>]+>"," ",txt)
    txt=re.sub(r"\s+"," ",txt).strip()
    low=txt.lower()
    return {
      "bytes":len(html.encode("utf-8",errors="ignore")),
      "has_h2h":("h2h" in low or "head to head" in low),
      "has_lineups":("lineup" in low or "aufstellung" in low),
      "has_corners":("corner" in low or "eckb" in low),
      "has_cards":("yellow card" in low or "red card" in low or "karten" in low),
      "has_btts":("btts" in low or "both teams to score" in low),
      "has_over25":("over 2.5" in low or "2.5 goals" in low),
      "has_odds":("odds" in low or "quoten" in low),
    }

def probe_all():
    rows=[]
    for name,url in SOURCES.items():
        started=time.monotonic(); html,mode,status=fetch_public(url)
        row={"source":name,"url":url,"mode":mode,"status":status,"ok":bool(html),"elapsed_s":round(time.monotonic()-started,2),"collected_at":datetime.now(timezone.utc).isoformat()}
        row.update(text_features(html) if html else {})
        rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
        time.sleep(1)
    return rows

def h2h_features(matches):
    """Leakage-safe aggregate for already parsed historical H2H rows.

    Expected row keys: date, home_goals, away_goals, ht_home_goals, ht_away_goals,
    corners. Caller must supply only matches known before the target kickoff.
    """
    if not matches: return {"h2h_n":0}
    rows=list(matches)[:10]; n=len(rows)
    goals=[float(x.get("home_goals",0))+float(x.get("away_goals",0)) for x in rows]
    btts=[1.0 if float(x.get("home_goals",0))>0 and float(x.get("away_goals",0))>0 else 0.0 for x in rows]
    over25=[1.0 if g>2.5 else 0.0 for g in goals]
    ht=[float(x.get("ht_home_goals",0))+float(x.get("ht_away_goals",0)) for x in rows if x.get("ht_home_goals") is not None and x.get("ht_away_goals") is not None]
    corners=[float(x["corners"]) for x in rows if x.get("corners") is not None]
    weights=[0.82**i for i in range(n)]; sw=sum(weights)
    wavg=lambda vals: sum(v*w for v,w in zip(vals,weights[:len(vals)]))/sum(weights[:len(vals)]) if vals else None
    return {"h2h_n":n,"h2h_avg_goals":round(wavg(goals),4),"h2h_btts_rate":round(wavg(btts),4),"h2h_over25_rate":round(wavg(over25),4),"h2h_avg_ht_goals":round(wavg(ht),4) if ht else None,"h2h_avg_corners":round(wavg(corners),4) if corners else None}

def main():
    rows=probe_all()
    with open("netrattler_public_source_summary.json","w",encoding="utf-8") as f: json.dump(rows,f,ensure_ascii=False,indent=2)
if __name__=="__main__": main()
