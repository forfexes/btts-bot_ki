#!/usr/bin/env python3
import csv, hashlib, json, math, os, time, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from io import StringIO
import requests
class Supabase:
    def __init__(self):
        self.url=(os.getenv('SUPABASE_URL') or '').rstrip('/'); self.key=os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or ''
        if not self.url or not self.key: raise RuntimeError('SUPABASE_URL / SUPABASE_KEY fehlt')
        self.rest=self.url+'/rest/v1'
    def headers(self,prefer=None):
        h={'apikey':self.key,'Authorization':'Bearer '+self.key,'Content-Type':'application/json'}
        if prefer: h['Prefer']=prefer
        return h
    def get(self,table,params=None,limit=None):
        params=dict(params or {})
        if limit is not None: params['limit']=limit
        qs=urllib.parse.urlencode(params,doseq=True); r=requests.get(self.rest+'/'+table+('?'+qs if qs else ''),headers=self.headers(),timeout=35)
        if r.status_code>=400: raise RuntimeError(f'GET {table} {r.status_code}: {r.text[:300]}')
        return r.json() if r.text else []
    def try_get(self,table,params=None,limit=None):
        try: return self.get(table,params,limit)
        except Exception as e: print(f'WARN {table} skip: {e}'); return []
    def upsert(self,table,rows,on_conflict=None,chunk=500):
        rows=[r for r in rows if isinstance(r,dict) and r]
        if not rows: return 0
        total=0
        for i in range(0,len(rows),chunk):
            part=rows[i:i+chunk]
            # FIX: PostgREST Bulk-Insert braucht in jedem Objekt exakt dieselben Keys.
            # Sonst kommt PGRST102: "All object keys must match".
            all_keys=set()
            for row in part:
                all_keys.update(row.keys())
            part=[{k: row.get(k, None) for k in all_keys} for row in part]
            url=self.rest+'/'+table
            if on_conflict: url += '?on_conflict='+urllib.parse.quote(on_conflict)
            r=requests.post(url,headers=self.headers('resolution=merge-duplicates,return=minimal'),data=json.dumps(part,ensure_ascii=False,default=str).encode(),timeout=45)
            if r.status_code>=400: print(f'WARN UPSERT {table} {r.status_code}: {r.text[:500]}')
            else: total += len(part)
            time.sleep(0.03)
        return total
    def count(self,table):
        try:
            r=requests.get(self.rest+'/'+table+'?select=*',headers={**self.headers(),'Prefer':'count=exact','Range':'0-0','Range-Unit':'items'},timeout=25)
            if r.status_code>=400: return None
            cr=r.headers.get('Content-Range','')
            return int(cr.split('/')[-1]) if '/' in cr and cr.split('/')[-1].isdigit() else len(r.json() if r.text else [])
        except Exception: return None
