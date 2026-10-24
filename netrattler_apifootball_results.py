"""API-Football day feed as a fallback result source for pending tips (1 request = all leagues of a day).
Rows use the same shape as netrattler_fotmob_results.parse_daily_payload (table match_results)."""
import os
import requests

B = "https://v3.football.api-sports.io"
FINISHED = {"FT", "AET", "PEN"}


def _key():
    ks = [k.strip() for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
    return ks[0] if ks else ""


def parse_fixtures(resp, day):
    rows = []
    for x in resp or []:
        fx, g, t, sc = x.get("fixture") or {}, x.get("goals") or {}, x.get("teams") or {}, x.get("score") or {}
        if (fx.get("status") or {}).get("short") not in FINISHED:
            continue
        hs, aw = g.get("home"), g.get("away")
        h, a = (t.get("home") or {}).get("name"), (t.get("away") or {}).get("name")
        if fx.get("id") is None or hs is None or aw is None or not h or not a:
            continue
        ht = sc.get("halftime") or {}
        rows.append({
            "source": "apifootball", "event_id": str(fx["id"]), "match_date": day,
            "home_team": h, "away_team": a, "home_score": int(hs), "away_score": int(aw),
            "ht_home": ht.get("home"), "ht_away": ht.get("away"),
            "league": (x.get("league") or {}).get("name") or "",
            "country": (x.get("league") or {}).get("country") or "", "status": "finished",
        })
    return rows


def fetch_day(day):
    k = _key()
    if not k:
        return []
    try:
        r = requests.get(B + "/fixtures", headers={"x-apisports-key": k}, params={"date": day}, timeout=30)
        return parse_fixtures(r.json().get("response"), day) if r.ok else []
    except Exception:
        return []
