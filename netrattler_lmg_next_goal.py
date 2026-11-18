"""Optional next-goal TEAM prediction for NETRATTLER Goal Hunter.

A directional hypothesis, NOT a calibrated probability or guaranteed event.
Only verified provider team statistics are accepted, and weak/close games abstain.
"""

from __future__ import annotations

from math import isfinite


def _valid_count(value):
    return type(value) is int and 0 <= value <= 200


def _valid_xg(value):
    return type(value) in (float, int) and isfinite(value) and 0 <= value <= 20


def select_next_goal(metrics):
    """Return 'home', 'away', or None. No model probability is fabricated.

    Requires an extreme shot/SOT imbalance, or a still-substantial imbalance
    corroborated by distinct, verified team xG totals. xG missing => higher bar.
    """
    teams = (metrics or {}).get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    for side in (home, away):
        if not _valid_count(side.get("shots")) or not _valid_count(side.get("sot")):
            return None
        if side["sot"] > side["shots"]:
            return None
    if home["sot"] == away["sot"]:
        return None
    side = "home" if home["sot"] > away["sot"] else "away"
    dominant = home if side == "home" else away
    other = away if side == "home" else home
    lead_sot = dominant["sot"] - other["sot"]
    lead_shots = dominant["shots"] - other["shots"]
    has_both_xg = _valid_xg(home.get("xg")) and _valid_xg(away.get("xg"))
    if has_both_xg:
        # Shot volume, shots on target and xG must ALL agree.
        if (dominant["sot"] < 5 or dominant["shots"] < 9
                or lead_sot < 3 or lead_shots < 4
                or dominant["xg"] < 0.8
                or dominant["xg"] - other["xg"] < 0.5
                or dominant["xg"] < 1.6 * other["xg"]):
            return None
    else:
        # No xG available: only especially dominant shot evidence qualifies.
        if (dominant["sot"] < 7 or dominant["shots"] < 15
                or lead_sot < 5 or lead_shots < 9):
            return None
    return side


def evaluate_next_goal(next_goal_side, initial_score, final_score):
    """Return status without inventing chronological goal order.

    When exactly one team scored after alert, next scorer is mathematically
    certain from the two scores. If BOTH scored, the final score alone cannot
    establish order, so return unverified. No goals => void.
    """
    if next_goal_side not in ("home", "away"):
        return None
    if (not isinstance(initial_score, (list, tuple))
            or not isinstance(final_score, (list, tuple))
            or len(initial_score) != 2 or len(final_score) != 2
            or not all(_valid_count(x) for x in (*initial_score, *final_score))):
        return "unverified"
    dh, da = final_score[0] - initial_score[0], final_score[1] - initial_score[1]
    if dh < 0 or da < 0:
        return "unverified"
    if dh == da == 0:
        return "void"
    if dh > 0 and da > 0:
        return "unverified"
    first = "home" if dh > 0 else "away"
    return "won" if next_goal_side == first else "lost"
