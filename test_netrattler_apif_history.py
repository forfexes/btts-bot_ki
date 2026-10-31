from datetime import date
import os
from unittest.mock import Mock, patch
import pytest
from netrattler_apif_history import number, completed, player_rows, corner_row, Importer

FX = {'fixture':{'id':1,'date':'2026-10-20T18:00:00Z','status':{'short':'FT'}},
      'league':{'id':39,'name':'Premier League'}, 'goals':{'home':2,'away':1},
      'teams':{'home':{'id':10,'name':'Home'},'away':{'id':20,'name':'Away'}}}


def test_missing_is_not_zero():
    assert number(None) is None
    assert number(True) is None
    assert number('nan') is None
    assert number('inf') is None
    assert number(-1) is None
    assert number(0) == 0
    rows = player_rows([{'team':{'id':10},'players':[{'player':{'id':7,'name':'Player'},
        'statistics':[{'games':{'minutes':90},'shots':{'total':0}}]}]}], FX)
    assert rows[0]['shots'] == 0
    assert rows[0]['shots_on'] is None
    assert rows[0]['fouls_drawn'] is None
    assert rows[0]['opponent'] == 'Away'


def test_unknown_team_or_no_appearance_excluded():
    assert player_rows([{'team':{'id':99},'players':[]}], FX) == []
    assert player_rows([{'team':{'id':10},'players':[{'player':{'id':1,'name':'P'},
        'statistics':[{'games':{'minutes':0}}]}]}], FX) == []


def test_corner_pair_requires_both_observed_values():
    def stats(a,b):
        return [{'team':{'id':10},'statistics':[{'type':'Corner Kicks','value':a}]},
                {'team':{'id':20},'statistics':[{'type':'Corner Kicks','value':b}]}]
    assert corner_row(stats(0,4), FX)['home_corners'] == 0
    assert corner_row(stats(None,4), FX) is None
    assert corner_row(stats(4,31), FX) is None


def test_future_and_today_not_used_as_history():
    assert not completed(FX, '2026-10-20')
    assert completed(FX, '2026-10-21')


def test_capacity_blocks_before_write():
    imp = Importer.__new__(Importer)
    imp.sb='https://example.invalid'; imp.h={}; imp.ceiling=430
    response = Mock(); response.json.return_value={'mb':430}
    with patch('netrattler_apif_history.requests.post', return_value=response) as post:
        with pytest.raises(RuntimeError, match='capacity'):
            imp.save('table', [{'x':1}], 'x')
        assert post.call_count == 1  # only the size RPC, never an INSERT


def test_same_corner_match_from_two_sources_is_one_game():
    from netrattler_corner_history import team_corner_profile
    row={'Date':'2026-10-20','HomeTeam':'Home','AwayTeam':'Away','HC':0,'AC':4,'FTHG':2,'FTAG':1}
    result=team_corner_profile([dict(row,_source='api-football'),row], 'Home', '2026-10-21', min_games=1)
    assert result['games'] == 1
    assert result['avg_corners_for'] == 0


def test_full_player_batch_budget_stops_player_calls_but_keeps_corners():
    from copy import deepcopy
    imp=Importer.__new__(Importer)
    imp.calls=0; imp.max_calls=400; imp.initial_mb=425
    history=[]
    for fid in range(1,4):
        fx=deepcopy(FX); fx['fixture']['id']=fid; history.append(fx)
    upcoming=deepcopy(FX); upcoming['fixture']['status']['short']='NS'; upcoming['league']['season']=2026
    def api(path, params):
        imp.calls += 1
        if path == '/fixtures':
            return history if 'team' in params else [upcoming]
        return []
    imp.api=Mock(side_effect=api)
    imp.rest=Mock(return_value=[])
    imp.save=Mock(side_effect=lambda table,rows,conflict: len(rows))
    imp.capacity=Mock(return_value=425)
    with patch.dict('os.environ', {'APIF_HISTORY_MAX_PLAYER_ROWS':'31'}), \
         patch('netrattler_apif_history.player_rows', return_value=[{} for _ in range(30)]):
        result=imp.run()
    assert result['player_calls'] == 2
    assert result['corner_calls'] == 3
    assert result['inserted_players'] == 30


def test_corner_store_does_not_modify_elo_or_ml_csv_loader():
    from types import SimpleNamespace
    import netrattler_api_corner_store as store
    original=Mock(return_value=[{'HomeTeam':'CSV','AwayTeam':'Other'}])
    bot=SimpleNamespace(_fd_co_uk_load_csv=original,API_FOOTBALL_LEAGUES={'League':39},log=Mock())
    response=Mock()
    response.json.return_value=[dict(match_date='2026-10-20',home_team='Home',away_team='Away',
        home_corners=0,away_corners=4,home_goals=2,away_goals=1)]
    with patch.dict(os.environ,{'SUPABASE_URL':'https://example.invalid','SUPABASE_KEY':'test'}), \
         patch('netrattler_api_corner_store.requests.get',return_value=response) as get:
        store.install(bot)
        assert bot._fd_co_uk_load_csv is original
        assert len(bot._ntr_corner_history('League'))==2
        assert len(bot._fd_co_uk_load_csv('League'))==1
        bot._ntr_corner_history('League')
        assert get.call_count==1
        store.install(bot)
        assert bot._fd_co_uk_load_csv is original
