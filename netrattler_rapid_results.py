"""RapidAPI 'free-api-live-football-data' day feed as last-resort result source for old pending tips.
1 request = all matches of a day (also small leagues, past days). Free plan: 100 requests, so use sparingly."""
import os
import requests

HOST = os.getenv("RAPIDAPI_HOST", "free-api-live-football-data.p.rapidapi.com")


def parse_matches(body, day):
    ms = ((body or {}).get("response") or {}).get("matches") if isinstance(body, dict) else None
    rows = []
    for m in ms or []:
        st = m.get("status") or {}
        h, a = m.get("home") or {}, m.get("away") or {}
        if not st.get("finished") or st.get("cancelled") or m.get("id") is None:
            continue
        hs, aw = h.get("score"), a.get("score")
        hn, an = h.get("longName") or h.get("name"), a.get("longName") or a.get("name")
        if hs is None or aw is None or not hn or not an:
            continue
        rows.append({
            "source": "rapidapi", "event_id": str(m["id"]), "match_date": day,
            "home_team": hn, "away_team": an, "home_score": int(hs), "away_score": int(aw),
            "ht_home": None, "ht_away": None, "league": str(m.get("leagueId") or ""),
            "country": "", "status": "finished",
        })
    return rows


def fetch_day(day):
    key = (os.getenv("RAPIDAPI_KEY") or "").strip()
    if not key:
        return []
    try:
        r = requests.get(f"https://{HOST}/football-get-matches-by-date",
                         headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST},
                         params={"date": day.replace("-", "")}, timeout=40)
        return parse_matches(r.json(), day) if r.ok else []
    except Exception:
        return []
