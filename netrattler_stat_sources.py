"""
NETRATTLER — Aggregierte Saison-Statistik-Quellen (StatBunker)
==============================================================

Liefert aggregierte Saison-Werte pro Spieler (Fouls, Tackles, Shots, SOT,
Karten, Minuten) — ideal als zusaetzliche Trainings-Features und als Fallback,
wenn player_avg_stats (aus scrape_player_stats) fuer einen Spieler duenn ist.

Format pro Spieler (kompatibel mit get_supabase_player_avg_stats-Nutzung):
    {
        "shots":  {"avg": 2.6, "games": 20},
        "sot":    {"avg": 1.1, "games": 20},
        "fouls":  {"avg": 1.3, "games": 20},
        "tackles":{"avg": 1.8, "games": 20},
        ...
    }

Fehlertolerant: jede Quelle in try/except, Fehler -> {} zurueck.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
}

_STATBUNKER_HOSTS = [
    "https://www.statbunker.com",
    "https://footballbettingdata.co.uk",
]

# In-Memory-Cache pro Prozess: {league_key: {player_norm: statdict}}
_SB_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _session():
    try:
        import cloudscraper as _cs
        return _cs.create_scraper()
    except Exception:
        return requests.Session() if requests else None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _num(x, default=0.0) -> float:
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _fetch(url: str, params: Optional[dict] = None, timeout: int = 15):
    sess = _session()
    if sess is None:
        return None
    try:
        r = sess.get(url, params=params or {}, headers=_HEADERS, timeout=timeout)
        if not r.ok:
            return None
        return r
    except Exception:
        return None


def fetch_statbunker_player_stats(player: str, league_hint: str = "") -> Dict[str, Any]:
    """
    Aggregierte Saison-Stats fuer EINEN Spieler.
    Sucht ueber die StatBunker-Suchseite; parst die relevanten Kennzahlen.
    Gibt {} zurueck, wenn nichts gefunden (dann greift der bestehende Supabase-Wert).
    """
    if not player:
        return {}
    pn = _norm(player)
    # Cache pruefen
    for tbl in _SB_CACHE.values():
        if pn in tbl:
            return tbl[pn]

    for host in _STATBUNKER_HOSTS:
        r = _fetch(f"{host}/competitions/search", params={"q": player})
        if r is None:
            continue
        html = r.text
        # StatBunker-Tabellen tragen die Kennzahlen als <td>-Werte neben Labels.
        # Robuster Ansatz: Labels -> nachfolgende Zahl per Regex ziehen.
        def grab(*labels) -> float:
            for lab in labels:
                m = re.search(
                    rf"{lab}\s*</[^>]+>\s*<[^>]+>\s*([0-9][0-9.,]*)",
                    html, re.IGNORECASE,
                )
                if not m:
                    m = re.search(rf"{lab}[^0-9]{{0,40}}([0-9][0-9.,]*)", html, re.IGNORECASE)
                if m:
                    return _num(m.group(1))
            return 0.0

        games = grab("Appearances", "Games Played", "Matches", "Apps")
        if games <= 0:
            continue
        stats = {
            "shots":            {"avg": grab("Shots per Game", "Total Shots") / (games if grab("Total Shots") else 1), "games": games},
            "sot":              {"avg": grab("Shots On Target per Game", "Shots on Target") / (games if grab("Shots on Target") else 1), "games": games},
            "fouls":            {"avg": grab("Fouls per Game", "Fouls Committed") / (games if grab("Fouls Committed") else 1), "games": games},
            "fouls_committed":  {"avg": grab("Fouls per Game", "Fouls Committed") / (games if grab("Fouls Committed") else 1), "games": games},
            "fouls_won":        {"avg": grab("Fouls Won", "Fouled") / (games if grab("Fouls Won") else 1), "games": games},
            "tackles":          {"avg": grab("Tackles per Game", "Total Tackles") / (games if grab("Total Tackles") else 1), "games": games},
            "cards":            {"avg": grab("Yellow Cards", "Cards") / (games if grab("Yellow Cards") else 1), "games": games},
            "minutes":          {"avg": grab("Minutes per Game", "Minutes"), "games": games},
        }
        # nur sinnvolle Werte behalten
        stats = {k: v for k, v in stats.items() if v["avg"] > 0}
        if stats:
            _SB_CACHE.setdefault(league_hint or "all", {})[pn] = stats
            return stats
    return {}


def merge_stats(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Ergaenzt primary (z.B. Supabase) um fehlende Keys aus fallback (StatBunker)."""
    if not fallback:
        return primary or {}
    out = dict(primary or {})
    for k, v in fallback.items():
        if k not in out or not (out.get(k) or {}).get("avg"):
            out[k] = v
    return out


__all__ = ["fetch_statbunker_player_stats", "merge_stats"]
