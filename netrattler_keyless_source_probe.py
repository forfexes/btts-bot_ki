#!/usr/bin/env python3
"""NETRATTLER keyless source probe.

Checks, from the GitHub Actions runner, which public sources WITHOUT an API key
deliver data we need: odds (all markets), fixtures/results, team stats, corners/cards,
H2H, lineups/injuries. Read-only. Writes one summary row to netrattler_card_diag
(counts only, no payloads).
"""
import csv
import datetime as dt
import io
import json
import os
import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en"}
TODAY = dt.date.today()
D = TODAY.strftime("%Y%m%d")
BLOCK = re.compile(r"captcha|cloudflare|access denied|just a moment|attention required", re.I)


def get(url, params=None, headers=None, timeout=15):
    try:
        r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=timeout)
        txt = r.text or ""
        try:
            js = r.json()
        except Exception:
            js = None
        return r.status_code, js, txt
    except Exception as exc:
        return 0, None, type(exc).__name__


def res(st, txt, n=None, **extra):
    out = {"http": st, "kb": round(len(txt or "") / 1024), "blocked": bool(BLOCK.search((txt or "")[:5000]))}
    if n is not None:
        out["n"] = n
    out.update(extra)
    out["ok"] = st == 200 and not out["blocked"] and (n is None or n > 0)
    return out


def safe(fn):
    try:
        return fn()
    except Exception as exc:
        return {"http": -1, "err": f"{type(exc).__name__}: {str(exc)[:80]}", "ok": False}


# ------------------------------------------------------------------ odds
def kambi():
    st, js, txt = get("https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football/all/all/all/matches.json",
                      {"lang": "en_GB", "market": "GB"})
    ev = (js or {}).get("events") or []
    return res(st, txt, len(ev))


def pinnacle():
    h = {"X-API-Key": os.getenv("PINNACLE_GUEST_KEY", ""), "Referer": "https://www.pinnacle.com/",
         "Origin": "https://www.pinnacle.com"}
    st, js, txt = get("https://guest.api.arcadia.pinnacle.com/0.1/sports/29/matchups", headers=h)
    return res(st, txt, len(js) if isinstance(js, list) else 0)


def bwin():
    p = {"x-bwin-accessid": "NTZiMjk3OGMtNjU5Mi00NjA5LWI2MWItZmU4MDRhN2QxZmEz", "lang": "en", "country": "GB",
         "userCountry": "GB", "fixtureTypes": "Standard", "state": "Latest", "offerMapping": "Filtered",
         "sportIds": "4", "skip": "0", "take": "50"}
    st, js, txt = get("https://sports.bwin.com/cds-api/bettingoffer/fixtures", p)
    fx = (js or {}).get("fixtures") or []
    corners = sum(1 for f in fx for g in (f.get("games") or []) if "corner" in str((g.get("name") or {}).get("value", "")).lower())
    return res(st, txt, len(fx), corner_markets=corners)


def espn_odds():
    st, js, txt = get("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard", {"dates": D})
    ev = (js or {}).get("events") or []
    with_odds = sum(1 for e in ev if ((e.get("competitions") or [{}])[0].get("odds")))
    return res(st, txt, len(ev), with_odds=with_odds)


def polymarket():
    st, js, txt = get("https://gamma-api.polymarket.com/events", {"tag_slug": "soccer", "closed": "false", "limit": "50"})
    return res(st, txt, len(js) if isinstance(js, list) else 0)


