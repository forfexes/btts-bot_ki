"""Only real bookmaker-issued multi-leg ticket prices reach NETRATTLER Telegram.

Multiplying individually observed leg odds is an indicative calculation,
NOT independently observed bookmaker combined odds. This guard never
fabricates a quote, and never silently applies a generic fallback.
"""
from __future__ import annotations

import math


def publishable_combo(combo):
    if not isinstance(combo,dict):
        return False
    if (combo.get("combined_odds_observed") is not True
            or not str(combo.get("combined_quote_id") or "").strip()
            or not str(combo.get("bookmaker") or "").strip()):
        return False
    try:
        quote=float(combo.get("total_odds"))
        if not math.isfinite(quote) or quote<=1.01 or quote>=100000:
            return False
    except (ValueError,TypeError):
        return False
    legs=combo.get("tips")
    if not isinstance(legs,list) or not 3<=len(legs)<=12:
        return False
    for tip in legs:
        if not isinstance(tip,dict):
            return False
        if not str(tip.get("match") or "").strip():
            return False
        if (tip.get("_no_real_odds") is True or
                tip.get("synthetic") is True or
                tip.get("estimated_odds") is True):
            return False
        try:
            leg_price=float(tip.get("odds",tip.get("oddsYes")))
        except (TypeError,ValueError):
            return False
        if not math.isfinite(leg_price) or not 1.01<leg_price<10000:
            return False
    return True
