"""
NETRATTLER — Extra Player-Prop Sources (fault-tolerant fallback chain)
=====================================================================

Ziel: Zusaetzliche Player-Prop-Quellen neben Pinnacle und bet365/SofaScore.
Jede Quelle ist in try/except gekapselt: liefert sie nichts (Block, Timeout,
Strukturaenderung), wird sie uebersprungen und die naechste probiert.

Alle Quellen geben dasselbe normalisierte Dict-Format zurueck, damit sie
direkt in _ntr_collect_prop() / den Builder-Pool wandern koennen:

    {
        "player":   "Lamine Yamal",
        "team":     "",
        "match":    "Spain vs Argentina",
        "league":   "",
        "market":   "Player Shots on Target",
        "category": "sot",
        "line":     1.5,
        "odds":     2.1,
        "source":   "kambi_unibet",
    }

Kein Modul-Import darf den Bot brechen: btts_bot importiert dies in try/except.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


# ------------------------------------------------------------------
# HTTP-Helfer: nutzt cloudscraper falls vorhanden, sonst requests.
# ------------------------------------------------------------------
def _session():
    try:
        import cloudscraper as _cs
        return _cs.create_scraper()
    except Exception:
        if requests is None:
            return None
        return requests.Session()


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 12):
    sess = _session()
    if sess is None:
        return None
    try:
        r = sess.get(url, params=params or {}, headers=_HEADERS, timeout=timeout)
        if not r.ok:
            return None
        return r.json()
    except Exception:
        return None


# ------------------------------------------------------------------
# Gemeinsamer Kategorie-Mapper (quellen-unabhaengig).
# Haelt die Kategorien synchron mit _SHARP_PLAYER_CATS_V31 im Builder.
# ------------------------------------------------------------------
def map_category(text: str) -> str:
    low = str(text or "").lower()
    # Team-/Matchmaerkte zuerst aussortieren.
    if "both teams" in low or "either team" in low or "team to score" in low:
        return "other"
    if ("outside box" in low or "outside the box" in low or "from outside" in low) and (
        "shot on target" in low or "shots on target" in low
    ):
        return "sot_outside_box"
    if "shots on target" in low or "shot on target" in low or "on target" in low:
        return "sot"
    if "headed" in low and "shot" in low:
        return "sot"
    if "shot" in low:
        return "shots"
    if "tackles received" in low or "to be tackled" in low:
        return "tackles_received"
    if "tackle" in low:
        return "tackles_committed"
    if "fouls won" in low or "to be fouled" in low or "fouled" in low:
        return "fouls_won"
    if "foul" in low:
        return "fouls"
    if "booking" in low or "booked" in low or "carded" in low or "card" in low:
        return "yellow_cards"
    if "first goalscorer" in low or "first scorer" in low:
        return "first_scorer"
    if "last goalscorer" in low or "last scorer" in low:
        return "last_scorer"
    if "goalscorer" in low or "to score" in low or "anytime scorer" in low:
        return "score"
    if "assist" in low:
        return "assist"
    if "save" in low:
        return "saves"
    if "offside" in low:
        return "offsides"
    if "pass" in low:
        return "passes"
    return "other"


def _line_from(text: str, default: float = 0.5) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
    return float(m.group(1)) if m else float(default)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _teams_match(cand: str, home: str, away: str) -> bool:
    c = _norm(cand)
    h, a = _norm(home), _norm(away)
    if not c or not h or not a:
        return False
    h_ok = h[:6] in c or c[:6] in h if len(h) >= 4 else h in c
    a_ok = a[:6] in c or c[:6] in a if len(a) >= 4 else a in c
    return bool(h_ok and a_ok)


# ==================================================================
# QUELLE: Kambi (powers Unibet, Betsson, NordicBet, ComeOn, Rizk ...)
#   Oeffentliche offering-API, sauberes JSON, kein Login.
# ==================================================================
_KAMBI_BRANDS = ["ub", "bs", "888", "nb"]  # unibet, betsson, 888sport, nordicbet
_KAMBI_HOSTS = [
    "https://eu-offering-api.kambicdn.com",
    "https://e0-api.kambi.com",
]


def fetch_kambi_player_props(home: str, away: str, brand: str = "ub") -> List[Dict[str, Any]]:
    """Holt Player-Props fuer ein Spiel ueber die Kambi offering-API."""
    props: List[Dict[str, Any]] = []
    event_id = None
    host_used = None
    for host in _KAMBI_HOSTS:
        data = _get_json(
            f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
            params={"lang": "en_GB", "market": "GB"},
        )
        if not data:
            continue
        events = data.get("events") or []
        for ev in events:
            e = ev.get("event") or ev
            name = e.get("name") or e.get("englishName") or ""
            home_n = e.get("homeName") or ""
            away_n = e.get("awayName") or ""
            combo = f"{home_n} {away_n}".strip() or name.replace(" - ", " ")
            if _teams_match(combo, home, away):
                event_id = e.get("id")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return []

    offer = _get_json(
        f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
        params={"lang": "en_GB", "market": "GB"},
    )
    if not offer:
        return []

    match_name = f"{home} vs {away}"
    for bo in offer.get("betOffers") or []:
        crit = (bo.get("criterion") or {}).get("label", "")
        cat = map_category(crit)
        if cat == "other":
            continue
        for oc in bo.get("outcomes") or []:
            player = oc.get("participant") or oc.get("label") or ""
            if not player or str(oc.get("label", "")).lower() in {"under", "no"}:
                continue
            try:
                odds = float(oc.get("odds", 0)) / 1000.0  # Kambi: millidds
            except (TypeError, ValueError):
                continue
            if odds <= 1.20:
                continue
            line = oc.get("line")
            line = float(line) / 1000.0 if line else _line_from(oc.get("label", ""), 0.5)
            props.append({
                "player": player, "team": "", "match": match_name, "league": "",
                "market": crit, "category": cat, "line": line, "odds": odds,
                "source": f"kambi_{brand}",
            })
    return props


# ==================================================================
# QUELLE: 1xbet-Familie (Melbet, Megapari, 888starz, Betwinner ...)
#   LineFeed-JSON. Groesste Prop-Tiefe, aber Bot-Schutz auf Single-IP.
# ==================================================================
_1X_HOSTS = ["https://1xbet.com", "https://ind.1xbet.com", "https://melbet.com"]
# 1xbet bet-group IDs fuer Player-Props (aus dem LineFeed-Schema):
_1X_PLAYER_GROUPS = {
    2059: "shots", 2060: "sot", 2061: "fouls", 2062: "tackles",
    2101: "yellow_cards", 15: "score", 2201: "offsides", 2205: "passes",
}


def fetch_1xbet_player_props(home: str, away: str) -> List[Dict[str, Any]]:
    """Best-effort Player-Props aus dem 1xbet LineFeed (JSON)."""
    props: List[Dict[str, Any]] = []
    event_id = None
    host_used = None
    for host in _1X_HOSTS:
        data = _get_json(
            f"{host}/LineFeed/Get1x2_VZip",
            params={"sports": 1, "count": 500, "lng": "en", "mode": 4, "country": 1},
        )
        if not data:
            continue
        for g in (data.get("Value") or []):
            o1 = g.get("O1") or g.get("HomeTeam") or ""
            o2 = g.get("O2") or g.get("AwayTeam") or ""
            if _teams_match(f"{o1} {o2}", home, away):
                event_id = g.get("I") or g.get("CI")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return []

    game = _get_json(
        f"{host_used}/LineFeed/GetGameZip",
        params={"id": event_id, "lng": "en", "cfview": 0, "grMode": 4, "country": 1},
    )
    if not game:
        return []
    val = game.get("Value") or {}
    match_name = f"{home} vs {away}"
    # Player-Props liegen in GE (GroupEvents) / E (Events) mit Spielernamen im PN-Feld.
    for grp in (val.get("GE") or []):
        gid = grp.get("G")
        cat = _1X_PLAYER_GROUPS.get(gid) or map_category(grp.get("GS", ""))
        if cat == "other":
            continue
        for row in (grp.get("E") or []):
            for e in (row if isinstance(row, list) else [row]):
                player = e.get("PN") or e.get("P") or ""
                try:
                    odds = float(e.get("C", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if not player or odds <= 1.20:
                    continue
                line = e.get("P") if isinstance(e.get("P"), (int, float)) else _line_from(e.get("PN", ""), 0.5)
                props.append({
                    "player": str(player), "team": "", "match": match_name, "league": "",
                    "market": grp.get("GS", cat), "category": cat,
                    "line": float(line or 0.5), "odds": odds, "source": "1xbet",
                })
    return props


# ==================================================================
# Einheitliche Sammel-Funktion: probiert alle Quellen der Reihe nach.
# ==================================================================
def collect_extra_player_props(
    fixtures: List[Dict[str, str]],
    log: Optional[Callable[[str], Any]] = None,
    max_matches: int = 12,
) -> List[Dict[str, Any]]:
    """
    fixtures: Liste von {"home","away"} (optional "league").
    Gibt alle Player-Props aller erreichbaren Quellen zurueck.
    Jede Quelle ist gekapselt — Fehler einer Quelle stoppt die Kette nicht.
    """
    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    sources = [
        ("kambi", lambda h, a: fetch_kambi_player_props(h, a, brand="ub")),
        ("1xbet", lambda h, a: fetch_1xbet_player_props(h, a)),
    ]
    out: List[Dict[str, Any]] = []
    per_source: Dict[str, int] = {}

    for fx in (fixtures or [])[:max_matches]:
        home = str(fx.get("home", "")).strip()
        away = str(fx.get("away", "")).strip()
        if not home or not away:
            continue
        for name, fn in sources:
            try:
                rows = fn(home, away) or []
            except Exception as exc:
                _log(f"   🔌 {name} Fehler ({home} vs {away}): {str(exc)[:60]}")
                rows = []
            if rows:
                out.extend(rows)
                per_source[name] = per_source.get(name, 0) + len(rows)

    if per_source:
        summary = ", ".join(f"{k}={v}" for k, v in per_source.items())
        _log(f"   🔌 Extra-Prop-Quellen: {summary} ({len(out)} Legs gesamt)")
    return out


__all__ = [
    "fetch_kambi_player_props",
    "fetch_1xbet_player_props",
    "collect_extra_player_props",
    "map_category",
]
