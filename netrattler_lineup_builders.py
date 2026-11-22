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
from netrattler_apif_response import checked_response

import netrattler_foul_props as fp
import netrattler_model_builders as mb
import netrattler_fouls_builder_premium as premium_fouls

B = "https://v3.football.api-sports.io"
KEYS = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
MIN_BEFORE = int(os.getenv("LINEUP_MIN_BEFORE", "15"))
MAX_BEFORE = int(os.getenv("LINEUP_MAX_BEFORE", "90"))
MAX_REQ = int(os.getenv("APIF_LINEUP_MAX_REQ", "35"))
MAX_TRIES = 3
PER_RUN = int(os.getenv("APIF_LINEUP_PER_RUN", "12"))
PRIORITY = [39, 140, 78, 135, 61, 2, 3, 848, 88, 94, 203, 207, 218, 144, 79, 40, 141, 136, 62, 253, 71, 128]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def name_matches(ours, starter):
    """'Moises Caicedo' passt zu 'M. Caicedo' (gleicher Nachname, gleicher Anfangsbuchstabe) oder zum vollen Namen."""
    a, b = norm(ours), norm(starter)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    # Substring matching can equate different players (e.g. Joao / Joao Pedro).
    # Require the same surname; full first names must agree, except an
    # explicitly abbreviated initial on either side.
    if ta[-1] != tb[-1]:
        return False
    if len(ta) == 1 or len(tb) == 1:
        return True
    first_a, first_b = ta[0], tb[0]
    return (first_a == first_b
            or (len(first_a) == 1 and first_a == first_b[0])
            or (len(first_b) == 1 and first_b == first_a[0]))


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


def filter_verified_team_starters(rows, strict_by_match):
    """Only actual right-team XI players from the verified provider fixture.

    A flat 22-name list is not a safe player-to-club join: a same-named
    opponent or transfer could otherwise be assigned to the wrong team.
    Without both exact provider team IDs, fail closed and defer the pick.
    """
    accepted=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        evidence=strict_by_match.get(row.get("match"))
        if not evidence:
            continue
        fixture, lineup = evidence
        expected_player=norm(row.get("player"))
        actual_team=row.get("team")
        if not expected_player or not actual_team:
            continue
        for side in ("home","away"):
            team_name=fixture.get(side)
            team_id=fixture.get(f"{side}_team_id")
            if not (team_id and fp.same_team(actual_team,team_name)):
                continue
            roster=(lineup.get(side) or {})
            if roster.get("team_id")!=team_id:
                continue
            # Exact full-name equality; abbreviations and surnames alone are
            # insufficient to establish a player identity in a betting slip.
            names={norm(x) for x in roster.get("starters",[])}
            if expected_player in names:
                accepted.append(row)
            break
    return accepted


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
        r = requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=_sbh(), data=json.dumps({"info": info}), timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        raise RuntimeError("Lineup state persistence failed") from None


def _diag_rows(probe, day):
    r = requests.get(f"{SB}/rest/v1/netrattler_card_diag", headers=_sbh(), timeout=20,
                     params={"select": "info", "order": "id.asc", "info->>probe": f"eq.{probe}", "info->>day": f"eq.{day}", "limit": "1000"})
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or len(rows) >= 1000:
        raise RuntimeError("Incomplete lineup state read")
    return [x["info"] for x in rows]


def _api(path, params):
    return requests.get(B + path, headers={"x-apisports-key": KEYS[0]}, params=params, timeout=30)


def load_fixtures(day, now):
    rows = [x for x in _diag_rows("lineup_fixtures", day) if x.get("fixtures")]  # leere Listen zaehlen nicht als Cache
    if rows:
        return rows[-1]["fixtures"], 0
    _diag({"probe": "lineup_req", "day": day, "request": "fixtures"})
    r = _api("/fixtures", {"date": day})
    resp = checked_response(r)
    body = r.json()
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
                         "away": (x.get("teams") or {}).get("away", {}).get("name", ""),
                         "home_team_id": (x.get("teams") or {}).get("home", {}).get("id"),
                         "away_team_id": (x.get("teams") or {}).get("away", {}).get("id")})
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
        import netrattler_player_photos as npp
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                          json=npp.apply_preview({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}))
        if not r.ok:
            return None
        res = (r.json() or {}).get("result") or {}
        return {"message_id": res.get("message_id"), "chat_id": (res.get("chat") or {}).get("id") or chat, "text": text}
    return send


