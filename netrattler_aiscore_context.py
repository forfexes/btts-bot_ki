"""Measured AiScore recent form and match context, with bounded on-demand fallback."""
from datetime import datetime, timezone, date
import os
import time
from netrattler_identity_hub import teams_match

_CACHE = {}
_CALLS = 0
_STARTED = None


def extract_context(payload, home, away, target_date=None):
    cutoff = min(date.fromisoformat(str(target_date or date.today())[:10]), date.today())
    state = payload.get('state', {}) if isinstance(payload, dict) else {}
    seo = state.get('seoH2h') or {}
    data = seo.get('h2hDetailData') or {}
    teams = {str(t.get('id')): t.get('name') for t in data.get('teams', []) if isinstance(t, dict)}
    comps = {str(t.get('id')): t.get('name') for t in data.get('comps', []) if isinstance(t, dict)}
    results = {}
    for group in ('home', 'away', 'h2h'):
        for row in data.get(group, []) or []:
            if not isinstance(row,dict) or row.get('statusId') != 8:
                continue
            h = teams.get(str((row.get('homeTeam') or {}).get('id')))
            a = teams.get(str((row.get('awayTeam') or {}).get('id')))
            if not h or not a or not any(teams_match(t,s) for t in (home,away) for s in (h,a)):
                continue
            try:
                day = datetime.fromtimestamp(float(row['matchTime']),timezone.utc).date()
                hg, ag = row['homeScores'][0], row['awayScores'][0]
                if isinstance(hg,bool) or isinstance(ag,bool) or not isinstance(hg,int) or not isinstance(ag,int): continue
                if day >= cutoff or min(hg,ag)<0 or max(hg,ag)>30: continue
            except (KeyError,ValueError,TypeError,IndexError,OverflowError):
                continue
            key = (str(row.get('id')),str(day),h,a)
            results[key] = {'match_id':str(row.get('id') or ''),'date':str(day),'home':h,'away':a,
                            'home_goals':hg,'away_goals':ag,'league':comps.get(str((row.get('competition') or {}).get('id')),''),'source':'aiscore'}
    detail = state.get('football/detail') or {}
    match = (detail.get('WebMatchData') or {}).get('match') or seo.get('matchInfo') or {}
    mh, ma = (match.get('homeTeam') or {}).get('name'), (match.get('awayTeam') or {}).get('name')
    exact = bool(mh and ma and ((teams_match(mh,home) and teams_match(ma,away)) or
                                (teams_match(mh,away) and teams_match(ma,home))))
    # Preserve labelled sections as evidence; never interpret unknown numeric stat IDs.
    return {'source':'aiscore','recent_results':sorted(results.values(),key=lambda r:r['date'],reverse=True)[:60],
            'match':match if exact else {}, 'lineups':detail.get('lineups') or {} if exact else {},
            'team_stats_raw':detail.get('stats') or {} if exact else {},
            'incidents':detail.get('incidents') or {} if exact else {}}


def team_form(context, team, target_date=None, window=15, min_games=8):
    cutoff = min(date.fromisoformat(str(target_date or date.today())[:10]),date.today())
    selected = {}; window=max(1,min(15,int(window)))
    for row in context.get('recent_results',[]) or []:
        if str(row.get('date') or '') >= str(cutoff): continue
        home,away=row.get('home'),row.get('away')
        if not home or not away or not (teams_match(team,home) ^ teams_match(team,away)):continue
        try:
            date.fromisoformat(row['date'])
            hg,ag=row['home_goals'],row['away_goals']
            if isinstance(hg,bool) or isinstance(ag,bool) or not isinstance(hg,int) or not isinstance(ag,int):continue
            if min(hg,ag)<0 or max(hg,ag)>30:continue
        except (ValueError,TypeError,KeyError):continue
        selected[(row['date'],home,away)]=row
    games=sorted(selected.values(),key=lambda r:r['date'],reverse=True)[:window]
    if len(games)<min_games:return {}
    n=len(games)
    return {'source':'aiscore','games':n,'window':window,
            'btts_pct':round(100*sum(r['home_goals']>0 and r['away_goals']>0 for r in games)/n,1),
            'over25_pct':round(100*sum(r['home_goals']+r['away_goals']>2.5 for r in games)/n,1)}


def recent_form_for_match(home,away,target_date=None):
    """At most eight pair lookups/run; cached; no browser or database writes."""
    global _CALLS,_STARTED
    from netrattler_aiscore import candidate_urls,_requests_html,_json_scripts
    if os.getenv('ENABLE_AISCORE_FORM','true').lower() not in {'1','true','yes','on'}:
        return ({},{})
    key=(home,away,str(target_date or date.today()))
    if key in _CACHE:return _CACHE[key]
    if _STARTED is None:_STARTED=time.monotonic()
    limit=max(0,min(12,int(os.getenv('NETRATTLER_AISCORE_FORM_MAX_MATCHES','8'))))
    if _CALLS>=limit or time.monotonic()-_STARTED>60:return ({},{})
    _CALLS+=1; out=({}, {})
    for url in candidate_urls(home,away)[:2]:
        html,status=_requests_html(url)
        if status in (401,403,429):break
        if not html:continue
        for payload in _json_scripts(html):
            context=extract_context(payload,home,away,target_date)
            h,a=team_form(context,home,target_date),team_form(context,away,target_date)
            if h and a:
                out=(h,a);break
        if out[0]:break
    _CACHE[key]=out
    return out
