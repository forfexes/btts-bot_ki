from netrattler_var import decode_var_prices,normalize_var_events


def game(g=8203,y=7416,n=7417):
    return {'GE':[{'G':g,'E':[[{'G':g,'T':y,'C':2.5},{'G':g,'T':n,'C':1.6}]]}]}


def test_verified_pairs():
    for g,y,n in [(8203,7416,7417),(8203,10043,10044),(8205,7418,7419),(9366,10068,10069)]:
        rows=decode_var_prices(game(g,y,n))
        assert len(rows)==2 and {r['selection'] for r in rows}=={'yes','no'}
        assert all(not r['tip_eligible'] and r['settlement_status']=='pending' for r in rows)


def test_unknown_half_incomplete_and_nonfinite_rejected():
    assert not decode_var_prices(game(999))
    assert not decode_var_prices({**game(),'PN':'1st half'})
    g=game();g['GE'][0]['E'][0][1]['C']=float('nan')
    assert not decode_var_prices(g)
    assert not decode_var_prices(game(8203,7418,7419))


def test_explicit_events_only_never_infer_no_var():
    assert normalize_var_events([])==[]
    assert normalize_var_events([{'type':'Goal','detail':'Normal Goal'}])==[]
    assert normalize_var_events([{'type':'Var','detail':'Goal cancelled'}])[0]['detail']=='Goal cancelled'
