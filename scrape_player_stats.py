#!/usr/bin/env python3
"""
NETRATTLER Player Stats Scraper V11
Multi-source: StatsBomb Open Data + SofaScore + FBref.
Graceful: 403/blocked Quellen crashen nicht.
Schreibt optional in Supabase:
- player_match_stats
- player_avg_stats
- source_health
"""

import os, re, time, json, argparse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": "Mozilla/5.0 Chrome/124 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.7",
    "Referer": "https://www.google.com/",
})

def log(x): print(x, flush=True)
def now(): return datetime.now(timezone.utc).isoformat()
def si(x, d=0):
    try: return int(float(str(x).replace(",", ".")))
    except Exception: return d
def sf(x, d=0.0):
    try: return float(str(x).replace(",", "."))
    except Exception: return d
def clean(s): return re.sub(r"\s+", " ", str(s or "")).strip()

def upsert(table: str, rows: List[Dict[str, Any]], conflict: str = "") -> int:
    if not rows: return 0
    if not SUPABASE_URL or not SUPABASE_KEY:
        log(f"⚠️ Supabase fehlt: {len(rows)} Rows nicht gespeichert ({table})")
        return 0
    total = 0
    h = dict(SB_HEADERS); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    url = f"{SUPABASE_URL}/rest/v1/{table}" + (f"?on_conflict={conflict}" if conflict else "")
    for i in range(0, len(rows), 350):
        chunk = rows[i:i+350]
        try:
            r = HTTP.post(url, headers=h, json=chunk, timeout=45)
            if not r.ok:
                log(f"⚠️ UPSERT {table} {r.status_code}: {r.text[:220]}")
                continue
            total += len(chunk)
        except Exception as e:
            log(f"⚠️ UPSERT {table} Fehler: {e}")
    return total

def sb_get(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        r = HTTP.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=params, timeout=35)
        return r.json() if r.ok else []
    except Exception:
        return []

def health(source, status, rows=0, msg=""):
    upsert("source_health", [{
        "source": source, "status": status, "rows": rows,
        "message": str(msg)[:400], "checked_at": now()
    }], "source")

# ---------- StatsBomb ----------
def jget(url):
    r = HTTP.get(url, timeout=25); r.raise_for_status(); return r.json()

def statsbomb_rows(max_matches=80):
    base = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    rows = []
    try:
        comps = jget(base + "/competitions.json")
    except Exception as e:
        log(f"⚠️ StatsBomb competitions Fehler: {e}"); health("statsbomb", "error", 0, e); return rows
    comps = [c for c in comps if any(x in str(c.get("competition_name","")).lower() for x in ["world cup","euro","copa america","champions league"])]
    seen = 0
    for c in comps[:8]:
        if seen >= max_matches: break
        try: matches = jget(f"{base}/matches/{c['competition_id']}/{c['season_id']}.json")
        except Exception: continue
        for m in matches:
            if seen >= max_matches: break
            mid = m.get("match_id")
            try: events = jget(f"{base}/events/{mid}.json")
            except Exception: continue
            seen += 1
            per = {}
            home = (m.get("home_team") or {}).get("home_team_name","")
            away = (m.get("away_team") or {}).get("away_team_name","")
            md = str(m.get("match_date") or "")
            for e in events:
                player = (e.get("player") or {}).get("name")
                if not player: continue
                p = per.setdefault(player, {
                    "player_name": clean(player), "team_name": clean((e.get("team") or {}).get("name","")),
                    "match_id": f"statsbomb_{mid}", "match_date": md, "home_team": home, "away_team": away,
                    "minutes": 0, "shots": 0, "sot": 0, "goals": 0, "assists": 0, "passes": 0,
                    "tackles": 0, "fouls_committed": 0, "fouls_won": 0, "cards": 0, "corners": 0,
                    "source": "statsbomb_open_data", "updated_at": now()
                })
                t = (e.get("type") or {}).get("name","")
                if t == "Shot":
                    p["shots"] += 1
                    out = ((e.get("shot") or {}).get("outcome") or {}).get("name","")
                    if out in ("Goal","Saved","Saved To Post"): p["sot"] += 1
                    if out == "Goal": p["goals"] += 1
                elif t == "Pass":
                    p["passes"] += 1
                    if ((e.get("pass") or {}).get("goal_assist") is True): p["assists"] += 1
                    if ((e.get("pass") or {}).get("type") or {}).get("name") == "Corner": p["corners"] += 1
                elif t == "Foul Committed":
                    p["fouls_committed"] += 1
                    if ((e.get("foul_committed") or {}).get("card") or {}).get("name"): p["cards"] += 1
                elif t == "Foul Won": p["fouls_won"] += 1
                elif t in ("Duel","Block","Interception","Ball Recovery"): p["tackles"] += 1
            rows.extend(per.values())
    health("statsbomb", "ok", len(rows), f"matches={seen}")
    return rows

