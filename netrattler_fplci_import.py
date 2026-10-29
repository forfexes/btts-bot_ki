"""Importiert Spieler-pro-Spiel-Stats (Tackles, Fouls, Schuesse, SoT, xG) aus dem offenen Datensatz
olbauday/FPL-Core-Insights (Premier League + Europacup-Spiele englischer Teams; wird 2x taeglich aktualisiert;
Wunsch des Autors: Quellenlink behalten) in Supabase `fplci_player_match`.
Nur rohe GET-Requests auf raw.githubusercontent.com, kein Key. Idempotent (Upsert auf match_id+player_id)."""
import csv, io, os, sys, requests
from datetime import date

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
RAW = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data"
SEASONS = [s for s in os.getenv("FPLCI_SEASONS", "2025-2026,2026-2027").split(",") if s]
MAX_GW = int(os.getenv("FPLCI_MAX_GW", "38"))


def fetch_csv(url):
    try:
        r = requests.get(url, timeout=30)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def fnum(v):
    try:
        if v in (None, ""):
            return None
        return float(v)
    except Exception:
        return None


def inum(v):
    f = fnum(v)
    return None if f is None else int(round(f))


def league_of(match_id):
    m = str(match_id or "")
    for key, name in (("prem-", "Premier League"), ("champions-league", "Champions League"), ("europa-league", "Europa League"),
                      ("conference-league", "Conference League"), ("efl-cup", "EFL Cup"), ("fa-cup", "FA Cup")):
        if key in m:
            return name
    return "Other"


def rows_for(season, gw):
    base = f"{RAW}/{season}/By%20Gameweek/GW{gw}"
    matches = fetch_csv(f"{base}/matches.csv")
    stats = fetch_csv(f"{base}/playermatchstats.csv")
    if not matches or not stats:
        return []
    teams = fetch_csv(f"{base}/teams.csv") or []
    players = fetch_csv(f"{base}/players.csv") or []
    tname = {}
    tcode = {}
    for t in teams:
        tname[str(inum(t.get("id")))] = t.get("name")
        tcode[str(inum(t.get("code")))] = t.get("name")
    pinfo = {}
    for p in players:
        pinfo[str(inum(p.get("player_id")))] = {
            "name": p.get("web_name") or " ".join(x for x in (p.get("first_name"), p.get("second_name")) if x),
            "team": tcode.get(str(inum(p.get("team_code")))),
            "pos": p.get("position"),
        }
    mi = {}
    today = date.today().isoformat()
    for m in matches:
        if str(m.get("finished")).lower() != "true":
            continue
        match_day = str(m.get("kickoff_time") or "")[:10]
        # Some upstream rows claim 'finished' while kickoff is in the future.
        # Never import future results as observed player history.
        if not match_day or match_day > today:
            continue
        mi[m["match_id"]] = {
            "date": match_day,
            "home": tname.get(str(inum(m.get("home_team")))),
            "away": tname.get(str(inum(m.get("away_team")))),
        }
    out = []
    for s in stats:
        m = mi.get(s.get("match_id"))
        if not m or not m["date"]:
            continue
        minutes = inum(s.get("minutes_played")) or 0
        if minutes <= 0:
            continue
        pi = pinfo.get(str(inum(s.get("player_id"))))
        if not pi or not pi["name"]:
            continue
        team = pi["team"]
        opp = m["away"] if team and team == m["home"] else (m["home"] if team and team == m["away"] else None)
        out.append({
            "match_id": s["match_id"], "player_id": inum(s.get("player_id")), "player_name": pi["name"], "team": team,
            "opponent": opp, "league": league_of(s["match_id"]), "match_date": m["date"], "minutes": minutes,
            "position": pi["pos"], "shots": inum(s.get("total_shots")), "shots_on": inum(s.get("shots_on_target")),
            "tackles": inum(s.get("tackles")), "tackles_won": inum(s.get("tackles_won")),
            "fouls_committed": inum(s.get("fouls_committed")), "fouls_drawn": inum(s.get("was_fouled")),
            "interceptions": inum(s.get("interceptions")), "xg": fnum(s.get("xg")),
            "goals": inum(s.get("goals")), "assists": inum(s.get("assists")),
        })
    return out


def upsert(rows):
    if not rows or not (SB and SK):
        return 0
    h = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
    n = 0
    for i in range(0, len(rows), 400):
        r = requests.post(f"{SB}/rest/v1/fplci_player_match?on_conflict=match_id,player_id", headers=h,
                          json=rows[i:i + 400], timeout=60)
        if r.status_code >= 300:
            print("upsert fehler", r.status_code, r.text[:200])
            continue
        n += len(rows[i:i + 400])
    return n


def main():
    total, written = 0, 0
    dry = "--dry" in sys.argv
    for season in SEASONS:
        for gw in range(1, MAX_GW + 1):
            rows = rows_for(season, gw)
            total += len(rows)
            if rows and not dry:
                written += upsert(rows)
    print({"probe": "fplci_import", "rows": total, "written": written})
    if SB and SK and not dry:
        try:
            requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=15,
                          headers={"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"},
                          json={"info": {"probe": "fplci_import", "rows": total, "written": written}})
        except Exception:
            pass


if __name__ == "__main__":
    main()
