#!/usr/bin/env python3
"""Standalone 1xBet-family player-market snapshot collector (evidence for the group decode).

The bot only snapshots a match when its own prop path happens to reach 1xBet, which gave
4 matches in 4 days. This job takes the public LineFeed list of upcoming football games from
a mirror, keeps major leagues whose player stats we later collect, skips matches already
snapshotted, and stores the "Players' stats" sub-game prices (g, t, line, odds, player).
Plain requests only; a blocked mirror is skipped, never evaded. Old snapshots are pruned.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

import netrattler_prop_sources as ps

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}
MAX_NEW = int(os.getenv("X1_SNAP_MAX_NEW", "40"))
HOURS_AHEAD = int(os.getenv("X1_SNAP_HOURS_AHEAD", "36"))
KEEP_DAYS = int(os.getenv("X1_SNAP_KEEP_DAYS", "14"))

# leagues for which FotMob/ESPN later deliver per-player stats (needed to prove a group)
_LEAGUE_KEYS = ("england. premier", "england. championship", "england. league one", "england. league two",
                "spain. laliga", "spain. la liga", "spain. segunda", "germany. bundesliga", "germany. 2. bundesliga",
                "italy. serie a", "italy. serie b", "france. ligue 1", "france. ligue 2", "netherlands. eredivisie",
                "portugal. primeira", "portugal. liga portugal", "belgium. jupiler", "belgium. pro league",
                "scotland. premiership", "turkey. super lig", "uefa champions league", "uefa europa league",
                "uefa conference league", "usa. mls", "austria. bundesliga", "switzerland. super league",
                "denmark. superliga", "sweden. allsvenskan", "norway. eliteserien", "greece. super league")


def wanted_league(name: Any) -> bool:
    low = str(name or "").lower()
    if any(w in low for w in ("women", "u19", "u21", "u23", "reserve", "youth", "amateur")):
        return False
    return any(k in low for k in _LEAGUE_KEYS)


def pick_games(items: List[Dict[str, Any]], done: set, now_ts: float, hours_ahead: int, limit: int):
    out = []
    for g in items or []:
        o1, o2 = str(g.get("O1") or ""), str(g.get("O2") or "")
        if not o1 or not o2 or not wanted_league(g.get("L")):
            continue
        name = f"{o1} vs {o2}"
        start = g.get("S")
        if isinstance(start, (int, float)) and not (now_ts < start <= now_ts + hours_ahead * 3600):
            continue
        if name in done:
            continue
        out.append((g.get("I") or g.get("CI"), name))
        if len(out) >= limit:
            break
    return out


def already_snapshotted() -> set:
    since = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    r = requests.get(f"{SB}/rest/v1/x1_player_snapshots", headers=H, timeout=30,
                     params={"select": "match_name", "captured_at": f"gte.{since}", "limit": "20000"})
    return {x["match_name"] for x in r.json()} if r.ok and isinstance(r.json(), list) else set()


def prune() -> None:
    cut = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    requests.delete(f"{SB}/rest/v1/x1_player_snapshots", headers=H, timeout=60, params={"captured_at": f"lt.{cut}"})


def run() -> Dict[str, int]:
    stats = {"listed": 0, "picked": 0, "matches_saved": 0, "rows": 0}
    if not SB or not SK:
        print("no supabase env"); return stats
    done = already_snapshotted()
    now_ts = time.time()
    for host in ps._1X_HOSTS:
        data = ps._get_json(f"{host}/service-api/LineFeed/Get1x2_VZip",
                            params={"sports": 1, "count": 1000, "lng": "en", "mode": 4, "country": 1}, timeout=15)
        items = (data or {}).get("Value") or []
        if not items:
            continue
        stats["listed"] = len(items)
        games = pick_games(items, done, now_ts, HOURS_AHEAD, MAX_NEW)
        stats["picked"] = len(games)
        for gid, name in games:
            game = ps._get_json(f"{host}/service-api/LineFeed/GetGameZip",
                                params={"id": gid, "lng": "en", "cfview": 0, "grMode": 4, "country": 1}, timeout=15)
            val = (game or {}).get("Value") or {}
            ps.X1_SNAPSHOT.clear()
            ps._snapshot_x1_player_markets(host, val, name)
            rows = list(ps.X1_SNAPSHOT)
            if rows:
                p = requests.post(f"{SB}/rest/v1/x1_player_snapshots", headers={**H, "Prefer": "return=minimal"},
                                  json=rows, timeout=60)
                if p.ok:
                    stats["matches_saved"] += 1; stats["rows"] += len(rows)
            time.sleep(0.4)
        break  # one working mirror is enough
    prune()
    print(f"x1 snapshot collector: {stats}")
    try:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, timeout=20,
                      json={"info": {"probe": "x1_snapshot_collector", **stats}})
    except Exception:
        pass
    return stats


if __name__ == "__main__":
    run()
