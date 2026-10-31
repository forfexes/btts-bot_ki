import ast
import math
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from netrattler_scorer_qualification import qualifies


@pytest.fixture(autouse=True)
def policy():
    with patch.dict(os.environ, {'NETRATTLER_SCORER_MIN_PROB':'0.26',
                                'NETRATTLER_SCORER_MIN_ODDS':'1.55',
                                'NETRATTLER_SCORER_MIN_EDGE':'0.005'}):
        yield


def test_existing_configuration_is_honoured():
    assert qualifies(4.0, 26, 'kambi_ub')[0]
    assert not qualifies(4.0, 25, 'kambi_ub')[0]
    assert not qualifies(3.9, 26, 'kambi_ub')[0]  # insufficient configured edge
    with patch.dict(os.environ, {'NETRATTLER_SCORER_MIN_PROB':'35'}):
        assert not qualifies(4.0, 26, 'kambi_ub')[0]


def test_no_synthetic_or_implausible_quotes():
    for odds, probability, source in [(30,38,'pinnacle'), (7.5,42,'pinnacle'),
        (4,26,'model'),(4,26,''),(float('nan'),30,'kambi_ub')]:
        assert not qualifies(odds,probability,source)[0]


def analyze(scorers, props):
    tree=ast.parse(Path('btts_bot.py').read_text())
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='analyze_scorer_tips')
    ctx={'normalize_team_name':lambda s: s.lower().replace(' ',''), 'requests':None,'os':os}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<scorer>','exec'),ctx)
    adjust=SimpleNamespace(load=lambda *a,**k:None,adjusted_prob_pct=lambda n,p:p)
    with patch.dict('sys.modules', {'netrattler_finishing_adjust':adjust}):
        return ctx['analyze_scorer_tips']({'home':'Home','away':'Away','home_id':1,'away_id':2},
                                         'League',scorers,props)


def test_real_analysis_allows_configured_26_percent_candidate():
    scorers=[{'name':'Player Alpha','team':'Home','team_id':1,'goals_per_game':0.31}]
    props=[{'player':'Player Alpha','market':'Anytime Goalscorer','odds':4.0,
            'home':'Home','away':'Away','source':'kambi_ub'}]
    tips=analyze(scorers,props)
    assert len(tips)==1
    assert tips[0]['probability']==27


def test_invalid_top_three_do_not_crowd_out_valid_scorer():
    names=['Player Alpha','Player Bravo','Player Charlie','Player Delta']
    scorers=[{'name':n,'team':'Home','team_id':1,'goals_per_game':0.6} for n in names]
    props=[{'player':n,'market':'Anytime Goalscorer','odds':9 if i<3 else 3,
            'home':'Home','away':'Away','source':'kambi_ub'} for i,n in enumerate(names)]
    tips=analyze(scorers,props)
    assert [t['player'] for t in tips]==['Player Delta']
