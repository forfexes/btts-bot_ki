"""Decoded 1xBet player-prop groups (G id -> stat). SHADOW DATA ONLY: not wired into tips.
Source: netrattler_1x_group_decode (skill vs base rate, 2026-10-22, 44k matched snapshots).
Only groups with n>=40, skill>=0.30 and a lead >=0.10 over the runner-up are listed.
Caveat: the decoder skips stats with base rate <3% (goals/assists), so a rare-event group could be
mis-decoded; re-verify before using any group for tips."""
from typing import Dict, Optional

GROUP_STAT: Dict[int, dict] = {
    3085: {"stat": "yellow_cards", "skill": 0.456, "n": 196},
    3217: {"stat": "offsides", "skill": 0.423, "n": 291},
    3357: {"stat": "shots", "skill": 0.413, "n": 2376},
    10792: {"stat": "saves", "skill": 0.301, "n": 416},
    11638: {"stat": "offsides", "skill": 0.449, "n": 233},
}
# Decoded but NOT trusted (no clear lead / weak skill): 9120, 11085, 11586, 11587, 11588, 3305, 11568.
# Ambiguous or unmatched (negative skill everywhere): 119, 737, 765, 2487, 2728, 3201, 3405, 7041, 7169, 11142,
# 11296, 11413-11416, 11591.


def stat_for_group(g) -> Optional[str]:
    try:
        d = GROUP_STAT.get(int(g))
    except (TypeError, ValueError):
        return None
    return d["stat"] if d else None
