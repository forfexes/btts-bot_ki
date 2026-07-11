#!/usr/bin/env python3
"""
NETRATTLER V16 ML PREDICTOR
===========================
Kann von btts_bot.py importiert werden.
Benutzt Modell aus Supabase netrattler_ml_models.
Keine externen ML-Libs nötig.
"""
import os, re, json, math, hashlib, unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

SUPABASE_URL=(os.getenv('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY') or ''
MODEL_NAME=os.getenv('NETRATTLER_ML_MODEL','netrattler_v16_ml')
_MODEL_CACHE=None
_MODEL_TS=0


def norm(s:Any)->str:
    s=unicodedata.normalize('NFKD',str(s or '').lower().strip())
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()


def anyv(row:Dict[str,Any], keys:List[str], default:Any='')->Any:
    for k in keys:
        if isinstance(row,dict) and row.get(k) not in (None,''):
            return row.get(k)
    return default


def unpack(row:Dict[str,Any])->Dict[str,Any]:
    out={}
    for k in ('tip_payload','payload','raw','data'):
        v=row.get(k) if isinstance(row,dict) else None
        if isinstance(v,dict): out.update(v)
    if isinstance(row,dict): out.update(row)
    return out


def odds_bucket(v:Any)->str:
    try: o=float(str(v).replace(',','.'))
    except Exception: return 'odds:unknown'
    if o < 1.50: return 'odds:<1.50'
    if o < 1.80: return 'odds:1.50-1.79'
    if o < 2.10: return 'odds:1.80-2.09'
    if o < 2.60: return 'odds:2.10-2.59'
    if o < 3.50: return 'odds:2.60-3.49'
    return 'odds:3.50+'


def market_text(p:Dict[str,Any])->str:
    vals=[]
    for k in ['selection','pick','tip','market','type','bet_type','category']:
        v=p.get(k)
        if v not in (None,''):
            vals.append(str(v))
    return ' / '.join(dict.fromkeys(vals))[:120] or 'unknown'


def match_parts(p:Dict[str,Any])->Tuple[str,str,str]:
    h=str(anyv(p,['home_team','home','team_home','HomeTeam','strHomeTeam'],''))
    a=str(anyv(p,['away_team','away','team_away','AwayTeam','strAwayTeam'],''))
    m=str(anyv(p,['match','fixture','game','event','entity_name','name','title'],''))
    if (not h or not a) and re.search(r'\s+v(s)?\.?\s+',m,re.I):
        parts=re.split(r'\s+vs\.?\s+|\s+v\.?\s+',m,flags=re.I)
        if len(parts)>=2: h,a=parts[0].strip(),parts[1].strip()
    return h,a,m or (f'{h} vs {a}' if h and a else '')


def extract_features(tip:Dict[str,Any])->List[str]:
    p=unpack(tip)
    group=str(anyv(p,['market_group','market','type','category'],'default')).lower()
    source=str(anyv(p,['source_table','_table','source'],'unknown')).lower()
    h,a,m=match_parts(p)
    league=str(anyv(p,['league','competition','country','source_league','_source_league'],'unknown'))[:80]
    odds=anyv(p,['odds','quote','price','oddsYes','total_odds','decimal_odds'],'')
    mt=market_text(p)
    fs=[f'group:{norm(group)}',f'source:{norm(source)}',odds_bucket(odds),f'league:{norm(league)}',f'market_text:{norm(mt)[:80]}']
    if h: fs.append(f'home:{norm(h)[:80]}')
    if a: fs.append(f'away:{norm(a)[:80]}')
    if p.get('hour') not in (None,''): fs.append(f"hour:{p.get('hour')}")
    if p.get('weekday') not in (None,''): fs.append(f"weekday:{p.get('weekday')}")
    return [x for x in fs if x and not x.endswith(':')]


def headers():
    return {'apikey':SUPABASE_KEY,'Authorization':'Bearer '+SUPABASE_KEY,'Content-Type':'application/json'}


def load_model(force:bool=False)->Optional[Dict[str,Any]]:
    global _MODEL_CACHE,_MODEL_TS
    now=datetime.now(timezone.utc).timestamp()
    if _MODEL_CACHE and not force and now-_MODEL_TS<300:
        return _MODEL_CACHE
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r=requests.get(f'{SUPABASE_URL}/rest/v1/netrattler_ml_models',headers=headers(),params={'model_name':f'eq.{MODEL_NAME}','select':'*','limit':'1'},timeout=15)
        if not r.ok or not r.text:
            return None
        rows=r.json()
        if not rows: return None
        model=rows[0].get('model_json') or {}
        _MODEL_CACHE=model; _MODEL_TS=now
        return model
    except Exception:
        return None


def implied_prob(odds:Any)->float:
    try:
        o=float(str(odds).replace(',','.'))
        if o>1: return 1/o
    except Exception: pass
    return 0.0


def predict_tip(tip:Dict[str,Any])->Dict[str,Any]:
    model=load_model(False)
    if not model:
        return {'ml_score':0,'edge':0,'recommendation':'NO_MODEL','reason':'ML sammelt Daten','features':[]}
    prior=float((model.get('prior') or {}).get('winrate') or 0.52)
    stats=model.get('feature_stats') or {}
    feats=extract_features(tip)
    weighted=prior*1.0; weight=1.0; hits=[]
    for f in feats:
        s=stats.get(f)
        if not s: continue
        bets=float(s.get('bets') or 0); wr=float(s.get('winrate') or prior); conf=float(s.get('confidence') or 0)
        w=max(0.1, conf) * min(3.0, math.log(bets+1))
        weighted += wr*w; weight += w
        hits.append({'feature':f,'bets':int(bets),'winrate':round(wr,3),'roi':s.get('roi',0)})
    prob=weighted/max(1e-9,weight)
    p=unpack(tip)
    odds=anyv(p,['odds','quote','price','oddsYes','total_odds','decimal_odds'],'')
    edge=(prob-implied_prob(odds))*100 if odds not in (None,'') else 0.0
    score=round(prob*100,1)
    if score>=63 and edge>=2: rec='STRONG'
    elif score>=57: rec='OK'
    elif score>=52: rec='LEAN'
    else: rec='SKIP'
    return {'ml_score':score,'edge':round(edge,1),'recommendation':rec,'reason':f'{len(hits)} gelernte Signale','features':hits[:8]}


def footer_for_tip(tip:Dict[str,Any])->str:
    p=predict_tip(tip)
    if p['recommendation']=='NO_MODEL':
        return '🤖 ML: Daten werden gesammelt'
    icon={'STRONG':'🔥','OK':'✅','LEAN':'⚠️','SKIP':'🚫'}.get(p['recommendation'],'🤖')
    return f"🤖 ML_SCORE: <b>{p['ml_score']}</b> · Edge {p['edge']}% · {icon} {p['recommendation']}"

if __name__=='__main__':
    print(json.dumps(predict_tip({'market':'btts','odds':1.85,'match':'Team A vs Team B'}),ensure_ascii=False,indent=2))
