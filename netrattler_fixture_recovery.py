"""NETRATTLER fixture recovery helpers.

Merge bookmaker-backed fixtures from secondary providers into the primary
matchup pool without duplicating matches already present.
"""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Tuple


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def matchup_key(home: Any, away: Any) -> Tuple[str, str]:
    return (_norm(home), _norm(away))


def _first(fx: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = fx.get(key)
        if value not in (None, ""):
            return value
    return ""


def fixture_start(fx: Dict[str, Any]) -> str:
    value = _first(
        fx, "startTime", "starts", "start", "commenceTime", "commence_time",
        "date", "startDate", "fixtureDate",
    )
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def oddspapi_to_matchup(fx: Dict[str, Any]) -> Dict[str, Any]:
    home = str(_first(fx, "participant1Name", "homeTeam", "home", "home_team") or "").strip()
    away = str(_first(fx, "participant2Name", "awayTeam", "away", "away_team") or "").strip()
    if not home or not away:
        return {}
    tournament = str(_first(fx, "tournamentName", "leagueName", "competitionName") or "").strip()
    category = str(_first(fx, "categoryName", "category", "countryName") or "").strip()
    league = tournament or category or "OddsPapi"
    if category and tournament and _norm(category) not in _norm(tournament):
        league = f"{category} - {tournament}"
    return {
        "home": home,
        "away": away,
        "league_name": league,
        "league": league,
        "starts": fixture_start(fx),
        "match_id": fx.get("fixtureId") or fx.get("id") or "",
        "_oddspapi_fixture_id": fx.get("fixtureId") or "",
        "source": "oddspapi_recovery",
    }


def merge_recovered_matchups(
    primary: Iterable[Dict[str, Any]],
    recovered_fixtures: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    merged = [dict(row) for row in (primary or []) if isinstance(row, dict)]
    seen = {
        matchup_key(row.get("home"), row.get("away"))
        for row in merged if row.get("home") and row.get("away")
    }
    added: List[Dict[str, Any]] = []
    for fx in recovered_fixtures or []:
        if not isinstance(fx, dict) or fx.get("hasOdds") is False:
            continue
        row = oddspapi_to_matchup(fx)
        if not row:
            continue
        key = matchup_key(row["home"], row["away"])
        if not all(key) or key in seen:
            continue
        seen.add(key)
        merged.append(row)
        added.append(row)
    return merged, added


__all__ = ["fixture_start", "matchup_key", "merge_recovered_matchups", "oddspapi_to_matchup"]
