#!/usr/bin/env python3
"""Diagnostic structure sampler for public OddsPortal/Flashscore football pages.

This is deliberately non-production. It records only DOM structure, candidate
match links/text and embedded JSON metadata so a parser can be built from actual
GitHub-runner HTML instead of guessing selectors. No login/bypass behavior.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}
SOURCES = {
    "oddsportal": "https://www.oddsportal.com/football/",
    "flashscore": "https://www.flashscore.com/football/",
}

ODDS_RE = re.compile(r"(?<!\d)(1\.\d{2}|[2-9]\.\d{2}|1[0-9]\.\d{2})(?!\d)")
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")


def clean(text: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def sample(url: str) -> Dict[str, Any]:
    r = requests.get(url, headers=H, timeout=25, allow_redirects=True)
    out: Dict[str, Any] = {
        "status": r.status_code,
        "final_url": r.url,
        "bytes": len(r.content),
        "title": "",
        "links": [],
        "odds_nodes": [],
        "scripts": [],
    }
    if not r.ok:
        return out
    soup = BeautifulSoup(r.text, "html.parser")
    out["title"] = clean(soup.title.get_text(" ", strip=True) if soup.title else "", 160)

    # Candidate event links. Keep href/class/text only, no full page dump.
    links: List[Dict[str, Any]] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        text = clean(a.get_text(" ", strip=True), 240)
        cls = " ".join(a.get("class") or [])
        low = f"{href} {cls} {text}".lower()
        if any(k in low for k in ("match", "event", "football", "soccer")) and (ODDS_RE.search(text) or TIME_RE.search(text) or " - " in text or " vs " in text):
            links.append({"href": href[:300], "class": cls[:220], "text": text})
        if len(links) >= 80:
            break
    out["links"] = links

    # Nodes containing multiple decimal-looking values are useful for identifying
    # fixture-row selectors. Limit to compact nodes to avoid dumping page content.
    nodes: List[Dict[str, Any]] = []
    for tag in soup.find_all(["div", "tr", "li", "section"]):
        text = clean(tag.get_text(" ", strip=True), 500)
        odds = ODDS_RE.findall(text)
        if len(odds) < 2 or len(text) > 500:
            continue
        cls = " ".join(tag.get("class") or [])
        ident = str(tag.get("id") or "")
        nodes.append({"tag": tag.name, "id": ident[:120], "class": cls[:260], "text": text, "odds": odds[:12]})
        if len(nodes) >= 80:
            break
    out["odds_nodes"] = nodes

    # Embedded JSON/script metadata: type/id/size plus a tiny schema summary.
    scripts: List[Dict[str, Any]] = []
    for s in soup.find_all("script"):
        raw = s.string or s.get_text() or ""
        if not raw.strip():
            continue
        typ = str(s.get("type") or "")
        sid = str(s.get("id") or "")
        entry: Dict[str, Any] = {"type": typ[:100], "id": sid[:100], "chars": len(raw)}
        if "json" in typ.lower() or sid in {"__NEXT_DATA__", "__NUXT_DATA__"}:
            try:
                data = json.loads(raw)
                entry["json_type"] = type(data).__name__
                if isinstance(data, dict):
                    entry["top_keys"] = list(data.keys())[:40]
            except Exception:
                entry["json_parse"] = False
        # Search only for structural keywords; never copy giant script bodies.
        low = raw.lower()
        entry["keywords"] = [k for k in ("odds", "bookmaker", "participant", "event", "match", "home", "away") if k in low]
        if entry.get("keywords") or "json" in typ.lower() or sid:
            scripts.append(entry)
        if len(scripts) >= 80:
            break
    out["scripts"] = scripts
    return out


def main() -> int:
    payload = {"captured_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name, url in SOURCES.items():
        try:
            row = sample(url)
        except Exception as exc:
            row = {"error": type(exc).__name__, "detail": str(exc)[:180]}
        payload["sources"][name] = row
        print(f"{name}: status={row.get('status')} bytes={row.get('bytes')} links={len(row.get('links') or [])} odds_nodes={len(row.get('odds_nodes') or [])} scripts={len(row.get('scripts') or [])}")
    with open("netrattler_web_odds_diag.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
