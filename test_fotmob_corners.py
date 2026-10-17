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