def now(): return datetime.now(timezone.utc).isoformat()
def day(): return datetime.now(timezone.utc).date().isoformat()
def sid(*x): return hashlib.sha1('|'.join(str(v or '') for v in x).encode()).hexdigest()
def clamp(v): return max(0,min(100,v))
SOURCES=[('Pinnacle','odds_props','guest/api','https://www.pinnacle.com/',True,False,88),('Football-Data.co.uk','stats_results_odds','csv','https://www.football-data.co.uk/',True,False,82),('ClubElo','elo','api_csv','http://api.clubelo.com/',True,False,80),('xgabora','history','github_csv','https://github.com/xgabora/Club-Football-Match-Data-2000-2025',True,False,78),('StatsBomb Open Data','player_events','github_json','https://github.com/statsbomb/open-data',True,False,85),('FPL','player_profiles_availability','api','https://fantasy.premierleague.com/api/bootstrap-static/',True,False,76),('TheSportsDB','results','api','https://www.thesportsdb.com/',True,False,68),('OpenLigaDB','results','api','https://www.openligadb.de/',True,False,72),('ScoreBat','video_evidence','api','https://www.scorebat.com/video-api/',True,False,62),('Google News RSS','news','rss','https://news.google.com/rss',True,False,58),('GitHub Open Source','open_source','github_api','https://api.github.com/',True,False,70),('Instagram Graph API','social','official_api','https://developers.facebook.com/docs/instagram-api/',False,True,55),('TikTok Research API','social','official_api','https://developers.tiktok.com/products/research-api/',False,True,50),('TheStatsAPI','stats_results_props','api','https://www.thestatsapi.com/',False,True,55)]
CHECKS=[('Football-Data.co.uk','https://www.football-data.co.uk/mmz4281/2526/E0.csv'),('ClubElo','http://api.clubelo.com/2026-06-28'),('FPL','https://fantasy.premierleague.com/api/bootstrap-static/'),('TheSportsDB','https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t=Arsenal'),('ScoreBat','https://www.scorebat.com/video-api/v3/'),('StatsBomb Open Data','https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json')]
CORE=['football_historical_matches','football_team_history_features','team_elo_history','league_goal_features','league_cards_features','league_corners_features','player_match_stats','player_avg_stats','player_profiles','injury_reports','player_availability_signals','prop_picks','odds_history','odds_snapshots','netrattler_clv_tracking','netrattler_source_roi_metrics','netrattler_news_signals','netrattler_social_signals','netrattler_github_open_source_sources','netrattler_source_registry','netrattler_source_health','netrattler_source_trust_scores','netrattler_learning_state','result_candidates','team_aliases','value_signals']
def run_health(db):
    rows=[{'source':s,'category':c,'source_type':t,'url':u,'is_free':free,'requires_key':key,'priority':p,'base_trust':p,'notes':'Best Database Simple','updated_at':now()} for s,c,t,u,free,key,p in SOURCES]
    print('netrattler_source_registry',db.upsert('netrattler_source_registry',rows,'source'))
    out=[]
    for s,u in CHECKS:
        t=time.time()
        try:
            r=requests.get(u,timeout=25,headers={'User-Agent':'NETRATTLER-BEST-SIMPLE/1.0'}); rows=1 if r.text else 0
            if s=='FPL' and r.ok: rows=len((r.json() or {}).get('elements',[]))
            out.append({'source':s,'status':'ok' if r.ok else f'http_{r.status_code}','http_status':r.status_code,'rows':rows,'latency_ms':int((time.time()-t)*1000),'message':'ok' if r.ok else r.text[:180],'checked_at':now()})
        except Exception as e: out.append({'source':s,'status':'error','rows':0,'latency_ms':int((time.time()-t)*1000),'message':str(e)[:220],'checked_at':now()})
    key=os.getenv('THESTATSAPI_KEY') or ''
    if not key: out.append({'source':'TheStatsAPI','status':'missing_key','rows':0,'message':'THESTATSAPI_KEY fehlt','checked_at':now()})
    else:
        try:
            r=requests.get('https://api.thestatsapi.com/v1/football/leagues',headers={'Authorization':'Bearer '+key,'x-api-key':key},timeout=25)
            out.append({'source':'TheStatsAPI','status':'invalid_key_401' if r.status_code==401 else ('ok' if r.ok else f'http_{r.status_code}'),'http_status':r.status_code,'rows':1 if r.ok else 0,'message':'ok' if r.ok else r.text[:200],'checked_at':now()})
        except Exception as e: out.append({'source':'TheStatsAPI','status':'error','rows':0,'message':str(e)[:220],'checked_at':now()})
    print('netrattler_source_health',db.upsert('netrattler_source_health',out,'source'))
def classify(txt):
    low=(txt or '').lower(); keys=[]
    for typ,kws in {'injury':['injured','injury','verletzung','out','doubtful'],'suspension':['suspended','gesperrt','ban'],'lineup':['lineup','starting xi','bench','rotation'],'form':['training','fit again']}.items():
        if any(k in low for k in kws): keys.append(typ)
    if not keys: keys=['news']
    sent=-0.6 if any(x in low for x in ['injur','out','suspended','gesperrt']) else (0.4 if 'training' in low or 'fit' in low else 0)
    return keys[0],keys,sent,55+min(35,len(keys)*10)
