import netrattler_footballdata_io as f

D = {"match": {"status": "complete", "match_id": "9", "match_date": "2026-10-21 19:00:00",
               "score": {"home": "2", "away": "2"}, "league": {"name": "UCL"},
               "home_team": {"team_name": "Bayern"}, "away_team": {"team_name": "Arsenal"}},
     "stats": {"fouls": {"home": "15", "away": "6", "total": "21"}, "half_time_goals": {"home": "1", "away": "1"}, "junk": 1}}


def test_parse():
    r = f.parse_match(D)
    assert r["match_id"] == "9" and r["home_goals"] == 2 and r["ht_away"] == 1
    assert r["stats"]["fouls"]["total"] == "21" and "junk" not in r["stats"]
    assert r["match_date"] == "2026-10-21T19:00:00+00:00"


def test_incomplete_none():
    assert f.parse_match({"match": {"status": "incomplete", "match_id": "1"}}) is None


def test_pick_new_limit():
    res = [{"match_id": i, "status": "complete"} for i in range(1, 40)]
    assert len(f.pick_new(res, {"1"}, 24)) == 24 and "1" not in f.pick_new(res, {"1"}, 24)
