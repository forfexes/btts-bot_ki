import netrattler_odds_key_diagnostic as d

def test_two_keys_no_secret_in_results():
    calls = []
    class Response:
        ok = True
        status_code = 200
        headers = {"x-requests-remaining":"400"}
        def json(self): return [{"key":"soccer_epl"},{"key":"basketball_nba"}]
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return Response()
    result=d.diagnose("SECRET_ONE,SECRET_TWO",get=get)
    assert len(result)==2
    assert all(x["soccer_leagues"]==1 for x in result)
    assert "SECRET_ONE" not in str(result) and "SECRET_TWO" not in str(result)
    assert all(url==d.BASE for url,_ in calls)
    assert [x["params"]["apiKey"] for _,x in calls]==["SECRET_ONE","SECRET_TWO"]

def test_duplicate_keys_deduplicated():
    assert len(d.diagnose("x,x",get=lambda *a,**k: type("R",(),{"ok":False,"status_code":401,"headers":{}})()))==1
