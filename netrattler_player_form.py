"""Observed L10/L15 player form; unknown measurements are never zero-filled."""
import math


def recent_form(payload, line=1.0):
    values = payload.get('series') if isinstance(payload, dict) else None
    if not isinstance(values, (list, tuple)):
        return None
    measured = []
    for value in values[:15]:
        if value is None or isinstance(value, bool) or value == '':
            continue
        try:
            number = float(value)
        except (ValueError, TypeError):
            continue
        if math.isfinite(number) and 0 <= number <= 100:
            measured.append(number)
    if len(measured) < 5:
        return None
    last10 = measured[:10]
    return dict(games=len(last10), avg=sum(last10)/len(last10),
                hit_rate=sum(x >= line for x in last10)/len(last10),
                l15_games=len(measured), l15_avg=sum(measured)/len(measured),
                series=last10, source='observed_L10_L15')
