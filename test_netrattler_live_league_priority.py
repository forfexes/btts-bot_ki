"""Prefer real active fixtures before stale league loops without dropping leagues."""
from datetime import datetime, timezone
import btts_bot as bot

START = datetime(2026, 11, 18, 17, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 19, 11, 0, tzinfo=timezone.utc)


def test_real_future_bookmaker_games_are_prioritized_without_dropping_leagues():
    original = ["Bundesliga", "Serie B", "Premier League",
                "Brasileirao Serie A", "Peru Primera", "Serie A"]
    fixtures = [
        {"league_name":"Brazil Serie A", "home":"H", "away":"A",
         "starts":"2026-11-18T20:00:00Z"},
        {"league_name":"Brasileirao Serie A", "home":"B", "away":"C",
         "starts":"2026-11-18T22:00:00+00:00"},
        {"league_name":"Peru Primera", "home":"D", "away":"E",
         "starts":"2026-11-19T01:00:00Z"},
        {"league_name":"Serie A", "home":"Old", "away":"Old2",
         "starts":"2026-11-17T22:00:00Z"},
    ]
    result = bot._ntr_prioritize_live_leagues(original,fixtures,START,END)
    assert result[:2] == ["Brasileirao Serie A", "Peru Primera"]
    assert sorted(result) == sorted(original)
    assert result[2:] == [x for x in original if x not in result[:2]]


def test_unverified_kickoff_and_missing_teams_have_no_priority():
    original = ["Bundesliga","Peru Primera","Premier League"]
    cases = [
        {"league_name":"Peru Primera","home":"A","away":"B",
         "starts":"2026-11-18T20:00:00"},  # timezone missing
        {"league_name":"Peru Primera","home":"A","away":"",
         "starts":"2026-11-18T20:00:00Z"},
        {"league_name":"Peru Primera","home":"A","away":"B",
         "starts":"2026-11-19T13:00:00Z"},  # outside live window
    ]
    assert bot._ntr_prioritize_live_leagues(original,cases,START,END)==original
    assert bot._ntr_prioritize_live_leagues(original,[],START,END)==original
