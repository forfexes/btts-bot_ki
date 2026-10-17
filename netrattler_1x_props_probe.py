#!/usr/bin/env python3
"""Bounded, read-only diagnostic: which player-prop groups does the public
1xBet-family LineFeed actually expose for real upcoming football matches?

Why: netrattler_prop_sources.fetch_1xbet_player_props() assumes group ids
2059-2062 (shots/sot/fouls/tackles) and player names in the PN field, but
this mapping was never verified, and the builder pool shows 0 tackles /
0 fouls-won legs. This probe records ONLY group ids, group names, counts
and sub-game titles for a few top-league fixtures. Plain requests with one
honest User-Agent; no impersonation, no cloudscraper, no bypass. Results
go to netrattler_card_diag (probe='x1_props_probe').
"""
from __future__ import annotations

import json
import os
from collections import Counter

import requests

HOSTS = ("https://22bet.com", "https://melbet.com", "https://betwinner.com")
HEADERS = {"User-Agent": "NETRATTLER-PublicSourceAudit/2.0 (+https://github.com/forfexes/btts-bot_ki)",
           "Accept": "application/json"}
TOP = ("england", "premier", "germany", "bundesliga", "spain", "laliga", "italy", "serie a",
       "france", "ligue 1", "championship")


def _get(url, params):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        return r.status_code, (r.json() if r.status_code == 200 else None)
    except Exception as exc:
        return type(exc).__name__, None


def summarize_game(val: dict) -> dict:
    groups = Counter()
    names = {}
    for grp in (val.get("GE") or []):
        gid = grp.get("G")
        n = sum(len(r) if isinstance(r, list) else 1 for r in (grp.get("E") or []))
        groups[gid] += n
        if grp.get("GS"):
            names[gid] = str(grp.get("GS"))[:40]
    subgames = [{"id": sg.get("CI"), "title": str(sg.get("TG") or sg.get("PN") or "")[:50]}
                for sg in (val.get("SG") or [])[:40]]
    return {"groups": groups.most_common(40), "group_names": names, "subgames": subgames}


def run() -> list:
    out = []
    for host in HOSTS:
        st, data = _get(f"{host}/service-api/LineFeed/Get1x2_VZip",
                        {"sports": 1, "count": 300, "lng": "en", "mode": 4, "country": 1})
        row = {"host": host, "list_http": st}
        games = (data or {}).get("Value") or []
        row["list_events"] = len(games)
        picked = [g for g in games if any(t in str(g.get("L") or "").lower() for t in TOP)][:3]
        row["fixtures"] = []
        for g in picked:
            gid = g.get("I")
            st2, game = _get(f"{host}/service-api/LineFeed/GetGameZip",
                             {"id": gid, "lng": "en", "cfview": 0, "grMode": 4, "country": 1,
                              "marketType": 1, "isSubGames": "true"})
            fx = {"match": f"{g.get('O1')} vs {g.get('O2')}"[:80], "league": str(g.get("L"))[:50], "http": st2}
            if game and game.get("Value"):
                fx.update(summarize_game(game["Value"]))
                # Player props usually live in sub-games: check up to 4 of them.
                sub_details = []
                for sg in (game["Value"].get("SG") or [])[:60]:
                    title = str(sg.get("TG") or sg.get("PN") or "").lower()
                    if not any(k in title for k in ("player", "foul", "tackle", "shot", "statistic")):
                        continue
                    st3, sub = _get(f"{host}/service-api/LineFeed/GetGameZip",
                                    {"id": sg.get("CI"), "lng": "en", "cfview": 0, "grMode": 4,
                                     "country": 1, "marketType": 1})
                    if sub and sub.get("Value"):
                        sv = sub["Value"]
                        sample = []
                        for grp in (sv.get("GE") or [])[:3]:
                            for r in (grp.get("E") or [])[:1]:
                                for e in (r if isinstance(r, list) else [r])[:2]:
                                    sample.append({k: e.get(k) for k in ("G", "T", "C", "P", "PN", "B") if k in e})
                        sub_details.append({"title": title[:50], "http": st3,
                                            "groups": summarize_game(sv)["groups"][:15],
                                            "group_names": summarize_game(sv)["group_names"],
                                            "sample": sample[:6]})
                    if len(sub_details) >= 4:
                        break
                fx["player_subgames"] = sub_details
            row["fixtures"].append(fx)
        out.append(row)
        if row["fixtures"]:
            break
    return out


def main() -> int:
    rows = run()
    print(json.dumps(rows, indent=2, ensure_ascii=False)[:8000])
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", timeout=15,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"info": {"probe": "x1_props_probe", "rows": rows}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
