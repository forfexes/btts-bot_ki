import netrattler_apifootball_players as a

FX = {"fixture": {"id": 5, "date": "2026-10-21T19:00:00+00:00", "status": {"short": "FT"}}, "league": {"id": 2}}
RESP = [{"team": {"name": "Bayern"}, "players": [
    {"player": {"id": 1, "name": "A"}, "statistics": [{"games": {"minutes": 90, "position": "M"}, "shots": {"total": 2, "on": 1},
     "fouls": {"drawn": 3, "committed": None}, "cards": {"yellow": 1, "red": 0}}]},
    {"player": {"id": 2, "name": "Bench"}, "statistics": [{"games": {"minutes": None}}]}]}]


def test_parse():
    r = a.parse_players(RESP, FX)
    assert len(r) == 1 and r[0]["fouls_drawn"] == 3 and r[0]["fouls_committed"] == 0 and r[0]["yellow"] == 1
    assert r[0]["match_date"] == "2026-10-21"


def test_pick_priority_and_known():
    mk = lambda i, l, s="FT": {"fixture": {"id": i, "status": {"short": s}}, "league": {"id": l}}
    got = a.pick_fixtures([mk(1, 999), mk(2, 39), mk(3, 2, "NS"), mk(4, 140)], {4}, 5)
    assert [x["fixture"]["id"] for x in got] == [2, 1]
