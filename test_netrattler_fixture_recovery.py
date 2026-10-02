from netrattler_fixture_recovery import merge_recovered_matchups


def run():
    primary = [{
        "home": "Denmark", "away": "Portugal",
        "league_name": "UEFA - Nations League",
        "starts": "2026-10-01T18:45:00Z",
    }]
    recovered = [
        {
            "fixtureId": "dupe", "participant1Name": "Denmark",
            "participant2Name": "Portugal", "tournamentName": "UEFA Nations League",
            "categoryName": "International", "startTime": "2026-10-01T18:45:00Z",
            "hasOdds": True,
        },
        {
            "fixtureId": "afc1", "participant1Name": "Japan",
            "participant2Name": "Australia", "tournamentName": "AFC Asian Cup",
            "categoryName": "International", "startTime": "2026-10-01T20:00:00Z",
            "externalProviders": {"pinnacleId": 123456789},
            "hasOdds": True,
        },
        {
            "fixtureId": "noodds", "participant1Name": "A",
            "participant2Name": "B", "tournamentName": "Friendly", "hasOdds": False,
        },
    ]
    merged, added = merge_recovered_matchups(primary, recovered)
    assert len(merged) == 2, merged
    assert len(added) == 1, added
    assert added[0]["home"] == "Japan"
    assert added[0]["away"] == "Australia"
    assert added[0]["source"] == "oddspapi_recovery"
    assert added[0]["_oddspapi_fixture_id"] == "afc1"
    assert added[0]["_pinnacle_id"] == 123456789
    assert added[0]["match_id"] == 123456789
    print("OK: fixture recovery dedupe + bookmaker-backed supplement")


if __name__ == "__main__":
    run()
