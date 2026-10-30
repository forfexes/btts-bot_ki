"""Read-only source audit: inventory every module/probe, test actual data separately.

Never executes arbitrary legacy probe scripts (some write to DB at import time).
No database writes, Telegram, paid API calls, proxy rotation or access-wall bypass.
HTTP reachability, structured data and production integration are separate facts.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

PUBLIC_PAGES={
 'aiscore':'https://m.aiscore.com/head-to-head/soccer-arsenal-vs-chelsea',
 'besoccer':'https://www.besoccer.com/',
 'onemillionpredictions':'https://onemillionpredictions.com/',
 'betmines':'https://betmines.com/',
 'todaymatchprediction':'https://www.todaymatchprediction.com/',
 'flashscore':'https://www.flashscore.com/football/',
 'afootballreport':'https://afootballreport.com/',
 'datamb':'https://datamb.football/teams/',
 'flashscore_match':'https://www.flashscore.com/match/football/chelsea-4fGZN2oK/manchester-united-ppjDR086/',
 'todaymatchprediction_match':'https://www.todaymatchprediction.com/gameprediction/1611435/aso-chlef-vs-es-setif.html',
 'besoccer_match':'https://www.besoccer.com/match/chelsea-fc/manchester-united-fc/20267390',
}


def inventory(root):
    root=Path(root);modules={};errors=[]
    workflows={p.name:p.read_text() for p in (root/'.github/workflows').glob('*.yml')}
    for p in sorted(root.glob('*.py')):
        text=p.read_text()
        try:tree=ast.parse(text,filename=p.name)
        except SyntaxError as e:
            errors.append({'file':p.name,'line':e.lineno});continue
        imports=set();domains=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.update(a.name.split('.')[0] for a in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:imports.add(n.module.split('.')[0])
            if isinstance(n,ast.Constant) and isinstance(n.value,str):
                for u in re.findall(r'https?://[A-Za-z0-9_.:-]+',n.value):
                    host=urlparse(u).hostname
                    if host:domains.add(host)
        modules[p.stem]={'file':p.name,'kind':'test' if p.name.startswith('test_') else 'probe' if ('probe' in p.stem or 'sweep' in p.stem) else 'module',
                         'domains':sorted(domains),'imports':sorted(imports),
                         'workflow_refs':sorted(k for k,v in workflows.items() if p.name in v)}
    # A dependency path is implementation evidence, not proof of healthy data.
    roots={'btts_bot','scrape_player_stats','netrattler_odds_harvester','netrattler_settlement_runner','netrattler_result_enrichment'}
    reachable=set();pending=list(roots)
    while pending:
        m=pending.pop()
        if m in reachable or m not in modules:continue
        reachable.add(m);pending.extend(modules[m]['imports'])
    for k,v in modules.items():v['runtime_import_path']=k in reachable
    return {'module_count':len(modules),'probe_count':sum(v['kind']=='probe' for v in modules.values()),
            'syntax_errors':errors,'modules':list(modules.values()),
            'warning':'Static workflow/import references do not prove production use or successful parsing.'}


def page_evidence(html, url=""):
    from netrattler_structured_pages import parse_public_page
    from bs4 import BeautifulSoup
    from netrattler_public_source_features import extract_labelled_tables
    s=BeautifulSoup(html or '', 'html.parser')
    return {'title':s.title.get_text(' ',strip=True)[:180] if s.title else '',
            'tables':len(s.select('table')),
            'sports_events':len(s.select('[itemtype$="SportsEvent"]')),
            'labelled_tables':extract_labelled_tables(html),
            'structured_context':parse_public_page(html,url),
            'match_dom': {sel:[str(x)[:1200] for x in s.select(sel)[:2]] for sel in
                          ['.match-info','.match-data','.team-name','.marker','time','[itemprop=homeTeam]','[itemprop=awayTeam]','[itemprop=startDate]'] } if '/match/' in url else {}}


def http_page(item):
    import requests
    name,url=item
    try:
        r=requests.get(url,timeout=12,headers={'User-Agent':'NETRATTLER-SourceAudit/1.0'},stream=True)
        body=bytearray()
        for part in r.iter_content(65536):
            body.extend(part)
            if len(body)>4_000_000:break
        r.close()
        out={'source':name,'status':r.status_code,'bytes':len(body),'reachable':r.status_code==200,
             'role':'candidate/context; never proof of usable bookmaker odds'}
        if r.status_code==200:out.update(page_evidence(bytes(body).decode('utf-8',errors='replace'),url))
        return out
    except requests.RequestException as e:return {'source':name,'error':type(e).__name__,'reachable':False}


def browser_pages():
    from playwright.sync_api import sync_playwright
    out=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context()
        for name,url in PUBLIC_PAGES.items():
            page=context.new_page()
            try:
                r=page.goto(url,wait_until='domcontentloaded',timeout=18000)
                page.wait_for_timeout(1200)
                row={'source':name,'status':r.status if r else None,'mode':'chromium'}
                if r and r.status==200:row.update(page_evidence(page.content(),url))
                out.append(row)
            except Exception as e:out.append({'source':name,'mode':'chromium','error':type(e).__name__})
            finally:page.close()
        browser.close()
    return out


def live_checks():
    import netrattler_keyless_source_probe as k
    import netrattler_quote_source_probe as q
    jobs=list(k.SOURCES.items())
    jobs += [('props_'+brand,lambda brand=brand:q.probe_kambi(brand)) for brand in q.ps._KAMBI_BRANDS]
    jobs += [('1x_'+urlparse(host).hostname,lambda host=host:q.probe_1xbet(host)) for host in q.ps._1X_HOSTS]
    def run(item):
        name,fn=item
        try:return {'source':name,'result':fn()}
        except Exception as e:return {'source':name,'error':type(e).__name__}
    with ThreadPoolExecutor(max_workers=5) as pool:
        sources=list(pool.map(run,jobs))
        pages=list(pool.map(http_page,PUBLIC_PAGES.items()))
    for row in sources+pages:print('SOURCE_AUDIT '+json.dumps(row,ensure_ascii=False),flush=True)
    return {'feeds':sources,'http_pages':pages}


def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--browser',action='store_true')
    p.add_argument('--output',default='netrattler_source_audit.json');args=p.parse_args()
    report={'captured_at':datetime.now(timezone.utc).isoformat(),'inventory':inventory(Path(__file__).parent)}
    if args.live:report['live']=live_checks()
    if args.browser:
        report['browser']=browser_pages()
        for row in report['browser']:print('SOURCE_BROWSER '+json.dumps(row,ensure_ascii=False),flush=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    inv=report['inventory'];print('SOURCE_INVENTORY',inv['module_count'],'modules',inv['probe_count'],'probes','syntax_errors',len(inv['syntax_errors']))
    return bool(inv['syntax_errors'])

if __name__=='__main__':raise SystemExit(main())
