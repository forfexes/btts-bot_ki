from copy import deepcopy
from netrattler_1x_verified_props import decode_player_props


def sample(g=775, t=1515, **extra):
    parent = {'O1': 'Home', 'O2': 'Away'}
    event = {'G': g, 'T': t, 'PL': {'N': 'Test Player', 'T': 1, 'I': 42}, 'C': 3.2, **extra}
    sub = {**parent, 'TG': "Players' stats", 'GE': [{'G': g, 'E': [[event]]}]}
    return parent, sub


def test_yellow_yes_real_price():
    row, = decode_player_props(*sample())
    assert (row['category'], row['line'], row['odds'], row['team']) == ('yellow_cards', .5, 3.2, 'Home')


def test_only_verified_over_and_yes():
    for g, t in [(775,1516),(1093,2206),(117,833),(118,834),(11569,16652),(3201,4366),(3217,4417)]:
        assert not decode_player_props(*sample(g,t,P=.5))
    for g,t,cat in [(3201,4365,'yellow_cards'),(3217,4416,'sot'),(3085,4197,'fouls_won'),(3305,4544,'fouls')]:
        assert decode_player_props(*sample(g,t,P=1.5))[0]['category'] == cat
        assert not decode_player_props(*sample(g,t))


def test_invalid_identity_period_lines_and_prices():
    p,s = sample()
    for field,value in [('PN','1st half'),('O1','Other'),('TG','Yellow cards')]:
        bad=deepcopy(s); bad[field]=value
        assert not decode_player_props(p,bad)
    for value in [float('nan'),float('inf'),1,0]:
        assert not decode_player_props(*sample(C=value))
    for value in [True,0,-.5,1,float('nan')]:
        assert not decode_player_props(*sample(3201,4365,P=value))
    bad=deepcopy(s);bad['GE'][0]['E'][0][0]['PL']['T']=0
    assert not decode_player_props(p,bad)


def test_collector_fetches_player_event_id_and_reuses_cache(monkeypatch):
    import time
    import netrattler_prop_sources as sources
    p,s=sample();p.update(I=10,S=time.time()+3600,SG=[{'I':11,'CI':999,'TG':"Players' stats",'PN':''}])
    monkeypatch.setattr(sources,'_1X_HOSTS',['https://22bet.com'])
    monkeypatch.setattr(sources,'_1X_LIST_CACHE',{'https://22bet.com':{'Value':[p]}})
    monkeypatch.setattr(sources,'_1X_GAME_CACHE',{('https://22bet.com','10'):{'Value':p}})
    monkeypatch.setattr(sources,'_snapshot_x1_player_markets',lambda *a:None)
    calls=[]
    def get(url,params):
        calls.append(params['id']);return {'Value':s}
    monkeypatch.setattr(sources,'_get_json',get)
    monkeypatch.setattr(sources,'_valid_player_candidate',lambda *a:True)
    assert sources.fetch_1xbet_player_props('Home','Away')[0]['category']=='yellow_cards'
    assert sources.fetch_1xbet_player_props('Home','Away')[0]['odds']==3.2
    assert calls==[11]
