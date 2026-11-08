"""API-Football free key: yesterday's finished matches -> player stats (fouls, fouls drawn, cards, shots).
1 request for the fixture list + up to MAX_REQ-1 player requests per run (Pro-Plan: 7500/Tag)."""
import os
import datetime as dt
import requests
from netrattler_apif_response import checked_response

B = "https://v3.football.api-sports.io"
KEYS = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
MAX_REQ = int(os.getenv("APIF_MAX_REQ", "90"))
# priority: PL, LaLiga, Bundesliga, SerieA, Ligue1, UCL, UEL, ECL, NL, PT, Super Lig, CH, AT, BE
PRIORITY = [39, 140, 78, 135, 61, 2, 3, 848, 88, 94, 203, 207, 218, 144, 79, 40, 141, 136, 62]


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def pick_fixtures(resp, known, limit):
    known_ids = {str(fid) for fid in known}
    ft = [x for x in resp if (x.get("fixture") or {}).get("status", {}).get("short") == "FT"
          and str(x["fixture"]["id"]) not in known_ids]
    def rank(x):
        lid = (x.get("league") or {}).get("id")
        return PRIORITY.index(lid) if lid in PRIORITY else len(PRIORITY)
    ft.sort(key=rank)
    return ft[:limit]


def _stat(v):
    from netrattler_apif_response import number
    return number(v)


def parse_players(resp, fx):
    rows = []
    fid = fx["fixture"]["id"]
    for t in resp or []:
        for p in t.get("players") or []:
            s = (p.get("statistics") or [{}])[0]
            g = s.get("games") or {}
            if not _i(g.get("minutes")):
                continue
            rows.append({
                "fixture_id": fid, "player_id": p["player"]["id"], "player_name": p["player"].get("name"),
                "team": (t.get("team") or {}).get("name"), "league_id": (fx.get("league") or {}).get("id"),
                "match_date": (fx["fixture"].get("date") or "")[:10] or None,
                "minutes": _i(g.get("minutes")), "position": g.get("position"),
                "shots": _stat((s.get("shots") or {}).get("total")), "shots_on": _stat((s.get("shots") or {}).get("on")),
                "fouls_committed": _stat((s.get("fouls") or {}).get("committed")),
                "fouls_drawn": _stat((s.get("fouls") or {}).get("drawn")),
                "yellow": _stat((s.get("cards") or {}).get("yellow")), "red": _stat((s.get("cards") or {}).get("red")),
                "tackles": _stat((s.get("tackles") or {}).get("total")), "passes": _stat((s.get("passes") or {}).get("total")),
            })
    return rows


def post_with_retry(url, rows, headers, tries=4, pause=3.0):
    """POST mit Wiederholung bei 5xx/Netzfehlern (Supabase 503 ist meist kurzzeitig)."""
    import time
    last = None
    for i in range(tries):
        try:
            p = requests.post(url, json=rows, timeout=30, headers=headers)
            if p.status_code < 500:
                return p
            last = p
        except requests.RequestException as e:
            last = e
        time.sleep(pause * (i + 1))
    if isinstance(last, requests.Response):
        return last
    raise last


def get_with_retry(url, headers, tries=4, pause=3.0):
    """GET mit Wiederholung bei 5xx/Netzfehlern (Supabase 503 ist meist kurzzeitig)."""
    import time
    last = None
    for i in range(tries):
        try:
            g = requests.get(url, timeout=20, headers=headers)
            if g.status_code < 500:
                return g
            last = g
        except requests.RequestException as e:
            last = e
        time.sleep(pause * (i + 1))
    if isinstance(last, requests.Response):
        return last
    raise last


def _sb(h=None):
    return {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json", **(h or {})}


def fetch_players(H, fixture_id, wait=65):
    """Spielerdaten holen; bei rateLimit (Minutenkontingent) einmal warten und wiederholen."""
    import time
    for attempt in (0, 1):
        r = requests.get(B + "/fixtures/players", headers=H, params={"fixture": fixture_id}, timeout=30)
        try:
            return checked_response(r)
        except RuntimeError as e:
            if attempt == 0 and "rateLimit" in str(e):
                time.sleep(wait)
                continue
            raise


BULK_PAUSE_MB = 440.0  # identisch mit DB-Trigger netrattler_bulk_capacity_guard


def db_paused():
    """True, wenn die DB-Reserve erreicht ist (Trigger weist Bulk-Inserts sonst mit 503 ab)."""
    try:
        r = requests.post(f"{SB}/rest/v1/rpc/db_size_mb", headers=_sb(), json={}, timeout=30)
        r.raise_for_status()
        return float(r.json()["mb"]) >= BULK_PAUSE_MB
    except Exception:
        return False


def run():
    if not (KEYS and SB and SK):
        raise RuntimeError("API-Football player import configuration missing")
    if db_paused():
        print(f"PAUSED: DB >= {BULK_PAUSE_MB:.0f} MB, Spieler-Import ausgesetzt (Reserve fuer Tipps/Settlement)")
        return 0
    H = {"x-apisports-key": KEYS[0]}
    d = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    resp = checked_response(requests.get(B + "/fixtures", headers=H, params={"date": d}, timeout=30))
    ids = [str(x["fixture"]["id"]) for x in resp]
    k = get_with_retry(f"{SB}/rest/v1/apif_player_match?select=fixture_id&fixture_id=in.({','.join(ids)})",
                       _sb()) if ids else None
    if k is not None:
        k.raise_for_status()
    known = {x["fixture_id"] for x in k.json()} if k is not None else set()
    saved = 0
    for fx in pick_fixtures(resp, known, MAX_REQ - 1):
        try:
            rows = parse_players(fetch_players(H, fx["fixture"]["id"]), fx)
        except RuntimeError as e:
            if "rateLimit" in str(e):
                # Minutenlimit trotz Wartezeit: bereits gespeicherte Spiele bleiben, Rest folgt im naechsten Lauf.
                print(f"rate limit, stop early with rows={saved}: {e}")
                break
            raise
        if rows:
            p = post_with_retry(f"{SB}/rest/v1/apif_player_match", rows,
                                _sb({"Prefer": "resolution=ignore-duplicates"}))
            p.raise_for_status()
            saved += len(rows)
    print("rows", saved)
    return saved


if __name__ == "__main__":
    run()