def sofascore_odds():
    st, js, txt = get(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{TODAY}")
    ev = (js or {}).get("events") or []
    out = res(st, txt, len(ev))
    if ev:
        st2, js2, txt2 = get(f"https://api.sofascore.com/api/v1/event/{ev[0]['id']}/odds/1/all")
        out["odds_http"] = st2
        out["odds_markets"] = len((js2 or {}).get("markets") or [])
    return out


def oddsportal():
    st, js, txt = get("https://www.oddsportal.com/matches/football/")
    return res(st, txt)


# ------------------------------------------------------------------ fixtures / results / stats
def espn_summary():
    st, js, txt = get("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard")
    ev = (js or {}).get("events") or []
    if not ev:
        return res(st, txt, 0)
    eid = ev[0]["id"]
    st2, js2, txt2 = get("https://site.web.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary", {"event": eid})
    js2 = js2 or {}
    stats = sum(len(t.get("statistics") or []) for t in ((js2.get("boxscore") or {}).get("teams") or []))
    return res(st2, txt2, len(js2.keys()), rosters=len(js2.get("rosters") or []), h2h=len(js2.get("headToHeadGames") or []),
               team_stats=stats, odds=len(js2.get("odds") or js2.get("pickcenter") or []))


def fotmob():
    st, js, txt = get("https://www.fotmob.com/api/matches", {"date": D})
    lg = (js or {}).get("leagues") or []
    return res(st, txt, sum(len(l.get("matches") or []) for l in lg))


def sofascore_stats():
    st, js, txt = get(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{TODAY}")
    ev = (js or {}).get("events") or []
    out = res(st, txt, len(ev))
    if ev:
        e = ev[0]
        for name, path in (("h2h", f"event/{e['id']}/h2h"), ("lineups", f"event/{e['id']}/lineups"),
                           ("form", f"event/{e['id']}/pregame-form")):
            s2, _, _ = get(f"https://api.sofascore.com/api/v1/{path}")
            out[name] = s2
    return out


def livescore():
    st, js, txt = get(f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{D}/0", {"MD": "1"})
    st_ = (js or {}).get("Stages") or []
    return res(st, txt, sum(len(s.get("Events") or []) for s in st_))


def football_data_csv():
    season = f"{str(TODAY.year - (1 if TODAY.month < 7 else 0))[2:]}{str(TODAY.year + (0 if TODAY.month < 7 else 1))[2:]}"
    st, _, txt = get(f"https://www.football-data.co.uk/mmz4281/{season}/E0.csv")
    rows = list(csv.DictReader(io.StringIO(txt))) if st == 200 else []
    cols = rows[0].keys() if rows else []
    return res(st, txt, len(rows), corners="HC" in cols, cards="HY" in cols, odds_cols=sum(1 for c in cols if c.startswith(("B365", "PS", "Max", "Avg"))))


def football_data_extra():
    st, _, txt = get("https://www.football-data.co.uk/new/BRA.csv")
    return res(st, txt, max(0, txt.count("\n") - 1) if st == 200 else 0)


def clubelo():
    st, _, txt = get(f"http://api.clubelo.com/{TODAY}")
    return res(st, txt, max(0, txt.count("\n") - 1) if st == 200 else 0)


def openligadb():
    st, js, txt = get("https://api.openligadb.de/getmatchdata/bl1")
    return res(st, txt, len(js) if isinstance(js, list) else 0)


def understat():
    st, _, txt = get("https://understat.com/league/EPL")
    return res(st, txt, 1 if "datesData" in txt else 0)


def fbref():
    st, _, txt = get("https://fbref.com/en/comps/9/Premier-League-Stats")
    return res(st, txt, 1 if "stats_squads" in txt else 0)


def transfermarkt():
    st, _, txt = get("https://www.transfermarkt.com/premier-league/verletztespieler/wettbewerb/GB1")
    return res(st, txt, txt.count("hauptlink"))


def fpl():
    st, js, txt = get("https://fantasy.premierleague.com/api/bootstrap-static/")
    return res(st, txt, len((js or {}).get("elements") or []))


def statsbomb():
    st, js, txt = get("https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json")
    return res(st, txt, len(js) if isinstance(js, list) else 0)


def match_dataset():
    try:
        r = requests.head("https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv", timeout=15)
        return {"http": r.status_code, "ok": r.ok, "mb": round(int(r.headers.get("content-length", 0)) / 1e6, 1)}
    except Exception as exc:
        return {"http": 0, "ok": False, "err": type(exc).__name__}


def worldfootball():
    st, _, txt = get("https://www.worldfootball.net/schedule/eng-premier-league-2025-2026-spieltag/1/")
    return res(st, txt, txt.count("standard_tabelle"))


def thesportsdb_free():
    st, js, txt = get("https://www.thesportsdb.com/api/v1/json/3/eventsday.php", {"d": str(TODAY), "s": "Soccer"})
    return res(st, txt, len((js or {}).get("events") or []))


SOURCES = {
    # odds
    "odds_kambi": kambi, "odds_pinnacle_guest": pinnacle, "odds_bwin": bwin, "odds_espn": espn_odds,
    "odds_polymarket": polymarket, "odds_sofascore": sofascore_odds, "odds_oddsportal": oddsportal,
    # fixtures / results / stats / h2h / lineups
    "stats_espn_summary": espn_summary, "stats_fotmob": fotmob, "stats_sofascore": sofascore_stats,
    "stats_livescore": livescore, "stats_football_data_csv": football_data_csv,
    "stats_football_data_extra": football_data_extra, "stats_clubelo": clubelo, "stats_openligadb": openligadb,
    "stats_understat": understat, "stats_fbref": fbref, "stats_transfermarkt_injuries": transfermarkt,
    "stats_fpl": fpl, "stats_statsbomb": statsbomb, "stats_match_dataset": match_dataset,
    "stats_worldfootball": worldfootball, "stats_thesportsdb_free": thesportsdb_free,
}


def main():
    out = {"probe": "keyless_sources", "date": str(TODAY)}
    for name, fn in SOURCES.items():
        out[name] = safe(fn)
        print(name, json.dumps(out[name]), flush=True)
    out["ok_count"] = sum(1 for k, v in out.items() if isinstance(v, dict) and v.get("ok"))
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15, json={"info": out},
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})


if __name__ == "__main__":
    main()
