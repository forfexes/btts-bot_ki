#!/usr/bin/env python3
"""NETRATTLER V36M — Bet365 football player-props collector.

Best-effort public-page/network parser. It never invents lines or odds.
It writes bet365_player_props_cache.json and, when compatible, stores rows in
Supabase player_prop_db. Failure is non-fatal by design.
"""
from __future__ import annotations
import argparse, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import requests

BET365_URL=os.getenv('BET365_FOOTBALL_URL','https://www.bet365.com/')
BET365_EVENT_URLS=[x.strip() for x in os.getenv('BET365_EVENT_URLS','').split(',') if x.strip()]
SUPABASE_URL=os.getenv('SUPABASE_URL','').rstrip('/')
SUPABASE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY','')
OUT=Path(os.getenv('BET365_PROPS_CACHE','bet365_player_props_cache.json'))
TIMEOUT=int(os.getenv('BET365_PROPS_TIMEOUT','120'))
MAX_EVENTS=int(os.getenv('BET365_PROPS_MAX_EVENTS','12'))

MARKETS={
 'shots_on_target':('shots on target','shot on target','sot'),
 'shots':('player shots','shots total','total shots','shots'),
 'tackles':('player tackles','tackles'),
 'passes':('player passes','passes'),
 'fouls_committed':('fouls committed','player fouls','commit fouls'),
 'fouled':('to be fouled','fouls won','player fouled'),
 'assists':('player assists','assists'),
 'goal_or_assist':('goal or assist','score or assist'),
 'goals':('anytime goalscorer','to score','player goals','2+ goals','3+ goals'),
 'cards':('player to be booked','to be carded','player card','booked'),
 'sent_off':('player sent off','red card'),
 'goalkeeper_saves':('goalkeeper saves','keeper saves','saves'),
 'headed_sot':('headed shots on target','header on target'),
 'outside_box_sot':('shots on target from outside','outside the box on target'),
}

BOOK='bet365'

def txt(v:Any)->str:
    return re.sub(r'\s+',' ',str(v or '')).strip()

def norm_market(name:str)->Optional[str]:
    n=txt(name).lower()
    for key, aliases in MARKETS.items():
        if any(a in n for a in aliases): return key
    return None

def decimal_odds(v:Any)->Optional[float]:
    if isinstance(v,(int,float)) and 1.001 <= float(v) <= 1001: return round(float(v),3)
    s=txt(v).replace(',','.')
    m=re.search(r'(?<!\d)(\d{1,4}(?:\.\d{1,3})?)(?!\d)',s)
    if not m: return None
    x=float(m.group(1))
    return round(x,3) if 1.001 <= x <= 1001 else None

def line_value(v:Any)->Optional[float]:
    s=txt(v).replace(',','.')
    m=re.search(r'(?<!\d)(\d+(?:\.5|\.0)?)(?:\+)?(?!\d)',s)
    return float(m.group(1)) if m else None

def player_from_selection(selection:str)->str:
    s=txt(selection)
    s=re.sub(r'\b(over|under)\b.*$','',s,flags=re.I)
    s=re.sub(r'\b\d+(?:\.5)?\+?\b.*$','',s).strip(' -–:')
    return s

def sub_on_play_on(*parts:Any)->bool:
    s=' '.join(txt(x) for x in parts).lower()
    return any(x in s for x in ('sub on play on','sub-on-play-on','sopo'))

def row_from(market_name:str, selection_name:str, odd:Any, context:Dict[str,Any]) -> Optional[Dict[str,Any]]:
    mk=norm_market(market_name)
    dec=decimal_odds(odd)
    player=player_from_selection(selection_name)
    if not mk or not dec or not player: return None
    sel=txt(selection_name)
    side='over' if re.search(r'\bover\b|\d+(?:\.5)?\+',sel,re.I) else ('under' if re.search(r'\bunder\b',sel,re.I) else 'yes')
    line=line_value(sel)
    return {
      'source':'bet365_public','sport':'football','bookmaker':BOOK,
      'event_id':txt(context.get('event_id') or context.get('eventId') or context.get('id')),
      'event_name':txt(context.get('event_name') or context.get('eventName') or context.get('name')),
      'home_team':txt(context.get('home_team') or context.get('homeTeam')),
      'away_team':txt(context.get('away_team') or context.get('awayTeam')),
      'start_time':txt(context.get('start_time') or context.get('startTime')),
      'market_key':mk,'market_name':txt(market_name),'player_name':player,
      'selection':side,'selection_name':sel,'line':line,'odds':dec,
      'sub_on_play_on':sub_on_play_on(market_name,selection_name,context.get('text')),
      'observed_at':datetime.now(timezone.utc).isoformat(),
      'raw':{'market':txt(market_name),'selection':sel,'odds':odd},
    }

