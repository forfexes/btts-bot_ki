#!/usr/bin/env python3
"""
NETRATTLER V16 ML TRAINER
=========================
Pure-Python ML/Scoring Layer ohne sklearn.
Trainiert aus netrattler_settlements und speichert ein Modell in Supabase:
  public.netrattler_ml_models / model_name='netrattler_v16_ml'

Lernt u.a.:
- Marktgruppe: BTTS, Over25, Combo, Builder, Props, Corners
- Quelle / source_table
- Quote-Bucket
- Liga, Teams, Markttext, Wochentag/Stunde, falls in tip_payload vorhanden
- ROI und Winrate je Feature
"""
import os, json, re, hashlib, unicodedata, math
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, List, Tuple
import requests

SUPABASE_URL=(os.getenv('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY') or ''
MODEL_NAME=os.getenv('NETRATTLER_ML_MODEL','netrattler_v16_ml')
LIMIT=int(os.getenv('ML_TRAIN_LIMIT','5000'))
MIN_FEATURE_BETS=int(os.getenv('ML_MIN_FEATURE_BETS','2'))
NOW=datetime.now(timezone.utc)


def log(x, level='INFO'):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {x}", flush=True)


def headers(pref='return=representation'):
    return {'apikey':SUPABASE_KEY,'Authorization':'Bearer '+SUPABASE_KEY,'Content-Type':'application/json','Prefer':pref}


def sb_get(table:str, params:Dict[str,str]) -> List[Dict[str,Any]]:
    try:
        r=requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers(), params=params, timeout=30)
        if r.status_code>=400:
            log(f"GET {table} {r.status_code}: {r.text[:180]}", 'WARN')
            return []
        return r.json() if r.text else []
    except Exception as e:
        log(f"GET {table}: {e}", 'WARN')
        return []


def sb_upsert(table:str, rows:List[Dict[str,Any]], conflict:str) -> int:
    ok=0
    for i in range(0,len(rows),100):
        part=rows[i:i+100]
        r=requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers('resolution=merge-duplicates,return=minimal'),
            params={'on_conflict':conflict},
            data=json.dumps(part, ensure_ascii=False, default=str),
            timeout=35,
        )
        if r.status_code in (200,201,204): ok+=len(part)
        else: log(f"UPSERT {table} {r.status_code}: {r.text[:220]}", 'WARN')
    return ok


def norm(s:Any) -> str:
    s=unicodedata.normalize('NFKD', str(s or '').lower().strip())
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()


def unpack(row:Dict[str,Any]) -> Dict[str,Any]:
    out={}
    for k in ('tip_payload','payload','raw','data'):
        v=row.get(k)
        if isinstance(v,dict): out.update(v)
    out.update(row)
    return out


def anyv(row:Dict[str,Any], keys:List[str], default:Any='') -> Any:
    for k in keys:
        if isinstance(row,dict) and row.get(k) not in (None,''):
            return row.get(k)
    return default


def odds_bucket(v:Any) -> str:
    try: o=float(str(v).replace(',','.'))
    except Exception: return 'odds:unknown'
    if o < 1.50: return 'odds:<1.50'
    if o < 1.80: return 'odds:1.50-1.79'
    if o < 2.10: return 'odds:1.80-2.09'
    if o < 2.60: return 'odds:2.10-2.59'
    if o < 3.50: return 'odds:2.60-3.49'
    return 'odds:3.50+'


def market_text(p:Dict[str,Any]) -> str:
    vals=[]
    for k in ['selection','pick','tip','market','type','bet_type','category']:
        v=p.get(k)
        if v not in (None,''):
            vals.append(str(v))
    return ' / '.join(dict.fromkeys(vals))[:120] or 'unknown'


def match_parts(p:Dict[str,Any]) -> Tuple[str,str,str]:
    h=str(anyv(p,['home_team','home','team_home','HomeTeam','strHomeTeam'],''))
    a=str(anyv(p,['away_team','away','team_away','AwayTeam','strAwayTeam'],''))
    m=str(anyv(p,['match','fixture','game','event','entity_name','name','title'],''))
    if (not h or not a) and re.search(r'\s+v(s)?\.?\s+',m,re.I):
        parts=re.split(r'\s+vs\.?\s+|\s+v\.?\s+',m,flags=re.I)
        if len(parts)>=2: h,a=parts[0].strip(),parts[1].strip()
    return h,a,m or (f'{h} vs {a}' if h and a else '')


