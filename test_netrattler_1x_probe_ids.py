import netrattler_1x_props_probe as probe


def test_probe_uses_event_id_and_validates_fixture(monkeypatch):
    monkeypatch.setattr(probe,'HOSTS',['https://example.invalid'])
    calls=[]
    fixture={'I':10,'O1':'Porto','O2':'Napoli','L':'Premier League','S':100}
    def get(url,params):
        calls.append(params)
        if 'Get1x2' in url:
            return 200,{'Value':[fixture]}
        if params['id']==10:
            return 200,{'Value':{**fixture,'SG':[{'I':11,'CI':999,'TG':"Players' stats"}]}}
        assert params['id']==11
        assert params['GroupEvents']=='true'
        return 200,{'Value':{'O1':'Wrong team','O2':'Napoli','GE':[]}}
    monkeypatch.setattr(probe,'_get',get)
    rows,snapshots=probe.run()
    assert calls[-1]['id']==11
    assert not snapshots
    assert rows[0]['fixtures'][0]['player_subgames']==[]
