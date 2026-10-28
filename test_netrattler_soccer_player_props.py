import netrattler_soccer_player_props as p

def test_player_props_normalization():
    event={"id":"evt1","home_team":"Arsenal","away_team":"Chelsea","commence_time":"2026-10-29T12:00:00Z","bookmakers":[{"key":"book","markets":[{"key":"player_shots_on_target","outcomes":[{"name":"Over","description":"Player One","point":1.5,"price":2.1},{"name":"Under","description":"Player One","point":1.5,"price":1.7}]},{"key":"player_goal_scorer_anytime","outcomes":[{"name":"Yes","description":"Player Two","price":2.4}]}]}]}
    rows=p.normalize(event,"soccer_epl")
    assert len(rows)==3
    assert len({r["selection"] for r in rows})==3
    assert {r["market"] for r in rows}=={"player_shots_on_target","player_goal_scorer_anytime"}
    assert rows[0]["raw"]["player"]=="Player One"
    assert rows[0]["raw"]["line"]==1.5

def test_missing_player_discarded():
    assert p.normalize({"bookmakers":[{"markets":[{"key":"player_shots_on_target","outcomes":[{"name":"Over","price":2.0}]}]}]},"soccer_epl")==[]
