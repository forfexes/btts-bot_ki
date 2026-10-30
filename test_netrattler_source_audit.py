import pytest

def test_github_token_never_sent_to_football_sites(monkeypatch):
    import netrattler_source_hub as h
    monkeypatch.setenv('GITHUB_TOKEN','test-token')
    for url in ['https://m.aiscore.com/','https://www.fotmob.com/','https://api.github.com.evil.invalid/']:
        assert 'Authorization' not in h._headers(url)
    assert h._headers('https://api.github.com/repos/x/y')['Authorization']=='Bearer test-token'


def x1(monkeypatch, group):
    import netrattler_prop_sources as p
    monkeypatch.setattr(p,'_1X_HOSTS',['https://example.invalid'])
    monkeypatch.setattr(p,'_1X_LIST_CACHE',{})
    monkeypatch.setattr(p,'_1X_GAME_CACHE',{})
    monkeypatch.setattr(p,'_snapshot_x1_player_markets',lambda *a:None)
    monkeypatch.setattr(p,'_get_json',lambda url,**kw: {'Value':[{'I':1,'O1':'Arsenal','O2':'Chelsea'}]} if 'Get1x2' in url else {'Value':{'GE':[group]}})
    return p.fetch_1xbet_player_props('Arsenal','Chelsea')


def test_1x_guessed_ids_and_unknown_selection_stay_shadow(monkeypatch):
    assert x1(monkeypatch,{'G':2059,'E':[[{'PN':'Bukayo Saka','P':1.5,'C':1.8,'T':9}]]})==[]
    assert x1(monkeypatch,{'GS':'Player shots','E':[[{'PN':'Bukayo Saka','P':1.5,'C':1.8,'T':9}]]})==[]


def test_labelled_1x_over_can_enter_and_under_cannot(monkeypatch):
    group={'GS':'Player shots','E':[[{'PN':'Bukayo Saka','P':1.5,'C':1.8,'label':'Over'},{'PN':'Bukayo Saka','P':1.5,'C':1.9,'label':'Under'}]]}
    rows=x1(monkeypatch,group)
    assert len(rows)==1 and rows[0]['category']=='shots' and rows[0]['odds']==1.8


def test_fotmob_probe_uses_actual_data_endpoint(monkeypatch):
    import netrattler_keyless_source_probe as p
    called=[]
    monkeypatch.setattr(p,'get',lambda url,*a,**k:(called.append(url) or 200,{'leagues':[{'matches':[{}]}]},'{}'))
    assert p.fotmob()['n']==1 and '/api/data/matches' in called[0]


def test_table_context_is_labelled_and_never_verified_odds():
    from netrattler_public_source_features import extract_labelled_tables
    rows=extract_labelled_tables('<table aria-label="Last 5 league games"><tr><td>1.8</td><td>Shots</td><td>2.1</td></tr></table>')
    assert rows[0]['rows']==[['1.8','Shots','2.1']]
    assert rows[0]['bookmaker_odds_verified'] is False


def test_inventory_reads_legacy_probes_without_executing_them(tmp_path):
    from netrattler_source_audit import inventory
    (tmp_path/'unused_probe.py').write_text('raise RuntimeError("must not execute")\nURL="https://example.com/path?key=not-a-secret"')
    r=inventory(tmp_path)
    assert r['probe_count']==1 and r['modules'][0]['domains']==['example.com']
    assert r['modules'][0]['runtime_import_path'] is False


def test_1x_probe_uses_same_service_api_as_runtime(monkeypatch):
    import netrattler_quote_source_probe as p
    called=[]
    monkeypatch.setattr(p.ps,'_get_json',lambda url,**kwargs:(called.append(url) or {'Value':[{'I':1}]}))
    assert p.probe_1xbet('https://22bet.com')['events']==1
    assert '/service-api/LineFeed/' in called[0]
