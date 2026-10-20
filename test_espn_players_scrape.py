import unittest
from unittest import mock
import scrape_player_stats as sp

class R:
    def __init__(s, d): s.d, s.ok = d, True
    def json(s): return s.d

class T(unittest.TestCase):
    def test_rows(self):
        sb = {"leagues": [{"name": "English Premier League"}], "events": [{"id": "9", "competitions": [{"status": {"type": {"completed": True}},
              "competitors": [{"homeAway": "home", "team": {"displayName": "A"}}, {"homeAway": "away", "team": {"displayName": "B"}}]}]}]}
        sm = {"rosters": [{"team": {"displayName": "A"}, "roster": [
            {"athlete": {"id": "1", "displayName": "P One"}, "stats": [{"name": "appearances", "value": 1}, {"name": "foulsCommitted", "value": 3}, {"name": "totalShots", "value": 2}]},
            {"athlete": {"id": "2", "displayName": "Bench"}, "stats": [{"name": "appearances", "value": 0}, {"name": "foulsCommitted", "value": 0}]}]}]}
        def get(url, **k): return R(sb if "scoreboard" in url else sm)
        with mock.patch.object(sp, "_ESPN_LEAGUES", ("eng.1",)), mock.patch.object(sp.requests, "get", side_effect=get), mock.patch.object(sp.time, "sleep"):
            rows = sp.scrape_espn_players_date("2026-10-18")
        got = {(r["player_name"], r["stat_name"]): r["stat_value"] for r in rows}
        self.assertEqual(got, {("P One", "fouls_committed"): 3.0, ("P One", "shots"): 2.0})
        wide = sp._long_to_wide(rows)
        self.assertEqual(len(wide), 1)
        self.assertIsNone(wide[0]["tackles"])

if __name__ == "__main__":
    unittest.main()
