#!/usr/bin/env python3
"""Collect 1xBet player-priced market observations without guessing group meanings.

The public LineFeed player sub-games put player identities inside E[].PL
(a dictionary containing N=name, I=id, T=team side). Group codes G and
outcome codes T are intentionally opaque: these records are never tip inputs.
"""
from __future__ import annotations

import math
from typing import Any, Mapping
import requests

MAX_SUBGAME_ROWS = 400
MAX_WRITE_ROWS = 1200
BATCH_SIZE = 200


def _player_subgame(title: str) -> bool:
    name = " ".join(str(title or "").lower().split())
    return ("players' stats" in name or "player stats" in name
            or "shots towards" in name or "player shots" in name
            or "player fouls" in name or "player tackles" in name)


def extract_snapshots(payload: Any, match_name: str, subgame_title: str,
                      max_rows: int = MAX_SUBGAME_ROWS) -> list[dict]:
    """Return only observed named-player price records; no inferred markets."""
    if not isinstance(payload, dict) or not _player_subgame(subgame_title):
        return []
    if " vs " not in str(match_name) or len(match_name) > 140:
        return []
    out, seen = [], set()
    for event in (payload.get("E") or []):
        if len(out) >= max_rows:
            break
        if not isinstance(event, dict):
            continue
        player = event.get("PL")
        if not isinstance(player, dict):
            continue
        name = str(player.get("N") or "").strip()
        ident = player.get("I")
        if not name or len(name) < 3 or len(name) > 100 or not ident:
            continue
        try:
            group, code, side = int(event["G"]), int(event["T"]), int(player.get("T") or 0)
            odds = float(event["C"])
        except (KeyError, ValueError, TypeError):
            continue
        if group <= 0 or code <= 0 or side not in (1, 2) or not math.isfinite(odds) or not (1.01 <= odds <= 200):
            continue
        line = event.get("P")
        if line is not None:
            try:
                line = float(line)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(line) or not (-100 <= line <= 100):
                continue
        key = (group, code, line, str(ident), side)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "match_name": str(match_name),
            "subgame_title": str(subgame_title)[:90],
            "g": group, "t": code, "line": line,
            "odds": round(odds, 4), "player": name, "side": side,
        })
    return out


def persist_snapshots(rows: list[dict], url: str, key: str, requester: Any = requests) -> int:
    """Append bounded shadow-only records. Fail visibly on Supabase write errors."""
    if not rows or not url or not key:
        return 0
    saved = 0
    for offset in range(0, min(len(rows), MAX_WRITE_ROWS), BATCH_SIZE):
        batch = rows[offset:offset + BATCH_SIZE]
        response = requester.post(
            f"{url.rstrip('/')}/rest/v1/x1_player_snapshots",
            json=batch, headers={
                "apikey": key, "Authorization": f"Bearer {key}",
                "Content-Type": "application/json", "Prefer": "return=minimal",
            }, timeout=15,
        )
        response.raise_for_status()
        saved += len(batch)
    return saved
