"""
NETRATTLER — Rollen-Kontext (Favorit vs. Außenseiter)
=====================================================

Kernidee (aus der Analyse von Nate/Aystar-Buildern):
In einem klaren Favorit-vs-Außenseiter-Spiel sind die Rollen vorhersehbar:
  • Favorit dominiert  → Angreifer: shots, sot, fouls_won, score, assist
  • Außenseiter verteidigt → fouls, tackles, cards, interceptions, clearances, duels
In einem ausgeglichenen Spiel (Top vs Top):
  • Beide Seiten: tackles, fouls, cards (umkämpftes Mittelfeld) + Angreifer shots

Schalter ist die Elo-Differenz (aus team_elo_history / ClubElo).

Dieses Modul liefert:
  • elo/elo_diff/favorite/game_type für ein Match
  • role_fit(category, player_team, home, away) → Prior 0..1, wie gut ein Prop
    zur erwarteten Rolle passt
Die Prioren sind bewusst als START-Gewichte gedacht: der Bot verschiebt sie über
die Settlement-/Builder-Learning-Schleife (welche Rollen-Props real gewinnen).

Fehlertolerant: fehlt Elo oder Team → neutrale Rückgabe (0.0 Boost), bricht nie.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").lower().strip())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


# ---- Elo-Cache (pro Prozess) -----------------------------------------------
_ELO: Dict[str, float] = {}
_ELO_LOADED = False


def load_team_elo(supabase_url: str = "", supabase_key: str = "") -> int:
    """Lädt {team_norm: elo} aus team_elo_history (neuester Wert je Team)."""
    global _ELO_LOADED
    if _ELO_LOADED:
        return len(_ELO)
    _ELO_LOADED = True
    url = supabase_url or os.getenv("SUPABASE_URL", "")
    key = supabase_key or os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key or requests is None:
        return 0
    try:
        r = requests.get(
            f"{url.rstrip('/')}/rest/v1/team_elo_history",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"select": "team_name,elo,rating_date", "order": "rating_date.desc", "limit": "20000"},
            timeout=30,
        )
        if not r.ok:
            return 0
        for row in r.json():
            tn = _norm(row.get("team_name", ""))
            if not tn or tn in _ELO:
                continue  # erster = neuester (desc)
            try:
                _ELO[tn] = float(row.get("elo") or 0)
            except (TypeError, ValueError):
                continue
    except Exception:
        return 0
    return len(_ELO)


def team_elo(team: str) -> Optional[float]:
    tn = _norm(team)
    if tn in _ELO:
        return _ELO[tn]
    # unscharfer Treffer (Präfix)
    for k, v in _ELO.items():
        if len(tn) >= 5 and (tn[:6] in k or k[:6] in tn):
            return v
    return None


def elo_diff(home: str, away: str) -> Optional[float]:
    eh, ea = team_elo(home), team_elo(away)
    if eh is None or ea is None:
        return None
    return eh - ea


def favorite(home: str, away: str) -> Optional[str]:
    """Gibt den Namen des Favoriten zurück (home/away-String) oder None."""
    d = elo_diff(home, away)
    if d is None:
        return None
    # Heimvorteil ~ 60-70 Elo-Punkte einpreisen
    d_adj = d + 65
    if d_adj > 0:
        return home
    return away


# Schwellen (Elo-Punkte) für Einseitigkeit — env-tunebar
def _onesided_threshold() -> float:
    try:
        return float(os.getenv("NETRATTLER_ONESIDED_ELO", "120"))
    except ValueError:
        return 120.0


def game_type(home: str, away: str) -> str:
    """'one_sided' | 'balanced' | 'unknown'."""
    d = elo_diff(home, away)
    if d is None:
        return "unknown"
    return "one_sided" if abs(d + 65) >= _onesided_threshold() else "balanced"


# ---- Rollen-Prioren ---------------------------------------------------------
# Angriffs- vs. Defensiv-/Kampf-Kategorien
_ATTACK = {"shots", "sot", "sot_outside_box", "shots_outside_box", "score",
           "first_scorer", "last_scorer", "assist", "score_assist", "fouls_won",
           "crosses", "key_passes", "offsides"}
_DEFENSE = {"fouls", "fouls_committed", "tackles", "tackles_committed",
            "tackles_received", "yellow_cards", "cards", "interceptions",
            "clearances", "duels", "duels_won", "saves"}


def role_fit(category: str, player_team: str, home: str, away: str) -> float:
    """
    Prior 0..1: wie gut passt dieser Prop zur erwarteten Spielzustand-Rolle.
    0.5 = neutral (keine Info). >0.5 = passt, <0.5 = passt schlecht.
    """
    cat = str(category or "").lower()
    gt = game_type(home, away)
    if gt == "unknown" or not player_team:
        return 0.5
    fav = favorite(home, away)
    if fav is None:
        return 0.5
    is_fav = _norm(player_team) == _norm(fav) or (
        len(_norm(player_team)) >= 5 and _norm(player_team)[:6] in _norm(fav)
    )

    if gt == "balanced":
        # Ausgeglichen: Kampf-Props beidseitig stark, Angriff neutral-positiv
        if cat in _DEFENSE:
            return 0.68
        if cat in _ATTACK:
            return 0.58
        return 0.5

    # one_sided
    if is_fav:
        # Favorit → Angriff belohnen, reine Defensiv-Props abwerten
        if cat in _ATTACK:
            return 0.80
        if cat in {"fouls", "fouls_committed", "tackles", "tackles_committed", "interceptions", "clearances"}:
            return 0.35
        return 0.5
    else:
        # Außenseiter → Kampf/Defensive belohnen, reine Torschützen abwerten
        if cat in _DEFENSE:
            return 0.80
        if cat in {"score", "first_scorer", "last_scorer", "assist", "score_assist"}:
            return 0.32
        if cat in {"shots", "sot"}:
            return 0.5   # Konter möglich
        return 0.5


def role_boost(category: str, player_team: str, home: str, away: str,
               weight: float = 0.15) -> float:
    """Wandelt role_fit in einen additiven Score-Boost (-w..+w) für den Builder."""
    fit = role_fit(category, player_team, home, away)
    return round((fit - 0.5) * 2.0 * weight, 4)


__all__ = [
    "load_team_elo", "team_elo", "elo_diff", "favorite", "game_type",
    "role_fit", "role_boost",
]
