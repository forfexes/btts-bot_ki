"""Spielerfotos fuer Builder- und Goalscorer-Tipps (kostenlos): FPL, ESPN, TheSportsDB, Wikipedia der Reihe nach.
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


def _name_ok(want, got):
    w, g = _norm(want).split(), _norm(got).split()
    if not w or not g or w[-1] != g[-1]:
        return False
    return not (len(w) > 1 and len(g) > 1 and w[0][0] != g[0][0])


def _get(url, **kw):
    r = requests.get(url, timeout=8, **kw)
    return r.json() if r.ok else None


_FPL = {}


def pick_fpl(bootstrap, name):
    """Premier-League-Spielerfoto aus dem offiziellen FPL-Datensatz (elements[].photo = '<code>.jpg')."""
    for e in (bootstrap or {}).get("elements", []):
        full = f"{e.get('first_name', '')} {e.get('second_name', '')}"
        if (_name_ok(name, full) or _name_ok(name, e.get("web_name", ""))) and e.get("photo"):
            code = str(e["photo"]).split(".")[0]
            return f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png"
    return None


def pick_espn(data, name):
    """ESPN-Suche: erster Fussballspieler mit passendem Namen; Bild-URL aus der Spieler-ID."""
    for it in (data or {}).get("items", []):
        if str(it.get("type", "player")).lower() != "player" or not _name_ok(name, it.get("displayName", "")):
            continue
        pid = re.search(r"a:(\d+)", str(it.get("uid") or "")) or re.fullmatch(r"(\d+)", str(it.get("id") or ""))
        tag = (str(it.get("uid") or "") + " " + str(it.get("sport") or "")).lower()
        if pid and ("s:600" in tag or "soccer" in tag or not tag.strip()):
            return f"https://a.espncdn.com/i/headshots/soccer/players/full/{pid.group(1)}.png"
    return None


def pick_wiki(data, name):
    for pg in ((data or {}).get("query") or {}).get("pages", {}).values():
        if _name_ok(name, pg.get("title", "")) and (pg.get("thumbnail") or {}).get("source"):
            return pg["thumbnail"]["source"]
    return None


def _src_fpl(name):
    if "d" not in _FPL:
        _FPL["d"] = _get("https://fantasy.premierleague.com/api/bootstrap-static/")
    return pick_fpl(_FPL["d"], name)


def _src_espn(name):
    return pick_espn(_get("https://site.web.api.espn.com/apis/common/v3/search",
                          params={"query": name, "limit": 5, "type": "player"}), name)


def _src_tsdb(name):
    return pick_photo((_get(API, params={"p": str(name)}) or {}).get("player"), name)


def _src_wiki(name):
    return pick_wiki(_get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 400,
        "generator": "search", "gsrsearch": f"{name} footballer", "gsrlimit": 3}), name)


SOURCES = [_src_fpl, _src_espn, _src_tsdb, _src_wiki]


def photo_url(name):
    """Quellen der Reihe nach (FPL, ESPN, TheSportsDB, Wikipedia); die erste mit passendem Foto gewinnt."""
    if not ON or not name:
        return None
    if not _MEM:
        _load()
    key = _norm(name)
    if key in _MEM:
        return _MEM[key] or None
    url, errors = None, 0
    for src in SOURCES:
        try:
            url = src(name)
        except Exception:
            errors += 1
            continue
        if url:
            break
    _MEM[key] = url or ""
    if url or errors < len(SOURCES):
        _save()  # nur speichern, wenn mindestens eine Quelle erreichbar war
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
