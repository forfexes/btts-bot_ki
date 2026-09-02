"""
NETRATTLER — OddsPapi-Anbindung (Haupt-Quotenquelle für Team-Märkte)
====================================================================

OddsPapi liefert echte Quoten von 130+ Buchmachern (inkl. Pinnacle, Bet365)
für ALLE Ligen weltweit — sauberes JSON, kein Scraping, kein Block.

Free-Tier: 250 Calls/Monat → deshalb sparsam:
  - 1× /fixtures pro Tag (alle Spiele) → gecacht
  - /odds nur für Spiele, die ein Tipp werden könnten → gecacht

Market-IDs (aus echter API-Antwort verifiziert):
  101   = 1X2            (101=Home, 102=Draw, 103=Away)
  104   = BTTS           (104=Yes, 105=No)
  1010  = Over/Under 2.5 (1010=Over, 1011=Under)
  1012  = Over/Under 3.5 (1012=Over, 1013=Under)
  1014  = Over/Under 1.5 (1014=Over, 1015=Under)
  10214 = Over/Under 1.5 HT
  10216 = BTTS HT
  10208 = Corners O/U
  108   = Double Chance

Fehlertolerant: jede Funktion in try/except, Fehler → None/{}. Bricht nie den Bot.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

BASE_URL = "https://api.oddspapi.io/v4"
SPORT_ID = 10  # Fußball

# Bevorzugte Buchmacher (Reihenfolge = Priorität; Pinnacle = sharp benchmark)
_PREFERRED_BOOKS = ["pinnacle", "bet365", "betano", "bwin", "888sport", "betsson",
                    "unibet", "williamhill", "1xbet", "22bet", "betway"]

_FIXTURES_CACHE: Dict[str, List[Dict]] = {}
_ODDS_CACHE: Dict[str, Dict] = {}
_CALL_COUNT = {"fixtures": 0, "odds": 0}


def call_stats() -> dict:
    return dict(_CALL_COUNT)


def _key() -> str:
    return (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDSPAPI_API_KEY", "")).strip()


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").lower().strip())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def _get(path: str, params: dict, timeout: int = 20):
    if requests is None or not _key():
        return None
    try:
        p = dict(params)
        p["apiKey"] = _key()
        r = requests.get(f"{BASE_URL}/{path}", params=p, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 429:
            return {"_rate_limited": True}
        if not r.ok:
            return None
        return r.json()
    except Exception:
        return None


def get_fixtures(target_date=None) -> List[Dict]:
    """Alle Fußball-Fixtures mit Quoten für heute+morgen. 1 Call, gecacht."""
    ds = str(target_date or datetime.now(timezone.utc).date())
    if ds in _FIXTURES_CACHE:
        return _FIXTURES_CACHE[ds]
    _to = str((datetime.fromisoformat(ds) + timedelta(days=1)).date()) if len(ds) == 10 else ds
    data = _get("fixtures", {"sportId": SPORT_ID, "from": ds, "to": _to})
    _CALL_COUNT["fixtures"] += 1
    fixtures = []
    if isinstance(data, list):
        fixtures = [f for f in data if f.get("hasOdds")]
    _FIXTURES_CACHE[ds] = fixtures
    return fixtures


def _price(market: dict, outcome_id: str) -> Optional[float]:
    """Zieht den Preis eines Outcomes aus einem Markt."""
    try:
        oc = market.get("outcomes", {}).get(outcome_id, {})
        pl = oc.get("players", {}).get("0", {})
        p = pl.get("price")
        if p and float(p) > 1.0 and pl.get("active", True):
            return round(float(p), 2)
    except Exception:
        pass
    return None


def _best_book_markets(bookmaker_odds: dict) -> dict:
    """Wählt den besten verfügbaren Buchmacher (Pinnacle bevorzugt)."""
    for bk in _PREFERRED_BOOKS:
        if bk in bookmaker_odds and bookmaker_odds[bk].get("markets"):
            return bookmaker_odds[bk]["markets"]
    # sonst irgendeinen aktiven
    for bk, bd in bookmaker_odds.items():
        if bd.get("markets"):
            return bd["markets"]
    return {}


def get_match_odds(fixture_id: str) -> Dict[str, Any]:
    """Alle relevanten Team-Markt-Quoten für ein Spiel. Gecacht."""
    if fixture_id in _ODDS_CACHE:
        return _ODDS_CACHE[fixture_id]
    result: Dict[str, Any] = {"_source": "oddspapi", "fixture_id": fixture_id}
    # Budget-Schutz: max Odds-Calls pro Lauf (Free-Tier 250/Monat).
    _cap = int(os.getenv("NETRATTLER_ODDSPAPI_MAX_CALLS", "40"))
    if _CALL_COUNT["odds"] >= _cap:
        _ODDS_CACHE[fixture_id] = result
        return result
    data = _get("odds", {"fixtureId": fixture_id})
    _CALL_COUNT["odds"] += 1
    if not data or data.get("_rate_limited"):
        _ODDS_CACHE[fixture_id] = result
        return result
    mk = _best_book_markets(data.get("bookmakerOdds", {}))
    if not mk:
        _ODDS_CACHE[fixture_id] = result
        return result

    # Market-ID → (Ergebnis-Key, Outcome-ID) aus verifizierter Struktur
    mapping = {
        "btts_yes":     ("104", "104"),
        "btts_no":      ("104", "105"),
        "over_25":      ("1010", "1010"),
        "under_25":     ("1010", "1011"),
        "over_35":      ("1012", "1012"),
        "over_15":      ("1014", "1014"),
        "over15_ht":    ("10214", "10214"),
        "btts_yes_ht":  ("10216", "10216"),
        "home":         ("101", "101"),
        "draw":         ("101", "102"),
        "away":         ("101", "103"),
    }
    for key, (mid, oid) in mapping.items():
        if mid in mk:
            v = _price(mk[mid], oid)
            if v:
                result[key] = v
    _ODDS_CACHE[fixture_id] = result
    return result


def find_fixture(home: str, away: str, target_date=None) -> Optional[Dict]:
    """Findet das OddsPapi-Fixture per Teamnamen."""
    h, a = _norm(home), _norm(away)
    for fx in get_fixtures(target_date):
        p1 = _norm(fx.get("participant1Name", ""))
        p2 = _norm(fx.get("participant2Name", ""))
        if not p1 or not p2:
            continue
        # beidseitiger Präfix-Match (robust gegen Namensvarianten)
        if (h[:6] in p1 or p1[:6] in h) and (a[:6] in p2 or p2[:6] in a):
            return fx
    return None


def get_odds_for_match(home: str, away: str, target_date=None) -> Dict[str, Any]:
    """Komplett-Lookup: Teamnamen → Fixture → Quoten. Für die Quoten-Kette."""
    fx = find_fixture(home, away, target_date)
    if not fx:
        return {}
    return get_match_odds(fx.get("fixtureId"))


def enrich_fixtures_with_ids(target_date=None) -> Dict[str, Dict]:
    """Match-ID-Übersetzer: {team_key: {pinnacleId, sofascoreId, flashscoreId, ...}}.
    Nutzbar, um Matches quellenübergreifend zu verknüpfen."""
    out = {}
    for fx in get_fixtures(target_date):
        k = f"{_norm(fx.get('participant1Name',''))}_{_norm(fx.get('participant2Name',''))}"
        out[k] = {
            "fixtureId": fx.get("fixtureId"),
            "tournamentName": fx.get("tournamentName"),
            "categoryName": fx.get("categoryName"),
            **(fx.get("externalProviders") or {}),
        }
    return out


__all__ = ["get_fixtures", "get_match_odds", "find_fixture",
           "get_odds_for_match", "enrich_fixtures_with_ids"]
