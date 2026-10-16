#!/usr/bin/env python3
"""Auditable read-only live check: how many 1xBet quotes actually corroborate?

Never sends picks, never writes DB rows and never certifies all BetClone brands.
The final production gate remains netrattler_odds_cache_guard.
"""
from collections import Counter
from datetime import datetime, timezone
import os
import netrattler_odds_cache_guard as guard


def summarize(verified_rows, shadow_rows):
    """Count complete independently verified 1X2 and 2.5 goals markets.

    Group by exact fixture identity, date and market. Count individual
    eligible rows only after the full market meets the production validator.
    """
    groups = {}
    joined = [*verified_rows, *shadow_rows]
    approved = guard._corroborated_x1_rows(joined)
    for row in shadow_rows:
        market = str(row.get("market") or "")
        if market not in guard.X1_CROSS_CHECK_MARKETS:
            continue
        key = (guard._norm(row.get("home_team")),
               guard._norm(row.get("away_team")),
               str(row.get("match_date") or ""), market)
        if key[0] and key[1] and id(row) in approved:
            groups.setdefault(key, set()).add(str(row.get("selection") or ""))
    by_market = Counter()
    for (_home, _away, _date, market), selections in groups.items():
        if guard.X1_CROSS_CHECK_MARKETS[market].issubset(selections):
            by_market[market] += 1
    return {
        "verified_reference_rows": len(verified_rows),
        "shadow_rows_evaluated": len(shadow_rows),
        "corroborated_x1_selections": len(approved),
        "complete_markets_1x2": by_market["1x2"],
        "complete_markets_totals_2_5": by_market["totals_2_5"],
        "complete_markets_btts": by_market["btts"],
        "all_other_betclone_families_verified": False,
    }


def main():
    if not guard.SUPABASE_URL or not guard.SUPABASE_KEY:
        raise SystemExit("Missing Supabase URL/key for read-only verification")
    reference = guard._load_rows(force=True)
    shadow = guard._load_x1_rows(force=True)
    stats = summarize(reference, shadow)
    print("BETCLONE_LIVE_SMOKE", stats, flush=True)
    # Fail when a non-permitted shadow market slips through the reader.
    assert all(r.get("market") in guard.X1_CROSS_CHECK_MARKETS for r in shadow)
    assert all(r.get("source") == "1xbet_platform" for r in shadow)
    # An empty market can be legitimate on a quiet calendar and is not an
    # excuse to invent bookmaker prices or assume a family is fully live.
    if stats["corroborated_x1_selections"] == 0:
        print("BETCLONE_LIVE_SMOKE no currently independently matched 1xBet markets", flush=True)


if __name__ == "__main__":
    main()
