import netrattler_fplci_import as f

def test_helpers():
    assert f.inum("3.0") == 3 and f.inum("") is None and f.fnum("x") is None
    assert f.league_of("26-27-prem-a-vs-b") == "Premier League"
    assert f.league_of("26-27-champions-league-a-vs-b-2026-09-08") == "Champions League"

def test_rows_for(monkeypatch):
    data = {
        "matches.csv": [{"match_id": "26-27-prem-a-vs-b", "kickoff_time": "2026-10-03T15:00:00", "finished": "True", "home_team": "1.0", "away_team": "2.0"}],
        "playermatchstats.csv": [
            {"match_id": "26-27-prem-a-vs-b", "player_id": "7", "minutes_played": "90.0", "total_shots": "3", "shots_on_target": "1", "tackles": "2", "tackles_won": "1", "fouls_committed": "2", "was_fouled": "1", "interceptions": "0", "xg": "0.4", "goals": "1", "assists": "0"},
            {"match_id": "26-27-prem-a-vs-b", "player_id": "8", "minutes_played": "0.0"}],
        "teams.csv": [{"id": "1", "code": "10", "name": "Arsenal"}, {"id": "2", "code": "20", "name": "Chelsea"}],
        "players.csv": [{"player_id": "7", "web_name": "Saka", "team_code": "10", "position": "Midfielder"},
                        {"player_id": "8", "web_name": "Bench", "team_code": "10", "position": "Defender"}],
    }
    monkeypatch.setattr(f, "fetch_csv", lambda url: data[url.rsplit("/", 1)[1]])
    rows = f.rows_for("2026-2027", 5)
    assert len(rows) == 1
    r = rows[0]
    assert (r["player_name"], r["team"], r["opponent"], r["tackles"], r["fouls_committed"], r["fouls_drawn"], r["shots_on"], r["match_date"]) == ("Saka", "Arsenal", "Chelsea", 2, 2, 1, 1, "2026-10-03")

    assert (r["goals"], r["assists"]) == (1, 0)
