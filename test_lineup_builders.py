import datetime as dt

import netrattler_lineup_builders as lb

NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)


def _fx(i, minutes, league=39):
    ko = (NOW + dt.timedelta(minutes=minutes)).isoformat()
    return {"id": i, "ko": ko, "league_id": league, "league": "L", "home": f"H{i}", "away": f"A{i}"}


def test_name_matching_initial_and_surname():
    assert lb.name_matches("Moises Caicedo", "M. Caicedo")
    assert lb.name_matches("Erling Haaland", "Erling Haaland")
    assert not lb.name_matches("Moises Caicedo", "J. Caicedo")
    assert not lb.name_matches("Moises Caicedo", "M. Palmer")


def test_filter_to_starters_keeps_only_confirmed_matches_and_players():
    rows = [{"match": "A vs B", "player": "Moises Caicedo"}, {"match": "A vs B", "player": "Bank Spieler"},
            {"match": "C vs D", "player": "Moises Caicedo"}]
    out = lb.filter_to_starters(rows, {"A vs B": ["M. Caicedo", "R. James"]})
    assert out == [{"match": "A vs B", "player": "Moises Caicedo"}]


def test_due_fixtures_window_tries_budget_and_priority():
    fx = [_fx(1, 5), _fx(2, 30), _fx(3, 60, league=999), _fx(4, 200), _fx(5, 45), _fx(6, 40)]
    state = {"6": {"done": True}, "5": {"tries": 3}}
    due = lb.due_fixtures(fx, state, NOW, used_req=0)
    assert [f["id"] for f in due] == [2, 3]  # 1 zu nah, 4 zu weit, 5 zu viele Versuche, 6 erledigt; Liga 39 vor 999
    assert lb.due_fixtures(fx, state, NOW, used_req=lb.MAX_REQ) == []


def test_starters_need_both_teams():
    one = [{"startXI": [{"player": {"name": "A"}}]}, {"startXI": []}]
    assert lb.starters_from(one) is None
    both = [{"startXI": [{"player": {"name": "A"}}]}, {"startXI": [{"player": {"name": "B"}}]}]
    assert lb.starters_from(both) == ["A", "B"]


def test_message_marks_lineup_confirmed(monkeypatch):
    import netrattler_model_builders as mb
    legs = [{"player": "P", "market": "P 2+ Fouls", "line": 2.0, "series": [2, 3, 2, 2, 3, 2, 2, 3, 2, 2], "match": "A vs B"}]
    pick = {"match": "A vs B", "legs": legs, "joint": 0.5, "fair": 2.0, "size": 1}
    monkeypatch.setenv("NETRATTLER_LINEUP_CONFIRMED", "1")
    assert "Startelf bestätigt" in mb.message(pick, "d")
    monkeypatch.delenv("NETRATTLER_LINEUP_CONFIRMED")
    assert "Startelf bestätigt" not in mb.message(pick, "d")
