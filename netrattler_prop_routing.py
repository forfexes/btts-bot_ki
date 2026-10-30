"""Evidence-based ordering for observed player-prop collectors; no win-rate claims."""
from collections import Counter
import math
import threading

ALLOWED_CATEGORIES=frozenset({'shots','sot','fouls','fouls_won','tackles_committed','tackles_received',
                             'yellow_cards','score','assist','passes','saves','offsides'})
CONTACT=frozenset({'fouls','fouls_won','tackles_committed','tackles_received'})

# Eligibility describes implemented data roles, not a guarantee of availability.
SOURCE_ROLES={
 'oddspapi':'configured_team_quotes','5dollar':'configured_team_statistics_and_quotes',
 'fieldfunded':'configured_team_quotes','sockodds':'configured_team_quotes','odds_api_net':'configured_team_quotes',
 'bwin':'team_quotes','matchbook':'team_quotes','smarkets':'team_quotes',
 'altenar':'corroborated_team_quotes_only','gamdom':'team_quote_research',
 'openligadb':'results','openfootball':'results','football_data_co_uk':'team_history_and_corners',
 'thesportsdb':'availability_limited_results','footballdata_io':'configured_match_statistics',
 'sportapiai':'configured_player_statistics','bigballs':'configured_statistics','statsbomb':'historical_events',
 'soccerdata':'wrapper_not_independent_source','oddsportal':'historical_odds_research',
 'betexplorer':'research_context','livescore':'public_results_research',
 'pinnacle':'observed_quotes','kambi':'observed_quotes','the_odds_api':'configured_observed_quotes',
 'sportsgameodds':'configured_observed_quotes','1xbet':'explicit_labelled_quotes_only',
 'oddspedia':'explicit_labelled_quotes_only','footymetrics':'explicit_labelled_quotes_only',
 'fotmob':'player_match_statistics','espn':'player_match_statistics','fpl':'player_match_statistics',
 'fplci':'player_match_statistics','api_football':'configured_player_statistics',
 'sofascore':'availability_limited_statistics','fbref':'availability_limited_statistics',
 'understat':'historical_xg_context','aiscore':'team_form_context',
 'flashscore':'fixture_context','besoccer':'unverified_context',
 'onemillionpredictions':'labelled_external_context','betmines':'unverified_context',
 'todaymatchprediction':'fixture_and_historical_context','afootballreport':'labelled_external_context',
 'datamb':'research_context','transfermarkt':'identity_and_candidates_only',
}


def validate_prop(row,home,away):
    """Validate normalized records before coverage or best-price selection."""
    from netrattler_identity_hub import normalize_team_name
    if not isinstance(row,dict):return None,'invalid_shape'
    cat=row.get('category')
    if cat not in ALLOWED_CATEGORIES:return None,'unknown_category'
    player=str(row.get('player') or '').strip()
    if not player:return None,'missing_player'
    if row.get('_no_real_odds') or row.get('observed') is False:return None,'not_observed'
    label=' '.join(str(row.get(k) or '') for k in ('side','selection','outcome')).strip().lower()
    if label and ('under' in label or label=='no'):return None,'wrong_selection'
    try:
        if isinstance(row.get('odds'),bool) or isinstance(row.get('line'),bool):return None,'invalid_number'
        odds=float(row['odds']);line=float(row['line'])
        if not math.isfinite(odds) or not math.isfinite(line) or not 1.20<odds<=100 or not 0<=line<=500:
            return None,'invalid_number'
    except (ValueError,TypeError,KeyError):return None,'invalid_number'
    # Do not allow a provider to attach an explicitly different fixture.
    h=row.get('home') or row.get('home_team');a=row.get('away') or row.get('away_team')
    if h and normalize_team_name(h)!=normalize_team_name(home):return None,'wrong_fixture'
    if a and normalize_team_name(a)!=normalize_team_name(away):return None,'wrong_fixture'
    if row.get('match') and str(row['match']).strip()!=f'{home} vs {away}':return None,'wrong_fixture'
    out=dict(row);out.update(odds=odds,line=line,category=cat,match=f'{home} vs {away}')
    return out,''


class SourceOrder:
    """Per-run measurements only. No synthetic trust score or extra DB history."""
    def __init__(self):
        self._rows={};self._lock=threading.RLock()
    def record(self,source,accepted,raw_count,elapsed_ms,error='',rejected=None):
        with self._lock:
            r=self._rows.setdefault(source,{'source':source,'calls':0,'raw_rows':0,'accepted_rows':0,'elapsed_ms':0,
                                            'categories':set(),'rejections':Counter(),'errors':0})
            unique={(str(x.get('player') or '').lower(),x.get('match'),x['category'],x['line']) for x in accepted}
            r['calls']+=1;r['raw_rows']+=raw_count;r['accepted_rows']+=len(unique)
            r['elapsed_ms']+=elapsed_ms;r['categories'].update(x['category'] for x in accepted)
            r['rejections'].update(rejected or {});r['errors']+=bool(error)
    def ordered(self,sources,prefix=''):
        with self._lock:
            def key(item):
                i,name=item;r=self._rows.get(prefix+name)
                if r is None:return (1,0,0,0,0,i)
                if not r['accepted_rows']:return (2,0,0,0,r['elapsed_ms']/r['calls'],i)
                return (0,-len(r['categories']&CONTACT),-len(r['categories']),sum(r['rejections'].values())/max(1,r['raw_rows']),r['elapsed_ms']/r['calls'],i)
            return [name for _,name in sorted(enumerate(sources),key=key)]
    def report(self):
        with self._lock:
            out=[]
            for source in self.ordered(list(self._rows)):
                r=self._rows[source]
                out.append({**{k:v for k,v in r.items() if k not in {'categories','rejections'}},
                            'categories':sorted(r['categories']),'rejections':dict(r['rejections']),
                            'status':'accepted' if r['accepted_rows'] else 'error' if r['errors'] else 'empty',
                            'mean_ms':round(r['elapsed_ms']/r['calls'],1),
                            'acceptance_rate':round(r['accepted_rows']/max(1,r['raw_rows']),4)})
            return out


def labelled_over_line(side,line,category,market):
    """Aggregator direction and line must be observed, never default to Over .5."""
    import re
    text=str(side or '').strip().lower()
    label=str(market or '').lower()
    if category=='score':
        if re.search(r'\b(first|last|next|half|period|second|third)\b|2\+|3\+',label):return None
        if re.search(r'any\s*time|to score(?: a goal)?\b',label) and text not in {'under','no'}:return .5
        return None
    if not re.match(r'^over(?:\s|$)|^yes$',text):return None
    if line in (None,''):
        m=re.search(r'\bover\s+(\d+(?:\.\d+)?)',text)
        if not m:return None
        line=m.group(1)
    try:
        if isinstance(line,bool):return None
        value=float(line)
        return value if math.isfinite(value) and 0<=value<=500 else None
    except (TypeError,ValueError):return None
