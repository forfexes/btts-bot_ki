import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
from netrattler_match_form import team_form

norm=lambda value:str(value or '').lower().replace(' ','')

def rows():
    return [dict(Date=f'2026-10-{d:02}',HomeTeam='Home',AwayTeam='Away',FTHG=3,FTAG=1,HTHG=1,HTAG=1)
            for d in range(1,11)]


def test_observed_form_and_home_away_orientation():
    h=team_form(rows(),'Home',norm,'2026-10-31')
    a=team_form(rows(),'Away',norm,'2026-10-31')
    assert h['games']==10 and h['avg_scored']==3 and h['avg_conceded']==1
    assert h['btts_ht_rate']==1 and h['o15ht_rate']==1 and h['form_pts']==1
    assert a['avg_scored']==1 and a['avg_conceded']==3 and a['form_pts']==0


def test_missing_halves_are_unknown_not_scoreless():
    data=rows()
    for row in data[:9]:row['HTHG']=None;row['HTAG']=None
    result=team_form(data,'Home',norm,'2026-10-31')
    assert result['ht_games']==1 and result['btts_ht_rate']==1
    for row in data:row['HTHG']=None
    assert team_form(data,'Home',norm,'2026-10-31')['ht_games']==0


def test_cutoff_duplicate_and_short_prefix_safety():
    data=rows()+[rows()[0],dict(rows()[0],Date='2026-11-01',FTHG=20)]
    assert team_form(data,'Home',norm,'2026-10-31')['games']==10
    assert team_form(data,'Home United',norm,'2026-10-31') is None
    assert team_form(data,'Home',norm,'2026-10-05') is None
    assert team_form(list(reversed(data)),'Home',norm,'2026-10-31')==team_form(data,'Home',norm,'2026-10-31')


def test_real_ml_path_receives_measured_form_features():
    tree=ast.parse(Path('btts_bot.py').read_text())
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='get_ml_prediction')
    captured=[]
    model=SimpleNamespace(predict_proba=lambda x:captured.append(x.tolist()) or [[0.5,0.5]])
    cols=['btts_rate_home','avg_scored_home','btts_ht_rate_home','form_pts_home']
    ctx=dict(_ml_load_models=lambda:None,_ML_MODELS={'over15_ht_model':model},
        _ML_MODEL_FEATURES={'over15_ht_model':cols},_ML_FEATURE_COLS=cols,
        _build_elo_ratings=lambda league:{},normalize_team_name=norm,ELO_RATINGS_CACHE={},
        _ml_get_team_form=lambda team:pytest.fail('measured history was ignored'),
        _fd_co_uk_load_csv=lambda league:rows(),get_national_team_btts_stats=lambda team:{},
        get_fd_co_uk_team_stats=lambda *args:{},_ML_H2H_HISTORY={},
        get_pinnacle_match_odds=lambda *args:{},log=lambda *args:None)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-ml>','exec'),ctx)
    output=ctx['get_ml_prediction']('Home','Away','League')
    assert output['over15_ht_pct']==50
    assert captured[0][0]==[1,3,1,1]
