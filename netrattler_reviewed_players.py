"""Fixture-specific observed player evidence; no absent-player or zero inference.

Full-match values reviewed 2026-11-04. A measured zero is explicit source data.
Keep source dates and require ordered teams, player and date before returning data.
"""
import json
from datetime import date

EVIDENCE = [
 dict(day='2026-11-04', home='Porto', away='Napoli', score=(4,1),
      team='Napoli', player='Amir Rrahmani', minutes=90,
      stats={'shots':0,'sot':0}, checked_at='2026-11-05',
      url='https://footballnation.eu/football-player/amir-rrahmani/',
      result_url='https://www.uefa.com/uefachampionsleague/match/2049617--porto-vs-napoli/'),
 dict(day='2026-10-29', home='Benfica', away='Gil Vicente', score=(4,1),
      team='Benfica', player='Gianluca Prestianni', minutes=18,
      stats={'sot':0,'fouls_won':0}, url='https://footydatalab.com/players/eoqiVrQN'),
 dict(day='2026-10-29', home='Braga', away='Famalicao', score=(2,2),
      team='Famalicao', player='Pedro Bondo', minutes=63,
      stats={'fouls_won':3}, url='https://footydatalab.com/players/PrLU99P5'),
]


def legs(tip):
    out=[tip]
    for key in ('legs','builder_legs'):
        rows=tip.get(key) or []
        if isinstance(rows,str):
            try: rows=json.loads(rows)
            except ValueError: rows=[]
        if isinstance(rows,list):out.extend(x for x in rows if isinstance(x,dict))
    return out


def matches(tip, item, match_parts, row_date, same):
    for leg in legs(tip):
        h,a,_=match_parts(leg)
        day=str(leg.get('match_date') or leg.get('date') or row_date(tip))[:10]
        if (day==item['day'] and same(h,item['home']) and same(a,item['away'])
            and str(leg.get('player') or leg.get('player_name') or '').casefold()==item['player'].casefold()
            and (not leg.get('team') or same(leg['team'],item['team']))):
            return True
    return False


def collect(tips,match_parts,row_date,same):
    results=[];players=[]
    for item in EVIDENCE:
        if not any(matches(t,item,match_parts,row_date,same) for t in tips):continue
        event='reviewed:'+item['day']+':'+item['home']+':'+item['away']
        identity=dict(source='reviewed_player_evidence',event_id=event,match_date=item['day'],
                      home_team=item['home'],away_team=item['away'])
        players.append(dict(identity,player_name=item['player'],team=item['team'],minutes=item['minutes'],
                            evidence_url=item['url'],**item['stats']))
        results.append(dict(identity,_result_table='reviewed_player_evidence',
                            home_score=item['score'][0],away_score=item['score'][1],
                            raw={'evidence_url':item.get('result_url',item['url']),'checked_at':item.get('checked_at','2026-11-04')}))
    return results,players


def recoverable(existing,unpack,confirmed,match_parts,row_date,same):
    """Revisit delivered data-timeout VOIDs when new observed evidence is available."""
    out=[]
    for row in existing:
        if row.get('status')!='void' or not str(row.get('reason') or '').startswith(
                ('void: kein Ergebnis nach','void: nicht bewertbar nach')):continue
        tip=unpack(row.get('tip_payload') or {})
        if not confirmed(tip):continue
        if not any(matches(tip,item,match_parts,row_date,same) for item in EVIDENCE):continue
        tip=dict(tip,_table=row.get('source_table') or 'netrattler_builder_picks')
        out.append(tip)
        if len(out)>=30:break
    return out
