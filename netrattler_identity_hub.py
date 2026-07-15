#!/usr/bin/env python3
"""
NETRATTLER Identity Hub V30
===========================
Providerübergreifendes Team-/Spieler-Matching für NETRATTLER.

Ziele:
- England darf niemals mit New England Revolution II matchen.
- Nationalteams werden strikt behandelt.
- Club-Aliase, OpenFootball-Names, REEP-/Transfermarkt-/FBref-/SofaScore-Namen
  können über dieselbe Normalisierung laufen.
- Funktioniert offline; optionale Drittbibliotheken sind nicht erforderlich.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from rapidfuzz import fuzz, process  # type: ignore
except Exception:  # pragma: no cover - optional
    fuzz = None
    process = None

ROMAN_REPLACEMENTS = {
    " ii": " 2", " iii": " 3", " iv": " 4",
    " u21": " u 21", " u20": " u 20", " u19": " u 19",
}

COUNTRY_ALIASES: Dict[str, str] = {
    "england national team": "england",
    "england men": "england",
    "england": "england",
    "argentina national team": "argentina",
    "argentina men": "argentina",
    "argentine": "argentina",
    "france national team": "france",
    "spain national team": "spain",
    "deutschland": "germany",
    "germany national team": "germany",
    "brasil": "brazil",
    "brazil national team": "brazil",
    "nederland": "netherlands",
    "netherlands national team": "netherlands",
    "usa": "united states",
    "u s a": "united states",
    "usmnt": "united states",
    "swiss": "switzerland",
}

NATIONAL_TEAMS = {
    "england", "argentina", "france", "spain", "germany", "brazil",
    "portugal", "italy", "netherlands", "belgium", "switzerland",
    "norway", "sweden", "morocco", "mexico", "colombia", "uruguay",
    "paraguay", "canada", "united states", "japan", "australia", "egypt",
    "ghana", "senegal", "south africa", "cote d ivoire", "ivory coast",
    "croatia", "austria", "algeria", "cape verde", "dr congo", "congo dr",
}

CLUB_ALIASES: Dict[str, str] = {
    "new england revolution ii": "new england revolution 2",
    "new england rev ii": "new england revolution 2",
    "new england ii": "new england revolution 2",
    "columbus crew ii": "columbus crew 2",
    "columbus ii": "columbus crew 2",
    "ldu de quito": "ldu quito",
    "liga de quito": "ldu quito",
    "universidad catolica ecuador": "universidad catolica del ecuador",
    "barcelona guayaquil": "barcelona sc",
    "athletico pr": "athletico paranaense",
    "athletico paranaense pr": "athletico paranaense",
}

# Optional runtime aliases loaded from OpenFootball/REEP/our generated cache.
_DYNAMIC_TEAM_ALIASES: Dict[str, str] = {}
_DYNAMIC_PLAYER_ALIASES: Dict[str, str] = {}

STOPWORDS = {
    "fc", "cf", "ac", "sc", "sv", "afc", "cfc", "club", "football", "futbol",
    "soccer", "team", "national", "men", "women", "w", "reserves", "reserve",
    "the", "de", "del", "da", "do", "du", "la", "le", "el", "cd", "ud",
}


def strip_accents(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def canonical_text(value: Any) -> str:
    text = strip_accents(value).lower().replace("&", " and ").strip()
    text = text.replace("ß", "ss")
    for old, new in ROMAN_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = re.sub(r"\b(u)[- ]?(\d{2})\b", r"u \2", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_team_name(name: Any, *, strict_country: bool = True) -> str:
    text = canonical_text(name)
    if not text:
        return ""
    text = COUNTRY_ALIASES.get(text, text)
    text = CLUB_ALIASES.get(text, text)
    text = _DYNAMIC_TEAM_ALIASES.get(text, text)

    # Remove common club legal words but keep identity words like "new".
    tokens = [t for t in text.split() if t not in STOPWORDS]
    text = " ".join(tokens)
    text = COUNTRY_ALIASES.get(text, text)
    text = CLUB_ALIASES.get(text, text)
    text = _DYNAMIC_TEAM_ALIASES.get(text, text)
    return text


def normalize_player_name(name: Any) -> str:
    text = canonical_text(name)
    return _DYNAMIC_PLAYER_ALIASES.get(text, text)


def is_national_team_name(name: Any) -> bool:
    n = normalize_team_name(name)
    return n in NATIONAL_TEAMS


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if fuzz is not None:
        try:
            return float(fuzz.token_set_ratio(a, b)) / 100.0
        except Exception:
            pass
    return SequenceMatcher(None, a, b).ratio()


def teams_match(name1: Any, name2: Any, *, league: str = "", threshold: float = 0.86) -> bool:
    """Conservative provider matching with national-team guard."""
    n1 = normalize_team_name(name1)
    n2 = normalize_team_name(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True

    # Hard guard: England != New England. Nationalteams only match exact country aliases.
    if n1 in NATIONAL_TEAMS or n2 in NATIONAL_TEAMS:
        return n1 == n2

    # Prevent short country token from matching a club containing it.
    if ("england" in {n1, n2}) and ("new england" in (n1 + " " + n2)):
        return False

    t1, t2 = set(n1.split()), set(n2.split())
    common = t1 & t2
    if len(common) >= 2 and len(common) / max(1, min(len(t1), len(t2))) >= 0.67:
        return True
    if len(n1) >= 9 and len(n2) >= 9 and (n1 in n2 or n2 in n1):
        return True
    return _ratio(n1, n2) >= threshold


def best_team_match(query: Any, candidates: Iterable[Any], *, league: str = "", min_score: float = 0.86) -> Optional[Tuple[str, float]]:
    q = normalize_team_name(query)
    if not q:
        return None
    best_name = None
    best_score = 0.0
    for cand in candidates:
        cn = normalize_team_name(cand)
        if not cn:
            continue
        if teams_match(q, cn, league=league):
            score = 1.0 if q == cn else max(_ratio(q, cn), 0.90)
        else:
            score = _ratio(q, cn)
        if score > best_score:
            best_name, best_score = str(cand), score
    if best_name is not None and best_score >= min_score:
        return best_name, best_score
    return None


def player_key(player: Any, team: Any = "", provider: str = "") -> str:
    return "|".join(x for x in [normalize_player_name(player), normalize_team_name(team), canonical_text(provider)] if x)


def load_aliases(payload: Dict[str, Any]) -> None:
    """Load generated alias maps. Format: {team_aliases:{alias:canonical}, player_aliases:{...}}."""
    for alias, canonical in (payload.get("team_aliases") or {}).items():
        a = normalize_team_name(alias, strict_country=False)
        c = normalize_team_name(canonical, strict_country=False)
        if a and c:
            _DYNAMIC_TEAM_ALIASES[a] = c
    for alias, canonical in (payload.get("player_aliases") or {}).items():
        a = normalize_player_name(alias)
        c = normalize_player_name(canonical)
        if a and c:
            _DYNAMIC_PLAYER_ALIASES[a] = c


def explain_match(name1: Any, name2: Any) -> Dict[str, Any]:
    n1, n2 = normalize_team_name(name1), normalize_team_name(name2)
    return {"a": str(name1), "b": str(name2), "norm_a": n1, "norm_b": n2, "match": teams_match(name1, name2), "score": round(_ratio(n1, n2), 3)}


__all__ = [
    "normalize_team_name", "normalize_player_name", "teams_match", "best_team_match",
    "player_key", "is_national_team_name", "load_aliases", "explain_match",
]
