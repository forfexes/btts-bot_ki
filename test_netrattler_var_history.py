from datetime import date
from netrattler_var_history import history


def test_bounded_history_preserves_unknown_absence():
    calls=[]
    def api(path,params):
        calls.append((path,params))
        if path=='/fixtures':
            return [{'fixture':{'id':params['league'],'date':'2026-11-01T12:00:00Z','status':{'short':'FT'}},'league':{'id':params['league']},'teams':{}}]
        return [{'type':'Var','detail':'Goal cancelled'}] if params['fixture']==39 else []
    result=history(api,date(2026,11,4),2)
    assert len(calls)==5 and result['fixture_count']==2 and result['var_events']==1
    assert all(not r['no_var_inferred'] and not r['tip_eligible'] for r in result['fixtures'])
    assert {r['fixture_id'] for r in result['fixtures']}=={39,140}
