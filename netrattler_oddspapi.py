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
_RATE_LIMITED_FLAG = {"hit": False}


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
            _RATE_LIMITED_FLAG["hit"] = True
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
            continue
        # Heim/Auswärts vertauscht? (manche Quellen listen andersrum)
        if _tok_overlap(h_tok, p2_tok) and _tok_overlap(a_tok, p1_tok):
            best = fx
    return best


def get_odds_for_match(home: str, away: str, target_date=None) -> Dict[str, Any]:
    """Komplett-Lookup: Teamnamen → Fixture → Quoten. Für die Quoten-Kette."""
    # Wenn die Fixtures-Liste rate-limited war → Flag durchreichen
    _fx_list = get_fixtures(target_date)
    if _RATE_LIMITED_FLAG.get("hit"):
        return {"_rate_limited": True}
    fx = find_fixture(home, away, target_date)
    if not fx:
        _CALL_COUNT["misses"] = _CALL_COUNT.get("misses", 0) + 1
        return {}
    _CALL_COUNT["hits"] = _CALL_COUNT.get("hits", 0) + 1
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


def get_results(target_date=None) -> List[Dict[str, Any]]:
    """Ergebnisse (Endstand + Halbzeit) für beendete Spiele eines Tages.
    Nutzt denselben /fixtures-Call (gecacht) — kostet keinen Extra-Call.
    Format: [{home, away, home_score, away_score, ht_home, ht_away, source}]."""
    out = []
    for fx in get_fixtures(target_date):
        try:
            _status = str(fx.get("status", "") or fx.get("statusType", "")).lower()
            _sc = fx.get("scores") or fx.get("score") or {}
            # Endstand
            hs = fx.get("participant1Score", (_sc.get("home") if isinstance(_sc, dict) else None))
            as_ = fx.get("participant2Score", (_sc.get("away") if isinstance(_sc, dict) else None))
            if hs is None or as_ is None:
                continue
            # nur beendete Spiele
            if _status and not any(k in _status for k in ("finished", "ended", "ft", "full")):
                continue
            row = {
                "home": fx.get("participant1Name", ""),
                "away": fx.get("participant2Name", ""),
                "home_score": hs, "away_score": as_,
                "source": "oddspapi",
            }
            # Halbzeit falls vorhanden
            _ht = fx.get("halfTimeScore") or fx.get("scoresHalfTime") or {}
            if isinstance(_ht, dict):
                if _ht.get("home") is not None:
                    row["ht_home"] = _ht.get("home")
                    row["ht_away"] = _ht.get("away")
            out.append(row)
        except Exception:
            continue
    return out


__all__ = ["get_fixtures", "get_match_odds", "find_fixture",
           "get_odds_for_match", "enrich_fixtures_with_ids", "get_results",
           "call_stats"]


def get_corner_quote_for_match(home: str, away: str, target_date=None, line: float = 9.5) -> Optional[float]:
    """Best-effort real OddsPapi corner-total quote for an exact offered line.

    Market 10208 is documented by the existing integration as Corners O/U. The
    API has used more than one payload shape, so this parser only accepts an
    observed active price whose observed point/line equals the requested line.
    It never derives a quote for a different line.
    """
    fx = find_fixture(home, away, target_date)
    if not fx or requests is None or not _key():
        return None
    fixture_id = fx.get("fixtureId")
    if not fixture_id:
        return None
    cache_key = f"corners:{fixture_id}:{line}"
    if cache_key in _ODDS_CACHE:
        value = _ODDS_CACHE[cache_key]
        return value if isinstance(value, (int, float)) and value > 1 else None
    if _CALL_COUNT["odds"] >= int(os.getenv("NETRATTLER_ODDSPAPI_MAX_CALLS", "40")):
        return None
    data = _get("odds", {"fixtureId": fixture_id})
    _CALL_COUNT["odds"] += 1
    if not isinstance(data, dict) or data.get("_rate_limited"):
        _ODDS_CACHE[cache_key] = None
        return None
    markets = _best_book_markets(data.get("bookmakerOdds", {}))
    market = markets.get("10208") or markets.get(10208)
    if not isinstance(market, dict):
        _ODDS_CACHE[cache_key] = None
        return None
    outcomes = market.get("outcomes") or {}
    iterable = outcomes.values() if isinstance(outcomes, dict) else outcomes if isinstance(outcomes, list) else []
    best = None
    for outcome in iterable:
        if not isinstance(outcome, dict):
            continue
        players = outcome.get("players") or {}
        plist = players.values() if isinstance(players, dict) else players if isinstance(players, list) else [outcome]
        for player in plist:
            if not isinstance(player, dict) or not player.get("active", True):
                continue
            designation = str(player.get("designation") or outcome.get("designation") or player.get("name") or outcome.get("name") or "").lower()
            if "over" not in designation and designation not in {"o", "1"}:
                continue
            point = player.get("point")
            if point is None: point = player.get("line")
            if point is None: point = player.get("handicap")
            if point is None: point = outcome.get("point")
            if point is None: point = outcome.get("line")
            try:
                if point is None or abs(float(point) - float(line)) > 0.01:
                    continue
                price = float(player.get("price") or outcome.get("price") or 0)
            except Exception:
                continue
            if price > 1 and (best is None or price > best):
                best = round(price, 3)
    _ODDS_CACHE[cache_key] = best
    return best


__all__.append("get_corner_quote_for_match")
