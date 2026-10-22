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

def rank_groups(agg, min_n=15):
    """agg[g][stat] = [n, sum_brier, sum_y]. Raw Brier favours rare stats (goals/assists are almost always 0),
    so rank by skill vs the constant base-rate forecast; skip degenerate stats (base rate <3% or >97%)."""
    res = rank_groups(agg)
    espn = [l for l in logs if l.get("fouls_committed") is not None]
    out = {"probe": "1x_group_decode", "rows_with_fouls": len(espn), "rows_total": len(logs), "snaps": len(snaps), "logs": len(logs), "matched": matched, "ranking": res, "winners": {g: clear_winner(rk) for g, rk in res.items() if clear_winner(rk)}}
    print(json.dumps(out)[:4000])
    r = requests.post(f"{mu.rstrip('/')}/rest/v1/netrattler_card_diag",
                      headers={"apikey": mk, "Authorization": f"Bearer {mk}", "Content-Type": "application/json"},
                      json={"info": out}, timeout=30)
    print("diag", r.status_code)

if __name__ == "__main__":
    main()
