from datetime import date, timedelta
from netrattler_corner_history import team_corner_profile


def rows():
    return [{'Date': str(date.today()-timedelta(days=i+1)), 'HomeTeam': 'Arsenal', 'AwayTeam': 'Chelsea',
             'HC': '6', 'AC': '4', 'FTHG': '1', 'FTAG': '0'} for i in range(20)]


def test_uses_last_15_dated_measured_games_and_correct_side():
    h = team_corner_profile(rows(), 'Arsenal')
    a = team_corner_profile(rows(), 'Chelsea')
    assert h['games'] == 15 and h['avg_corners_for'] == 6 and h['avg_corners_against'] == 4
    assert a['avg_corners_for'] == 4 and a['avg_corners_against'] == 6


def test_missing_zero_future_duplicates_and_unrelated_team():
    r = rows()[:5]
    assert team_corner_profile(r+[dict(r[0], HC='')], 'Arsenal')['games'] == 5
    assert team_corner_profile([dict(x, HC='0') for x in r], 'Arsenal')['avg_corners_for'] == 0
    assert team_corner_profile(r*3, 'Arsenal')['games'] == 5
    assert team_corner_profile(r, 'Manchester City') is None
    assert team_corner_profile([dict(x, Date=str(date.today()+timedelta(days=1))) for x in r], 'Arsenal') is None
    assert team_corner_profile([dict(x, FTHG='') for x in r], 'Arsenal') is None


def test_corner_bot_works_without_api_ids_from_measured_history(monkeypatch):
    import btts_bot as b
    monkeypatch.setenv('NETRATTLER_CORNER_REQUIRE_TEAM_STATS', 'true')
    monkeypatch.setattr(b, '_fd_co_uk_load_csv', lambda league: rows())
    monkeypatch.setattr(b, '_ntr_observed_corner_quotes', lambda *args: {7.5: (1.60, 'bookmaker')})
    tip = b.analyze_corners_tip({'home': 'Arsenal', 'away': 'Chelsea'}, 'Premier League')
    assert tip and tip['odds'] == 1.6 and tip['corner_history_home_games'] == 15
    monkeypatch.setattr(b, '_ntr_observed_corner_quotes', lambda *args: {})
    assert b.analyze_corners_tip({'home': 'Arsenal', 'away': 'Chelsea'}, 'Premier League') is None


def test_target_date_matches_swiss_window_at_midnight_and_dst():
    from datetime import datetime, timezone
    import btts_bot as b
    assert str(b._ntr_target_date(datetime(2026, 10, 29, 23, 30, tzinfo=timezone.utc))) == '2026-10-30'
    assert str(b._ntr_target_date(datetime(2026, 7, 1, 22, 30, tzinfo=timezone.utc))) == '2026-07-02'
    assert str(b._ntr_target_date(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc))) == '2026-10-29'


def test_corner_criterion_rejects_team_and_combined_markets():
    from netrattler_prop_sources import is_full_match_corner_criterion as valid
    for text in ('Total Corners', 'Total Corners - Over/Under', 'Corner Kicks', 'Number of Corners'):
        assert valid(text)
    for text in ('Total Corners by Arsenal', 'Arsenal Total Corners', 'Total Corners & Goals',
                 '1st Half Total Corners', 'Asian Total Corners', 'Corners - Handicap'):
        assert not valid(text)


def test_team_corner_quote_cannot_replace_full_match_quote(monkeypatch):
    import netrattler_prop_sources as p
    monkeypatch.setattr(p, '_KAMBI_LIST_CACHE', {})
    monkeypatch.setattr(p, '_KAMBI_OFFER_CACHE', {})
    monkeypatch.setattr(p, '_KAMBI_HOSTS', ['https://example.invalid'])
    def fake(url, **kwargs):
        if 'listView' in url:
            return {'events': [{'event': {'id': 1, 'homeName': 'Arsenal', 'awayName': 'Chelsea'}}]}
        def offer(label, odds):
            return {'criterion': {'label': label}, 'outcomes': [{'label': 'Over 7.5', 'line': 7500, 'odds': odds}]}
        return {'betOffers': [offer('Total Corners', 1700), offer('Total Corners by Arsenal', 3800)]}
    monkeypatch.setattr(p, '_get_json', fake)
    result = p.fetch_kambi_match_corners('Arsenal', 'Chelsea')
    assert len(result) == 1 and result[0]['odds'] == 1.7
