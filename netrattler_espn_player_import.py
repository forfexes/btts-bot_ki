"""Spieler-pro-Spiel-Stats aus der oeffentlichen ESPN-Site-API (ohne Key) -> fplci_player_match (source='espn').
Liefert Schuesse, Schuesse aufs Tor, Tore, Assists, Fouls (begangen/erlitten), Gelb/Rot, Paraden fuer MLS,
Champions League und weitere Wettbewerbe. KEINE Tackles. Nur abgeschlossene Spiele, nur Spieler mit Einsatz.
Wenige Requests (ESPN_DAYS Tage zurueck), Pause zwischen Aufrufen, bei 403/429 Abbruch ohne Umgehung."""
import os, sys, time, requests
from datetime import date, timedelta

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LEAGUES = {
    "usa.1": "MLS", "eng.1": "Premier League", "ger.1": "Bundesliga", "esp.1": "La Liga", "ita.1": "Serie A",
    "fra.1": "Ligue 1", "uefa.champions": "Champions League", "uefa.europa": "Europa League",
    "uefa.europa.conf": "Conference League", "mex.1": "Liga MX", "bra.1": "Brasileirao Serie A",
    "arg.1": "Liga Argentinien", "aus.1": "A-League", "jpn.1": "J1 League Japan", "kor.1": "K League 1",
    "sau.1": "Saudi Pro League", "eng.2": "Championship", "ned.1": "Eredivisie", "por.1": "Primeira Liga",
    "tur.1": "Super Lig", "bel.1": "Pro League Belgien", "sco.1": "Scottish Premiership",
}
DAYS = int(os.getenv("ESPN_DAYS", "3"))
PAUSE = float(os.getenv("ESPN_PAUSE_SEC", "0.4"))
STAT_MAP = {"totalShots": "shots", "shotsOnTarget": "shots_on", "totalGoals": "goals", "goalAssists": "assists",
            "foulsCommitted": "fouls_committed", "foulsSuffered": "fouls_drawn", "yellowCards": "yellow",
            "redCards": "red", "saves": "saves"}


class Blocked(Exception):
    pass


def get_json(url, params=None):
    r = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=20)
    if r.status_code in (403, 429):
        raise Blocked(f"{r.status_code} {url}")
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def rows_from_summary(js, event, league_name):
    out = []
    rosters = (js or {}).get("rosters") or []
    names = [((r.get("team") or {}).get("displayName") or "") for r in rosters]
    day = str((event.get("date") or ""))[:10]
    for i, ros in enumerate(rosters):
        team = names[i]
        opp = names[1 - i] if len(names) == 2 else None
        for p in ros.get("roster") or []:
            ath = p.get("athlete") or {}
            stats = {s.get("name"): s.get("value") for s in (p.get("stats") or []) if s.get("name")}
            if not stats or float(stats.get("appearances") or 0) < 1:
                continue
            try:
                pid = int(ath.get("id"))
            except (TypeError, ValueError):
                continue
            row = {"match_id": f"espn-{event.get('id')}", "player_id": pid, "player_name": ath.get("displayName"),
                   "team": team, "opponent": opp, "league": league_name, "match_date": day,
                   "position": (p.get("position") or {}).get("abbreviation"), "source": "espn"}
            for k, col in STAT_MAP.items():
                if k in stats and stats[k] is not None:
                    row[col] = int(round(float(stats[k])))
            out.append(row)
    return out


def upsert(rows):
    if not rows or not (SB and SK):
        return 0
    h = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
    n = 0
    for i in range(0, len(rows), 400):
        part = rows[i:i + 400]
        # PostgREST verlangt gleiche Schluessel je Zeile
        keys = set().union(*[r.keys() for r in part])
        part = [{k: r.get(k) for k in keys} for r in part]
        r = requests.post(f"{SB}/rest/v1/fplci_player_match?on_conflict=match_id,player_id", headers=h, json=part, timeout=60)
        if r.status_code >= 300:
            print("upsert fehler", r.status_code, r.text[:200])
            continue
        n += len(part)
    return n


def main():
    dry = "--dry" in sys.argv
    total, events_n, blocked = 0, 0, None
    rows_all = []
    written = 0
    try:
        for back in range(DAYS):
            day_rows = []
            d = (date.today() - timedelta(days=back)).strftime("%Y%m%d")
            for slug, name in LEAGUES.items():
                sbd = get_json(f"{BASE}/{slug}/scoreboard", {"dates": d})
                time.sleep(PAUSE)
                for ev in (sbd or {}).get("events") or []:
                    if not ((ev.get("status") or {}).get("type") or {}).get("completed"):
                        continue
                    events_n += 1
                    js = get_json(f"{BASE}/{slug}/summary", {"event": ev.get("id")})
                    time.sleep(PAUSE)
                    day_rows.extend(rows_from_summary(js, ev, name))
            rows_all.extend(day_rows)
            if not dry:
                written += upsert(day_rows)  # tageweise speichern, damit ein Abbruch nichts verliert
    except Blocked as exc:
        blocked = str(exc)[:120]
        print("ESPN blockiert, Abbruch ohne Umgehung:", blocked)
    total = len(rows_all)
    info = {"probe": "espn_player_import", "events": events_n, "rows": total, "written": written, "blocked": blocked}
    print(info)
    if SB and SK and not dry:
        try:
            requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=15,
                          headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                          json={"info": info})
        except Exception:
            pass


if __name__ == "__main__":
    main()