def run():
    if not (KEYS and SB and SK):
        raise RuntimeError("Lineup configuration missing")
    now = dt.datetime.now(dt.timezone.utc)
    day = now.date().isoformat()
    used = len(_diag_rows("lineup_req", day))
    if used >= MAX_REQ:
        print("Lineup daily request budget exhausted")
        return 0
    if _diag_rows("lineup_suspended", day):
        print("API-Football suspended today; lineup run skipped")
        return 0
    try:
        fixtures, _ = load_fixtures(day, now)
    except RuntimeError as exc:
        if "account suspended" not in str(exc):
            raise
        _diag({"probe": "lineup_suspended", "day": day})  # Anbieter-Sperre: einmal je Tag vermerken, kein 20-Min-Fehlalarm
        print("API-Football account suspended; lineup run skipped")
        return 0
    state = {}
    for s in _diag_rows("lineup_state", day):
        state[str(s.get("fixture_id"))] = {"done": s.get("done", False), "tries": s.get("tries", 0)}
    used = len(_diag_rows("lineup_req", day))
    todo = due_fixtures(fixtures, state, now, used)
    matches, starters_by_match, confirmed_ids = [], {}, []
    strict_foul_fixtures = {}
    for f in todo:
        _diag({"probe": "lineup_req", "day": day, "fixture_id": f["id"]})
        r = _api("/fixtures/lineups", {"fixture": f["id"]})
        provider_lineups = checked_response(r)
        names = starters_from(provider_lineups)
        tries = state.get(str(f["id"]), {}).get("tries", 0) + 1
        _diag({"probe": "lineup_state", "day": day, "fixture_id": f["id"], "done": False, "tries": tries})
        if not names:
            continue
        match = f"{f['home']} vs {f['away']}"
        # Preserve exact provider club IDs and both independent 11-player XIs
        # for the *new* Fouls scanner. Legacy flat-name matching is not proof
        # that a player belongs to the correct side of this fixture.
        exact_fixture = {
            "fixture_id": f["id"], "home_team_id": f.get("home_team_id"),
            "away_team_id": f.get("away_team_id"), "home": f["home"],
            "away": f["away"], "league": f.get("league"), "kickoff": f["ko"],
            "status": "NS",
        }
        try:
            seen_at = dt.datetime.now(dt.timezone.utc)
            verified = premium_fouls.lineup_from_api_football(
                exact_fixture, provider_lineups, observed_at=seen_at)
            strict_foul_fixtures[match] = (exact_fixture, verified)
        except ValueError as exc:
            print("PREMIUM_FOUL_XI_SKIPPED",f["id"],str(exc)[:85])
        matches.append({"match": match, "league": f.get("league", ""), "kickoff": f["ko"]})
        starters_by_match[match] = names
        confirmed_ids.append(f["id"])
    sent = 0
    if matches:
        os.environ["NETRATTLER_LINEUP_CONFIRMED"] = "1"
        rows = fp.rows_for_matches(matches, SB, SK, norm)
        rows = filter_to_starters(rows, starters_by_match)
        # Security: the old flat 22-name list is insufficient for any
        # player-prop builder, not just Fouls. Require verified team-specific
        # XI identity for every leg BEFORE model ranking and DB reservation.
        rows = filter_verified_team_starters(rows, strict_foul_fixtures)
        for match, (exact_fixture,verified) in strict_foul_fixtures.items():
            try:
                # Read-only scouting. Zero bookable tips without a genuine
                # combined ticket; NEVER send a fallback Fouls card.
                board = premium_fouls.scout_foul_candidates(
                    exact_fixture, verified, rows,
                    now=dt.datetime.now(dt.timezone.utc))
                print("PREMIUM_FOUL_SCOUT_RESEARCH_ONLY",
                      exact_fixture["fixture_id"],len(board["candidates"]))
            except ValueError as exc:
                print("PREMIUM_FOUL_SCOUT_BLOCKED",
                      exact_fixture["fixture_id"],str(exc)[:85])
        try:
            sent = mb.run(rows, day, make_sender(), SB, SK)
        finally:
            os.environ.pop("NETRATTLER_LINEUP_CONFIRMED", None)
        for fid in confirmed_ids:
            # A confirmed lineup is not proof of delivery. Keep zero-send fixtures
            # eligible for a later attempt while the existing retry cap applies.
            # run() returns an aggregate delivery count, not receipts per fixture.
            # Never mark *all* checked fixtures done because one of them sent.
            # On multi-fixture runs leave them retryable; the existing MAX_TRIES,
            # daily budget and deterministic builder IDs still bound retries.
            done = bool(sent) and len(confirmed_ids) == 1
            _diag({"probe": "lineup_state", "day": day, "fixture_id": fid, "done": done, "tries": state.get(str(fid), {}).get("tries", 0) + 1})
    _diag({"probe": "lineup_run", "day": day, "fixtures": len(fixtures), "checked": len(todo), "confirmed": len(matches), "sent": sent})
    print(f"fixtures={len(fixtures)} checked={len(todo)} confirmed={len(matches)} sent={sent}")
    return sent


if __name__ == "__main__":
    run()
