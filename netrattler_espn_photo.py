"""Player photo via provider-specific API-Football ID (never via an ESPN ID)."""
import os
import requests

_CACHE = {}
_URL = "https://media.api-sports.io/football/players/{}.png"  # ONLY source='apif*' IDs


def unique_id(rows):
    """Genau eine player_id fuer den Namen, sonst leer (nie ein fremdes Gesicht)."""
    ids = {str((r or {}).get("player_id") or "").strip() for r in rows or []}
    ids.discard("")
    # Valid API-Football IDs can have 1-3 digits (e.g. player 502).
    # The source filter below, not the number of digits, establishes ID namespace.
    ids = {i for i in ids if i.isdigit() and int(i) > 0}
    return next(iter(ids)) if len(ids) == 1 else ""


def espn_photo(name):
    name = " ".join(str(name or "").split())
    if len(name.split()) < 2:
        return ""
    if name in _CACHE:
        return _CACHE[name]
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    url = ""
    if base and key:
        try:
            r = requests.get(base + "/rest/v1/player_game_log", timeout=6,
                             headers={"apikey": key, "Authorization": "Bearer " + key},
                             params={"select": "player_id,source", "player_name": "eq." + name,
                                     "source": "like.apif*", "limit": "100"})
            if r.ok:
                pid = unique_id([row for row in (r.json() or [])
                                 if isinstance(row, dict) and str(row.get("source") or "").startswith("apif")])
                url = _URL.format(pid) if pid else ""
        except (requests.RequestException, ValueError):
            pass
    if url:
        _CACHE[name] = url
    return url


_ESPN_CACHE = {}


def espn_photo_by_id(name, team):
    """ESPN headshot only for an exact full name AND verified fixture club.

    The stored player_id must come from an ESPN source row, not API-Football.
    No surname matches, no first search result and no unverified fallback.
    """
    name = " ".join(str(name or "").split())
    team = " ".join(str(team or "").split())
    if len(name.split()) < 2 or not team:
        return ""
    cache_key = (name.casefold(), team.casefold())
    if cache_key in _ESPN_CACHE:
        return _ESPN_CACHE[cache_key]
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not (base.startswith("https://") and key):
        return ""
    from netrattler_crest_identity import same_club

    candidates = set()
    # fplci_player_match carries more provider IDs than the narrower game log.
    for table in ("fplci_player_match", "player_game_log"):
        try:
            response = requests.get(base + "/rest/v1/" + table, timeout=6,
                headers={"apikey": key, "Authorization": "Bearer " + key},
                params={"select": "player_name,player_id,team,source",
                        "source": "eq.espn", "player_name": "eq." + name,
                        "order": "match_date.desc", "limit": "100"})
            if not response.ok:
                continue
            for row in response.json() or []:
                if (str(row.get("player_name") or "").casefold() == name.casefold()
                        and row.get("source") == "espn"
                        and same_club(team, row.get("team"))
                        and str(row.get("player_id") or "").isdigit()
                        and int(row["player_id"]) > 0):
                    candidates.add(str(row["player_id"]))
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            continue
    url = ("https://a.espncdn.com/i/headshots/soccer/players/full/"
           + next(iter(candidates)) + ".png") if len(candidates) == 1 else ""
    if url:
        _ESPN_CACHE[cache_key] = url
    return url
