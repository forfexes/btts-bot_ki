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

def test_verified_club_aliases_for_real_index_assets():
    for short_name, official in [
        ('Atalanta', 'Atalanta BC'),
        ('Bayer Leverkusen', 'Bayer 04 Leverkusen'),
        ('Lens', 'RC Lens'),
        ('PSV', 'PSV Eindhoven'),
        ('Lyon', 'Olympique Lyon'),
        ('Nice', 'OGC Nice'),
        ('Sassuolo', 'US Sassuolo'),
        ('Juventus', 'Juventus FC'),
        ('Frosinone', 'Frosinone Calcio'),
        ('Atlético-MG', 'Atlético Mineiro'),
        ('RC Deportivo La Coruña', 'Deportivo A Coruña'),
    ]:
        assert same_club(short_name, official)
    assert not same_club('PSV', 'PSV II')
    assert not same_club('Lens', 'Lens II')
    assert not same_club('Atalanta', 'Atalanta U23')


def test_football_logos_reject_wrong_club_filename(monkeypatch):
    """The provider must never attach Sporting CP to Atletico CP."""
    monkeypatch.setenv("ENABLE_FOOTBALL_LOGOS_CC", "true")
    monkeypatch.setattr(cards, "_fl_country_slugs", lambda country: [])
    monkeypatch.setattr(cards, "_fl_get", lambda url:
        '<img src="https://assets.football-logos.cc/logos/portugal/700x700/sporting-cp.6d17a40c.png">')
    assert cards._fl_logo("Atletico CP", "Portugal - Primeira Liga") == ""


def test_football_logos_accept_matching_club_filename(monkeypatch):
    monkeypatch.setenv("ENABLE_FOOTBALL_LOGOS_CC", "true")
    monkeypatch.setattr(cards, "_fl_country_slugs", lambda country: [])
    actual = "https://assets.football-logos.cc/logos/germany/700x700/bayer-04-leverkusen.1234abcd.png"
    monkeypatch.setattr(cards, "_fl_get", lambda url: '<img src="' + actual + '">')
    assert cards._fl_logo("Bayer Leverkusen", "Germany - Bundesliga") == actual


def test_wrong_named_cached_club_wappen_is_rejected(monkeypatch):
    from netrattler_crest_identity import named_crest_url_matches_club
    bad = "https://assets.football-logos.cc/logos/portugal/700x700/sporting-cp.6d17a40c.png"
    good = "https://assets.football-logos.cc/logos/germany/700x700/bayer-04-leverkusen.0000ffae.png"
    self_opaque = "https://media.api-sports.io/football/teams/100.png"
    assert named_crest_url_matches_club("Atletico CP", bad) is False
    assert named_crest_url_matches_club("Bayer Leverkusen", good) is True
    assert named_crest_url_matches_club("Atletico CP", self_opaque) is None
    class Response:
        ok = True
        def json(self):
            return [
                {"team_key":"v2:atleticocp","team":"Atletico CP","url":bad},
                {"team_key":"v2:bayerleverkusen","team":"Bayer Leverkusen","url":good},
            ]
    monkeypatch.setattr(cards,"_sb",lambda:("https://example/rest/v1/netrattler_match_cards",{}))
    monkeypatch.setattr(cards,"_LOGO_CACHE",{})
    monkeypatch.setattr(cards.requests,"get",lambda *a,**k:Response())
    cards._crest_cache_load()
    assert "atleticocp" not in cards._LOGO_CACHE
    assert cards._LOGO_CACHE["bayerleverkusen"] == good


def test_verified_club_country_hint_finds_nashville_and_sabah_without_league(monkeypatch):
    monkeypatch.setenv("ENABLE_FOOTBALL_LOGOS_CC", "true")
    monkeypatch.setattr(cards, "_fl_country_slugs", lambda country: [])
    nashville = "https://assets.football-logos.cc/logos/usa/700x700/nashville-sc.1234abcd.png"
    sabah = "https://assets.football-logos.cc/logos/azerbaijan/700x700/sabah.1234abcd.png"
    seen = []
    def get(url):
        seen.append(url)
        if url == "https://football-logos.cc/usa/nashville-sc/":
            return '<img src="' + nashville + '">'
        if url == "https://football-logos.cc/azerbaijan/sabah/":
            return '<img src="' + sabah + '">'
        return ""
    monkeypatch.setattr(cards, "_fl_get", get)
    assert cards._fl_logo("Nashville SC", "") == nashville
    assert cards._fl_logo("Sabah FK", "") == sabah
    assert "https://football-logos.cc/azerbaijan/sabah/" in seen
    assert cards._fl_logo("Unrelated Club", "") == ""
