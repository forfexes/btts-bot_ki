import netrattler_espn_player_import as e

def test_rows_from_summary_skips_bench_and_maps_stats():
    js = {"rosters": [
        {"team": {"displayName": "Columbus Crew"}, "roster": [
            {"athlete": {"id": "11", "displayName": "Chase Adams"}, "position": {"abbreviation": "M"},
             "stats": [{"name": "appearances", "value": 1.0}, {"name": "totalShots", "value": 2.0}, {"name": "shotsOnTarget", "value": 1.0},
                       {"name": "foulsCommitted", "value": 3.0}, {"name": "yellowCards", "value": 1.0}]},
            {"athlete": {"id": "12", "displayName": "Bench Guy"}, "stats": [{"name": "appearances", "value": 0.0}, {"name": "totalShots", "value": 0.0}]}]},
        {"team": {"displayName": "Charlotte FC"}, "roster": []}]}
    rows = e.rows_from_summary(js, {"id": "999", "date": "2026-10-14T23:30Z"}, "MLS")
    assert len(rows) == 1
    r = rows[0]
    assert (r["match_id"], r["player_id"], r["team"], r["opponent"], r["league"], r["match_date"]) == ("espn-999", 11, "Columbus Crew", "Charlotte FC", "MLS", "2026-10-14")
    assert (r["shots"], r["shots_on"], r["fouls_committed"], r["yellow"], r["source"]) == (2, 1, 3, 1, "espn")
    assert "goals" not in r
