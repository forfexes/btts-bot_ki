#!/usr/bin/env python3
"""Read-only Bericht: welche Wappen / Spielerfotos / Spielerhistorien fehlen fuer Builder und Tipps (Probe 'data_gap')."""
import os, json, requests
from datetime import date, timedelta
U = (os.getenv("SUPABASE_URL") or "").rstrip("/")
K = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json"}
since = (date.today() - timedelta(days=int(os.getenv("DIAG_DAYS","14")))).isoformat()


def get(table, **params):
    r = requests.get(f"{U}/rest/v1/{table}", headers=H, params=params, timeout=40)
    r.raise_for_status()
    return r.json()


teams, players, err = set(), {}, []
try:
    for b in get("netrattler_builder_picks", select="legs", match_date=f"gte.{since}", limit="600"):
        for lg in b.get("legs") or []:
            m = lg.get("match") or ""
            if " vs " in m:
                a, c = m.split(" vs ", 1); teams |= {a.strip(), c.strip()}
            if lg.get("player"):
                players[lg["player"]] = lg.get("team") or ""
except Exception as e:
    err.append("builder:" + str(e)[:120])
try:
    for t in get("tips", select="match,market,player_name", date=f"gte.{since}", limit="1500"):
        m = t.get("match") or ""
        if " vs " in m and " / " not in m:
            a, c = m.split(" vs ", 1); teams |= {a.strip(), c.strip()}
        if t.get("player_name"):
            players.setdefault(t["player_name"], "")
except Exception as e:
    err.append("tips:" + str(e)[:120])

import netrattler_stats_match_cards as c
no_crest = []
for t in sorted(teams):
    try:
        if not c._badge_bytes(t):
            no_crest.append(t)
    except Exception:
        no_crest.append(t)
no_photo = []
for n, t in sorted(players.items())[:250]:
    try:
        if not c._player_photo(n, t):
            no_photo.append(n)
    except Exception:
        no_photo.append(n)
no_hist = []
try:
    import btts_bot as b
    st = b._supabase_game_log_stats(sorted(players), 20)
    no_hist = [n for n in players if not (st.get(n) or {})]
except Exception as e:
    err.append("hist:" + str(e)[:160])
out = {"probe": "data_gap", "teams": len(teams), "players": len(players), "no_crest": no_crest,
       "no_photo": no_photo, "no_history": no_hist, "errors": err, "photo_stats": dict(c.STATS)}
print(json.dumps(out)[:3500])
requests.post(f"{U}/rest/v1/netrattler_card_diag", headers=H, json={"info": out}, timeout=20)
