"""Spielerfoto ueber die API-Football-Spieler-ID aus player_game_log (keine API-Kontingente, auch Nationalspieler)."""
import os
import urllib.parse
import requests

_CACHE = {}
_URL = "https://media.api-sports.io/football/players/{}.png"  # player_game_log.player_id = API-Football-ID


def unique_id(rows):
    """Genau eine player_id fuer den Namen, sonst leer (nie ein fremdes Gesicht)."""
    ids = {str((r or {}).get("player_id") or "").strip() for r in rows or []}
    ids.discard("")
    ids = {i for i in ids if i.isdigit() and len(i) >= 4}  # kurze IDs (z.B. 580) sind Platzhalter
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
                             params={"select": "player_id", "player_name": "eq." + name, "limit": "60"})
            if r.ok:
                pid = unique_id(r.json())
                url = _URL.format(pid) if pid else ""
        except (requests.RequestException, ValueError):
            pass
    _CACHE[name] = url
    return url
