"""Observed chronological match form for ML features; independent of bookmaker prices."""
from datetime import date, datetime
import math


def _goals(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        v=float(value)
        return int(v) if math.isfinite(v) and v.is_integer() and 0 <= v <= 30 else None
    except (TypeError,ValueError):
        return None


def team_form(rows, team, normalize, target_date=None, window=10, min_games=5):
    cutoff=min(date.fromisoformat(str(target_date or date.today())[:10]),date.today())
    wanted=normalize(team)
    if not wanted:
        return None
    games={}
    for row in rows or []:
        home,away=normalize(row.get('HomeTeam','')),normalize(row.get('AwayTeam',''))
        if not home or not away or (wanted == home) == (wanted == away):
            continue
        day=None
        for fmt in ('%d/%m/%Y','%d/%m/%y','%Y-%m-%d'):
            try:
                day=datetime.strptime(str(row.get('Date') or ''),fmt).date();break
            except ValueError:
                pass
        if day is None or day >= cutoff:
            continue
        h,a=_goals(row.get('FTHG')),_goals(row.get('FTAG'))
        if h is None or a is None:
            continue
        hh,ha=_goals(row.get('HTHG')),_goals(row.get('HTAG'))
        half_known=hh is not None and ha is not None and hh <= h and ha <= a
        own,opp=(h,a) if wanted == home else (a,h)
        games[(day,home,away)]=dict(btts=int(h>0 and a>0),over25=int(h+a>2),
            btts_ht=int(hh>0 and ha>0) if half_known else None,
            over15_ht=int(hh+ha>1) if half_known else None,
            scored=own,conceded=opp,result='W' if own>opp else ('D' if own==opp else 'L'))
    selected=[v for _,v in sorted(games.items())][-window:]
    if len(selected)<min_games:
        return None
    streak=0
    for g in reversed(selected):
        if g['result']!='W':break
        streak+=1
    half=[g for g in selected if g['btts_ht'] is not None]
    n=len(selected)
    return dict(btts_rate=sum(g['btts'] for g in selected)/n,
        o25_rate=sum(g['over25'] for g in selected)/n,
        avg_scored=sum(g['scored'] for g in selected)/n,
        avg_conceded=sum(g['conceded'] for g in selected)/n,
        btts_ht_rate=sum(g['btts_ht'] for g in half)/len(half) if half else 0.20,
        o15ht_rate=sum(g['over15_ht'] for g in half)/len(half) if half else 0.45,
        form_pts=sum(3 if g['result']=='W' else (1 if g['result']=='D' else 0) for g in selected[-5:])/15,
        streak_win=min(streak/5,1),games=n,ht_games=len(half),source='observed_match_form')
