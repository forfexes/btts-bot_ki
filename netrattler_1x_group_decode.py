"""Prove which stat each unnamed 1xBet player-prop group (G) is, from results.
For each G and candidate stat: Brier score of implied prob 1/odds vs the real
outcome (stat > line) from player_game_log. Read-only; writes ranking to diag."""
import os, re, json, unicodedata, datetime, requests

STATS = ["shots", "sot", "goals", "assists", "fouls_committed", "fouls_won", "tackles",
         "yellow_cards", "saves", "offsides", "passes"]

def norm(n):
    v = unicodedata.normalize("NFKD", str(n or "").lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in v if not unicodedata.combining(c)))

def fetch(url, key, table, params):
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    out, start = [], 0
    while True:
        r = requests.get(f"{url.rstrip('/')}/rest/v1/{table}", params=params,
                         headers=dict(h, **{"Range-Unit": "items", "Range": f"{start}-{start+999}"}), timeout=60)
        r.raise_for_status()
        b = r.json(); out += b
        if len(b) < 1000 or start > 200000: break
        start += 1000
    return out

def main():
    mu, mk = os.environ["MAIN_URL"], os.environ["MAIN_KEY"]
    vu, vk = os.environ["V2_URL"], os.environ["V2_KEY"]
    snaps = fetch(mu, mk, "x1_player_snapshots", {"select": "captured_at,match_name,g,t,line,odds,player,side", "line": "not.is.null"})
    logs = fetch(vu, vk, "player_game_log", {"select": "player_name,home_team,away_team,match_date," + ",".join(STATS), "match_date": "gte.2026-10-10"})
    idx = {}
    for l in logs:
        idx.setdefault(norm(l["player_name"]), []).append(l)
    agg = {}
    matched = 0
    for s in snaps:
        cands = idx.get(norm(s["player"]))
        if not cands: continue
        cap = s["captured_at"][:10]
        mn = norm(s["match_name"])
        row = next((c for c in cands if norm(c["home_team"])[:6] in mn and cap <= c["match_date"] <= (datetime.date.fromisoformat(cap) + datetime.timedelta(days=4)).isoformat()), None)
        if not row: continue
        matched += 1
        try: line, p = float(s["line"]), 1 / float(s["odds"])
        except Exception: continue
        for st in STATS:
            v = row.get(st)
            if v is None: continue
            y = 1.0 if float(v) > line else 0.0
            a = agg.setdefault(str(s["g"]), {}).setdefault(st, [0, 0.0])
            a[0] += 1; a[1] += (y - p) ** 2
    res = {}
    for g, d in agg.items():
        rk = sorted(((round(b / n, 4), st, n) for st, (n, b) in d.items() if n >= 15))
        res[g] = rk[:3]
    espn = [l for l in logs if l.get("fouls_committed") is not None]
    out = {"probe": "1x_group_decode", "rows_with_fouls": len(espn), "rows_total": len(logs), "snaps": len(snaps), "logs": len(logs), "matched": matched, "ranking": res}
    print(json.dumps(out)[:4000])
    r = requests.post(f"{mu.rstrip('/')}/rest/v1/netrattler_card_diag",
                      headers={"apikey": mk, "Authorization": f"Bearer {mk}", "Content-Type": "application/json"},
                      json={"info": out}, timeout=30)
    print("diag", r.status_code)

main()
