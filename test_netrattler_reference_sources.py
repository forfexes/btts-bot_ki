from unittest.mock import Mock,patch
import netrattler_season_profiles as season
import netrattler_reference_images as images


def test_uploaded_profiles_are_unique_aggregates_not_match_logs():
    assert sum(len(rows) for rows in season.load_profiles().values())==2224
    row=season.profile('Lamine Yamal','Barcelona','2026-10-31')
    assert row['grain']=='season_aggregate' and row['source']=='user_season_csv'
    assert row['MP']=='9' and row['Min']=='738'
    assert 'Saison 2026/27' in season.summary('Lamine Yamal','Barcelona','fouls_won','2026-10-31')
    assert 'L10' not in season.summary('Lamine Yamal','Barcelona','shots','2026-10-31')
    assert season.profile('Lamine Yamal','Barcelona','2026-10-30') is None
    assert season.profile('Lamine Yamal','Real Madrid') is None
    assert season.profile('Lamine','Barcelona') is None


def test_missing_season_values_stay_unknown():
    assert season.number('') is None and season.number('nan') is None
    assert season.number('0')==0
    row={'MP':'5','Min':'300','Sh':''}
    with patch.object(season,'profile',return_value=row):
        assert season.summary('A','B','shots')==''


def html(name='Lamine Yamal',club='Barcelona',pid='126898',photo='126898'):
    return f'<table><tr><td><a href="/player.php?pid={pid}">{name}</a></td><td><a href="/squad.php?clubid=140">{club}</a></td><td><img data-src="https://cdn.soccerwiki.org/images/player/{photo}.png"></td></tr></table>'


def test_soccerwiki_identity_and_placeholder_checks():
    assert images.soccerwiki_url(html(),'Lamine Yamal','Barcelona').endswith('/126898.png')
    assert not images.soccerwiki_url(html(club='Real Madrid'),'Lamine Yamal','Barcelona')
    assert not images.soccerwiki_url(html(name='Lamine Other'),'Lamine Yamal','Barcelona')
    assert not images.soccerwiki_url(html(photo='missing_player'),'Lamine Yamal','Barcelona')
    assert not images.soccerwiki_url(html()+html(pid='42',photo='42'),'Lamine Yamal','Barcelona')


def test_wiki_rejects_wrong_full_name_and_wrong_team():
    response=Mock();response.json.return_value={'query':{'pages':[{'title':'Lamine Other',
        'extract':'Barcelona footballer','thumbnail':{'source':'https://upload.wikimedia.org/wrong.png'}}]}}
    with patch.object(images,'_CACHE',{}),patch.object(images,'_get',side_effect=[None,response,response]):
        assert images.player_urls('Lamine Yamal','Barcelona')==[]


def test_reference_budget_stops_without_request():
    with patch.object(images,'_CALLS',images.MAX_CALLS),patch.object(images.requests,'get') as get:
        assert images._get('https://de.soccerwiki.org/') is None
    get.assert_not_called()
