import netrattler_foul_props as fp


def _g(fc, fw=1, minutes=90):
    return {"minutes": minutes, "fouls_committed": fc, "fouls_won": fw, "team": "Sevilla", "player_name": "X"}


def test_picks_highest_line_that_holds():
    games = [_g(c) for c in (3, 2, 2, 3, 2, 4, 2, 2, 3, 2)]
    legs = {l[0]: l for l in fp.legs_for_player("X", games)}
    assert legs["fouls_committed"][1] == 2 and legs["fouls_committed"][2] == 1.0


def test_too_few_games_or_minutes():
    assert fp.legs_for_player("X", [_g(3)] * 5) == []
    assert fp.legs_for_player("X", [_g(3, minutes=20)] * 10) == []


def test_build_rows_marks_model_line_without_odds():
    by = {"X": [_g(3)] * 10}
    rows = fp.build_rows(by, "Sevilla", "Sevilla vs Osasuna", "La Liga", "k")
    assert rows and rows[0]["odds"] == 0 and rows[0]["source"] == "model_line_fouls"
    assert rows[0]["category"] in ("fouls", "fouls_won")


def test_missing_minutes_do_not_exclude_player():
    games = [{"minutes": None, "fouls_committed": 2, "fouls_won": 1, "shots": 2, "sot": 1, "tackles": None} for _ in range(10)]
    legs = {l[0] for l in fp.legs_for_player("X", games)}
    assert "fouls_committed" in legs


def test_zero_action_rows_without_minutes_are_not_games():
    played = {"minutes": None, "fouls_committed": 2, "fouls_won": 1, "shots": 1, "sot": 0, "tackles": None, "passes": 30}
    bench = {"minutes": None, "fouls_committed": 0, "fouls_won": 0, "shots": 0, "sot": 0, "tackles": None, "passes": 0}
    games = [played] * 8 + [bench] * 4
    legs = {l[0]: l for l in fp.legs_for_player("X", games)}
    assert legs["fouls_committed"][3] == 8  # nur die 8 echten Einsaetze


def test_same_team_suffix_and_false_friends():
    assert fp.same_team("Chicago Fire FC", "Chicago Fire")
    assert fp.same_team("Botafogo", "Botafogo FR RJ")
    assert not fp.same_team("Internazionale", "Inter Miami")
    assert not fp.same_team("Deportes Tolima", "Deportes Quindio")
    assert not fp.same_team("Manchester City", "Manchester United")


def test_foul_profiles_need_both_series():
    g = {"minutes": None, "fouls_committed": 2, "fouls_won": 1, "shots": 1, "sot": 0, "tackles": None, "passes": 20}
    prof = fp.foul_profiles({"X": [g] * 10, "Y": [g] * 3}, "T", "T vs U", "L", "k")
    assert [p["player"] for p in prof] == ["X"] and prof[0]["source"] == "foul_profile"
    assert prof[0]["fouls"] == [2] * 10 and prof[0]["fouls_won"] == [1] * 10



def test_repeated_exact_team_only_fetches_once_per_run(monkeypatch):
    seen = []
    def get_rows(url, key, team):
        seen.append(team)
        return []
    monkeypatch.setattr(fp, "fetch_team_rows", get_rows)
    matches = [
        {"match": "Sevilla vs Osasuna", "league": "La Liga", "kickoff": "2026-11-19"},
        {"match": "Sevilla vs Granada", "league": "La Liga", "kickoff": "2026-11-19"},
    ]
    rows = fp.rows_for_matches(matches, "https://db", "key", lambda s:s.casefold())
    assert rows == []
    assert seen == ["Sevilla", "Osasuna", "Granada"]
    assert fp.STATS_LAST["teams"] == 4


def test_quota_402_is_detected_without_retrying_every_team(monkeypatch):
    class Response:
        status_code = 402
        ok = False
    calls=[]
    def blocked(*args,**kwargs):
        calls.append(True)
        return Response()
    monkeypatch.setattr(fp.requests, "get", blocked)
    import pytest
    with pytest.raises(fp.HistoryQuotaBlocked):
        fp.fetch_team_rows("https://db", "key", "Sevilla")
    assert len(calls) == 1

    matches = [{"match": "Sevilla vs Osasuna", "league": "La Liga",
                "kickoff": "2026-11-19"} for _ in range(10)]
    rows = fp.rows_for_matches(matches, "https://db", "key", lambda s:s.casefold())
    assert rows == []  # No partial/history-derived picks with a broken source.
    assert fp.STATS_LAST["quota_blocked"] is True
    assert len(calls) == 2  # First explicit test and first request inside the run.


def test_other_http_failure_keeps_safe_empty_data(monkeypatch):
    class Response:
        status_code = 503
        ok = False
    monkeypatch.setattr(fp.requests, "get", lambda *a,**k: Response())
    assert fp.fetch_team_rows("https://db", "key", "Sevilla") == []
