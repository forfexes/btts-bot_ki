"""Daten-getriebenes Gate: sperrt (Markt, Quotenband)-Gruppen, die im Rolling-Fenster
strukturell Geld verlieren (Muster aus PROP HUNTER 'block structurally-losing').

Regel: n >= MIN_N abgerechnete Tipps und ROI < MAX_ROI  ->  Gruppe gesperrt.
Faellt bei fehlender DB still auf 'nichts sperren' zurueck.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Dict, Iterable, Mapping, Optional, Set, Tuple

DAYS = int(os.getenv("NETRATTLER_GATE_DAYS", "45"))
MIN_N = int(os.getenv("NETRATTLER_GATE_MIN_N", "40"))
MAX_ROI = float(os.getenv("NETRATTLER_GATE_MAX_ROI", "-0.25"))  # hart nur bei extremen Verlierern
MIN_N_HARD = int(os.getenv("NETRATTLER_GATE_MIN_N_HARD", "100"))
PRIOR_K = float(os.getenv("NETRATTLER_GATE_PRIOR_K", "40"))
_RATES: Optional[Dict[Tuple[str, str], Tuple[int, float]]] = None
SKIP_MARKETS = {"combo_multi"}  # Quotenqualitaet unsicher, nicht ueber ROI beurteilen
_NUM = re.compile(r"^\d+(\.\d+)?$")
_CACHE: Optional[Set[Tuple[str, str]]] = None


def odds_band(odds: float) -> str:
    if odds < 1.5:
        return "<1.5"
    if odds < 2.0:
        return "1.5-2"
    if odds < 3.0:
        return "2-3"
    return "3+"


def blocked_groups(rows: Iterable[Mapping]) -> Dict[Tuple[str, str], Tuple[int, float]]:
    agg: Dict[Tuple[str, str], list] = {}
    for r in rows:
        status = str(r.get("status", "")).lower()
        if status not in ("win", "loss"):
            continue
        market = str(r.get("market", "")).lower()
        o = str(r.get("odds", ""))
        if market in SKIP_MARKETS or not _NUM.match(o):
            continue
        o = float(o)
        if o <= 1.0:
            continue
        a = agg.setdefault((market, odds_band(o)), [0, 0.0])
        a[0] += 1
        a[1] += (o - 1.0) if status == "win" else -1.0
    return {k: (n, u / n) for k, (n, u) in agg.items() if n >= MIN_N_HARD and u / n < MAX_ROI}


def group_rates(rows: Iterable[Mapping]) -> Dict[Tuple[str, str], Tuple[int, float]]:
    agg: Dict[Tuple[str, str], list] = {}
    for r in rows:
        st = str(r.get('status', '')).lower()
        o = str(r.get('odds', ''))
        m = str(r.get('market', '')).lower()
        if st not in ('win', 'loss') or m in SKIP_MARKETS or not _NUM.match(o) or float(o) <= 1.0:
            continue
        a = agg.setdefault((m, odds_band(float(o))), [0, 0])
        a[0] += 1
        a[1] += st == 'win'
    return {k: (n, w / n) for k, (n, w) in agg.items() if n >= 20}


def load_blocked(url: str, key: str) -> Set[Tuple[str, str]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    _CACHE = set()
    if not url or not key:
        return _CACHE
    try:
        import requests
        since = (date.today() - timedelta(days=DAYS)).isoformat()
        rows, off = [], 0
        while off < 20000:
            r = requests.get(
                f"{url}/rest/v1/tips",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"select": "market,status,odds", "status": "in.(win,loss)",
                        "date": f"gte.{since}", "limit": 1000, "offset": off},
                timeout=20,
            )
            if not r.ok:
                break
            b = r.json()
            rows += b
            if len(b) < 1000:
                break
            off += 1000
        _CACHE = set(blocked_groups(rows))
        global _RATES
        _RATES = group_rates(rows)
    except Exception:
        pass
    return _CACHE


def is_blocked(url: str, key: str, market: str, odds: float) -> bool:
    return (str(market).lower(), odds_band(float(odds))) in load_blocked(url, key)


def adjust_probability(url: str, key: str, market: str, odds: float, p: float) -> float:
    """Weiche Korrektur statt Sperre: p wird bayesisch mit der beobachteten Trefferquote
    der Gruppe gemischt und nie darueber angehoben. Der normale Edge-Check entscheidet dann."""
    load_blocked(url, key)
    h = (_RATES or {}).get((str(market).lower(), odds_band(float(odds))))
    if not h:
        return p
    n, rate = h
    blended = (n * rate + PRIOR_K * p) / (n + PRIOR_K)
    return min(p, blended)