def run_news(db):
    rows=[]; qs=[q.strip() for q in (os.getenv('NETRATTLER_SIGNAL_QUERIES') or 'football injury lineup suspension today|soccer starting XI injury suspension').split('|') if q.strip()]
    for q in qs[:10]:
        try:
            r=requests.get('https://news.google.com/rss/search?q='+urllib.parse.quote_plus(q)+'&hl=en-US&gl=US&ceid=US:en',timeout=25,headers={'User-Agent':'NETRATTLER-BEST-SIMPLE/1.0'}); r.raise_for_status(); root=ET.fromstring(r.text)
            for it in root.findall('.//item')[:15]:
                title=it.findtext('title') or ''; link=it.findtext('link') or ''; typ,kw,sent,conf=classify(title)
                rows.append({'signal_id':sid('google',q,title,link),'source':'Google News RSS','title':title,'url':link,'signal_type':typ,'sentiment':sent,'confidence':conf,'keywords':kw,'raw':{'query':q},'created_at':now()})
        except Exception as e: print('WARN Google News',q,e)
    try:
        r=requests.get('https://www.scorebat.com/video-api/v3/',timeout=30,headers={'User-Agent':'NETRATTLER-BEST-SIMPLE/1.0'}); r.raise_for_status()
        for x in (r.json() or {}).get('response',[])[:80]: rows.append({'signal_id':sid('scorebat',x.get('matchviewUrl') or x.get('title')),'source':'ScoreBat','title':x.get('title'),'url':x.get('matchviewUrl'),'published_at':x.get('date'),'signal_type':'video_evidence','sentiment':0,'confidence':58,'keywords':['highlight','video'],'raw':x,'created_at':now()})
    except Exception as e: print('WARN ScoreBat',e)
    print('netrattler_news_signals',db.upsert('netrattler_news_signals',rows,'signal_id'))
    social=[]; url=os.getenv('SOCIAL_SIGNAL_CSV_URL','').strip()
    if url:
        try:
            for r in csv.DictReader(StringIO(requests.get(url,timeout=30).text)):
                body=r.get('text') or r.get('caption') or r.get('title') or ''; typ,kw,sent,conf=classify(body)
                social.append({'signal_id':sid(r.get('platform'),r.get('url'),body[:80]),'platform':r.get('platform') or 'social','source':r.get('source') or r.get('platform') or 'social','url':r.get('url'),'posted_at':r.get('posted_at') or r.get('date'),'team_name':r.get('team_name'),'player_name':r.get('player_name'),'signal_type':typ,'text':body,'engagement':float(r.get('engagement') or r.get('likes') or 0),'confidence':conf,'raw':r,'created_at':now()})
        except Exception as e: print('WARN Social CSV',e)
    print('netrattler_social_signals',db.upsert('netrattler_social_signals',social,'signal_id'))
def run_github(db):
    rows=[]; repos=[('probberechts/soccerdata','multi_source_scraper',['soccerdata','fbref','sofascore','understat']),('statsbomb/open-data','open_event_data',['statsbomb','events']),('openfootball/football.json','fixtures_results',['openfootball']),('xgabora/Club-Football-Match-Data-2000-2025','history',['history','csv'])]
    for repo,cat,tags in repos:
        try:
            h={'Accept':'application/vnd.github+json','User-Agent':'NETRATTLER-BEST-SIMPLE/1.0'}; tok=os.getenv('GITHUB_TOKEN') or os.getenv('GH_TOKEN')
            if tok: h['Authorization']='Bearer '+tok
            r=requests.get('https://api.github.com/repos/'+repo,headers=h,timeout=25); d=r.json() if r.ok else {'full_name':repo,'html_url':'https://github.com/'+repo,'description':'HTTP '+str(r.status_code)}
        except Exception as e: d={'full_name':repo,'html_url':'https://github.com/'+repo,'description':str(e)}
        lic=d.get('license') or {}; lic=lic.get('spdx_id') if isinstance(lic,dict) else ''; stars=int(d.get('stargazers_count') or 0); forks=int(d.get('forks_count') or 0)
        rows.append({'repo_full_name':d.get('full_name') or repo,'url':d.get('html_url'),'category':cat,'description':d.get('description'),'stars':stars,'forks':forks,'last_pushed_at':d.get('pushed_at'),'license':lic,'trust_score':min(95,45+min(30,stars/500)+min(10,forks/300)+(10 if lic else 0)),'tags':tags,'raw':d,'updated_at':now()})
    print('netrattler_github_open_source_sources',db.upsert('netrattler_github_open_source_sources',rows,'repo_full_name'))
