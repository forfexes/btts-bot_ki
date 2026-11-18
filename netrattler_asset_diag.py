#!/usr/bin/env python3
"""Read-only coverage probe for new player-photo and crest cards.

Never sends tips, does not write to Supabase. Uses latest builder legs as the
sample so the test probes real players, not unrelated stock images.
"""
import json
import os
import requests
from datetime import date, timedelta

import netrattler_stats_match_cards as cards
from netrattler_visual_gate import club_for_player, club_same


def probe():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if not (url and key):
        raise RuntimeError("Supabase readonly config missing")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    since = (date.today() - timedelta(days=2)).isoformat()
    response = requests.get(
        url + "/rest/v1/netrattler_builder_picks", headers=headers,
        params={"select":"legs,match_date","match_date":"gte." + since,
                "telegram_sent":"eq.true","order":"created_at.desc","limit":"35"},timeout=25)
    response.raise_for_status()
    entries = response.json()
    players, teams = {}, set()
    for row in entries if isinstance(entries, list) else []:
        day = str(row.get("match_date") or "")
        for leg in row.get("legs") or []:
            if not isinstance(leg, dict):
                continue
            name, match = leg.get("player") or "", leg.get("match") or ""
            if not name or not match:
                continue
            sides = cards._teams(match)
            teams.update(side for side in sides if side)
            club = leg.get("team") or club_for_player(name, match, day)
            if club and any(club_same(club, x) for x in sides):
                players[(name,club)] = day
    sample = sorted(players.items())[:int(os.getenv("NETRATTLER_ASSET_PROBE_MAX", "10"))]
    out = {"probe":"asset_diag_v2","players":len(players),"sample":len(sample),
           "teams":len(teams),"missing_photo":[],"missing_crest":[],
           "checked_photos":0,"checked_crests":0}
    for name, team in [x[0] for x in sample]:
        try:
            ok=bool(cards._player_photo(name, team))
        except Exception:
            ok=False
        out["checked_photos"] += 1
        if not ok:
            out["missing_photo"].append([name,team])
    for team in sorted(teams)[:12]:
        try:
            ok=bool(cards._badge_bytes(team))
        except Exception:
            ok=False
        out["checked_crests"] += 1
        if not ok:
            out["missing_crest"].append(team)
    out["photo_stats"] = {k:v for k,v in cards.STATS.items() if k.startswith("player_")}
    print(json.dumps(out,ensure_ascii=False,default=str))
    return out


if __name__ == "__main__":
    probe()
