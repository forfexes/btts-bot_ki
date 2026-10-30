import math
import pytest
from netrattler_prop_routing import SourceOrder,validate_prop


def prop(**kw):
    row={'player':'Bukayo Saka','match':'Arsenal vs Chelsea','category':'shots','market':'Player shots','line':1.5,'odds':1.8}
    row.update(kw);return row

@pytest.mark.parametrize('extra',[{'odds':float('nan')},{'odds':float('inf')},{'line':None},{'line':float('nan')},
 {'line':True},{'odds':True},{'category':'first_scorer'},{'_no_real_odds':True},{'selection':'Under'},
 {'match':'Chelsea vs Arsenal'},{'home':'Manchester City'}])
def test_invalid_props_cannot_inflate_source_rating(extra):
    assert validate_prop(prop(**extra),'Arsenal','Chelsea')[0] is None


def test_explicit_zero_line_not_silently_changed():
    row,error=validate_prop(prop(line=0),'Arsenal','Chelsea')
    assert row['line']==0 and not error


def test_contact_depth_and_observed_latency_determine_order():
    order=SourceOrder()
    order.record('empty',[],0,10)
    order.record('shots',[prop()]*100,100,20)
    order.record('contact',[prop(category='fouls'),prop(category='tackles_committed')],2,40)
    assert order.ordered(['empty','unknown','shots','contact'])==['contact','shots','unknown','empty']
    r=order.report();assert r[0]['source']=='contact' and r[-1]['status']=='empty'


def test_team_pair_matching_never_uses_common_prefix_or_reversed_sides():
    import netrattler_prop_sources as p
    assert not p._team_pair_match('Manchester City','Chelsea','Manchester United','Chelsea')
    assert not p._team_pair_match('Chelsea','Arsenal','Arsenal','Chelsea')
    assert not p._team_pair_match('Arsenal U21','Chelsea','Arsenal','Chelsea')
    assert p._team_pair_match('Arsenal','Chelsea','Arsenal','Chelsea')
    assert not p._event_pair_match({'name':'Manchester City - Chelsea'},'Manchester United','Chelsea')


def test_collector_reports_unique_selected_rows_and_rejects_missing_line(monkeypatch):
    import netrattler_prop_sources as p
    monkeypatch.delenv('SUPABASE_URL',raising=False);monkeypatch.delenv('SUPABASE_KEY',raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY',raising=False)
    monkeypatch.setenv('NETRATTLER_PROP_WORKERS','1')
    monkeypatch.setattr(p,'_KAMBI_BRANDS',['a','b'])
    monkeypatch.setattr(p,'fetch_kambi_player_props',lambda h,a,brand:[prop(odds=1.8 if brand=='a' else 1.9),prop(player='Cole Palmer',line=None)])
    monkeypatch.setattr(p,'fetch_1xbet_player_props',lambda *a:[])
    monkeypatch.setattr(p,'fetch_oddspedia_player_props',lambda *a:[])
    monkeypatch.setattr(p,'fetch_footymetrics_player_props',lambda *a:[])
    monkeypatch.setattr(p,'X1_SNAPSHOT',[])
    logs=[];rows=p.collect_extra_player_props([{'home':'Arsenal','away':'Chelsea','league':'Premier League'}],log=logs.append)
    assert len(rows)==1 and rows[0]['odds']==1.9 and rows[0]['source']=='kambi_b'
    report=p.collect_extra_player_props.last_source_report
    assert sum(x['accepted_rows'] for x in report)==2
    assert sum(x['rejections'].get('invalid_number',0) for x in report)==2
    assert any('unique=1' in l for l in logs)


def test_aggregator_missing_side_or_line_is_never_defaulted():
    from netrattler_prop_routing import labelled_over_line as line
    assert line('',None,'shots','Player shots') is None
    assert line('Under',1.5,'shots','Player shots') is None
    assert line('Over',None,'shots','Player shots') is None
    assert line('Over 1.5',None,'shots','Player shots')==1.5
    assert line('Over',0,'shots','Player shots')==0
    assert line('Bukayo Saka',None,'score','Anytime Goalscorer')==.5
    assert line('Bukayo Saka',None,'score','First Goalscorer') is None


def test_footymetrics_accepts_only_explicit_side_and_line(monkeypatch):
    import netrattler_prop_sources as p
    monkeypatch.setattr(p,'_FOOTYMETRICS_HOSTS',['https://example.invalid'])
    monkeypatch.setattr(p,'_get_json',lambda *a,**k:{'props':[
        {'player':'Bukayo Saka','market':'Player shots','line':1.5,'side':'Over','odds':1.8},
        {'player':'Cole Palmer','market':'Player shots','line':1.5,'odds':1.9},
        {'player':'Cole Palmer','market':'Player shots','side':'Over','odds':1.9}]})
    r=p.fetch_footymetrics_player_props('Arsenal','Chelsea')
    assert len(r)==1 and r[0]['line']==1.5


def test_runtime_and_team_quote_layers_reject_same_prefix_wrong_team(monkeypatch):
    import netrattler_prop_sources as p
    import netrattler_runtime_patch as runtime
    import netrattler_kambi_team_odds as team
    monkeypatch.setattr(p,'_KAMBI_HOSTS',['https://example.invalid'])
    monkeypatch.setattr(p,'_KAMBI_LIST_CACHE',{})
    monkeypatch.setattr(p,'_get_json',lambda *a,**k:{'events':[{'event':{'id':1,'homeName':'Manchester City','awayName':'Chelsea'}}]})
    assert runtime.fetch_kambi_player_props_rich('Manchester United','Chelsea','ub')==[]
    assert team._offer_for_match('Manchester United','Chelsea','ub') is None
