"""Bounded historical VAR evidence. No Telegram, database writes or inferred zeros."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from netrattler_apif_response import checked_response
from netrattler_var import normalize_var_events

BASE = 'https://v3.football.api-sports.io'
LEAGUES = (39, 140, 135, 78, 61, 94, 2, 3, 848)
MAX_FIXTURES = 36
MAX_CALLS = 2 * len(LEAGUES) + MAX_FIXTURES


def history(api, today, max_fixtures=MAX_FIXTURES):
    max_fixtures = max(0, min(MAX_FIXTURES, int(max_fixtures)))
    start = today - timedelta(days=30)
    candidates = {}
    coverage = {}
    season = today.year if today.month >= 7 else today.year - 1
    for league in LEAGUES:
        metadata = api('/leagues', {'id': league, 'season': season})
        seasons = [s for item in metadata if (item.get('league') or {}).get('id') == league
                   for s in item.get('seasons') or [] if s.get('year') == season]
        events_available = any(((s.get('coverage') or {}).get('fixtures') or {}).get('events') is True for s in seasons)
        coverage[str(league)] = dict(events_available=events_available, var_coverage='unverified')
        if not events_available:
            continue
        for fx in api('/fixtures', {'league':league,'season':today.year if today.month>=7 else today.year-1,
                                    'from':start.isoformat(),'to':(today-timedelta(days=1)).isoformat(),'status':'FT'}):
            f = fx.get('fixture') or {}
            day = str(f.get('date') or '')[:10]
            if f.get('id') and (f.get('status') or {}).get('short')=='FT' and start.isoformat()<=day<today.isoformat():
                candidates[f['id']] = fx
    # Round-robin leagues rather than filling the sample from a single competition.
    buckets = [[f for f in candidates.values() if (f.get('league') or {}).get('id')==lid]
               for lid in LEAGUES]
    for bucket in buckets:
        bucket.sort(key=lambda f:f['fixture']['date'],reverse=True)
    fixtures=[]
    while any(buckets) and len(fixtures)<max_fixtures:
        for bucket in buckets:
            if bucket and len(fixtures)<max_fixtures:
                fixtures.append(bucket.pop(0))
    rows=[]
    for fx in fixtures:
        events=api('/fixtures/events',{'fixture':fx['fixture']['id']})
        rows.append(dict(fixture_id=fx['fixture']['id'],date=fx['fixture']['date'],
            league=fx.get('league'),teams=fx.get('teams'),events=normalize_var_events(events),
            event_count=len(events),coverage='unverified',no_var_inferred=False,
            tip_eligible=False))
    return dict(source='api-football',from_date=start.isoformat(),to_date=(today-timedelta(days=1)).isoformat(),
                league_coverage=coverage,fixture_count=len(rows),var_events=sum(len(r['events']) for r in rows),fixtures=rows)


def main():
    keys=(os.getenv('API_FOOTBALL_KEYS') or os.getenv('API_FOOTBALL_KEY') or '').replace('\n',',').split(',')
    key=next((k.strip() for k in keys if k.strip()),'')
    if not key:
        raise RuntimeError('API-Football credentials missing')
    calls=0
    def api(path,params):
        nonlocal calls
        if calls>=MAX_CALLS:
            raise RuntimeError('Historical VAR API budget exhausted')
        calls+=1
        response=requests.get(BASE+path,params=params,headers={'x-apisports-key':key},timeout=25)
        return checked_response(response)
    result=history(api,datetime.now(timezone.utc).date())
    result['api_calls']=calls
    Path('netrattler_var_history.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='fixtures'}))


if __name__=='__main__':
    main()
