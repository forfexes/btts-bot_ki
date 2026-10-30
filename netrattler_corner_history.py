"""Measured, dated team corner history; no league-average fallback or invented zeros."""
from datetime import date, datetime
from netrattler_identity_hub import teams_match



def observed_corner_lines(quotes):
    """Observed half lines only; integer/quarter lines need different settlement."""
    import math
    lines = set()
    for raw in quotes or {}:
        try:
            line = float(raw)
        except (ValueError, TypeError):
            continue
        if math.isfinite(line) and 6.5 <= line <= 14.5 and line % 1 == 0.5:
            lines.add(line)
    return sorted(lines)

def team_corner_profile(rows, team, target_date=None, window=15, min_games=5):
    cutoff = min(date.fromisoformat(str(target_date or date.today())[:10]), date.today())
    games = {}
    for row in rows or []:
        home, away = row.get('HomeTeam'), row.get('AwayTeam')
        if not home or not away:
            continue
        is_home, is_away = teams_match(team, home), teams_match(team, away)
        if is_home == is_away:
            continue
        day = None
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
            try:
                day = datetime.strptime(str(row.get('Date') or ''), fmt).date()
                break
            except ValueError:
                pass
        if day is None or day >= cutoff:
            continue
        # FTHG/FTAG prove the row has been played. Missing corners are not zero.
        try:
            if row.get('HC') in (None, '') or row.get('AC') in (None, ''):
                continue
            int(row['FTHG']); int(row['FTAG'])
            hc, ac = int(row['HC']), int(row['AC'])
            if min(hc, ac) < 0 or max(hc, ac) > 30:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        key = (day, str(home), str(away))
        games[key] = (hc, ac) if is_home else (ac, hc)
    selected = [v for _, v in sorted(games.items(), reverse=True)[:window]]
    if len(selected) < min_games:
        return None
    return {'avg_corners_for': sum(v[0] for v in selected)/len(selected),
            'avg_corners_against': sum(v[1] for v in selected)/len(selected),
            'games': len(selected), 'source': 'football-data.co.uk', 'window': window}
