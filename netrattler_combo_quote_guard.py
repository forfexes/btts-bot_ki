"""NETRATTLER combo gate: publish real-legged combos without a combined book ticket.

An unconfirmed price is strictly the calculated product of individually
observed decimal odds, NOT an accepted bookmaker offer or a realised P/L.
"""
from __future__ import annotations

import math


def publishable_combo(combo):
    if not isinstance(combo, dict):
        return False
    legs = combo.get("tips")
    if not isinstance(legs, list) or not 3 <= len(legs) <= 12:
        return False
    prices = []
    for tip in legs:
        if not isinstance(tip, dict):
            return False
        if not str(tip.get("match") or "").strip():
            return False
        if (tip.get("_no_real_odds") is True or
                tip.get("synthetic") is True or
                tip.get("estimated_odds") is True):
            return False
        try:
            price = float(tip.get("odds", tip.get("oddsYes")))
        except (ValueError, TypeError, OverflowError):
            return False
        if not math.isfinite(price) or not 1.01 < price < 10000:
            return False
        prices.append(price)

    observed = (combo.get("combined_odds_observed") is True
                and bool(str(combo.get("combined_quote_id") or "").strip())
                and bool(str(combo.get("bookmaker") or "").strip()))
    if observed:
        try:
            quote = float(combo.get("total_odds"))
        except (ValueError, TypeError, OverflowError):
            return False
        if not math.isfinite(quote) or not 1.01 < quote < 100000:
            return False
        combo["combined_quote_calculated"] = False
        return True

    # Never trust an old displayed estimated total when its real leg quotes
    # disagree. Recompute from the current observed legs and label it.
    product = math.prod(prices)
    if not math.isfinite(product) or product <= 1.01:
        return False
    combo["total_odds"] = round(product, 4)
    combo["combined_odds_observed"] = False
    combo["combined_quote_calculated"] = True
    combo["odds_source_type"] = "calculated_from_observed_leg_odds"
    combo["combined_quote_id"] = ""
    return True
