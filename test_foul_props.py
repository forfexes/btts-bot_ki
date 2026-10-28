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
