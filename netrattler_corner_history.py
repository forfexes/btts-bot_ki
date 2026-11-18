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
        home, away = row.get('HomeTeam') or row.get('home_team'), row.get('AwayTeam') or row.get('away_team')
        if not home or not away:
            continue
        is_home, is_away = teams_match(team, home), teams_match(team, away)
        if is_home == is_away:
            continue
        day = None
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
            try:
                day = datetime.strptime(str(row.get('Date') or row.get('match_date') or ''), fmt).date()
                break
            except ValueError:
                pass
        if day is None or day >= cutoff:
            continue
        # FTHG/FTAG prove the row has been played. Missing corners are not zero.
        try:
            hc_raw = row.get('HC') if row.get('HC') is not None else row.get('home_corners')
            ac_raw = row.get('AC') if row.get('AC') is not None else row.get('away_corners')
            hg_raw = row.get('FTHG') if row.get('FTHG') is not None else row.get('home_goals')
            ag_raw = row.get('FTAG') if row.get('FTAG') is not None else row.get('away_goals')
            if hc_raw in (None, '') or ac_raw in (None, ''):
                continue
            int(hg_raw); int(ag_raw)
            hc, ac = int(hc_raw), int(ac_raw)
            if min(hc, ac) < 0 or max(hc, ac) > 30:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        key = (day, str(home), str(away))
        duplicate = next((k for k in games if k[0] == day
                          and teams_match(k[1], home) and teams_match(k[2], away)), None)
        if duplicate is not None:
            key = duplicate
        pair = (hc, ac) if is_home else (ac, hc)
        games[key] = (*pair, row.get('_source') or row.get('source') or 'football-data.co.uk')
    selected = [v for _, v in sorted(games.items(), reverse=True)[:window]]
    if len(selected) < min_games:
        return None
    return {'avg_corners_for': sum(v[0] for v in selected)/len(selected),
            'avg_corners_against': sum(v[1] for v in selected)/len(selected),
            'games': len(selected), 'source': '+'.join(sorted({v[2] for v in selected})), 'window': window}
