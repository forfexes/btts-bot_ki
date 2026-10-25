#!/usr/bin/env python3
"""Opt-in HTML odds scraper. Only explicitly labelled JSON-LD bookmaker prices.

Set NETRATTLER_HTML_ODDS_URLS to comma-separated HTTPS event pages you are
authorized to access. No login, CAPTCHA bypass, browser fingerprint spoofing,
or synthetic odds. Results remain a separate untrusted shadow source until
independently verified and explicitly promoted.
"""
import json
import os
import re
from html import unescape
from urllib.parse import urlparse
import requests

SCRIPT = re.compile(r'<script\\b[^>]*type=["\\\']application/ld\\+json["\\\'][^>]*>(.*?)</script>', re.I | re.S)
MARKETS = {"1x2": {"home", "draw", "away"}, "btts": {"yes", "no"}}

def parse_html(html, url, target_date):
    from netrattler_odds_harvester import _row
    rows = []
    for script in SCRIPT.findall(html):
        try:
            payload = json.loads(unescape(script.strip()))
        except (ValueError, TypeError):
            continue
        objects = payload if isinstance(payload, list) else [payload]
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            if isinstance(obj.get("@graph"), list):
                objects.extend(obj["@graph"])
                continue
            if obj.get("@type") not in ("SportsEvent", "Event"):
                continue
            home, away = obj.get("homeTeam"), obj.get("awayTeam")
            home = home.get("name") if isinstance(home, dict) else None
            away = away.get("name") if isinstance(away, dict) else None
            kickoff = obj.get("startDate")
            if not home or not away or not kickoff or str(kickoff)[:10] != target_date:
                continue
            offers = obj.get("offers", [])
            for offer in offers if isinstance(offers, list) else [offers]:
                if not isinstance(offer, dict):
                    continue
                market = str(offer.get("market", "")).lower()
                selection = str(offer.get("selection", "")).lower()
                if selection not in MARKETS.get(market, set()):
                    continue
                bookmaker = offer.get("seller")
                bookmaker = bookmaker.get("name") if isinstance(bookmaker, dict) else bookmaker
                if not bookmaker:
                    continue
                item = _row(source="html_odds_shadow", bookmaker=str(bookmaker),
                            event_id=str(obj.get("@id") or url), league="",
                            home=home, away=away, commence_time=kickoff,
                            market=market, selection=selection, odds=offer.get("price"),
                            raw={"page_url": url, "scraper": "jsonld"})
                if item:
                    rows.append(item)
    return rows

def collect_html_odds(target_date):
    urls = [u.strip() for u in os.getenv("NETRATTLER_HTML_ODDS_URLS", "").split(",") if u.strip()]
    rows = []
    for url in urls[:5]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            continue
        # Explicit allowlist prevents arbitrary URL fetching via configuration.
        hosts = {h.strip().lower() for h in os.getenv("NETRATTLER_HTML_ODDS_HOSTS", "").split(",") if h.strip()}
        if parsed.hostname.lower() not in hosts:
            continue
        try:
            response = requests.get(url, timeout=8, headers={"User-Agent": "NETRATTLER-OddsResearch/1.0"})
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                continue
            rows.extend(parse_html(response.text, url, target_date))
        except requests.RequestException:
            continue
    return rows
