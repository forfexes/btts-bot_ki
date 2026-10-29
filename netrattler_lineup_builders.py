"""Aufstellungs-Run: Modell-Builder erst senden, wenn die Startelf bestaetigt ist.

Laeuft alle ~20 Minuten (Workflow netrattler_lineup_builders.yml). Pro Lauf:
1. Spielplan des Tages einmal von API-Football holen (1 Abfrage/Tag, in netrattler_card_diag zwischengespeichert).
2. Spiele, die in 15-90 Minuten beginnen, auf Aufstellungen pruefen (1 Abfrage je Spiel, max. 3 Versuche).
3. Fuer Spiele mit bestaetigter Startelf die Modell-Builder bauen, nur mit Spielern aus der Startelf, und senden.
Budget: APIF_LINEUP_MAX_REQ (Standard 35) von 100 Gratis-Abfragen pro Tag; die Spielerstatistik-Abfrage nutzt den Rest.
"""
import datetime as dt
import json
import os
import re
import unicodedata

import requests

import netrattler_foul_props as fp
import netrattler_model_builders as mb

B = "https://v3.football.api-sports.io"
KEYS = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
MIN_BEFORE = int(os.getenv("LINEUP_MIN_BEFORE", "15"))
MAX_BEFORE = int(os.getenv("LINEUP_MAX_BEFORE", "90"))
MAX_REQ = int(os.getenv("APIF_LINEUP_MAX_REQ", "35"))
MAX_TRIES = 3
PER_RUN = 12
PRIORITY = [39, 140, 78, 135, 61, 2, 3, 848, 88, 94, 203, 207, 218, 144, 79, 40, 141, 136, 62, 253, 71, 128]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def name_matches(ours, starter):
    """'Moises Caicedo' passt zu 'M. Caicedo' (gleicher Nachname, gleicher Anfangsbuchstabe) oder zum vollen Namen."""
    a, b = norm(ours), norm(starter)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = a.split(), b.split()
    if ta[-1] != tb[-1]:
        return False
    return len(ta) == 1 or len(tb) == 1 or ta[0][0] == tb[0][0]


def filter_to_starters(rows, starters_by_match):
    """Nur Zeilen von Spielern der bestaetigten Startelf behalten (starters_by_match: {match: [namen]})."""
    out = []
    for r in rows:
        starters = starters_by_match.get(r.get("match"))
        if starters is None:
            continue
        if any(name_matches(r.get("player"), s) for s in starters):
            out.append(r)
    return out


def due_fixtures(fixtures, state, now, used_req):
    """Spiele im Zeitfenster, noch nicht erledigt, unter MAX_TRIES; nach Liga-Prioritaet, begrenzt durch Budget."""
    cands = []
    for f in fixtures:
        try:
            ko = dt.datetime.fromisoformat(f["ko"])
        except (KeyError, ValueError):
            continue
        mins = (ko - now).total_seconds() / 60.0
        st = state.get(str(f["id"]), {})
        if st.get("done") or st.get("tries", 0) >= MAX_TRIES:
            continue
        if MIN_BEFORE <= mins <= MAX_BEFORE:
            rank = PRIORITY.index(f["league_id"]) if f.get("league_id") in PRIORITY else len(PRIORITY)
            cands.append((rank, ko, f))
    cands.sort(key=lambda x: (x[0], x[1]))
    room = max(0, MAX_REQ - used_req)
    return [f for _, _, f in cands[:min(PER_RUN, room)]]


def _sbh(extra=None):
    return {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json", **(extra or {})}


def _diag(info):
    try:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=_sbh(), data=json.dumps({"info": info}), timeout=15)
    except Exception:
        pass


def _diag_rows(probe, day):
    r = requests.get(f"{SB}/rest/v1/netrattler_card_diag", headers=_sbh(), timeout=20,
                     params={"select": "info", "info->>probe": f"eq.{probe}", "info->>day": f"eq.{day}", "limit": "1000"})
    return [x["info"] for x in r.json()] if r.ok and isinstance(r.json(), list) else []


