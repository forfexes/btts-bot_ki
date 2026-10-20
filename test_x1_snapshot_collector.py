import unittest
import netrattler_x1_snapshot_collector as c

class T(unittest.TestCase):
    def test_league_filter(self):
        self.assertTrue(c.wanted_league("England. Premier League"))
        self.assertTrue(c.wanted_league("UEFA Champions League"))
        self.assertFalse(c.wanted_league("England. Premier League. Women"))
        self.assertFalse(c.wanted_league("Thailand. League 3"))

    def test_pick_skips_done_and_out_of_window(self):
        now = 1_000_000.0
        items = [
            {"I": 1, "O1": "Arsenal", "O2": "Chelsea", "L": "England. Premier League", "S": now + 3600},
            {"I": 2, "O1": "Leeds", "O2": "Hull", "L": "England. Championship", "S": now + 3600},
            {"I": 3, "O1": "Bayern", "O2": "Mainz", "L": "Germany. Bundesliga", "S": now + 5 * 86400},
            {"I": 4, "O1": "A", "O2": "B", "L": "Thailand. League 3", "S": now + 3600},
        ]
        got = c.pick_games(items, {"Leeds vs Hull"}, now, 36, 10)
        self.assertEqual(got, [(1, "Arsenal vs Chelsea")])

if __name__ == "__main__":
    unittest.main()