# ---------- SofaScore ----------
def sofa(path):
    url = "https://api.sofascore.com/api/v1" + path
    try:
        r = HTTP.get(url, timeout=18)
        if r.status_code == 403:
            log(f"  [GET] 403 {url}"); return None
        if not r.ok:
            log(f"  [GET] {r.status_code} {url}"); return None
        return r.json()
    except Exception as e:
        log(f"  [GET] ERR {url}: {e}"); return None

def sofascore_event_rows(eid):
    data = sofa(f"/event/{eid}/lineups")
    if not data: return []
    evdata = sofa(f"/event/{eid}") or {}
    ev = evdata.get("event", {})
    home = (ev.get("homeTeam") or {}).get("name","")
    away = (ev.get("awayTeam") or {}).get("name","")
    ts = ev.get("startTimestamp")
    md = datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else ""
    rows = []
    for side in ("home","away"):
        team = home if side == "home" else away
        for item in ((data.get(side) or {}).get("players") or []):
            player = item.get("player") or {}
            st = item.get("statistics") or {}
            name = player.get("name") or player.get("shortName")
            if not name: continue
            rows.append({
                "player_name": clean(name), "team_name": team, "match_id": f"sofascore_{eid}",
                "match_date": md, "home_team": home, "away_team": away,
                "minutes": si(st.get("minutesPlayed") or st.get("minutes")),
                "shots": si(st.get("totalShots") or st.get("shots")),
                "sot": si(st.get("shotsOnTarget")),
                "goals": si(st.get("goals")), "assists": si(st.get("goalAssist") or st.get("assists")),
                "passes": si(st.get("totalPass") or st.get("passes")),
                "tackles": si(st.get("totalTackle") or st.get("tackles")),
                "fouls_committed": si(st.get("fouls") or st.get("foulsCommitted")),
                "fouls_won": si(st.get("wasFouled") or st.get("foulsWon")),
                "cards": si(st.get("yellowCards")) + si(st.get("redCards")),
                "corners": 0, "source": "sofascore", "updated_at": now()
            })
    return rows

def sofascore_rows_for_date(d, max_events=25):
    data = sofa(f"/sport/football/scheduled-events/{d}")
    if not data:
        health("sofascore", "blocked_or_empty", 0, d); return []
    events = data.get("events") or []
    fin = [e for e in events if ((e.get("status") or {}).get("type") or "").lower() in ("finished","afterpenalties","afterextra")]
    log(f"  → SofaScore {d}: {len(events)} Events, {len(fin)} beendet")
    rows = []
    for ev in fin[:max_events]:
        if ev.get("id"):
            rows.extend(sofascore_event_rows(ev["id"]))
            time.sleep(0.25)
    health("sofascore", "ok" if rows else "empty", len(rows), d)
    return rows

# ---------- FBref ----------
FBREF_URLS = [
    "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
    "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
    "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
    "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
    "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
]
def strip(html):
    html = re.sub(r"<br\s*/?>", " ", html)
    html = re.sub(r"<.*?>", "", html)
    return re.sub(r"\s+", " ", html).strip()

def fbref_parse(html):
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S|re.I):
        if 'data-stat="player"' not in tr: continue
        cells = {}
        for stat, val in re.findall(r'data-stat="([^"]+)"[^>]*>(.*?)</t[dh]>', tr, re.S|re.I):
            cells[stat] = strip(val)
        player = cells.get("player")
        if not player or player.lower() == "player": continue
        rows.append({
            "player_name": clean(player), "team_name": clean(cells.get("team") or cells.get("squad") or ""),
            "match_id": "fbref_season", "match_date": "", "home_team": "", "away_team": "",
            "minutes": si(cells.get("minutes")), "shots": si(cells.get("shots_total")),
            "sot": si(cells.get("shots_on_target")), "goals": si(cells.get("goals")),
            "assists": si(cells.get("assists")), "passes": si(cells.get("passes_completed")),
            "tackles": si(cells.get("tackles")), "fouls_committed": 0, "fouls_won": 0,
            "cards": si(cells.get("cards_yellow")) + si(cells.get("cards_red")),
            "corners": 0, "source": "fbref", "updated_at": now()
        })
    return rows

