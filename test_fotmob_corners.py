"""FotMob team-corner extraction uses full-match stats only."""
import scrape_player_stats as s

D = {"content": {"stats": {"Periods": {
    "FirstHalf": {"stats": [{"key": "corners", "stats": [2, 1]}]},
    "All": {"stats": [{"title": "Top stats", "stats": [{"key": "BallPossesion", "stats": [55, 45]}, {"title": "Corners", "key": "corners", "stats": [7, 3]}]}]},
    "SecondHalf": {"stats": [{"key": "corners", "stats": [5, 2]}]}}}}}

assert s._fotmob_team_corners(D) == (7, 3)
assert s._fotmob_team_corners({"content": {}}) is None
assert s._fotmob_team_corners({"content": {"stats": {"Periods": {"FirstHalf": {"stats": [{"key": "corners", "stats": [2, 1]}]}}}}}) is None
print("OK fotmob corners")

rows = s._stats_to_rows("fotmob", 1, {"id": 5, "name": "X Y"},
                        [{"title": "Defense", "stats": {"Tackles": {"key": "matchstats.headers.tackles", "stat": {"value": 3, "total": 4}}}}],
                        team="T", league="L", home="A", away="B", match_date="2026-10-16")
assert [(r["stat_name"], r["stat_value"]) for r in rows] == [("tackles", 3.0)]
print("OK fotmob tackles")
