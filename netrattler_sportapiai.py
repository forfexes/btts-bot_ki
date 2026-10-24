"""sportapi.ai daily collector (free plan: 2000 req/day, we use <=120).
Finished matches of yesterday: team stats (fouls, shots, tackles, yellow cards, saves, passes) + events
(goal / assist / yellow_card with player name and minute). Stored in sapiai_match."""
import os
import datetime as dt
import requests

B = "https://sportapi.ai/api"
KEY = os.getenv("SPORTAPI_AI_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
MAX_MATCHES = int(os.getenv("SAPIAI_MAX_MATCHES", "55"))  # 2 requests per match


def _num(v):
    try:
        return float(v) if "." in str(v) else int(v)
    except (TypeError, ValueError):
        return None


def parse_stats(data):
    """{'home': {...}, 'away': {...}} with numeric values; None when not available."""
    if not isinstance(data, dict) or not (data.get("home") or data.get("away")):
        return None
    return {side: {k: _num(v) for k, v in (data.get(side) or {}).items() if _num(v) is not None} for side in ("home", "away")}


def parse_events(data):
    keep = {"goal", "assist", "yellow_card", "red_card"}
    return [{"minute": e.get("minute"), "type": e.get("event_type"), "player": e.get("player_name"), "side": e.get("team_side")}
            for e in data or [] if e.get("event_type") in keep]


def pick_finished(fixtures, known, limit):
    out = []
    for m in fixtures or []:
        if m.get("status") == "FT" and m.get("id") is not None and str(m["id"]) not in known:
            out.append(m)
    return out[:limit]


def _h():
    return {"X-Api-Key": KEY, "Accept": "application/json"}


def _sb():
    return {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}


def run():
    if not (KEY and SB and SK):
        print("missing secrets")
        return 0
    day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    fx = requests.get(f"{B}/fixtures/date/{day}", headers=_h(), timeout=30).json().get("data") or []
    ids = [str(m["id"]) for m in fx if m.get("id") is not None]
    k = requests.get(f"{SB}/rest/v1/sapiai_match?select=fixture_id&fixture_id=in.({','.join(ids)})", headers=_sb(), timeout=20) if ids else None
    known = {str(x["fixture_id"]) for x in k.json()} if k is not None and k.ok else set()
    rows = []
    for m in pick_finished(fx, known, MAX_MATCHES):
        s = requests.get(f"{B}/fixtures/{m['id']}/stats", headers=_h(), timeout=30)
        e = requests.get(f"{B}/fixtures/{m['id']}/events", headers=_h(), timeout=30)
        rows.append({"fixture_id": m["id"], "match_date": day, "league": m.get("league_name"),
                     "home_team": m.get("home_team"), "away_team": m.get("away_team"),
                     "home_score": m.get("home_score"), "away_score": m.get("away_score"),
                     "team_stats": parse_stats((s.json() if s.ok else {}).get("data")),
                     "events": parse_events((e.json() if e.ok else {}).get("data"))})
    if rows:
        p = requests.post(f"{SB}/rest/v1/sapiai_match", json=rows, timeout=40,
                          headers={**_sb(), "Prefer": "resolution=ignore-duplicates"})
        print("saved", len(rows) if p.ok else f"failed {p.status_code}")
    return len(rows)


if __name__ == "__main__":
    run()