def fbref_rows(max_pages=5):
    rows = []
    for url in FBREF_URLS[:max_pages]:
        try:
            r = HTTP.get(url, timeout=20)
            if r.status_code in (403,429):
                log(f"  FBref block {r.status_code}: {url}"); continue
            if not r.ok:
                log(f"  FBref {r.status_code}: {url}"); continue
            parsed = fbref_parse(r.text)
            log(f"  FBref: {len(parsed)} Spieler")
            rows.extend(parsed)
            time.sleep(2.0)
        except Exception as e:
            log(f"  FBref Fehler: {e}")
    health("fbref", "ok" if rows else "blocked_or_empty", len(rows), "")
    return rows

# ---------- Rebuild ----------
def rebuild(days_back=240):
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
    rows = sb_get("player_match_stats", {"select":"*", "match_date":f"gte.{since}", "limit":"20000"})
    if not rows:
        log("  ⚠️ Keine player_match_stats für Rebuild"); return 0
    agg = {}
    for r in rows:
        p = clean(r.get("player_name"))
        if not p: continue
        a = agg.setdefault(p, {"player_name":p, "team_name":r.get("team_name") or "", "games":0})
        a["games"] += 1
        for k in ("minutes","shots","sot","goals","assists","passes","tackles","fouls_committed","fouls_won","cards","corners"):
            a[k] = a.get(k,0.0) + sf(r.get(k))
    out = []
    for p,a in agg.items():
        g = max(1, a["games"])
        out.append({
            "player_name": p, "team_name": a["team_name"], "games": a["games"],
            "minutes_avg": round(a.get("minutes",0)/g,2),
            "shots_avg": round(a.get("shots",0)/g,3), "sot_avg": round(a.get("sot",0)/g,3),
            "goals_avg": round(a.get("goals",0)/g,3), "assists_avg": round(a.get("assists",0)/g,3),
            "passes_avg": round(a.get("passes",0)/g,3), "tackles_avg": round(a.get("tackles",0)/g,3),
            "fouls_committed_avg": round(a.get("fouls_committed",0)/g,3),
            "fouls_won_avg": round(a.get("fouls_won",0)/g,3), "cards_avg": round(a.get("cards",0)/g,3),
            "corners_avg": round(a.get("corners",0)/g,3), "source": "rebuild_multi_source", "updated_at": now()
        })
    return upsert("player_avg_stats", out, "player_name")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--source", default="all", choices=["all","statsbomb","sofascore","fbref"])
    ap.add_argument("--rebuild-only", action="store_true")
    ap.add_argument("--days-back", type=int, default=240)
    ap.add_argument("--statsbomb-matches", type=int, default=int(os.getenv("STATSBOMB_MAX_MATCHES","80")))
    ap.add_argument("--sofascore-events", type=int, default=int(os.getenv("SOFASCORE_MAX_EVENTS","25")))
    ap.add_argument("--fbref-pages", type=int, default=int(os.getenv("FBREF_MAX_PAGES","5")))
    args = ap.parse_args()

    if args.rebuild_only:
        log(f"✅ player_avg_stats aktualisiert: {rebuild(args.days_back)}"); return

    all_rows = []
    if args.source in ("all","statsbomb"):
        log("📦 StatsBomb Open Data...")
        r = statsbomb_rows(args.statsbomb_matches); log(f"  StatsBomb Rows: {len(r)}"); all_rows += r
    if args.source in ("all","sofascore"):
        d = args.date or (datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()
        log(f"📦 SofaScore {d}...")
        r = sofascore_rows_for_date(d, args.sofascore_events); log(f"  SofaScore Rows: {len(r)}"); all_rows += r
    if args.source in ("all","fbref"):
        log("📦 FBref...")
        r = fbref_rows(args.fbref_pages); log(f"  FBref Rows: {len(r)}"); all_rows += r

    dedup = {}
    for r in all_rows:
        dedup[(r.get("source"), r.get("match_id"), r.get("player_name"), r.get("team_name"))] = r
    final = list(dedup.values())
    log(f"📦 Rows gebaut total: {len(final)}")
    saved = upsert("player_match_stats", final, "source,match_id,player_name")
    log(f"✅ player_match_stats gespeichert: {saved}")
    log(f"✅ player_avg_stats aktualisiert: {rebuild(args.days_back)}")

if __name__ == "__main__":
    main()
