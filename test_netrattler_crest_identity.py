from netrattler_crest_identity import same_club
import netrattler_stats_match_cards as cards


def test_club_identity_does_not_guess_city_or_squad():
    for a,b in [('Manchester City','Manchester United'),('Atletico Madrid','Real Madrid'),('Auckland FC','Auckland FC II'),('Chelsea','Chelsea Women'),('Inter','Inter Miami'),('Boca Juniors','Boca Juniors de Cali')]:
        assert not same_club(a,b)
        assert cards._name_score(a,b)==0
    assert same_club('FC Bayern München','Bayern Munich')
    assert same_club('Swansea City AFC','Swansea')


def test_index_rejects_prefix_and_partial_matches(monkeypatch):
    monkeypatch.setattr(cards,'_load_crest_index',lambda:{'repo':'example/repo','sha':'abc','rows':[('Manchester United','united.png',set(),set(),'manchesterunited')]})
    assert cards._crest_from_index('Manchester City')==''
    assert cards._crest_from_index('Manchester')==''
    assert cards._crest_from_index('Manchester United').endswith('united.png')


def test_no_random_wikipedia_thumbnail():
    assert cards._wiki_badge('Some Club')==''


def test_search_does_not_take_first_wrong_team(monkeypatch):
    class Response:
        ok=True
        status_code=200
        def json(self):
            return {'teams':[{'strSport':'Soccer','strTeam':'Manchester United','strBadge':'wrong.png'}]}
    monkeypatch.setattr(cards.requests,'get',lambda *a,**k:Response())
    monkeypatch.setattr(cards,'_TSDB_LAST',0)
    assert cards._search_badge('Manchester','3',cards._norm('Manchester City'))==('',False)


def test_old_unverified_cache_is_not_loaded(monkeypatch):
    class Response:
        ok=True
        def json(self):
            return [{'team_key':'v2:chelsea','url':'verified.png'}]
    calls=[]
    monkeypatch.setattr(cards,'_sb',lambda:('https://example/rest/v1/netrattler_match_cards',{}))
    monkeypatch.setattr(cards,'_LOGO_CACHE',{})
    def get(*a,**k):
        calls.append(k['params']);return Response()
    monkeypatch.setattr(cards.requests,'get',get)
    cards._crest_cache_load()
    assert calls[0]['team_key']=='like.v2:*'
    assert cards._LOGO_CACHE=={'chelsea':'verified.png'}
