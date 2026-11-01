"""Conservative scorer identity, legacy-field recovery and receipt-based dedupe."""
import re
import unicodedata


def norm(value):
    s=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]','',s)


def person(value):
    """Spieler-Schluessel: Nachname + Anfangsbuchstabe des Vornamens ('A. Gouiri' == 'Amine Gouiri')."""
    toks=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower().replace('.',' ').split()
    toks=[re.sub(r'[^a-z0-9]','',t) for t in toks]
    toks=[t for t in toks if t]
    if not toks:return ''
    if len(toks)==1:return toks[0]
    return toks[-1]+'|'+toks[0][0]


def club(value):
    s=re.sub(r'\b(fc|afc|cf)\b','',str(value or ''),flags=re.I)
    n=norm(s)
    return {'swanseacity':'swansea','blackburnrovers':'blackburn',
            'brightonhovealbion':'brighton','estactroyes':'troyes','parissaintgermain':'psg'}.get(n,n)


def fixture(value):
    pair=re.split(r'\s+vs\.?\s+',str(value or ''),flags=re.I)
    return tuple(club(x) for x in pair) if len(pair)==2 else ()


def recover(row):
    data=dict(row)
    if str(data.get('market') or data.get('group_key') or '').lower()!='scorer':return data
    data.setdefault('category','score')
    if not (data.get('player') or data.get('player_name')):
        tid=str(data.get('tip_id') or '')
        suffix='_'+str(data.get('match') or '').replace(' ','_')+'_'+str(data.get('date') or data.get('match_date') or '')[:10]
        if tid.startswith('scorer_') and suffix!='__' and tid.endswith(suffix):
            player=tid[len('scorer_'):-len(suffix)].replace('_',' ').strip()
            if player and len(player)<100:data['player']=player
    if data.get('player_name') and not data.get('player'):data['player']=data['player_name']
    if data.get('player_team') and not data.get('team'):data['team']=data['player_team']
    return data


class ReceiptDedupe:
    def __init__(self,rows):
        self.seen={(fixture(r.get('match')),person(recover(r).get('player'))) for r in rows if r.get('telegram_msg_id')}
    def contains(self,tip):return (fixture(tip.get('match')),person(tip.get('player'))) in self.seen
    def add(self,tip):self.seen.add((fixture(tip.get('match')),person(tip.get('player'))))


def dedupe_history(rows):
    out=[];seen=set()
    for row in sorted(rows,key=lambda r:str(r.get('settled_at') or ''),reverse=True):
        if row.get('market_group')!='scorer':out.append(row);continue
        tip=recover(row.get('tip_payload') or {})
        key=(str(row.get('tip_date') or tip.get('date') or '')[:10],fixture(tip.get('match')),person(tip.get('player')))
        if not all(key):out.append(row);continue
        if key in seen:continue
        seen.add(key);out.append(row)
    return out
