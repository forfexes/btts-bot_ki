from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
import netrattler_apif_settlement as api
import netrattler_settlement_v16_final as settlement


def fixture(day,status='FT',fid=42,home='Alpha',away='Beta'):
    return {'fixture':{'id':fid,'date':day+'T12:00:00Z','status':{'short':status}},
            'teams':{'home':{'id':1,'name':home},'away':{'id':2,'name':away}},
            'league':{'id':39,'name':'League'},'goals':{'home':0,'away':1},
            'score':{'halftime':{'home':0,'away':0}}}


def response(rows):
    r=Mock(ok=True);r.json.return_value={'errors':[],'response':rows};return r


def run(day,fixtures,players=None,stats=None,max_calls='150'):
    tip={'match':'Cross-Match','match_date':day,'legs':[{'match':'Alpha vs Beta',
         'player':'Player A','category':'sot','line':.5,'match_date':day}]}
    payloads=[response(fixtures),response(players or []),response(stats or [])]
    with patch.dict('os.environ',{'API_FOOTBALL_KEYS':'test','SETTLEMENT_APIF_MAX_CALLS':max_calls,'SETTLEMENT_APIF_ADJACENT_DAYS':'0'}), \
         patch.object(api.requests,'get',side_effect=payloads) as get:
        rows,people=api.collect([tip],settlement.match_parts,settlement.row_date,
                               lambda a,b:a==b,lambda s:None)
    return rows,people,get


def test_only_exact_completed_fixture_and_real_zero_are_used():
    day=(datetime.now(timezone.utc).date()-timedelta(days=2)).isoformat()
    players=[{'team':{'id':1},'players':[{'player':{'id':7,'name':'Player A'},
               'statistics':[{'games':{'minutes':90},'shots':{'total':2,'on':0}}]}]}]
    stats=[{'team':{'id':t},'statistics':[{'type':'Corner Kicks','value':n}]} for t,n in [(1,0),(2,5)]]
    rows,people,get=run(day,[fixture(day,'NS',1),fixture(day,'FT',2,'Wrong','Pair'),fixture(day)],players,stats)
    assert len(rows)==len(people)==1 and get.call_count==3
    assert rows[0]['home_corners']==0 and rows[0]['home_score_ht']==0
    assert people[0]['sot']==0 and people[0]['fouls_won'] is None
    assert get.call_args_list[1].kwargs['params']=={'fixture':42}
    leg={'match':'Alpha vs Beta','match_date':day,'player':'Player A','category':'sot','line':.5,'side':'over'}
    assert settlement.settle_player_market(leg,people,rows[0])[0]=='loss'
    leg['category']='fouls_won'
    assert settlement.settle_player_market(leg,people,rows[0])[0]=='pending'


def test_lookback_and_call_cap_are_bounded():
    day=(datetime.now(timezone.utc).date()-timedelta(days=2)).isoformat()
    rows,people,get=run(day,[fixture(day)],max_calls='1')
    assert len(rows)==1 and people==[] and get.call_count==1
    old=(datetime.now(timezone.utc).date()-timedelta(days=31)).isoformat()
    rows,people,get=run(old,[fixture(old)])
    assert rows==people==[] and not get.called


def test_provider_errors_do_not_create_evidence():
    day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
    with patch.dict('os.environ',{'API_FOOTBALL_KEYS':'test'}),patch.object(api.requests,'get') as get:
        get.return_value=Mock(ok=True);get.return_value.json.return_value={'errors':{'access':'suspended'},'response':[]}
        rows,people=api.collect([{'match':'Alpha vs Beta','match_date':day}],settlement.match_parts,
            settlement.row_date,lambda a,b:a==b,lambda s:None)
    assert rows==people==[]


def test_adjacent_utc_day_is_fetched_without_relabeling_or_duplicate_details():
    day=(datetime.now(timezone.utc).date()-timedelta(days=2)).isoformat()
    actual=(datetime.fromisoformat(day).date()+timedelta(days=1)).isoformat()
    tip={'match':'Alpha vs Beta','match_date':day}
    requests_seen=[]
    def get(url,params,**kw):
        requests_seen.append((url,params))
        if url.endswith('/fixtures') and params['date']==actual:return response([fixture(actual)])
        return response([])
    with patch.dict('os.environ',{'API_FOOTBALL_KEYS':'test','SETTLEMENT_APIF_ADJACENT_DAYS':'1'}), \
         patch.object(api.requests,'get',side_effect=get):
        rows,_=api.collect([tip],settlement.match_parts,settlement.row_date,lambda a,b:a==b,lambda s:None)
    assert len(rows)==1 and rows[0]['match_date']==actual
    assert sum(url.endswith('/fixtures/players') for url,params in requests_seen)==1
