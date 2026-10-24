import netrattler_rapid_results as r

B = {"response": {"matches": [
    {"id": 1, "home": {"longName": "Everton", "score": 0}, "away": {"longName": "Chelsea", "score": 2},
     "status": {"finished": True, "cancelled": False}, "leagueId": 47},
    {"id": 2, "home": {"name": "A", "score": 1}, "away": {"name": "B", "score": 1}, "status": {"finished": False}},
    {"id": 3, "home": {"name": "C", "score": 1}, "away": {"name": "D", "score": 0}, "status": {"finished": True, "cancelled": True}}]}}


def test_only_finished():
    rows = r.parse_matches(B, "2026-10-17")
    assert len(rows) == 1 and rows[0]["home_team"] == "Everton" and rows[0]["away_score"] == 2 and rows[0]["source"] == "rapidapi"


def test_bad_body():
    assert r.parse_matches(None, "x") == [] and r.parse_matches({"response": {}}, "x") == []
