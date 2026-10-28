"""Probe: SportsGameOdds Gratisplan - welche Top-5-Liga-Spiele und welche Spieler-Props (Tackles/Fouls/Shots/Cards)
sind sichtbar, mit welchen Buchmachern? Verbraucht nur wenige Objekte (limit je Liga). Schluessel nie ausgeben."""
import os, re, json, collections, requests

KEY = os.getenv("SPORTSGAMEODDS_API_KEY", "")
BASE = os.getenv("SGO_BASE", "https://api.sportsgameodds.com/v2")
LEAGUES = [x for x in os.getenv("SGO_LEAGUES", "EPL,LA_LIGA,BUNDESLIGA,IT_SERIE_A,FR_LIGUE_1").split(",") if x]
LIMIT = int(os.getenv("SGO_LIMIT", "5"))
STATS = ("tackles", "fouls", "foulsDrawn", "shots", "shots_onGoal", "yellowCards", "combinedCards", "goalie_saves")


def main():
    out = {"probe": "sgo_probe", "has_key": bool(KEY), "leagues": {}}
    if not KEY:
        print(out); post(out); return
    try:
        rl = requests.get(f"{BASE}/leagues", headers={"X-Api-Key": KEY}, params={"sportID": "SOCCER"}, timeout=30)
        out["leagues_list_status"] = rl.status_code
        if rl.ok:
            out["soccer_leagues"] = [x.get("leagueID") for x in (rl.json().get("data") or [])][:60]
    except Exception as exc:
        out["leagues_list_error"] = type(exc).__name__
    for lg in LEAGUES:
        info = {}
        try:
            r = requests.get(f"{BASE}/events", headers={"X-Api-Key": KEY},
                             params={"leagueID": lg, "oddsAvailable": "true", "limit": str(LIMIT), "finalized": "false"}, timeout=40)
            info["status"] = r.status_code
            if not r.ok:
                info["error"] = r.text[:160].replace(KEY, "<key>")
                out["leagues"][lg] = info; continue
            body = r.json()
            events = body.get("data") or []
            info["events"] = len(events)
            stat_books = collections.defaultdict(set); stat_n = collections.Counter()
            for ev in events:
                for oid, od in (ev.get("odds") or {}).items():
                    m = re.match(r"^([A-Za-z_]+)-([A-Z0-9_]+)-(game|1h|2h)-", oid)
                    key = (m.group(1) if m else oid.split("-")[0]) + ("_player" if m else "")
                    stat_n[key] += 1
                    for b in (od.get("byBookmaker") or {}):
                        stat_books[key].add(b)
            info["stats"] = {s: {"odds": stat_n[s], "books": sorted(stat_books[s])[:8]} for s in sorted(stat_n, key=lambda k: -stat_n[k])[:40]}
            if events:
                info["sample"] = f'{(events[0].get("teams") or {}).get("home", {}).get("names", {}).get("long")} vs {(events[0].get("teams") or {}).get("away", {}).get("names", {}).get("long")}'
        except Exception as exc:
            info["exception"] = type(exc).__name__
        out["leagues"][lg] = info
    print(json.dumps(out)[:3000]); post(out)


def post(info):
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/"); k = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and k:
        try:
            requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=20, json={"info": info},
                          headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        except Exception:
            pass


if __name__ == "__main__":
    main()
