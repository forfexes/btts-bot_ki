"""footballdata.io collector (free plan: 1000 req/month). Max 25 requests/run, 1 run/day.
Stores finished-match team stats (fouls, cards, corners, shots, xG, HT goals) in fdio_match_stats."""
import os
import requests

BASE = "https://footballdata.io/api/v1"
KEY = os.getenv("FOOTBALLDATA_IO_KEY", "").strip()
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
MAX_REQ = int(os.getenv("FDIO_MAX_REQ", "25"))
STAT_KEYS = ("fouls", "yellow_cards", "red_cards", "cards", "corners", "shots", "shots_on_target",
             "offsides", "possession", "xg", "half_time_goals", "penalties_won")


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_match(data):
    """data = response['data'] of /matches/{id}/stats -> row dict or None."""
    m = (data or {}).get("match") or {}
    st = (data or {}).get("stats") or {}
    if m.get("status") != "complete" or not m.get("match_id"):
        return None
    sc = m.get("score") or {}
    ht = st.get("half_time_goals") or {}
    return {
        "match_id": str(m["match_id"]),
        "match_date": (m.get("match_date") or "").replace(" ", "T") + "+00:00" if m.get("match_date") else None,
        "league": (m.get("league") or {}).get("name"),
        "home_team": (m.get("home_team") or {}).get("team_name"),
        "away_team": (m.get("away_team") or {}).get("team_name"),
        "home_goals": _i(sc.get("home")), "away_goals": _i(sc.get("away")),
        "ht_home": _i(ht.get("home")), "ht_away": _i(ht.get("away")),
        "stats": {k: st[k] for k in STAT_KEYS if k in st},
    }


def _hdr():
    return {"Authorization": f"Bearer {KEY}", "Accept": "application/json"}


def _sb(h=None):
    return {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json", **(h or {})}


def pick_new(results, known, limit):
    ids = []
    for m in results:
        mid = str(m.get("match_id") or "")
        if mid and m.get("status") == "complete" and mid not in known and mid not in ids:
            ids.append(mid)
    return ids[:limit]


def run():
    if not (KEY and SB and SK):
        print("missing secrets")
        return 0
    used = 1
    r = requests.get(BASE + "/fixtures/results", headers=_hdr(), timeout=30)
    results = (r.json().get("data") or {}).get("matches") or [] if r.ok else []
    ids = [str(m.get("match_id")) for m in results if m.get("match_id")]
    k = requests.get(f"{SB}/rest/v1/fdio_match_stats?select=match_id&match_id=in.({','.join(ids)})",
                     headers=_sb(), timeout=20) if ids else None
    known = {x["match_id"] for x in k.json()} if k is not None and k.ok else set()
    saved = 0
    for mid in pick_new(results, known, MAX_REQ - used):
        s = requests.get(f"{BASE}/matches/{mid}/stats", headers=_hdr(), timeout=30)
        if not s.ok:
            continue
        row = parse_match(s.json().get("data"))
        if row:
            p = requests.post(f"{SB}/rest/v1/fdio_match_stats", json=row, timeout=20,
                              headers=_sb({"Prefer": "resolution=ignore-duplicates"}))
            saved += 1 if p.ok else 0
    print("saved", saved)
    return saved


if __name__ == "__main__":
    run()
