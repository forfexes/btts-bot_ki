"""Uploaded season aggregates, isolated from match history, model features and settlement."""
import csv
import math
import unicodedata
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name('data') / 'player_season_2026_2027.csv'
SEASON = '2026/27'
SNAPSHOT = '2026-10-31'
FIELDS = ['Player','Squad','Comp','Pos','MP','Starts','Min','Gls','Ast','Sh','SoT','Fld','Fls','CrdY','CrdR','TklW','Int','Saves']
METRICS = {'shots':('Sh','Schüsse'), 'sot':('SoT','aufs Tor'), 'score':('Gls','Tore'),
           'fouls':('Fls','Fouls'), 'fouls_won':('Fld','Fouls gezogen'),
           'yellow_cards':('CrdY','Gelbe'), 'saves':('Saves','Paraden')}


def norm(value):
    text=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]','',text)


def number(value):
    try:
        v=float(str(value).replace(',',''))
        return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError): return None


@lru_cache(maxsize=1)
def load_profiles():
    index={}
    try:
        with DATA.open(encoding='utf-8',newline='') as f:
            for row in csv.DictReader(f):
                key=(norm(row.get('Player')),norm(row.get('Squad')))
                if not all(key):continue
                index.setdefault(key,[]).append(row)
    except OSError:return {}
    return index


def profile(player,team,match_date=None):
    # No guessed/fuzzy joins and no backtest leakage before the uploaded snapshot.
    if not player or not team or (match_date and str(match_date)[:10]<SNAPSHOT):return None
    rows=load_profiles().get((norm(player),norm(team)),[])
    if len(rows)!=1:return None
    return {**rows[0],'season':SEASON,'snapshot_date':SNAPSHOT,'source':'user_season_csv',
            'grain':'season_aggregate'}


def summary(player,team,category,match_date=None):
    row=profile(player,team,match_date)
    if not row:return ''
    key,label=METRICS.get(category,('',''))
    value=number(row.get(key));minutes=number(row.get('Min'));games=number(row.get('MP'))
    if not key or value is None or not minutes or games is None:return ''
    return f'Saison {SEASON} · {games:g} Spiele · {value*90/minutes:.2f} {label}/90'


def compact_import(light,full,destination=DATA):
    """Cross-check shared columns; keep one compact row, never append to game logs."""
    with open(light,encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    with open(full,encoding='utf-8',newline='') as f:other=list(csv.DictReader(f))
    key=lambda r:(r['Player'],r['Squad'],r['Comp'])
    lookup={key(r):r for r in other}
    if len(lookup)!=len(other) or len({key(r) for r in rows})!=len(rows):raise ValueError('Duplicate season identity')
    for row in rows:
        if key(row) not in lookup:raise ValueError('Source identity mismatch')
        for field in FIELDS:
            if row.get(field,'')!=lookup[key(row)].get(field,''):raise ValueError('Source metric mismatch: '+field)
        for field in FIELDS[4:]:
            if row.get(field,'') and number(row[field]) is None:raise ValueError('Invalid season metric')
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        w.writerows({k:r.get(k,'') for k in FIELDS} for r in rows)
    return len(rows)


if __name__=='__main__':
    import sys
    print(compact_import(*sys.argv[1:3]))