def run_coverage(db):
    rows=[]; counts={}
    for t in CORE:
        c=db.count(t); counts[t]=int(c or 0); status='ok' if c and c>0 else ('empty' if c==0 else 'missing_or_blocked')
        rows.append({'table_name':t,'row_count':int(c or 0),'status':status,'message':f'{t}: {status}','checked_at':now()})
    db.upsert('netrattler_source_coverage_report',rows,'table_name'); return counts
def run_trust(db):
    reg=db.try_get('netrattler_source_registry',{'select':'*'},500); health=db.try_get('netrattler_source_health',{'select':'*','order':'checked_at.desc'},5000); hb={}
    for h in health:
        if h.get('source') and h['source'] not in hb: hb[h['source']]=h
    rows=[]
    for s in reg:
        name=s.get('source'); base=float(s.get('base_trust') or 50); h=hb.get(name,{}); rc=int(h.get('rows') or 0); st=(h.get('status') or h.get('message') or '').lower()
        hs=75+min(20,math.log10(max(rc,1))*5) if 'ok' in st else (15 if '401' in st or 'invalid' in st else (25 if '403' in st else (35 if 'error' in st or 'timeout' in st else 50)))
        cov=clamp(40+math.log10(max(rc,1))*12); pen=30 if '401' in st or 'invalid' in st else (15 if '403' in st else (10 if 'timeout' in st else 0)); trust=clamp(base*.35+hs*.30+cov*.20+50*.15-pen)
        rows.append({'source':name,'score_date':day(),'trust_score':round(trust,2),'health_score':round(hs,2),'coverage_score':round(cov,2),'clv_score':50,'roi_score':50,'freshness_score':65 if h else 45,'penalty_score':pen,'samples':rc,'reason':f'base={base} health={round(hs,1)} cov={round(cov,1)} penalty={pen}','updated_at':now()})
    print('netrattler_source_trust_scores',db.upsert('netrattler_source_trust_scores',rows,'source,score_date'))
def run_status(db,counts):
    comp={'Odds':counts.get('odds_history',0)+counts.get('odds_snapshots',0),'Props':counts.get('prop_picks',0),'Stats':counts.get('player_match_stats',0)+counts.get('player_avg_stats',0),'Results':counts.get('football_historical_matches',0)+counts.get('result_candidates',0),'CLV':counts.get('netrattler_clv_tracking',0),'News':counts.get('netrattler_news_signals',0),'Social Signals':counts.get('netrattler_social_signals',0),'GitHub/Open Source':counts.get('netrattler_github_open_source_sources',0),'Learning':counts.get('netrattler_learning_state',0),'ROI':counts.get('netrattler_source_roi_metrics',0),'Source Trust':counts.get('netrattler_source_trust_scores',0),'Coverage':counts.get('netrattler_source_coverage_report',0)}
    db.upsert('netrattler_best_database_status',[{'component':k,'status':'ok' if v>0 else 'empty','row_count':int(v),'message':f'{k}: {v}','checked_at':now()} for k,v in comp.items()],'component')
    db.upsert('netrattler_learning_state',[{'scope':'best_database','key':'simple_summary','value':{'updated_at':now(),'components':comp,'coverage':counts},'score':sum(1 for v in comp.values() if v>0),'samples':len(comp),'updated_at':now()}],'scope,key')
    print(comp)
def main():
    print('NETRATTLER BEST DATABASE SIMPLE — ONEFILE')
    db=Supabase(); run_health(db); run_news(db); run_github(db); run_trust(db); counts=run_coverage(db); run_status(db,counts); print('Fertig')
if __name__=='__main__': main()