def _api(path, params):
    return requests.get(B + path, headers={"x-apisports-key": KEYS[0]}, params=params, timeout=30)


def load_fixtures(day, now):
    rows = [x for x in _diag_rows("lineup_fixtures", day) if x.get("fixtures")]  # leere Listen zaehlen nicht als Cache
    if rows:
        return rows[-1]["fixtures"], 0
    r = _api("/fixtures", {"date": day})
    body = r.json() if r.ok else {}
    resp = body.get("response") or []
    if not resp:  # nicht zwischenspeichern, sonst bleibt der Tag leer; Fehlertext zur Diagnose ablegen
        _diag({"probe": "lineup_error", "day": day, "http": r.status_code, "errors": str(body.get("errors"))[:300],
               "results": body.get("results")})
        return [], 1
    fixtures = []
    for x in resp or []:
        if (x.get("fixture", {}).get("status") or {}).get("short") != "NS":
            continue
        fixtures.append({"id": x["fixture"]["id"], "ko": x["fixture"]["date"], "league_id": (x.get("league") or {}).get("id"),
                         "league": (x.get("league") or {}).get("name", ""),
                         "home": (x.get("teams") or {}).get("home", {}).get("name", ""),
                         "away": (x.get("teams") or {}).get("away", {}).get("name", "")})
    fixtures = fixtures[:400]
    _diag({"probe": "lineup_fixtures", "day": day, "fixtures": fixtures})
    return fixtures, 1


def starters_from(resp):
    teams = [t for t in (resp or []) if (t.get("startXI") or [])]
    if len(teams) < 2:
        return None
    names = []
    for t in teams:
        names += [(p.get("player") or {}).get("name") for p in t["startXI"]]
    return [n for n in names if n]


def make_sender():
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = (os.getenv("TELEGRAM_GROUP_BUILDER") or os.getenv("TELEGRAM_GROUP_PLAYER_PROPS")
            or os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID"))

    def send(text):
        if not token or not chat:
            return None
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        if not r.ok:
            return None
        res = (r.json() or {}).get("result") or {}
        return {"message_id": res.get("message_id"), "chat_id": (res.get("chat") or {}).get("id") or chat, "text": text}
    return send


def run():
    if not (KEYS and SB and SK):
        print("missing secrets")
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    day = now.date().isoformat()
    fixtures, used = load_fixtures(day, now)
    state = {}
    for s in _diag_rows("lineup_state", day):
        state[str(s.get("fixture_id"))] = {"done": s.get("done", False), "tries": s.get("tries", 0)}
    used += sum(1 for _ in _diag_rows("lineup_req", day))
    todo = due_fixtures(fixtures, state, now, used)
    matches, starters_by_match = [], {}
    for f in todo:
        r = _api("/fixtures/lineups", {"fixture": f["id"]})
        _diag({"probe": "lineup_req", "day": day, "fixture_id": f["id"]})
        names = starters_from(r.json().get("response") if r.ok else [])
        tries = state.get(str(f["id"]), {}).get("tries", 0) + 1
        _diag({"probe": "lineup_state", "day": day, "fixture_id": f["id"], "done": bool(names), "tries": tries})
        if not names:
            continue
        match = f"{f['home']} vs {f['away']}"
        matches.append({"match": match, "league": f.get("league", ""), "kickoff": f["ko"]})
        starters_by_match[match] = names
    sent = 0
    if matches:
        os.environ["NETRATTLER_LINEUP_CONFIRMED"] = "1"
        rows = fp.rows_for_matches(matches, SB, SK, norm)
        rows = filter_to_starters(rows, starters_by_match)
        sent = mb.run(rows, day, make_sender(), SB, SK)
    _diag({"probe": "lineup_run", "day": day, "fixtures": len(fixtures), "checked": len(todo), "confirmed": len(matches), "sent": sent})
    print(f"fixtures={len(fixtures)} checked={len(todo)} confirmed={len(matches)} sent={sent}")
    return sent


if __name__ == "__main__":
    run()
