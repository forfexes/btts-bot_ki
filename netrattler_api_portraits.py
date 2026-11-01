"""Resolve abbreviated scorer names to verified API player ids from existing history."""
import os
import requests
from netrattler_scorer_identity import norm,club
_CALLS=0


def portrait(name,team):
    global _CALLS
    if not name or not team or _CALLS>=20:return ''
    base=(os.getenv('SUPABASE_URL') or '').rstrip('/')
    key=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
    if not base or not key:return ''
    words=str(name).split();last=words[-1]
    if len(norm(last))<4:return ''
    _CALLS+=1
    try:
        r=requests.get(base+'/rest/v1/fplci_player_match',headers={'apikey':key,'Authorization':'Bearer '+key},
            params={'select':'player_id,player_name,team','source':'eq.apif','player_name':'ilike.*'+last+'*',
                    'order':'match_date.desc','limit':'100'},timeout=5)
        if not r.ok:return ''
        ids=set()
        for row in r.json():
            candidate=str(row.get('player_name') or '');parts=candidate.split()
            exact=norm(name)==norm(candidate)
            abbreviated=(len(words)>1 and len(norm(words[0]))==1 and parts
                         and norm(words[-1])==norm(parts[-1]) and norm(words[0])==norm(parts[0])[:1])
            if club(team)==club(row.get('team')) and (exact or abbreviated) and str(row.get('player_id') or '').isdigit():
                ids.add(str(row['player_id']))
        if len(ids)==1:return 'https://media.api-sports.io/football/players/'+next(iter(ids))+'.png'
    except (requests.RequestException,ValueError,TypeError):pass
    return ''
