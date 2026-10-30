"""Structured public-page context. Fixtures, history and predictions stay distinct.

No JavaScript execution, synthesized odds, inferred scores or missing-as-zero stats.
These rows are context/discovery evidence, not automatic settlement authority.
"""
from datetime import date, datetime, timezone
import json
import html as html_module
import re
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup

SITES={'www.flashscore.com':'flashscore','flashscore.com':'flashscore',
       'www.todaymatchprediction.com':'todaymatchprediction','todaymatchprediction.com':'todaymatchprediction',
       'www.besoccer.com':'besoccer','besoccer.com':'besoccer'}


def _day(value):
    try:return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError,TypeError):return None


def _team(value):
    if isinstance(value,dict):return str(value.get('name') or '').strip()
    return str(value or '').strip() if isinstance(value,str) else ''


def _schema_events(soup,source,url):
    out=[]
    def walk(x):
        if isinstance(x,list):
            for v in x:walk(v)
        elif isinstance(x,dict):
            kind=x.get('@type')
            if kind=='SportsEvent' or (isinstance(kind,list) and 'SportsEvent' in kind):
                home,away=_team(x.get('homeTeam')),_team(x.get('awayTeam'))
                # A competitor list alone does not define home/away order.
                if not(home and away) and source=='todaymatchprediction':
                    names=re.split(r'\s+vs\.?\s+',str(x.get('name') or ''),flags=re.I)
                    competitors={_team(t) for t in x.get('competitor',[]) if isinstance(t,dict)}
                    if len(names)==2 and set(names)==competitors:home,away=names
                day=_day(x.get('startDate'))
                event_url=urljoin(url,str(x.get('url') or url))
                if source=='todaymatchprediction' and (urlparse(event_url).hostname not in {'www.todaymatchprediction.com','todaymatchprediction.com'} or not urlparse(event_url).path.startswith('/gameprediction/')):
                    continue_event=True
                else:
                    continue_event=False
                location=x.get('location') or {}
                league=location.get('address') if isinstance(location,dict) else ''
                if home and away and home!=away and day and not continue_event:
                    out.append({'source':source,'home':home,'away':away,'date':day,
                                'league':league if isinstance(league,str) else '',
                                'source_url':event_url,
                                'starts':str(x.get('startDate') or ''),'role':'fixture_context',
                                'bookmaker_odds_verified':False})
            for k in ('@graph','itemListElement','item'):
                if k in x:walk(x[k])
    for tag in soup.find_all('script',type='application/ld+json'):
        try:walk(json.loads(tag.string or tag.get_text()))
        except (ValueError,TypeError):continue
    return out


def _flashscore(soup,url):
    for tag in soup.find_all('script'):
        text=tag.string or tag.get_text() or ''
        m=re.search(r'\bwindow\.environment\s*=\s*',text)
        if not m:continue
        try:
            env=json.JSONDecoder().raw_decode(text[m.end():].lstrip())[0]
            if not isinstance(env,dict) or str(env.get('sport_id'))!='1':continue
            teams=env.get('participantsData') or {};h=teams.get('home') or [];a=teams.get('away') or []
            if len(h)!=1 or len(a)!=1:continue
            home,away=_team(h[0]),_team(a[0]);event=str(env.get('event_id_c') or '')
            if not home or not away or home==away or not event:continue
            stamp=env.get('eventStageStartTime')
            if isinstance(stamp,bool) or not isinstance(stamp,(int,float)):continue
            starts=datetime.fromtimestamp(stamp,timezone.utc)
            if not 2000<=starts.year<=2100:continue
            stage=str(env.get('eventStageId') or '')
            header=env.get('header') or {}
            league=header.get('tournament_name') or header.get('tournament') or ''
            if isinstance(league,dict):league=league.get('tournament') or league.get('name') or ''
            status=html_module.unescape(str((env.get('eventStageTranslations') or {}).get(stage) or '')).strip() or 'unknown'
            return [{'source':'flashscore','match_id':event,'home':home,'away':away,'date':starts.date().isoformat(),
                     'starts':starts.isoformat(),'league':str(league),
                     'status':status,
                     'source_url':url,'role':'fixture_context','bookmaker_odds_verified':False}]
        except (ValueError,TypeError,IndexError,OverflowError,OSError):continue
    return []


def _today_history(soup,cutoff):
    out=[]
    for row in soup.select('.game-result .lisleaguegames'):
        d=row.select_one('.team-schedule__date');names=row.select_one('.team-meta__nameresults');score=row.select_one('.colorscore')
        if not(d and names and score):continue
        try:day=datetime.strptime(d.get_text(strip=True),'%d.%m.%Y').date()
        except ValueError:continue
        if day>=cutoff:continue
        pair=re.split(r'\s+vs\.?\s+',names.get_text(' ',strip=True),flags=re.I)
        goals=re.fullmatch(r'(\d{1,2})\s*:\s*(\d{1,2})',score.get_text(strip=True))
        if len(pair)!=2 or not all(pair) or pair[0]==pair[1] or not goals:continue
        hg,ag=map(int,goals.groups())
        if max(hg,ag)>30:continue
        league=row.select_one('.team-schedule__compet')
        out.append({'date':str(day),'home':pair[0],'away':pair[1],'home_goals':hg,'away_goals':ag,
                    'league':league.get_text(' ',strip=True) if league else '',
                    'source':'todaymatchprediction','role':'historical_context'})
    return out


def parse_public_page(html,url,target_date=None):
    source=SITES.get((urlparse(url).hostname or '').lower())
    result={'source':source or 'unsupported','fixtures':[],'recent_results':[],
            'bookmaker_odds':[],'settlement_results':[]}
    if not source:return result
    soup=BeautifulSoup(html or '', 'html.parser')
    cutoff=min(date.fromisoformat(str(target_date or date.today())[:10]),date.today())
    fixtures=_flashscore(soup,url) if source=='flashscore' else _schema_events(soup,source,url)
    seen=set()
    for row in fixtures:
        key=(row['date'],row['home'],row['away'])
        if key not in seen and (target_date is None or row['date']==str(target_date)[:10]):
            result['fixtures'].append(row);seen.add(key)
    if source=='todaymatchprediction':
        seen=set()
        for row in _today_history(soup,cutoff):
            key=(row['date'],row['home'],row['away'])
            if key not in seen:result['recent_results'].append(row);seen.add(key)
    return result
