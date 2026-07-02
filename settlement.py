#!/usr/bin/env python3
import os, re, json, hashlib, unicodedata
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
import requests

SUPABASE_URL=(os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
TG_TOKEN=os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
TG_DEFAULT=os.getenv("TELEGRAM_CHAT_ID") or ""
DAYS=int(os.getenv("SETTLEMENT_DAYS","7"))
LIMIT=int(os.getenv("SETTLEMENT_LIMIT","1000"))
NOW=datetime.now(timezone.utc)
TODAY=NOW.date()
GROUPS={
 "btts":os.getenv("TELEGRAM_GROUP_BTTS") or TG_DEFAULT,
 "over25":os.getenv("TELEGRAM_GROUP_OVER25") or TG_DEFAULT,
 "combo":os.getenv("TELEGRAM_GROUP_COMBO") or TG_DEFAULT,
 "btts_ht":os.getenv("TELEGRAM_GROUP_BTTS_HT") or TG_DEFAULT,
 "over15_ht":os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
 "builder":os.getenv("TELEGRAM_GROUP_BUILDER") or os.getenv("TELEGRAM_GROUP_PROPS") or TG_DEFAULT,
 "props":os.getenv("TELEGRAM_GROUP_PROPS") or TG_DEFAULT,
 "corners":os.getenv("TELEGRAM_GROUP_CORNERS") or os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
 "stats":os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
 "default":TG_DEFAULT,
}

def log(x,l="INFO"): print(f"[{datetime.now().strftime('%H:%M:%S')}] [{l}] {x}",flush=True)
def hsh(*x): return hashlib.sha1("||".join(str(v or "") for v in x).encode()).hexdigest()
def norm(s):
 s=str(s or "").lower().strip()
 s=unicodedata.normalize("NFKD",s); s="".join(c for c in s if not unicodedata.combining(c))
 s=re.sub(r"\b(fc|sc|cf|afc|fk|ac|club|de|the)\b"," ",s)
 s=re.sub(r"[^a-z0-9]+"," ",s); return re.sub(r"\s+"," ",s).strip()
def sim(a,b):
 a=norm(a); b=norm(b)
 if not a or not b: return 0
 if a==b: return 1
 if a in b or b in a: return .86
 sa=set(a.split()); sb=set(b.split())
 return len(sa&sb)/max(1,len(sa|sb))
def anyv(r,ks,d=""):
 for k in ks:
  if k in r and r[k] not in (None,""): return r[k]
 return d
def dt(x):
 if not x: return None
 s=str(x).replace("Z","+00:00")
 try:
  d=datetime.fromisoformat(s); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
 except: return None
def tip_date(r):
 for k in ["match_date","date","ko","kickoff","event_time","created_at"]:
  d=dt(r.get(k))
  if d: return d.date().isoformat()
 return TODAY.isoformat()
def headers(pref="return=representation"):
 return {"apikey":SUPABASE_KEY,"Authorization":"Bearer "+SUPABASE_KEY,"Content-Type":"application/json","Prefer":pref}
def get(table,params):
 try:
  r=requests.get(f"{SUPABASE_URL}/rest/v1/{table}",headers=headers(),params=params,timeout=25)
  if r.status_code>=400: log(f"GET {table} {r.status_code}: {r.text[:140]}","WARN"); return []
  return r.json() if r.text else []
 except Exception as e: log(f"GET {table}: {e}","WARN"); return []
def upsert(table,rows,conflict):
 ok=0
 for i in range(0,len(rows),200):
  part=rows[i:i+200]
  try:
   r=requests.post(f"{SUPABASE_URL}/rest/v1/{table}",headers=headers("resolution=merge-duplicates,return=minimal"),params={"on_conflict":conflict},data=json.dumps(part,ensure_ascii=False,default=str),timeout=30)
   if r.status_code in (200,201,204): ok+=len(part)
   else: log(f"UPSERT {table} {r.status_code}: {r.text[:180]}","WARN")
  except Exception as e: log(f"UPSERT {table}: {e}","WARN")
 return ok
def tg(chat,text):
 if not TG_TOKEN or not chat: return False
 try:
  r=requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",json={"chat_id":chat,"text":text[:3900],"parse_mode":"HTML","disable_web_page_preview":True},timeout=15)
  if not r.ok: log(f"TG {r.status_code}: {r.text[:120]}","WARN")
  return r.ok
 except Exception as e: log(f"TG: {e}","WARN"); return False
def market(r):
 low=" ".join(str(anyv(r,[k],"")) for k in ["market","type","bet_type","category","group","channel","selection","pick"]).lower()
 if any(x in low for x in ["builder","god","aystar","nate"]): return "builder"
 if any(x in low for x in ["combo","multi","parlay"]): return "combo"
 if any(x in low for x in ["corner","ecken"]): return "corners"
 if any(x in low for x in ["player","booked","shot","foul","tackle","card"]): return "props"
 if "btts_ht" in low or "btts ht" in low: return "btts_ht"
 if "over 1.5 ht" in low or "over15_ht" in low: return "over15_ht"
 if "over" in low and "2.5" in low: return "over25"
 if "btts" in low or "both teams" in low: return "btts"
 return "default"
def tid(r): return str(anyv(r,["id","tip_id","pick_id","uuid"],"")) or hsh(anyv(r,["match","fixture","game"],""),anyv(r,["market","type"],""),anyv(r,["selection","pick"],""),tip_date(r))
def match_parts(r):
 h=str(anyv(r,["home_team","home","team_home"],"")); a=str(anyv(r,["away_team","away","team_away"],"")); m=str(anyv(r,["match","fixture","game","event","entity_name"],""))
 if (not h or not a) and re.search(r"\s+v(s)?\s+",m,re.I):
  p=re.split(r"\s+vs\s+|\s+v\s+",m,flags=re.I); h=p[0].strip(); a=p[1].strip() if len(p)>1 else ""
 return h,a,m or (f"{h} vs {a}" if h and a else "")
def load_tips():
 tables=["tips","bet_tips","netrattler_tips","sent_tips","pending_tips","prop_picks","player_prop_db","value_signals"]
 out=[]
 for t in tables:
  rows=get(t,{"select":"*","limit":str(LIMIT)})
  for r in rows:
   st=str(anyv(r,["status","result"],"pending")).lower()
   if st in ("","pending","open","none","null"): r["_table"]=t; out.append(r)
 seen=set(); res=[]
 for r in out:
  i=tid(r)
  if i not in seen: seen.add(i); res.append(r)
 log(f"Offene Tipps: {len(res)}"); return res[:LIMIT]
def score_from_result(r):
 p=r.get("payload") if isinstance(r.get("payload"),dict) else {}
 raw=r.get("raw") if isinstance(r.get("raw"),dict) else {}
 m={}; m.update(p); m.update(raw); m.update(r)
 h,a,mm=match_parts(m)
 hs=anyv(m,["home_score","home_goals","FTHG","intHomeScore","score_home"],None)
 aw=anyv(m,["away_score","away_goals","FTAG","intAwayScore","score_away"],None)
 try: hs=int(float(hs))
 except: hs=None
 try: aw=int(float(aw))
 except: aw=None
 return h,a,hs,aw
def public_results(d):
 out=[]
 try:
  js=requests.get("https://www.thesportsdb.com/api/v1/json/3/eventsday.php",params={"d":d,"s":"Soccer"},timeout=15).json()
  for e in js.get("events") or []:
   out.append({"home_team":e.get("strHomeTeam"),"away_team":e.get("strAwayTeam"),"home_score":e.get("intHomeScore"),"away_score":e.get("intAwayScore"),"match_date":d,"raw":e,"_result_table":"TheSportsDB"})
 except: pass
 return out
def load_results(dates):
 tables=["match_results","results","football_results","football_historical_matches","result_candidates","netrattler_data_lake_raw"]
 out=[]
 for d in dates:
  for t in tables:
   for col in ["date","match_date"]:
    rows=get(t,{"select":"*",col:f"eq.{d}","limit":"1000"})
    if rows:
     for r in rows: r["_result_table"]=t
     out+=rows; break
  out+=public_results(d)
 log(f"Result candidates: {len(out)}"); return out
def find_res(tip,results):
 th,ta,tm=match_parts(tip); td=tip_date(tip); best=None; bs=0
 for r in results:
  rh,ra,hs,aw=score_from_result(r)
  if hs is None or aw is None: continue
  s=max((sim(th,rh)+sim(ta,ra))/2 if th and ta else sim(tm,f"{rh} vs {ra}"), (sim(th,ra)+sim(ta,rh))/2 if th and ta else 0)
  if str(anyv(r,["date","match_date"],td))[:10]==td: s+=.15
  if s>bs: bs=s; best={"home":rh,"away":ra,"home_score":hs,"away_score":aw,"score":s,"raw":r}
 return best if best and bs>=.68 else None
def settle_single(t,res):
 hs=res["home_score"]; aw=res["away_score"]; total=hs+aw
 low=" ".join(str(anyv(t,[k],"")) for k in ["market","type","selection","pick","category"]).lower()
 if "btts" in low or "both teams" in low: return ("win" if hs>0 and aw>0 else "loss",f"{hs}:{aw}")
 if "over" in low:
  m=re.search(r"over\s*([0-9]+(\.[0-9]+)?)",low); line=float(m.group(1)) if m else 2.5
  return ("win" if total>line else "loss",f"{hs}:{aw} Tore={total} Over {line}")
 if "under" in low:
  m=re.search(r"under\s*([0-9]+(\.[0-9]+)?)",low); line=float(m.group(1)) if m else 2.5
  return ("win" if total<line else "loss",f"{hs}:{aw} Tore={total} Under {line}")
 if any(x in low for x in ["booked","card","shot","foul","tackle","corner","player"]): return "pending","Player/Corner Stats fehlen"
 return "pending",f"{hs}:{aw} Markt nicht erkannt"
def legs(t):
 for k in ["legs","builder_legs","combo_legs","selections"]:
  v=t.get(k)
  if isinstance(v,list): return [x if isinstance(x,dict) else {"selection":str(x)} for x in v]
  if isinstance(v,str) and v.strip().startswith("["):
   try: return json.loads(v)
   except: pass
 txt=str(anyv(t,["message","text","tip_text","selection","pick"],""))
 out=[]
 for line in txt.splitlines():
  if any(x in line.lower() for x in [" vs ","over","btts","booked","shot","foul","corner"]): out.append({"selection":line,"match":line})
 return out
def settle_tip(t,results):
 g=market(t); i=tid(t); leg_payload=[]
 if g in ("combo","builder"):
  lg=legs(t); w=l=p=0
  for le in lg:
   fake=dict(t); fake.update(le if isinstance(le,dict) else {"selection":str(le)})
   r=find_res(fake,results)
   if not r: p+=1; leg_payload.append({"leg":le,"status":"pending"}); continue
   st,why=settle_single(fake,r)
   w+=st=="win"; l+=st=="loss"; p+=st=="pending"; leg_payload.append({"leg":le,"status":st,"reason":why})
  status="loss" if l else "pending" if p else "win"; reason=f"{w}/{len(lg)} Legs · {l} lost · {p} offen"
 else:
  r=find_res(t,results)
  if not r: status,reason="pending","kein Result gefunden"
  else: status,reason=settle_single(t,r)
 odds=anyv(t,["odds","quote","price","total_odds"],None)
 try: odds=float(odds)
 except: odds=None
 profit=(odds-1) if status=="win" and odds else -1 if status=="loss" else 0
 return {"settlement_id":hsh(i,status,reason),"tip_id":i,"source_table":t.get("_table",""),"market_group":g,"status":status,"result_label":"✅ WIN" if status=="win" else "❌ LOST" if status=="loss" else "⏳ PENDING","reason":reason,"odds":odds,"stake":1,"profit":round(profit,4),"tip_date":tip_date(t),"tip_payload":t,"legs_payload":leg_payload,"settled_at":NOW.isoformat()}
def fmt(s):
 p=s["tip_payload"]; h,a,m=match_parts(p); match=m or f"{h} vs {a}"
 return f"{s['result_label']} <b>{s['market_group'].upper()}</b>\n{match}\n{anyv(p,['market','type','category'],'')}: {anyv(p,['selection','pick'],'')}\n{s['reason']}"
def reports(settled):
 by=defaultdict(list)
 for s in settled:
  if s["status"]!="pending": by[s["market_group"]].append(s)
 for g,items in by.items():
  chat=GROUPS.get(g) or GROUPS["default"]
  msg=f"📊 <b>NETRATTLER AUSWERTUNG {g.upper()}</b>\n{TODAY}\n\n"
  for s in items[:40]: msg+=fmt(s)+"\n\n"
  tg(chat,msg)
def stats(settled):
 closed=[x for x in settled if x["status"] in ("win","loss")]
 rows=[]; by=defaultdict(list)
 for x in closed: by[x["market_group"]].append(x)
 lines=[f"📈 <b>NETRATTLER HEUTE / MONAT / JAHR</b>\n{TODAY}"]
 for g,it in sorted(by.items()):
  w=sum(x["status"]=="win" for x in it); l=sum(x["status"]=="loss" for x in it); prof=sum(float(x["profit"]) for x in it); roi=100*prof/max(1,len(it))
  rows.append({"stat_id":hsh("today",g,TODAY),"period":"today","market_group":g,"bets":len(it),"wins":w,"losses":l,"profit":round(prof,2),"roi":round(roi,2),"updated_at":NOW.isoformat()})
  lines.append(f"{g.upper()}: {w}-{l} | ROI {roi:.1f}% | Profit {prof:.2f}")
 upsert("netrattler_group_stats",rows,"stat_id")
 tg(GROUPS.get("stats") or GROUPS["default"],"\n".join(lines))
def main():
 log("⚽ NETRATTLER Settlement V16 FINAL startet")
 tips=load_tips()
 dates=sorted(set(tip_date(t) for t in tips)); log(f"Dates: {dates}")
 results=load_results(dates)
 settled=[settle_tip(t,results) for t in tips]
 c=Counter(x["status"] for x in settled); log(f"Counts: {dict(c)}")
 ok=upsert("netrattler_settlements",settled,"settlement_id"); log(f"Settlements gespeichert: {ok}")
 reports(settled); stats(settled)
 log("✅ Settlement V16 FINAL fertig")
if __name__=="__main__": main()
