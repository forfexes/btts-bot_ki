"""Bounded API-Football settlement evidence in memory. No raw or player-table writes."""
import json
import os
from datetime import datetime,timedelta,timezone
import requests
from netrattler_apif_response import checked_response,number
from netrattler_apif_history import player_rows,corner_row

BASE='https://v3.football.api-sports.io'


def collect(tips,match_parts,row_date,same,log=print):
    key=next((k.strip() for k in (os.getenv('API_FOOTBALL_KEYS') or '').replace('\n',',').split(',') if k.strip()),'')
    if not key:return [],[]
    today=datetime.now(timezone.utc).date()
    lookback=max(1,min(30,int(os.getenv('SETTLEMENT_APIF_LOOKBACK_DAYS','14'))))
    ceiling=max(1,min(250,int(os.getenv('SETTLEMENT_APIF_MAX_CALLS','150'))))
    wanted={}
    for tip in tips:
        day=row_date(tip)
        candidates=[tip]
        for field in ('legs','builder_legs'):
            legs=tip.get(field) or []
            if isinstance(legs,str):
                try:legs=json.loads(legs)
                except ValueError:legs=[]
            if isinstance(legs,list):candidates.extend(l for l in legs if isinstance(l,dict))
        for row in candidates:
            d=str(row.get('match_date') or row.get('date') or day)[:10]
            try:date=datetime.fromisoformat(d).date()
            except (TypeError,ValueError):continue
            if not today-timedelta(days=lookback)<=date<=today:continue
            home,away,_=match_parts(row)
            if home and away:wanted.setdefault(d,set()).add((home,away))
    calls=0;results=[];players=[];seen=set()
    def api(path,params):
        nonlocal calls
        if calls>=ceiling:return []
        calls+=1
        try:
            response=requests.get(BASE+path,params=params,headers={'x-apisports-key':key},timeout=8)
            return checked_response(response)
        except Exception as exc:
            # Never log request URLs or credentials from exception text.
            log('API settlement request unavailable: '+type(exc).__name__)
            return []
    for day,pairs in sorted(wanted.items(),reverse=True):
        if calls>=ceiling:break
        for fx in api('/fixtures',{'date':day}):
            fixture=fx.get('fixture') or {};teams=fx.get('teams') or {}
            home=(teams.get('home') or {}).get('name');away=(teams.get('away') or {}).get('name')
            fid=fixture.get('id')
            if (not fid or fid in seen or fixture.get('date','')[:10]!=day
                or (fixture.get('status') or {}).get('short')!='FT'
                or not any(same(h,home) and same(a,away) for h,a in pairs)):continue
            hs=number((fx.get('goals') or {}).get('home'));aw=number((fx.get('goals') or {}).get('away'))
            if hs is None or aw is None:continue
            seen.add(fid)
            half=(fx.get('score') or {}).get('halftime') or {}
            row={'source':'apifootball_settlement','_result_table':'apifootball_settlement',
                 'event_id':str(fid),'match_date':day,'home_team':home,'away_team':away,
                 'home_score':hs,'away_score':aw,'home_score_ht':number(half.get('home')),
                 'away_score_ht':number(half.get('away'))}
            if calls<ceiling:
                try:
                    for p in player_rows(api('/fixtures/players',{'fixture':fid}),fx):
                        p.update(source='apifootball_settlement',event_id=str(fid),home_team=home,away_team=away,
                                 sot=p.get('shots_on'),shots_on_target=p.get('shots_on'),
                                 fouls_won=p.get('fouls_drawn'),yellow_cards=p.get('yellow'),red_cards=p.get('red'))
                        players.append(p)
                except (KeyError,TypeError,ValueError):log('API settlement player payload incomplete')
            if calls<ceiling:
                try:
                    corners=corner_row(api('/fixtures/statistics',{'fixture':fid}),fx)
                    if corners:row.update(home_corners=corners['home_corners'],away_corners=corners['away_corners'])
                except (KeyError,TypeError,ValueError):log('API settlement match statistics incomplete')
            results.append(row)
    log(f'API settlement evidence: fixtures={len(results)} player_rows={len(players)} calls={calls}/{ceiling} db_writes=0')
    return results,players
