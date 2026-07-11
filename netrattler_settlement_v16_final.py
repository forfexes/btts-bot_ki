#!/usr/bin/env python3
"""
NETRATTLER Settlement V16 ML GROUP FINAL
Dateiname bleibt v16: netrattler_settlement_v16_final.py
"""
import os, re, json, hashlib, unicodedata
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
import requests

SUPABASE_URL=(os.getenv('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY') or ''
TG_TOKEN=os.getenv('TELEGRAM_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or ''
TG_DEFAULT=os.getenv('TELEGRAM_CHAT_ID') or ''
DAYS=int(os.getenv('SETTLEMENT_DAYS','14'))
LIMIT=int(os.getenv('SETTLEMENT_LIMIT','1500'))
SEND_EMPTY=os.getenv('SEND_EMPTY_GROUP_REPORTS','true').lower() not in ('0','false','no')
UPDATE_TIPS=os.getenv('UPDATE_SOURCE_TIPS','true').lower() not in ('0','false','no')
NOW=datetime.now(timezone.utc)
TODAY=NOW.date()
TODAY_S=TODAY.isoformat()
MONTH_S=TODAY.replace(day=1).isoformat()
YEAR_S=TODAY.replace(month=1,day=1).isoformat()

GROUPS={
 'btts':os.getenv('TELEGRAM_GROUP_BTTS') or TG_DEFAULT,
 'over25':os.getenv('TELEGRAM_GROUP_OVER25') or TG_DEFAULT,
 'combo':os.getenv('TELEGRAM_GROUP_COMBO') or TG_DEFAULT,
 'btts_ht':os.getenv('TELEGRAM_GROUP_BTTS_HT') or TG_DEFAULT,
 'over15_ht':os.getenv('TELEGRAM_GROUP_STATS') or TG_DEFAULT,
 'builder':os.getenv('TELEGRAM_GROUP_BUILDER') or os.getenv('TELEGRAM_GROUP_PROPS') or TG_DEFAULT,
 'props':os.getenv('TELEGRAM_GROUP_PROPS') or TG_DEFAULT,
 'corners':os.getenv('TELEGRAM_GROUP_CORNERS') or os.getenv('TELEGRAM_GROUP_STATS') or TG_DEFAULT,
 'stats':os.getenv('TELEGRAM_GROUP_STATS') or TG_DEFAULT,
 'default':TG_DEFAULT,
}
ORDER=['btts','over25','combo','btts_ht','over15_ht','builder','props','corners']
TIP_TABLES=['tips','ml_tips','prop_picks','player_prop_db']
RESULT_TABLES={
 'international_results':['date','match_date','Date','game_date','event_date'],
 'football_historical_matches':['match_date','Date','game_date','utc_date','event_date'],
 'netrattler_data_lake_raw':['match_date','Date','game_date','event_date','created_at'],
}

def log(x,l='INFO'):
 print(f"[{datetime.now().strftime('%H:%M:%S')}] [{l}] {x}",flush=True)

def hsh(*x):
 return hashlib.sha1('||'.join(str(v or '') for v in x).encode()).hexdigest()

def norm(s):
 s=str(s or '').lower().strip()
 s=unicodedata.normalize('NFKD',s)
 s=''.join(c for c in s if not unicodedata.combining(c))
 s=s.replace('&',' and ')
 s=re.sub(r'\b(fc|sc|cf|afc|fk|ac|club|de|the|team|women|wfc)\b',' ',s)
 s=re.sub(r'[^a-z0-9]+',' ',s)
 return re.sub(r'\s+',' ',s).strip()

def sim(a,b):
 a,b=norm(a),norm(b)
 if not a or not b: return 0
 if a==b: return 1
 if a in b or b in a: return .88
 sa,sb=set(a.split()),set(b.split())
 return len(sa&sb)/max(1,len(sa|sb))

def anyv(r,ks,d=''):
 if not isinstance(r,dict): return d
 for k in ks:
  if k in r and r[k] not in (None,''):
   return r[k]
 return d

def unpack(r):
 m={}
 if isinstance(r,dict):
  for k in ('payload','raw','data'):
   if isinstance(r.get(k),dict): m.update(r[k])
  m.update(r)
 return m

def pdt(x):
 if not x: return None
 s=str(x).strip().replace('Z','+00:00')
 try:
  d=datetime.fromisoformat(s)
  return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
 except Exception:
  pass
 for f in ('%Y-%m-%d','%d/%m/%Y','%d.%m.%Y','%Y/%m/%d'):
  try: return datetime.strptime(s[:10],f).replace(tzinfo=timezone.utc)
  except Exception: pass
 return None

def row_date(r):
 m=unpack(r)
 for k in ('match_date','date','Date','game_date','event_date','ko','kickoff','event_time','commence_time','created_at'):
  d=pdt(m.get(k))
  if d: return d.date().isoformat()
 return TODAY_S

def hdr(pref='return=representation'):
 return {'apikey':SUPABASE_KEY,'Authorization':'Bearer '+SUPABASE_KEY,'Content-Type':'application/json','Prefer':pref}

def get(table,params,quiet=True):
 if not SUPABASE_URL or not SUPABASE_KEY: return []
 try:
  r=requests.get(f'{SUPABASE_URL}/rest/v1/{table}',headers=hdr(),params=params,timeout=30)
  if r.status_code>=400:
   if not quiet: log(f'GET {table} {r.status_code}: {r.text[:160]}','WARN')
   return []
  return r.json() if r.text else []
 except Exception as e:
  if not quiet: log(f'GET {table}: {e}','WARN')
  return []

def upsert(table,rows,conflict):
 ok=0
 for i in range(0,len(rows),200):
  part=rows[i:i+200]
  try:
   r=requests.post(f'{SUPABASE_URL}/rest/v1/{table}',headers=hdr('resolution=merge-duplicates,return=minimal'),params={'on_conflict':conflict},data=json.dumps(part,ensure_ascii=False,default=str),timeout=35)
   if r.status_code in (200,201,204): ok+=len(part)
   else: log(f'UPSERT {table} {r.status_code}: {r.text[:200]}','WARN')
  except Exception as e: log(f'UPSERT {table}: {e}','WARN')
 return ok

def patch(table,col,val,payload):
 if not val: return False
 try:
  r=requests.patch(f'{SUPABASE_URL}/rest/v1/{table}',headers=hdr('return=minimal'),params={col:f'eq.{val}'},data=json.dumps(payload,ensure_ascii=False,default=str),timeout=20)
  return r.status_code in (200,204)
 except Exception: return False

def tg(chat,text):
 if not TG_TOKEN or not chat: return False
 try:
  r=requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',json={'chat_id':chat,'text':text[:3900],'parse_mode':'HTML','disable_web_page_preview':True},timeout=20)
  if not r.ok: log(f'TG {r.status_code}: {r.text[:160]}','WARN')
  return r.ok
 except Exception as e:
  log(f'TG: {e}','WARN'); return False

def market_text(r):
 m=unpack(r); vals=[]
 for k in ('selection','pick','bet','tip','market','type','bet_type','category'):
  v=m.get(k)
  if v not in (None,''):
   t=str(v).strip()
   if t and t.lower() not in ('none','null','nan'): vals.append(t)
 return ' / '.join(dict.fromkeys(vals)).strip() or 'Market nicht erkannt'

def group_of(r):
 m=unpack(r)
 low=' '.join(str(anyv(m,[k],'')) for k in ('market','type','bet_type','category','group','channel','selection','pick','message','text','tip_text','title')).lower()
 if any(x in low for x in ('builder','god','aystar','nate')): return 'builder'
 if any(x in low for x in ('combo','multi','parlay','acca','same game')): return 'combo'
 if 'btts_ht' in low or 'btts ht' in low or 'both teams to score ht' in low: return 'btts_ht'
 if 'over15_ht' in low or 'over 1.5 ht' in low or 'over 1.5 first half' in low: return 'over15_ht'
 if any(x in low for x in ('corner','corners','ecken')): return 'corners'
 if any(x in low for x in ('player','booked','to be carded','shot','sot','foul','tackle','card')): return 'props'
 if ('over' in low and '2.5' in low) or 'over25' in low: return 'over25'
 if 'btts' in low or 'both teams' in low: return 'btts'
 return 'default'

def match_parts(r):
 m=unpack(r)
 h=str(anyv(m,['home_team','home','team_home','HomeTeam','strHomeTeam','homeTeam','home_name','homeTeamName'],''))
 a=str(anyv(m,['away_team','away','team_away','AwayTeam','strAwayTeam','awayTeam','away_name','awayTeamName'],''))
 if isinstance(m.get('homeTeam'),dict): h=h or str(anyv(m['homeTeam'],['name','shortName','displayName'],''))
 if isinstance(m.get('awayTeam'),dict): a=a or str(anyv(m['awayTeam'],['name','shortName','displayName'],''))
 mt=str(anyv(m,['match','fixture','game','event','entity_name','name','title'],''))
 if (not h or not a) and re.search(r'\s+v(s)?\.?\s+',mt,re.I):
  p=re.split(r'\s+vs\.?\s+|\s+v\.?\s+',mt,flags=re.I)
  if len(p)>=2: h,a=p[0].strip(),p[1].strip()
 if not mt and h and a: mt=f'{h} vs {a}'
 return h,a,mt

def tip_id(r):
 m=unpack(r)
 for k in ('id','tip_id','pick_id','uuid'):
  if m.get(k) not in (None,''): return str(m[k])
 h,a,mt=match_parts(r)
 return hsh(mt,h,a,market_text(r),row_date(r))

def source_key(r):
 m=unpack(r)
 for k in ('id','tip_id','pick_id','uuid'):
  if m.get(k) not in (None,''): return k,m[k]
 return '', ''

def include_tip(r):
 st=str(anyv(unpack(r),['status','result','settlement_status'],'pending')).lower().strip()
 if st in ('win','won','green','loss','lost','red','void','push','cancelled','canceled','settled'):
  return False
 if os.getenv('STRICT_SETTLEMENT_DAYS','false').lower() in ('1','true','yes'):
  return row_date(r) >= (TODAY-timedelta(days=DAYS)).isoformat()
 return True

def load_tips():
 out=[]
 for t in TIP_TABLES:
  rows=get(t,{'select':'*','limit':str(LIMIT)},True)
  if rows: log(f'Tip-Tabelle {t}: {len(rows)} Rows geladen')
  for r in rows:
   if include_tip(r): r['_table']=t; out.append(r)
 seen=set(); clean=[]
 for r in out:
  k=tip_id(r)
  if k not in seen: seen.add(k); clean.append(r)
 clean=clean[:LIMIT]
 log(f'Offene Tipps total: {len(clean)}')
 log(f'Offene Tipps nach Gruppen: {dict(Counter(group_of(x) for x in clean))}')
 return clean

def score_row(r):
 m=unpack(r); h,a,_=match_parts(m)
 hs=anyv(m,['home_score','home_goals','FTHG','intHomeScore','score_home','homeScore','home_goals_ft','homeGoals'],None)
 aw=anyv(m,['away_score','away_goals','FTAG','intAwayScore','score_away','awayScore','away_goals_ft','awayGoals'],None)
 for k in ('score','result','ft_score','full_time_score'):
  if hs in (None,'') and isinstance(m.get(k),str):
   nums=re.findall(r'\d+',m[k])
   if len(nums)>=2: hs,aw=nums[0],nums[1]; break
 try: hs=int(float(hs))
 except Exception: hs=None
 try: aw=int(float(aw))
 except Exception: aw=None
 return h,a,hs,aw

def public_results(day):
 out=[]
 try:
  js=requests.get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php',params={'d':day,'s':'Soccer'},timeout=20).json()
  for e in js.get('events') or []:
   out.append({'home_team':e.get('strHomeTeam'),'away_team':e.get('strAwayTeam'),'home_score':e.get('intHomeScore'),'away_score':e.get('intAwayScore'),'match_date':day,'raw':e,'_result_table':'TheSportsDB'})
 except Exception: pass
 return out

def load_results(dates):
 out=[]
 for day in dates:
  for table,cols in RESULT_TABLES.items():
   for col in cols:
    rows=get(table,{'select':'*',col:f'eq.{day}','limit':'3000'},True)
    if rows:
     for r in rows: r['_result_table']=table
     out+=rows; log(f'Results {table} {day} via {col}: {len(rows)}'); break
  pr=public_results(day)
  if pr: out+=pr; log(f'Results TheSportsDB {day}: {len(pr)}')
 seen=set(); clean=[]
 for r in out:
  h,a,hs,aw=score_row(r)
  if hs is None or aw is None: continue
  key=(norm(h),norm(a),hs,aw,str(anyv(unpack(r),['date','match_date','Date','game_date'],''))[:10])
  if key not in seen: seen.add(key); clean.append(r)
 log(f'Result candidates mit Score: {len(clean)}')
 return clean

def find_result(tip,results):
 th,ta,tm=match_parts(tip); td=row_date(tip); best=None; bs=0
 for r in results:
  rh,ra,hs,aw=score_row(r)
  if hs is None or aw is None: continue
  s=max((sim(th,rh)+sim(ta,ra))/2 if th and ta else sim(tm,f'{rh} vs {ra}'),(sim(th,ra)+sim(ta,rh))/2 if th and ta else 0)
  rd=str(anyv(unpack(r),['date','match_date','Date','game_date'],td))[:10]
  if rd==td: s+=.15
  if s>bs: bs=s; best={'home':rh,'away':ra,'home_score':hs,'away_score':aw,'match_score':round(s,3),'raw':r}
 return best if best and bs>=.66 else None

def odds_of(r):
 try: return float(anyv(unpack(r),['odds','quote','price','total_odds','decimal_odds'],None))
 except Exception: return None

def settle_score_market(tip,res):
 hs,aw=int(res['home_score']),int(res['away_score']); total=hs+aw
 low=(market_text(tip)+' '+' '.join(str(anyv(unpack(tip),[k],'')) for k in ('message','text','tip_text'))).lower()
 if 'btts' in low or 'both teams' in low:
  return ('win' if hs>0 and aw>0 else 'loss',f'{hs}:{aw}')
 if 'over' in low:
  m=re.search(r'over\s*([0-9]+(?:\.[0-9]+)?)',low); line=float(m.group(1)) if m else 2.5
  return ('win' if total>line else 'loss',f'{hs}:{aw} Tore={total} Over {line}')
 if 'under' in low:
  m=re.search(r'under\s*([0-9]+(?:\.[0-9]+)?)',low); line=float(m.group(1)) if m else 2.5
  return ('win' if total<line else 'loss',f'{hs}:{aw} Tore={total} Under {line}')
 return 'pending',f'{hs}:{aw} Markt nicht automatisch erkannt'

def legs_of(tip):
 m=unpack(tip)
 for k in ('legs','builder_legs','combo_legs','selections'):
  v=m.get(k)
  if isinstance(v,list): return [x if isinstance(x,dict) else {'selection':str(x)} for x in v]
  if isinstance(v,str) and v.strip().startswith('['):
   try:
    x=json.loads(v)
    if isinstance(x,list): return [y if isinstance(y,dict) else {'selection':str(y)} for y in x]
   except Exception: pass
 text=str(anyv(m,['message','text','tip_text','selection','pick'],'')); out=[]
 for line in text.splitlines():
  if any(x in line.lower() for x in (' vs ',' v ','over','under','btts','both teams','booked','shot','sot','foul','corner','tackle')):
   out.append({'selection':line.strip(),'match':line.strip()})
 return out

def settle_tip(tip,results):
 g=group_of(tip); tid=tip_id(tip); payload=[]
 if g in ('combo','builder'):
  legs=legs_of(tip) or [tip]; w=l=p=0
  for le in legs:
   fake=dict(tip); fake.update(le if isinstance(le,dict) else {'selection':str(le)})
   r=find_result(fake,results)
   if not r:
    p+=1; payload.append({'leg':le,'status':'pending','reason':'kein Result gefunden'}); continue
   st,why=settle_score_market(fake,r)
   leglow=market_text(fake).lower()
   if any(x in leglow for x in ('booked','card','shot','sot','foul','tackle','corner')):
    st,why='pending','Player/Corner Stats fehlen'
   w+=st=='win'; l+=st=='loss'; p+=st=='pending'; payload.append({'leg':le,'status':st,'reason':why})
  status='loss' if l else 'pending' if p else 'win'
  reason=f'{w}/{len(legs)} Legs gewonnen · {l} verloren · {p} offen'
 else:
  r=find_result(tip,results)
  if not r: status,reason='pending','kein Result gefunden'
  elif g in ('props','corners'): status,reason='pending','Player/Corner Stats fehlen'
  else: status,reason=settle_score_market(tip,r)
 odds=odds_of(tip)
 profit=(odds-1) if status=='win' and odds else (1 if status=='win' else -1 if status=='loss' else 0)
 return {'settlement_id':hsh(tid,g,status,reason),'tip_id':tid,'source_table':tip.get('_table',''),'market_group':g,'status':status,'result_label':'✅ WIN' if status=='win' else '❌ LOST' if status=='loss' else '⏳ PENDING','reason':reason,'odds':odds,'stake':1,'profit':round(profit,4),'tip_date':row_date(tip),'tip_payload':tip,'legs_payload':payload,'settled_at':NOW.isoformat()}

def update_tip(s):
 if not UPDATE_TIPS or s['status'] not in ('win','loss'): return
 p=s.get('tip_payload') or {}; table=s.get('source_table') or p.get('_table') or ''
 col,val=source_key(p)
 if not table or not col: return
 for payload in ({'status':s['status'],'result':s['status'],'settled_at':NOW.isoformat()},{'status':s['status'],'settled_at':NOW.isoformat()},{'result':s['status']}):
  if patch(table,col,val,payload): return

def report_key(s):
 p=s.get('tip_payload') or {}; h,a,mt=match_parts(p); match=norm(mt or f'{h} vs {a}')
 g=s.get('market_group',''); st=s.get('status',''); reason=str(s.get('reason',''))
 if g in ('btts','over25','btts_ht','over15_ht'):
  m=re.search(r'\d+\s*:\s*\d+',reason); score=m.group(0) if m else reason
  return f'{g}|{match}|{st}|{score}'
 return f'{g}|{match}|{market_text(p)}|{st}|{reason}'

def dedup(items,include_pending=True):
 seen=set(); out=[]
 for s in items:
  if not include_pending and s.get('status')=='pending': continue
  k=report_key(s)
  if k not in seen: seen.add(k); out.append(s)
 return out

def existing_settlements():
 return get('netrattler_settlements',{'select':'*','tip_date':f'gte.{YEAR_S}','limit':'5000'},True) or []

def norm_status(x):
 x=str(x or '').lower()
 if x in ('win','won','green'): return 'win'
 if x in ('loss','lost','red'): return 'loss'
 return 'pending'

def summary(items,g,start):
 arr=[]
 for x in items:
  if x.get('market_group')!=g: continue
  st=norm_status(x.get('status'))
  if st not in ('win','loss'): continue
  if str(x.get('tip_date') or '')[:10] >= start:
   y=dict(x); y['status']=st; arr.append(y)
 arr=dedup(arr,False); w=sum(x['status']=='win' for x in arr); l=sum(x['status']=='loss' for x in arr)
 prof=sum(float(x.get('profit') or (1 if x['status']=='win' else -1)) for x in arr); bets=w+l; roi=100*prof/max(1,bets)
 return {'bets':bets,'wins':w,'losses':l,'profit':round(prof,2),'roi':round(roi,1)}

def save_stats(allitems):
 rows=[]
 for g in ORDER:
  for period,start in (('today',TODAY_S),('month',MONTH_S),('year',YEAR_S)):
   s=summary(allitems,g,start)
   rows.append({'stat_id':hsh(period,g,start),'period':period,'market_group':g,'bets':s['bets'],'wins':s['wins'],'losses':s['losses'],'profit':s['profit'],'roi':s['roi'],'updated_at':NOW.isoformat()})
 log(f'Gruppenstats gespeichert: {upsert("netrattler_group_stats",rows,"stat_id")}')

def fmt(s):
 p=s.get('tip_payload') or {}; h,a,mt=match_parts(p); match=mt or f'{h} vs {a}'
 return f"{s['result_label']} <b>{s['market_group'].upper()}</b>\n{match}\n{market_text(p)}\n{s.get('reason','')}"

def group_text(g,items,history):
 items=dedup(items,True); closed=[x for x in items if x.get('status') in ('win','loss')]; pending=[x for x in items if x.get('status')=='pending']
 w=sum(x['status']=='win' for x in closed); l=sum(x['status']=='loss' for x in closed); prof=sum(float(x.get('profit') or 0) for x in closed); roi=100*prof/max(1,w+l)
 mon=summary(history,g,MONTH_S); yr=summary(history,g,YEAR_S)
 msg=f"📊 <b>NETRATTLER AUSWERTUNG {g.upper()}</b>\n{TODAY_S}\n\nHeute: <b>{w}-{l}</b> | Offen {len(pending)}\nROI heute: <b>{roi:.1f}%</b> | Profit <b>{prof:.2f} Units</b>\nMonat: <b>{mon['wins']}-{mon['losses']}</b> | ROI <b>{mon['roi']:.1f}%</b> | Profit <b>{mon['profit']:.2f}</b>\nJahr: <b>{yr['wins']}-{yr['losses']}</b> | ROI <b>{yr['roi']:.1f}%</b> | Profit <b>{yr['profit']:.2f}</b>\n\n"
 if closed:
  msg+='✅❌ <b>Abgeschlossen</b>\n\n'
  for s in closed[:25]:
   block=fmt(s)+'\n\n'
   if len(msg)+len(block)>3600: break
   msg+=block
 if pending:
  msg+='⏳ <b>Noch offen / nicht auswertbar</b>\n\n'
  for s in pending[:12]:
   block=fmt(s)+'\n\n'
   if len(msg)+len(block)>3600: break
   msg+=block
 if not closed and not pending: msg+='Keine Tipps in dieser Gruppe gefunden.\n'
 return msg

def send_reports(nowitems,history):
 by=defaultdict(list)
 for s in nowitems: by[s.get('market_group','default')].append(s)
 status=[]
 for g in ORDER:
  items=by.get(g,[])
  if not items and not SEND_EMPTY: continue
  chat=GROUPS.get(g) or GROUPS.get('default')
  if not chat: log(f'Keine Telegram-Gruppe für {g}','WARN'); continue
  ok=tg(chat,group_text(g,items,history)); status.append(f'{g}:{"OK" if ok else "FAIL"}')
 log('Gruppenreports: '+', '.join(status))

def send_stats(history):
 lines=[f'📈 <b>NETRATTLER ROI REPORT</b>\n{TODAY_S}\n']
 for g in ORDER:
  td=summary(history,g,TODAY_S); mo=summary(history,g,MONTH_S); yr=summary(history,g,YEAR_S)
  lines.append(f"<b>{g.upper()}</b>\nHeute: {td['wins']}-{td['losses']} | ROI {td['roi']:.1f}% | Profit {td['profit']:.2f}\nMonat: {mo['wins']}-{mo['losses']} | ROI {mo['roi']:.1f}% | Profit {mo['profit']:.2f}\nJahr: {yr['wins']}-{yr['losses']} | ROI {yr['roi']:.1f}% | Profit {yr['profit']:.2f}\n")
 chat=GROUPS.get('stats') or GROUPS.get('default')
 if chat: tg(chat,'\n'.join(lines))

def main():
 log('⚽ NETRATTLER Settlement V16 ML GROUP FINAL startet')
 if not SUPABASE_URL or not SUPABASE_KEY:
  log('SUPABASE_URL oder SUPABASE_KEY fehlt','ERROR'); return
 tips=load_tips(); dates=sorted(set(row_date(t) for t in tips)); log(f'Dates: {dates}')
 results=load_results(dates); settled=[settle_tip(t,results) for t in tips]
 log(f'Counts: {dict(Counter(x["status"] for x in settled))}')
 log(f'Settled nach Gruppen: {dict(Counter(x["market_group"] for x in settled))}')
 log(f'Settlements gespeichert: {upsert("netrattler_settlements",settled,"settlement_id")}')
 for s in settled: update_tip(s)
 history=existing_settlements()+settled
 save_stats(history); send_reports(settled,history); send_stats(history)
 log('✅ Settlement V16 ML GROUP FINAL fertig')

if __name__=='__main__':
 main()
