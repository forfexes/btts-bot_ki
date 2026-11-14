"""API-Football /players/profiles Suche als Foto-Fallback (auch Nationalspieler, auch ohne Team)."""
import os
import re
import unicodedata
import requests

_CALLS = 0
_MAX = int(os.getenv("NETRATTLER_PROFILE_PHOTO_MAX", "25"))


def _n(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def pick(rows, name):
    """Genau ein Profil mit gleichem Namen (oder gleicher Nachname + gleicher Anfangsbuchstabe)."""
    words = str(name).replace(".", ". ").split()
    if not words:
        return ""
    last, first = _n(words[-1]), _n(words[0])
    exact, loose = [], []
    for r in rows or []:
        p = (r or {}).get("player") or {}
        photo = p.get("photo") or ""
        if not photo:
            continue
        full = _n(str(p.get("firstname") or "") + str(p.get("lastname") or ""))
        shown = _n(p.get("name"))
        if _n(name) in (full, shown):
            exact.append(photo)
        elif len(words) > 1 and _n(p.get("lastname")) == last and _n(p.get("firstname"))[:1] == first[:1]:
            loose.append(photo)
    pool = list(dict.fromkeys(exact)) or list(dict.fromkeys(loose))
    return pool[0] if len(pool) == 1 else ""


def profile_photo(name):
    global _CALLS
    keys = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
    words = str(name or "").split()
    if not keys or not words or _CALLS >= _MAX or len(_n(words[-1])) < 4:
        return ""
    _CALLS += 1
    r = requests.get("https://v3.football.api-sports.io/players/profiles",
                     headers={"x-apisports-key": keys[0]}, params={"search": _n(words[-1])}, timeout=8)
    return pick(r.json().get("response"), name) if r.ok else ""