def status_of(row:Dict[str,Any]) -> str:
    s=str(row.get('status') or '').lower()
    if s in ('win','won','green'): return 'win'
    if s in ('loss','lost','red'): return 'loss'
    return 'pending'


def profit_of(row:Dict[str,Any], status:str) -> float:
    try: return float(row.get('profit'))
    except Exception: pass
    if status=='win':
        try: return float(row.get('odds') or 2.0)-1.0
        except Exception: return 1.0
    if status=='loss': return -1.0
    return 0.0


def features(row:Dict[str,Any]) -> List[str]:
    p=unpack(row)
    group=str(row.get('market_group') or p.get('market_group') or p.get('market') or 'default').lower()
    source=str(row.get('source_table') or p.get('_table') or 'unknown').lower()
    h,a,m=match_parts(p)
    league=str(anyv(p,['league','competition','country','source_league','_source_league'],'unknown'))[:80]
    hour=str(anyv(p,['hour','tip_hour'],''))
    weekday=str(anyv(p,['weekday','tip_weekday'],''))
    odds=anyv(row,['odds','quote','price','total_odds'], anyv(p,['odds','quote','price','oddsYes','total_odds'],''))
    mt=market_text(p)
    fs=[
        f'group:{norm(group)}',
        f'source:{norm(source)}',
        odds_bucket(odds),
        f'league:{norm(league)}',
        f'market_text:{norm(mt)[:80]}',
    ]
    if h: fs.append(f'home:{norm(h)[:80]}')
    if a: fs.append(f'away:{norm(a)[:80]}')
    if hour!='': fs.append(f'hour:{hour}')
    if weekday!='': fs.append(f'weekday:{weekday}')
    return [x for x in fs if x and not x.endswith(':')]


def train(rows:List[Dict[str,Any]]) -> Dict[str,Any]:
    closed=[]
    for r in rows:
        st=status_of(r)
        if st in ('win','loss'):
            x=dict(r); x['status']=st; x['_profit_calc']=profit_of(r,st); closed.append(x)

    total=len(closed); wins=sum(1 for r in closed if r['status']=='win')
    losses=total-wins
    profit=sum(float(r.get('_profit_calc') or 0) for r in closed)
    prior=(wins+1)/(total+2) if total else 0.52

    buckets=defaultdict(lambda:{'bets':0,'wins':0,'losses':0,'profit':0.0})
    for r in closed:
        for f in features(r):
            b=buckets[f]; b['bets']+=1; b['wins']+= int(r['status']=='win'); b['losses']+=int(r['status']=='loss'); b['profit']+=float(r.get('_profit_calc') or 0)

    feature_stats={}
    for k,b in buckets.items():
        if b['bets'] < MIN_FEATURE_BETS: continue
        bets=b['bets']; wr=(b['wins']+prior*2)/(bets+2); roi=100*b['profit']/max(1,bets)
        conf=min(1.0, math.log(bets+1)/math.log(40))
        feature_stats[k]={
            'bets':bets,'wins':b['wins'],'losses':b['losses'],
            'profit':round(b['profit'],3),'roi':round(roi,2),'winrate':round(wr,4),
            'confidence':round(conf,4),
        }

    return {
        'model_name':MODEL_NAME,
        'version':'v16_ml_statistical_bayes',
        'trained_at':NOW.isoformat(),
        'rows_total':len(rows),
        'rows_closed':total,
        'prior':{'bets':total,'wins':wins,'losses':losses,'profit':round(profit,3),'winrate':round(prior,4),'roi':round(100*profit/max(1,total),2)},
        'feature_stats':feature_stats,
        'min_feature_bets':MIN_FEATURE_BETS,
    }


def main():
    log('🤖 NETRATTLER V16 ML Trainer startet')
    rows=sb_get('netrattler_settlements',{'select':'*','status':'in.(win,loss)','order':'tip_date.desc','limit':str(LIMIT)})
    log(f'Settlements geladen: {len(rows)}')
    model=train(rows)
    ok=sb_upsert('netrattler_ml_models',[{'model_name':MODEL_NAME,'model_json':model,'rows_trained':model['rows_closed'],'trained_at':NOW.isoformat(),'note':'NETRATTLER V16 pure-python ML from settlements'}],'model_name')
    log(f'Model gespeichert: {ok}')
    log(f"Closed={model['rows_closed']} Winrate={model['prior']['winrate']} ROI={model['prior']['roi']} Features={len(model['feature_stats'])}")
    log('✅ NETRATTLER V16 ML Trainer fertig')

if __name__=='__main__':
    main()
