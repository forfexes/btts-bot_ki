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
    # Diagnose (via print → landet im GitHub-Log)
    try:
        if not _key():
            print("   🍋 OddsPapi: KEIN KEY gefunden (ODDSPAPI_KEY Secret gesetzt?)")
        elif data is None:
            print("   🍋 OddsPapi: API-Antwort leer/Fehler (Key gültig? Endpoint?)")
        elif isinstance(data, dict) and data.get("_rate_limited"):
            print("   🍋 OddsPapi: Rate-Limit (429) erreicht")
        else:
            print(f"   🍋 OddsPapi: {len(fixtures)} Fixtures mit Quoten geladen ({ds})")
    except Exception:
        pass
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


def _tokens(name: str) -> set:
    """Signifikante Wörter eines Teamnamens (ohne Füllwörter)."""
    stop = {"fc", "cf", "sc", "ac", "sv", "us", "if", "bk", "fk", "cd", "club",
            "de", "the", "city", "united", "real", "cd", "afc", "ss", "as", "rc"}
    raw = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower())
    return {w for w in raw.split() if len(w) >= 3 and w not in stop}


def find_fixture(home: str, away: str, target_date=None) -> Optional[Dict]:
    """Findet das OddsPapi-Fixture per Teamnamen (token-basiert, robust)."""
    h_tok, a_tok = _tokens(home), _tokens(away)
    h_norm, a_norm = _norm(home), _norm(away)
    best = None
    for fx in get_fixtures(target_date):
        p1_name = fx.get("participant1Name", "") or ""
        p2_name = fx.get("participant2Name", "") or ""
        p1, p2 = _norm(p1_name), _norm(p2_name)
        if not p1 or not p2:
            continue
        # 1) Exakter/Substring-Match (schnell)
        if (h_norm[:6] and (h_norm[:6] in p1 or p1[:6] in h_norm)) and \
           (a_norm[:6] and (a_norm[:6] in p2 or p2[:6] in a_norm)):
            return fx
        # 2) Token-Match: teilen sich Heim UND Auswärts je ein signifikantes Wort
        #    (auch Teilwort: "man" ⊂ "manchester")
        p1_tok, p2_tok = _tokens(p1_name), _tokens(p2_name)
        def _tok_overlap(ta, tb):
            for x in ta:
                for y in tb:
                    if x == y or (len(x) >= 4 and x in y) or (len(y) >= 4 and y in x):
                        return True
            return False
        if _tok_overlap(h_tok, p1_tok) and _tok_overlap(a_tok, p2_tok):
            best = fx
    return best


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
