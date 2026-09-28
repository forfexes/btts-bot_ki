"""NETRATTLER InPlayFlux public-blog adapter (shadow/features only).

The adapter intentionally does NOT promote InPlayFlux market prices to
REAL_ODDS.  It collects public model/features for source learning and later
match enrichment.  Production tips still require the existing observed
bookmaker-odds pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from html import unescape
import re
from typing import Dict, List, Optional

import requests

BASE_URL = "https://inplayflux.com/blog/"
UA = "NETRATTLER-InPlayFlux/1.0 (+https://github.com/forfexes/btts-bot_ki)"


@dataclass
class InPlayFluxPick:
    match: str
    signal: str
    confidence: int
    league: str = ""
    kickoff: str = ""
    url: str = ""
    source: str = "inplayflux"
    shadow_only: bool = True

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_daily_index(html: str, min_confidence: int = 70) -> List[Dict[str, object]]:
    """Parse the public date table/list without inventing missing fields.

    InPlayFlux currently exposes rows containing time, league, match, signal,
    confidence and an Analysis link.  The parser is deliberately conservative:
    a row without an explicit percentage and signal is ignored.
    """
    out: List[Dict[str, object]] = []
    seen = set()
    # Table rows are the stable representation on the public date pages.
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html or "", flags=re.I | re.S):
        cells = [_clean(x) for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)]
        text = _clean(row)
        cm = re.search(r"\b(\d{2,3})\s*%", text)
        sm = re.search(r"\b(Over\s+[123]\.5|BTTS(?:\s+Yes)?)\b", text, flags=re.I)
        if not cm or not sm:
            continue
        confidence = int(cm.group(1))
        if confidence < int(min_confidence) or confidence > 100:
            continue
        hrefm = re.search(r'href=["\']([^"\']+)["\']', row, flags=re.I)
        url = hrefm.group(1) if hrefm else ""
        if url.startswith("/"):
            url = "https://inplayflux.com" + url
        kickoff = next((c for c in cells if re.fullmatch(r"\d{1,2}:\d{2}", c)), "")
        signal = sm.group(1).strip()
        # Match cell normally contains "Home - Away". Avoid treating signal/result as match.
        match = next((c for c in cells if " - " in c and not re.search(r"\bWon\b|\bLost\b", c, re.I)), "")
        if not match:
            continue
        league = ""
        for c in cells:
            if c not in {kickoff, match} and signal.lower() not in c.lower() and "%" not in c and not re.search(r"\bWon\b|\bLost\b|Analysis", c, re.I):
                league = c
                break
        key = (match.lower(), signal.lower(), confidence)
        if key in seen:
            continue
        seen.add(key)
        out.append(InPlayFluxPick(match=match, signal=signal, confidence=confidence, league=league, kickoff=kickoff, url=url).to_dict())
    return out


def fetch_daily(day: Optional[date] = None, min_confidence: int = 70, timeout: int = 15) -> List[Dict[str, object]]:
    day = day or date.today()
    r = requests.get(BASE_URL, params={"d": day.isoformat(), "lang": "en"}, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return parse_daily_index(r.text, min_confidence=min_confidence)


def parse_analysis_features(html: str) -> Dict[str, object]:
    """Extract only explicitly printed model/features from an analysis page."""
    text = _clean(html)
    result: Dict[str, object] = {"source": "inplayflux", "shadow_only": True}
    patterns = {
        "confidence": r"CONFIDENCE SCORE\s*%?\s*(\d{1,3})",
        "prob_over15": r"OVER 1\.5\s*%?\s*(\d{1,3})",
        "prob_over25": r"OVER 2\.5\s*%?\s*(\d{1,3})",
        "prob_over35": r"OVER 3\.5\s*%?\s*(\d{1,3})",
        "prob_btts": r"BTTS YES\s*%?\s*(\d{1,3})",
        "combined_goal_expectation": r"Combined Expectation\s*([0-9]+(?:\.[0-9]+)?)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text, flags=re.I)
        if m:
            value = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
            result[key] = value
    # Keep displayed market information informational only; never REAL_ODDS.
    m = re.search(r"Over 2\.5 Market Odds:\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I)
    if m:
        result["displayed_market_over25"] = float(m.group(1))
        result["displayed_market_real_odds"] = False
    peak = re.search(r"Peak scoring window:\s*(\d{1,2}-\d{1,2})", text, flags=re.I)
    if peak:
        result["peak_scoring_window"] = peak.group(1)
    return result
