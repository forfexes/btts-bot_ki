import json
from datetime import date,timedelta,datetime,timezone
import pytest
from netrattler_structured_pages import parse_public_page

FS='https://www.flashscore.com/match/football/home-x/away-y/'
TMP='https://www.todaymatchprediction.com/gameprediction/1/home-vs-away.html'

def fs(**kwargs):
    env={'sport_id':1,'event_id_c':'event1','participantsData':{'home':[{'name':'Home FC'}],'away':[{'name':'Away FC'}]},
         'eventStageStartTime':1793449800,'eventStageId':1,'eventStageTranslations':{'1':'&nbsp;'},
         'header':{'tournament':{'tournament':'Premier League'}}}
    env.update(kwargs)
    return '<script>window.environment = '+json.dumps(env)+';</script>'


def test_flashscore_real_identity_date_and_league_no_zero_scores():
    r=parse_public_page(fs(),FS,'2026-10-31');row=r['fixtures'][0]
    assert row['match_id']=='event1' and row['home']=='Home FC' and row['away']=='Away FC'
    assert row['starts']=='2026-10-31T12:30:00+00:00' and row['league']=='Premier League'
    assert row['status']=='unknown' and 'home_goals' not in row
    assert r['bookmaker_odds']==[] and r['settlement_results']==[]
    assert parse_public_page(fs(),FS,'2026-10-30')['fixtures']==[]

@pytest.mark.parametrize('payload',[{'sport_id':2},{'participantsData':{}},{'event_id_c':''},{'eventStageStartTime':True},{'eventStageStartTime':float('inf')}])
def test_flashscore_rejects_incomplete_or_wrong_sport(payload):
    assert parse_public_page(fs(**payload),FS)['fixtures']==[]


def schema(**kwargs):
    e={'@type':'SportsEvent','name':'Home FC vs Away FC','startDate':'2026-10-30',
       'competitor':[{'name':'Away FC'},{'name':'Home FC'}]}
    e.update(kwargs)
    return '<script type="application/ld+json">'+json.dumps(e)+'</script>'


def test_prediction_event_is_only_fixture_context():
    r=parse_public_page(schema(description='Correct score prediction 5-0',offers={'price':2.8}),TMP,'2026-10-30')
    assert r['fixtures'][0]['home']=='Home FC' and r['fixtures'][0]['away']=='Away FC'
    assert r['recent_results']==[] and r['settlement_results']==[] and r['bookmaker_odds']==[]
    assert parse_public_page(schema(name='Ambiguous game'),TMP)['fixtures']==[]
    assert parse_public_page(schema(), 'https://evil.invalid/')['fixtures']==[]


def test_besoccer_schema_requires_explicit_team_roles():
    url='https://www.besoccer.com/match/home/away/123'
    assert parse_public_page(schema(),url)['fixtures']==[]
    html=schema(homeTeam={'name':'Home FC'},awayTeam={'name':'Away FC'})
    assert parse_public_page(html,url)['fixtures'][0]['home']=='Home FC'


def history(day,score='1 : 2'):
    return f'<div class="game-result"><div class="lisleaguegames"><div class="team-schedule__date">{day}</div><h6 class="team-meta__nameresults">Home FC <span>vs</span> Away FC</h6><span class="colorscore">{score}</span></div></div>'


def test_only_dated_past_results_not_forecasts_or_future():
    day=(date.today()-timedelta(days=1)).strftime('%d.%m.%Y')
    html=history(day)*2+history(date.today().strftime('%d.%m.%Y'))+history(day,'2-1 predicted')+history('invalid')
    r=parse_public_page(html,TMP)
    assert len(r['recent_results'])==1
    assert r['recent_results'][0]['home_goals']==1 and r['recent_results'][0]['away_goals']==2
    assert r['settlement_results']==[]


def test_flashscore_homepage_never_becomes_fake_match(monkeypatch):
    import flashscore_scraper as f
    monkeypatch.setattr(f,'_page',lambda url:'<html>Football fixtures</html>')
    assert f.scrape_day('2026-10-30')==[]


def test_flashscore_discovery_respects_day_and_source_host(monkeypatch):
    import flashscore_scraper as f
    html='<a href="/match/football/home-x/away-y/">Game</a><a href="https://evil.invalid/match/football/x/y/">Bad</a>'
    monkeypatch.setattr(f,'_page',lambda url:html if url==f.BASE else fs())
    r=f.scrape_day('2026-10-31')
    assert len(r)==1 and r[0]['id']=='event1' and r[0]['home_team']=='Home FC'
    assert f.scrape_day('2026-10-30')==[]
