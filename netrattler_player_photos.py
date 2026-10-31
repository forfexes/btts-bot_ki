"""Spielerfotos fuer Builder- und Goalscorer-Tipps (kostenlos, TheSportsDB-Gratisschluessel).
Das Foto wird als Link-Vorschau ueber dem Text angezeigt: unsichtbarer Link im Text + link_preview_options beim Senden.
Fehlt ein Foto oder ist die Quelle nicht erreichbar, bleibt der Tipp unveraendert."""
import json
import os
import re
import unicodedata
import urllib.parse

import requests

ON = os.getenv("NETRATTLER_PLAYER_PHOTOS", "1") != "0"
API = "https://www.thesportsdb.com/api/v1/json/" + (os.getenv("THESPORTSDB_KEY") or "3") + "/searchplayers.php"
CACHE_FILE = os.getenv("NETRATTLER_PHOTO_CACHE", "player_photos_cache.json")
_MEM = {}
_MARK = re.compile(r'<a href="(https?://[^"]+)">​</a>')


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def _load():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _MEM.update(json.load(f))
    except Exception:
        pass


def _save():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_MEM, f)
    except Exception:
        pass


def pick_photo(players, name):
    """Aus der API-Antwort das Spielerfoto waehlen: nur Fussballer, Nachname muss passen."""
    want = _norm(name).split()
    if not want:
        return None
    for p in players or []:
        if str(p.get("strSport") or "Soccer").lower() != "soccer":
            continue
        have = _norm(p.get("strPlayer")).split()
        if not have or have[-1] != want[-1]:
            continue
        if len(want) > 1 and len(have) > 1 and have[0][0] != want[0][0]:
            continue
        for k in ("strCutout", "strThumb", "strRender"):
            if p.get(k):
                return p[k]
    return None


def photo_url(name):
    if not ON or not name:
        return None
    if not _MEM:
        _load()
    key = _norm(name)
    if key in _MEM:
        return _MEM[key] or None
    url = None
    try:
        r = requests.get(API, params={"p": str(name)}, timeout=8)
        if r.ok:
            url = pick_photo((r.json() or {}).get("player"), name)
        _MEM[key] = url or ""
        _save()
    except Exception:
        _MEM[key] = ""  # nur im Speicher: bei Netzfehler nicht nochmal im selben Lauf versuchen
        return None
    return url


def anchor(name):
    """Unsichtbarer Link am Textanfang oder leerer String."""
    url = photo_url(name)
    return f'<a href="{url}">​</a>' if url else ""


def apply_preview(payload):
    """Im sendMessage-Payload die Foto-Vorschau einschalten, wenn der Text einen Foto-Link traegt."""
    m = _MARK.search(str(payload.get("text") or ""))
    if not m:
        return payload
    payload.pop("disable_web_page_preview", None)
    payload["link_preview_options"] = {"is_disabled": False, "url": m.group(1), "show_above_text": True}
    return payload
