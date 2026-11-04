import ast
from pathlib import Path
from unittest.mock import patch
import netrattler_foul_props as fp
import netrattler_builder_limit as bl


def test_club_identity_regressions():
    for first,second in [('Juventus','YF Juventus'),('Boca Juniors','Boca Juniors de Cali'),
                          ('PSV Eindhoven','FC Eindhoven'),('Auckland FC','Auckland FC II')]:
        assert not fp.same_team(first,second)
    assert fp.same_team('Chicago Fire FC','Chicago Fire')
    assert fp.same_team('Botafogo','Botafogo FR RJ')
    # An unsafe upstream normalizer must not override club identity.
    assert fp.player_rows([dict(team='Boca Juniors',player_name='X')], 'same',lambda x:'same','Boca Juniors de Cali') == {}


def test_wrong_squad_never_fetches_mens_history():
    with patch.object(fp,'fetch_team_rows') as fetch:
        rows=fp.rows_for_matches([dict(match='Austria Vienna vs Juventus',league='UEFA Champions League Women')],
                                 'https://example.invalid','key',str.lower)
    assert rows==[] and not fetch.called
    assert fp.senior_fixture('Braga vs Famalicao','League Cup')


def test_duplicate_guard_blocks_on_db_failure():
    legs=[dict(match='Home vs Away')]
    with patch.object(bl.requests,'get',side_effect=TimeoutError):
        assert bl.at_limit('https://example.invalid','key','2026-11-04',legs)
    class Reply:
        ok=True
        def json(self):return []
    with patch.object(bl.requests,'get',return_value=Reply()):
        assert not bl.at_limit('https://example.invalid','key','2026-11-04',legs)


def test_no_fixture_no_tip_but_verified_fixture_passes():
    tree=ast.parse(Path('btts_bot.py').read_text())
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='validate_tips')
    ns=dict(log=lambda *x:None, teams_match=lambda a,b:a==b,get_local_time=lambda s:s)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<quality>','exec'),ns)
    tip=dict(match='Home vs Away')
    assert ns['validate_tips']([tip],[],[])==[]
    assert ns['validate_tips']([tip],[dict(home='Home',away='Other')],[])==[]
    assert ns['validate_tips']([tip],[dict(home='Home',away='Away',time_local='20:00')],[])==[dict(tip,time='20:00')]