def walk(node:Any, context:Optional[Dict[str,Any]]=None)->Iterable[Dict[str,Any]]:
    context=dict(context or {})
    if isinstance(node,dict):
        for k in ('event_id','eventId','id','event_name','eventName','name','home_team','homeTeam','away_team','awayTeam','start_time','startTime'):
            if k in node and node[k] not in (None,''): context[k]=node[k]
        market=node.get('marketName') or node.get('market_name') or node.get('market') or node.get('groupName') or node.get('title')
        sels=node.get('selections') or node.get('outcomes') or node.get('participants')
        if market and isinstance(sels,list):
            for s in sels:
                if not isinstance(s,dict): continue
                name=s.get('name') or s.get('selectionName') or s.get('label') or s.get('participant')
                odd=s.get('odds') or s.get('price') or s.get('decimalOdds') or s.get('displayOdds')
                r=row_from(str(market),str(name or ''),odd,{**context,'text':json.dumps(node,ensure_ascii=False)[:5000]})
                if r: yield r
        for v in node.values(): yield from walk(v,context)
    elif isinstance(node,list):
        for v in node: yield from walk(v,context)

def dedupe(rows:List[Dict[str,Any]])->List[Dict[str,Any]]:
    out={}
    for r in rows:
        key=(r['event_id'],r['market_key'],r['player_name'].lower(),r['selection'],r['line'],r['odds'])
        out[key]=r
    return list(out.values())

def collect() -> List[Dict[str,Any]]:
    from playwright.sync_api import sync_playwright
    rows=[]; payloads=[]; urls=[]
    def on_response(resp):
        u=resp.url.lower()
        if any(x in u for x in ('api','event','sport','market','coupon')):
            try:
                ct=(resp.headers.get('content-type') or '').lower()
                if 'json' in ct:
                    data=resp.json()
                    payloads.append(data)
            except Exception: pass
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(locale='en-GB',viewport={'width':1440,'height':1200})
        page.on('response',on_response)
        targets=list(BET365_EVENT_URLS or [BET365_URL])
        visited=set()
        deadline=time.time()+TIMEOUT
        while targets and len(visited)<MAX_EVENTS and time.time()<=deadline:
            url=targets.pop(0)
            if not url or url in visited:
                continue
            visited.add(url)
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=45000)
                page.wait_for_timeout(5000)
                # DOM fallback is discovery-only; lines and odds still come from observed JSON.
                discovered=page.eval_on_selector_all(
                    'a',
                    """els=>els.map(e=>e.href).filter(h=>
                      h && /bet365/i.test(h) &&
                      new RegExp('(football|soccer|event|fixture|match|AC/B1)','i').test(h)
                    )""",
                )
                urls.extend(discovered)
                for link in discovered:
                    if link not in visited and link not in targets:
                        targets.append(link)
                for script in page.locator('script').all():
                    try:
                        t=script.text_content(timeout=1000) or ''
                        if len(t)>20 and t.lstrip().startswith(('{','[')):
                            payloads.append(json.loads(t))
                    except Exception:
                        pass
            except Exception as e:
                print('BET365 PAGE WARN',str(e)[:180])
        browser.close()
    for data in payloads: rows.extend(walk(data))
    rows=dedupe(rows)
    print(f'BET365 payloads={len(payloads)} links={len(set(urls))} props={len(rows)}')
    return rows

def _key_groups(rows:List[Dict[str,Any]])->List[List[Dict[str,Any]]]:
    """PostgREST requires identical object keys inside each bulk request."""
    groups:Dict[Tuple[str,...],List[Dict[str,Any]]]={}
    for row in rows:
        groups.setdefault(tuple(sorted(row.keys())),[]).append(row)
    return list(groups.values())

def save_supabase(rows:List[Dict[str,Any]])->int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY: return 0
    endpoint=f'{SUPABASE_URL}/rest/v1/player_prop_db'
    headers={
      'apikey':SUPABASE_KEY,
      'Authorization':f'Bearer {SUPABASE_KEY}',
      'Content-Type':'application/json',
      'Prefer':'return=minimal',
    }
    # Raw JSON cache stays authoritative when the project table has an older schema.
    common=(
      'source','sport','event_id','event_name','home_team','away_team',
      'start_time','bookmaker','market_key','market_name','player_name',
      'selection','selection_name','line','odds','sub_on_play_on',
      'observed_at','raw',
    )
    payload=[{k:r[k] for k in common if k in r and r[k] not in ('',None)} for r in rows]
    saved=0
    for same_keys in _key_groups(payload):
        for i in range(0,len(same_keys),200):
            chunk=same_keys[i:i+200]
            try:
                resp=requests.post(endpoint,headers=headers,json=chunk,timeout=45)
                if resp.ok:
                    saved+=len(chunk)
                else:
                    print('SUPABASE player_prop_db WARN',resp.status_code,resp.text[:240])
            except Exception as e:
                print('SUPABASE WARN',str(e)[:180])
    return saved

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default='today'); args=ap.parse_args()
    rows=collect()
    OUT.write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'date':args.date,'count':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    saved=save_supabase(rows)
    print(f'BET365 PLAYER PROPS cache={OUT} rows={len(rows)} saved={saved}')
    return 0
if __name__=='__main__': raise SystemExit(main())
