"""Verify which side of a fixture a player belongs to from the CURRENT squads.

Used when the stored player history cannot tell (nicknames, long legal names,
club changes). Fail closed: exactly one squad entry across both teams must match.
"""
import os
import re
import unicodedata
from functools import lru_cache

import requests

_STOP = {"de", "da", "do", "dos", "das", "di", "del", "van", "von", "jr", "junior"}


def _tokens(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"['’`´]", "", text)
    return [t for t in re.findall(r"[a-z0-9]+", text)]


def names_match(player, squad_name):
    """Conservative name match: nickname, middle names and initials tolerated."""
    p, s = _tokens(player), _tokens(squad_name)
    if not p or not s:
        return False
    if p == s:
        return True
    p_full = [t for t in p if t not in _STOP]
    s_full = [t for t in s if len(t) > 1 and t not in _STOP]
    initials = [t for t in s if len(t) == 1]
    # Squad name (maybe "A. Surname" / "Nickname") is contained in the player's full name.
    # A lone first name ("Pedro") is never enough to identify a player.
    lone_first = len(s_full) == 1 and len(p_full) > 1 and s_full[0] == p_full[0]
    if (s_full and not lone_first and any(len(t) >= 4 for t in s_full)
            and all(t in p_full for t in s_full)):
        rest = list(p_full)
        for t in s_full:
            rest.remove(t)
        if all(any(r.startswith(i) for r in rest) for i in initials):
            return True
    # Player's (shorter) name is contained in the squad's full name; needs 2+ words.
    if len(p_full) >= 2 and all(t in s_full for t in p_full):
        return True
    return False


def _keys():
    raw = (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",")
    return [k.strip() for k in raw if k.strip()]


@lru_cache(maxsize=200)
def squad_names(team_id):
    keys = _keys()
    if not keys or not team_id:
        return ()
    try:
        r = requests.get("https://v3.football.api-sports.io/players/squads",
                         headers={"x-apisports-key": keys[0]}, params={"team": int(team_id)}, timeout=9)
        data = r.json() if r.ok else {}
        if not isinstance(data, dict) or data.get("errors"):
            return ()
        rows = data.get("response") or []
        players = (rows[0].get("players") if rows and isinstance(rows[0], dict) else None) or []
        return tuple(str(p.get("name") or "") for p in players if isinstance(p, dict) and p.get("name"))
    except (requests.RequestException, ValueError, TypeError):
        return ()


def club_from_squads(player, home, away, fixtures, same):
    """Return `home` or `away` (as spelled in the match) or "" if not exactly one squad entry matches.

    `fixtures`: provider fixture rows; `same(a, b)`: club-name comparison.
    """
    ids = {}
    for x in fixtures or ():
        teams = (x or {}).get("teams") or {}
        h, a = teams.get("home") or {}, teams.get("away") or {}
        if same(home, h.get("name")) and same(away, a.get("name")):
            ids = {home: h.get("id"), away: a.get("id")}
            break
    if not ids or not all(ids.values()):
        return ""
    hits = []
    for side, tid in ids.items():
        for entry in squad_names(int(tid)):
            if names_match(player, entry):
                hits.append(side)
    return hits[0] if len(hits) == 1 else ""
