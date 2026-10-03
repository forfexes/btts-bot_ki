"""NETRATTLER — L20-Spielerhistorie aus der zweiten Supabase-DB (player_game_log).

Liefert Zeilen im breiten Format nur für die Teams der heutigen Fixtures,
neueste Spiele zuerst. Non-fatal: jeder Fehler -> leere Liste.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

PLAYERS_DB_URL = (os.getenv("SUPABASE_PLAYERS_URL") or "").strip().rstrip("/")
PLAYERS_DB_KEY = (os.getenv("SUPABASE_PLAYERS_SERVICE_KEY") or "").strip()

# Spalte in player_game_log -> kanonische Stat im Bot
COLUMN_TO_STAT = {
    "shots": "shots", "sot": "sot", "goals": "goals", "assists": "assists",
    "fouls_committed": "fouls", "fouls_won": "fouls_won",
    "tackles": "tackles_committed", "yellow_cards": "cards",
    "saves": "saves", "offsides": "offsides",
}
_SELECT = ("player_name,team,league,match_date,event_id,minutes,"
           + ",".join(COLUMN_TO_STAT))
_STOP = {"football", "soccer", "fc", "afc", "cf", "sc", "club", "united", "city", "real", "the", "de", "ac", "as"}


def is_configured() -> bool:
    return bool(PLAYERS_DB_URL and PLAYERS_DB_KEY)


def team_tokens(names: Iterable[str]) -> List[str]:
    """Längstes aussagekräftiges Wort je Teamname für ein grobes ilike-Vorfilter."""
    out = set()
    for n in names:
        words = [w for w in re.findall(r"[a-zà-ÿ0-9]+", str(n or "").lower()) if len(w) >= 4]
        words = [w for w in words if w not in _STOP] or words
        if words:
            out.add(max(words, key=len))
    return sorted(out)


def fetch_l20_rows(team_names: Iterable[str], max_rows: int = 40000,
                   log: Optional[Callable[[str], Any]] = None) -> List[Dict[str, Any]]:
    if not is_configured():
        return []
    tokens = team_tokens(team_names)
    if not tokens:
        return []
    headers = {"apikey": PLAYERS_DB_KEY, "Authorization": f"Bearer {PLAYERS_DB_KEY}"}
    rows: List[Dict[str, Any]] = []
    # In Gruppen, damit die URL kurz bleibt
    for i in range(0, len(tokens), 12):
        group = tokens[i:i + 12]
        cond = ",".join(f"team.ilike.*{t}*" for t in group)
        offset = 0
        while len(rows) < max_rows:
            try:
                r = requests.get(
                    f"{PLAYERS_DB_URL}/rest/v1/player_game_log",
                    headers={**headers, "Range": f"{offset}-{offset + 999}"},
                    params={"select": _SELECT, "or": f"({cond})",
                            "order": "match_date.desc.nullslast,event_id.desc"},
                    timeout=40,
                )
            except requests.RequestException as exc:
                if log:
                    log(f"🔑 player_game_log: {str(exc)[:80]}")
                return rows
            if not r.ok:
                if log:
                    log(f"🔑 player_game_log HTTP {r.status_code}: {r.text[:120]}")
                break
            batch = r.json() or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
    return rows


__all__ = ["is_configured", "fetch_l20_rows", "team_tokens", "COLUMN_TO_STAT"]
