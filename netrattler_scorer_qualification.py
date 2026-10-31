"""Shared scorer gates, evaluated before ranking and limiting candidates."""
import math
import os


def qualifies(odds, probability_pct, source):
    try:
        q, p = float(odds), float(probability_pct)
        minimum = float(os.getenv('NETRATTLER_SCORER_MIN_PROB', '0.26'))
        minimum = minimum * 100 if minimum <= 1 else minimum
        min_odds = float(os.getenv('NETRATTLER_SCORER_MIN_ODDS', '1.55'))
        min_edge = float(os.getenv('NETRATTLER_SCORER_MIN_EDGE', '0.005'))
    except (ValueError, TypeError):
        return False, 'invalid_number'
    if not all(math.isfinite(x) for x in (q,p,minimum,min_odds,min_edge)) or not 0 < p < 100:
        return False, 'invalid_number'
    if str(source or '').strip().lower() in ('', 'observed', 'estimated', 'model'):
        return False, 'no_bookmaker_source'
    if q <= 1 or q > 10 or q * p / 100 > 3:
        return False, 'implausible_quote'
    if p < minimum:
        return False, 'below_probability'
    if q < min_odds:
        return False, 'below_odds'
    if p / 100 - 1 / q < min_edge:
        return False, 'below_edge'
    return True, ''
