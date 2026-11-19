#!/usr/bin/env python3
"""Read-only paired live source coverage for Goal Hunter.

This audit NEVER selects tips, writes to Supabase or posts to Telegram.
It compares exact in-play FotMob fixtures with ESPN coverage; an
unverified or ambiguous match is not merged.
"""
from __future__ import annotations
import datetime as dt
import json
import requests
import netrattler_lmg_free as common
import netrattler_lmg_fotmob as fotmob


def pair_coverage(fixtures: list[dict], board: dict) -> dict:
    candidates = common.fixtures_from_espn(board)
    used = set()
    matched = []
    ambiguous = 0
    for fx in fixtures:
        possible = [
            event for event in candidates
            if fotmob._club_name(event["home"]) == fotmob._club_name(fx["home"])
            and fotmob._club_name(event["away"]) == fotmob._club_name(fx["away"])
            and abs((event["kickoff"] - fx["kickoff"]).total_seconds()) <= 900
            and (event["hg"], event["ag"]) == (fx["hg"], fx["ag"])
            and abs(event["minute"] - fx["minute"]) <= 5
        ]
        if len(possible) != 1:
            ambiguous += len(possible) > 1
            continue
        event = possible[0]
        key = event["fixture_id"]
        if key in used:
            ambiguous += 1
            continue
        used.add(key)
        matched.append({
            "fotmob_id": fx["fixture_id"],
            "espn_id": key,
            "minute": fx["minute"],
            "kickoff_delta_seconds": int(abs((event["kickoff"] - fx["kickoff"]).total_seconds())),
        })
    return {
        "fotmob_in_window": len(fixtures),
        "espn_in_window": len(candidates),
        "paired": len(matched),
        "ambiguous": ambiguous,
        "unpaired_fotmob": len(fixtures) - len(matched),
        "pairs": matched[:16],
        "production_routing_changed": False,
        "telegram_messages": 0,
    }


def main() -> None:
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    try:
        daily = fotmob.fetch_fotmob(day)
        board = common._get(f"{common.ESPN}/all/scoreboard",
                            params={"dates": day, "limit": "1000"})
        result = pair_coverage(fotmob.fixtures_from_fotmob(daily), board)
        print("LMG_PAIRED_SOURCE_AUDIT", json.dumps(result, ensure_ascii=False), flush=True)
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        print("LMG_PAIRED_SOURCE_UNAVAILABLE",
              json.dumps({"type": type(exc).__name__, "production_routing_changed": False}),
              flush=True)


if __name__ == "__main__":
    main()
