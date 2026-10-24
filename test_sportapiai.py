import netrattler_sportapiai as s


def test_parse_stats_numeric():
    r = s.parse_stats({"home": {"fouls": "9", "pass_accuracy": "79.5", "x": "n/a"}, "away": {"fouls": "11"}})
    assert r["home"] == {"fouls": 9, "pass_accuracy": 79.5} and r["away"]["fouls"] == 11
    assert s.parse_stats({}) is None and s.parse_stats(None) is None


def test_parse_events_keeps_relevant():
    ev = [{"minute": "13'", "event_type": "assist", "player_name": "D. Munoz", "team_side": "away"},
          {"minute": "20'", "event_type": "substitution", "player_name": "X"},
          {"minute": "50'", "event_type": "yellow_card", "player_name": "Y", "team_side": "home"}]
    r = s.parse_events(ev)
    assert [e["type"] for e in r] == ["assist", "yellow_card"] and r[1]["player"] == "Y"


def test_pick_finished_skips_known_and_limits():
    fx = [{"id": i, "status": "FT"} for i in range(1, 10)] + [{"id": 99, "status": "LIVE"}]
    got = s.pick_finished(fx, {"1"}, 3)
    assert [m["id"] for m in got] == [2, 3, 4]
