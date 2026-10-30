from datetime import date, datetime, timedelta, timezone
import pytest
from netrattler_nuxt_data import decode_nuxt
from netrattler_aiscore_context import extract_context, team_form


def test_literal_decoder_resolves_data_without_javascript_execution():
    s='window.__NUXT__=(function(a,b,c){b.id=a;c[0]={name:"Arsenal"};return {state:{x:b,rows:c,n:.5}}}(3,{},[]));'
    assert decode_nuxt(s)=={'state':{'x':{'id':3},'rows':[{'name':'Arsenal'}],'n':.5}}

@pytest.mark.parametrize('source',[
 'window.__NUXT__=(function(a){return fetch("https://example.com")}(0));',
 'window.__NUXT__=(function(a){a.__proto__={};return a}({}));',
 'window.__NUXT__=(function(a){return {x:process.env}}(0));',
 'window.__NUXT__=(function(a){return {x:a}}(Array(10001)));',
 'window.__NUXT__=(function(a){return a}());',
])
def test_decoder_rejects_code_and_unsafe_shapes(source):
    with pytest.raises(ValueError):decode_nuxt(source)


def context_payload():
    games=[]
    for i in range(20):
        day=date.today()-timedelta(days=i+1)
        games.append({'id':str(i),'statusId':8,'matchTime':datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc).timestamp(),
                      'homeTeam':{'id':'a'},'awayTeam':{'id':'b'},'homeScores':[2,1],'awayScores':[1,0]})
    return {'state':{'seoH2h':{'h2hDetailData':{'teams':[{'id':'a','name':'Arsenal'},{'id':'b','name':'Chelsea'}],
                    'home':games,'away':games,'h2h':games}}}}


def test_recent_form_dedupes_limits_and_excludes_future():
    p=context_payload();c=extract_context(p,'Arsenal','Chelsea')
    assert len(c['recent_results'])==20
    f=team_form(c,'Arsenal');assert f['games']==15 and f['btts_pct']==100 and f['over25_pct']==100
    assert team_form(c,'Other FC')=={}
    assert team_form({'recent_results':c['recent_results'][:4]},'Arsenal')=={}
    cutoff=date.today()-timedelta(days=18)
    assert len(extract_context(p,'Arsenal','Chelsea',cutoff)['recent_results'])==2
    p['state']['seoH2h']['h2hDetailData']['home'][0]['statusId']=1
    assert len(extract_context(p,'Arsenal','Chelsea')['recent_results'])==19


def test_real_sections_not_localized_menu_words():
    from netrattler_aiscore import _json_scripts
    html='<script>window.__NUXT__=(function(a){return {state:{languageJsonMap:{x:"lineups"},seoH2h:{home:a},"football/detail":{lineups:{}}}}}("Arsenal"));</script>'
    p=_json_scripts(html)[0]
    assert 'languageJsonMap' not in p['state']
    assert p['state']['seoH2h']['home']=='Arsenal'
    assert extract_context(p,'Arsenal','Chelsea')['lineups']=={}


def test_runtime_form_is_cached_and_has_call_budget(monkeypatch):
    import netrattler_aiscore_context as c
    import netrattler_aiscore as a
    calls=[]
    monkeypatch.setattr(c,'_CACHE',{});monkeypatch.setattr(c,'_CALLS',0);monkeypatch.setattr(c,'_STARTED',None)
    monkeypatch.setenv('NETRATTLER_AISCORE_FORM_MAX_MATCHES','1')
    monkeypatch.setattr(a,'_requests_html',lambda url:(calls.append(url) or 'html',200))
    monkeypatch.setattr(a,'_json_scripts',lambda html:[context_payload()])
    h,w=c.recent_form_for_match('Arsenal','Chelsea')
    assert h['games']==15 and w['games']==15
    assert c.recent_form_for_match('Arsenal','Chelsea')==(h,w) and len(calls)==1
    assert c.recent_form_for_match('Other FC','Another FC')==({}, {}) and len(calls)==1

@pytest.mark.parametrize('label',['First Half Match Result 1X2','Second Half Both Teams To Score','Total Corners by Arsenal','Arsenal Total Corners','Total Goals by Arsenal'])
def test_ambiguous_aiscore_markets_not_full_match(label):
    from netrattler_aiscore import _classify_market
    assert _classify_market(label,'Over',2.5,'Arsenal','Chelsea') is None


def test_player_total_is_never_a_match_total():
    from netrattler_aiscore import _classify_market
    r=_classify_market('Player Total Shots','Over',2.5,'Arsenal','Chelsea')
    assert r[0].startswith('player_prop:')
