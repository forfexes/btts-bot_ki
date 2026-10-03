"""
NETRATTLER — Transfermarkt National Team Props
===============================================
Holt Nationalteam-Kader + Spieler-Stammdaten von Transfermarkt.
Liefert Prop-Kandidaten (Starter, Marktwert, Einsatzminuten) für den Builder-Pool.

Ausgabe: Liste von Dicts kompatibel mit _ntr_collect_prop():
    {
        "player":   "Lamine Yamal",
        "team":     "Spain",
        "match":    "Spain vs France",
        "league":   "UEFA Nations League",
        "market":   "Player Shots on Target",
        "category": "sot",
        "line":     0.5,
        "odds":     0.0,        # keine echten Quoten — nur Kandidaten
        "source":   "transfermarkt_nt",
        "market_value_m": 120,  # Marktwert in Mio. EUR
        "minutes_l5": 450,      # Einsatzminuten letzte 5 NT-Spiele
        "position":  "AM",
        "is_starter": True,
    }

Nur non-fatal: jeder Fehler wird geloggt und übersprungen.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup as _BS
    _BS_AVAILABLE = True
except ImportError:
    _BS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
_BASE = "https://www.transfermarkt.com"
_SEARCH = f"{_BASE}/schnellsuche/ergebnis/schnellsuche"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_TIMEOUT = 14
_CACHE: Dict[str, Any] = {}
_BLOCKED = False

# Offizielle TM-Slugs für häufige Nationalteams (Fallback wenn Suche fehlschlägt)
_KNOWN_NT_SLUGS: Dict[str, str] = {
    "germany":      "deutschland/startseite/verein/3262",
    "france":       "frankreich/startseite/verein/3377",
    "spain":        "spanien/startseite/verein/3375",
    "england":      "england/startseite/verein/3",
    "portugal":     "portugal/startseite/verein/8695",
    "italy":        "italien/startseite/verein/3376",
    "netherlands":  "niederlande/startseite/verein/4465",
    "brazil":       "brasilien/startseite/verein/3439",
    "argentina":    "argentinien/startseite/verein/3437",
    "belgium":      "belgien/startseite/verein/3382",
    "croatia":      "kroatien/startseite/verein/4878",
    "switzerland":  "schweiz/startseite/verein/3384",
    "austria":      "oesterreich/startseite/verein/3383",
    "poland":       "polen/startseite/verein/4353",
    "denmark":      "daenemark/startseite/verein/4861",
    "sweden":       "schweden/startseite/verein/4380",
    "norway":       "norwegen/startseite/verein/4862",
    "turkey":       "tuerkei/startseite/verein/4377",
    "ukraine":      "ukraine/startseite/verein/5385",
    "slovakia":     "slowakei/startseite/verein/4385",
    "czechia":      "tschechien/startseite/verein/4867",
    "serbia":       "serbien/startseite/verein/4380",
    "usa":          "vereinigte-staaten/startseite/verein/3633",
    "mexico":       "mexiko/startseite/verein/5765",
    "japan":        "japan/startseite/verein/9674",
    "south korea":  "suedkorea/startseite/verein/9682",
    "morocco":      "marokko/startseite/verein/28695",
    "senegal":      "senegal/startseite/verein/28702",
}

# Märkte die aus Transfermarkt-Daten abgeleitet werden
_MARKETS_FROM_TM = [
    ("Player Shots on Target", "sot", 0.5),
    ("Player Shots", "shots", 1.5),
    ("Player to be Booked", "yellow_cards", 0.5),
    ("Anytime Goalscorer", "score", 0.5),
]

# Minimaler Marktwert (Mio. EUR) um als Starter-Kandidat zu gelten
_MIN_MV_STARTER_M = 5.0
# Top-N nach Marktwert = wahrscheinliche Startelf
_TOP_N_STARTERS = 11


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower()).strip()


def _sess():
    if _requests is None:
        return None
    try:
        import cloudscraper as _cs
        return _cs.create_scraper()
    except Exception:
        s = _requests.Session()
        s.headers.update(_HEADERS)
        return s


def _get(url: str, params: Optional[dict] = None, timeout: int = _TIMEOUT) -> Optional[str]:
    global _BLOCKED
    if _BLOCKED:
        return None
    s = _sess()
    if s is not None:
        try:
            r = s.get(url, params=params or {}, headers=_HEADERS, timeout=timeout)
            if r.status_code in (403, 429, 503):
                pass  # Fallback zu curl_cffi unten
            elif r.ok:
                return r.text
        except Exception:
            pass

    # curl_cffi Chrome-Impersonation als Fallback (umgeht Cloudflare)
    try:
        from curl_cffi import requests as _creq
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(params)}" if params else url
        r2 = _creq.get(full_url, headers=_HEADERS, impersonate="chrome", timeout=timeout)
        if r2.status_code == 200:
            return r2.text
        if r2.status_code in (403, 429, 503):
            _BLOCKED = True
    except Exception:
        pass

    return None


def _parse_market_value(text: str) -> float:
    """'€120.00m' → 120.0  |  '€500k' → 0.5  |  fallback 0.0"""
    t = str(text or "").lower().replace(",", ".")
    m = re.search(r"[\d.]+", t)
    if not m:
        return 0.0
    val = float(m.group())
    if "k" in t:
        val /= 1000
    return round(val, 2)


def _slug_for_team(team_name: str) -> Optional[str]:
    """Gibt TM-Slug zurück: erst Cache, dann bekannte Slugs, dann Suche."""
    key = _norm(team_name)
    if key in _CACHE:
        return _CACHE[key]

    # Bekannte Slugs
    for known, slug in _KNOWN_NT_SLUGS.items():
        if known in key or key in known:
            _CACHE[key] = slug
            return slug

    # Transfermarkt Schnellsuche
    html = _get(_SEARCH, {"query": team_name, "Datei": "Verein"})
    if not html:
        return None

    if _BS_AVAILABLE:
        soup = _BS(html, "html.parser")
        for a in soup.select("table.items td.hauptlink a"):
            href = a.get("href", "")
            if "/startseite/verein/" in href:
                slug = href.lstrip("/")
                _CACHE[key] = slug
                return slug
    else:
        m = re.search(r'href="(/[^"]+/startseite/verein/\d+)"', html)
        if m:
            slug = m.group(1).lstrip("/")
            _CACHE[key] = slug
            return slug

    return None


def _fetch_squad(team_name: str) -> List[Dict[str, Any]]:
    """
    Holt Kader-Seite von TM und extrahiert:
    - Spielername, Position, Marktwert, Nationalität
    Gibt Liste von Dicts zurück.
    """
    slug = _slug_for_team(team_name)
    if not slug:
        return []

    cache_key = f"squad_{slug}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = f"{_BASE}/{slug}"
    html = _get(url)
    if not html:
        return []

    players = []

    if _BS_AVAILABLE:
        soup = _BS(html, "html.parser")
        for row in soup.select("table.items tbody tr"):
            try:
                name_el = row.select_one("td.hauptlink a")
                pos_el = row.select_one("td[title]")
                mv_el = row.select_one("td.rechts.hauptlink")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                pos = pos_el.get("title", "") if pos_el else ""
                mv = _parse_market_value(mv_el.get_text() if mv_el else "")
                players.append({"name": name, "position": pos, "market_value_m": mv})
            except Exception:
                continue
    else:
        # Regex-Fallback
        for m in re.finditer(
            r'class="hauptlink"[^>]*>\s*<a[^>]+>([^<]+)</a>.*?'
            r'class="rechts hauptlink"[^>]*>([^<]+)<',
            html, re.DOTALL
        ):
            name = m.group(1).strip()
            mv = _parse_market_value(m.group(2))
            if name:
                players.append({"name": name, "position": "", "market_value_m": mv})

    # Sortiere nach Marktwert → Top-11 = Starter
    players.sort(key=lambda p: p["market_value_m"], reverse=True)
    for i, p in enumerate(players):
        p["is_starter"] = (i < _TOP_N_STARTERS and p["market_value_m"] >= _MIN_MV_STARTER_M)

    _CACHE[cache_key] = players
    return players


def _position_to_markets(pos: str) -> List[tuple]:
    """Gibt relevante Märkte nach Position zurück."""
    p = _norm(pos)
    if any(x in p for x in ("torwart", "goalkeeper", "gk", "keeper")):
        return []  # Keeper keine Player-Props
    if any(x in p for x in ("sturm", "forward", "striker", "centre-forward", "attacker")):
        return [
            ("Anytime Goalscorer", "score", 0.5),
            ("Player Shots on Target", "sot", 0.5),
            ("Player Shots", "shots", 1.5),
        ]
    if any(x in p for x in ("mittelfeld", "midfield", "attacking mid", "winger", "flügel")):
        return [
            ("Player Shots on Target", "sot", 0.5),
            ("Player Shots", "shots", 1.5),
            ("Player to be Booked", "yellow_cards", 0.5),
        ]
    if any(x in p for x in ("verteidiger", "defender", "back", "centre-back")):
        return [
            ("Player to be Booked", "yellow_cards", 0.5),
        ]
    # Unbekannt → Standard
    return [
        ("Player Shots on Target", "sot", 0.5),
        ("Player to be Booked", "yellow_cards", 0.5),
    ]


def fetch_transfermarkt_nt_props(
    home: str,
    away: str,
    league: str = "",
    log: Optional[Callable[[str], Any]] = None,
    only_starters: bool = True,
    max_players_per_team: int = 8,
) -> List[Dict[str, Any]]:
    """
    Hauptfunktion: Holt Nationalteam-Kader beider Teams von TM
    und gibt Prop-Kandidaten zurück.

    Args:
        home: Heimteam (z.B. "Spain")
        away: Auswärtsteam (z.B. "France")
        league: Liga-Name (z.B. "UEFA Nations League")
        log: optionale Log-Funktion
        only_starters: Nur wahrscheinliche Starter (Top-11 nach Marktwert)
        max_players_per_team: Max. Spieler pro Team im Output

    Returns:
        Liste von Prop-Kandidaten (kein odds-Feld = 0.0, kein clash mit echten Props)
    """
    global _BLOCKED
    if _BLOCKED:
        return []

    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    match_name = f"{home} vs {away}"
    out: List[Dict[str, Any]] = []

    for team_name in (home, away):
        squad = _fetch_squad(team_name)
        if not squad:
            _log(f"   🌍 TM-NT: Kein Kader für {team_name}")
            continue

        _log(f"   🌍 TM-NT: {team_name} — {len(squad)} Spieler, "
             f"{sum(1 for p in squad if p.get('is_starter'))} Starter")

        candidates = [p for p in squad if (not only_starters or p.get("is_starter"))]
        candidates = candidates[:max_players_per_team]

        for player in candidates:
            name = player.get("name", "")
            pos = player.get("position", "")
            mv = player.get("market_value_m", 0.0)
            is_starter = player.get("is_starter", False)

            markets = _position_to_markets(pos) or _MARKETS_FROM_TM[:2]

            for market, category, line in markets:
                out.append({
                    "player":          name,
                    "team":            team_name,
                    "match":           match_name,
                    "league":          league,
                    "market":          market,
                    "category":        category,
                    "line":            line,
                    "odds":            0.0,      # kein echter Kurs — nur Kandidat
                    "source":          "transfermarkt_nt",
                    "market_value_m":  mv,
                    "position":        pos,
                    "is_starter":      is_starter,
                })

        time.sleep(0.3)  # Rate-limit

    _log(f"   🌍 TM-NT: {match_name} → {len(out)} Prop-Kandidaten")
    return out


def is_international_match(league: str) -> bool:
    """Prüft ob eine Liga ein internationales/Nationalteam-Turnier ist."""
    l = _norm(league)
    keywords = (
        "nations league", "world cup", "wm", "copa", "euro", "euros",
        "afc", "asian cup", "africa cup", "afcon", "concacaf", "gold cup",
        "friendl", "freundschaft", "international", "national",
        "qualif", "qualification",
    )
    return any(k in l for k in keywords)


__all__ = [
    "fetch_transfermarkt_nt_props",
    "is_international_match",
]
