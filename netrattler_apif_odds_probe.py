"""Read-only samples of actual API-Football bookmaker markets; never treats catalogue entries as quotes."""
import json
import os
from datetime import datetime,timezone,timedelta
from pathlib import Path
import requests
from netrattler_apif_response import checked_response,number
from netrattler_apifootball_players import PRIORITY


def main():
    keys=[k.strip() for k in os.getenv('API_FOOTBALL_KEYS','').replace('\n',',').split(',') if k.strip()]
    if not keys:raise RuntimeError('API-Football configuration missing')
    calls=0
    def api(path,params):
        nonlocal calls
        calls+=1
        return checked_response(requests.get('https://v3.football.api-sports.io'+path,
            headers={'x-apisports-key':keys[0]},params=params,timeout=25))
    today=datetime.now(timezone.utc).date()
    fixtures=[]
    for i in range(3):fixtures.extend(api('/fixtures',{'date':str(today+timedelta(days=i))}))
    by={}
    for fx in fixtures:
        lid=(fx.get('league') or {}).get('id')
        if lid in PRIORITY and (fx.get('fixture') or {}).get('status',{}).get('short')=='NS':
            by.setdefault(lid,[]).append(fx)
    chosen=[]
    for lid in PRIORITY:
        if by.get(lid):chosen.append(sorted(by[lid],key=lambda f:f['fixture']['date'])[0])
    report=[]
    for fx in chosen[:8]:
        fid=fx['fixture']['id']
        payload=api('/odds',{'fixture':fid})
        markets={};books=set()
        for item in payload:
            if (item.get('fixture') or {}).get('id')!=fid:continue
            for book in item.get('bookmakers') or []:
                books.add(book.get('name') or str(book.get('id')))
                for bet in book.get('bets') or []:
                    label=str(bet.get('name') or '')
                    if not any(w in label.lower() for w in ('corner','scor','player','shot','foul','tackle','card')):continue
                    valid=[]
                    for value in bet.get('values') or []:
                        try:q=float(value.get('odd') or 0)
                        except (TypeError,ValueError):continue
                        if 1<q<=1000:valid.append({'selection':str(value.get('value') or '')[:100],'odds':q})
                    if valid and label not in markets:
                        markets[label]={'bet_id':bet.get('id'),'bookmaker':book.get('name'),'quotes':valid[:3],
                                        'available_values':len(valid)}
        row={'fixture_id':fid,'match':fx['teams']['home']['name']+' vs '+fx['teams']['away']['name'],
             'league':fx['league']['name'],'bookmakers':len(books),'relevant_markets':markets}
        report.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    Path('apif_odds_samples.json').write_text(json.dumps({'api_calls':calls,'fixtures':report},ensure_ascii=False,indent=2))
    print(json.dumps({'probe':'apif_actual_odds','api_calls':calls,'sampled_fixtures':len(report),
                      'fixtures_with_relevant_quotes':sum(bool(r['relevant_markets']) for r in report)}))


if __name__=='__main__':main()
