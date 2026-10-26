import unittest
from netrattler_game_log_sync import to_log_row

class T(unittest.TestCase):
    def test_maps_fields(self):
        r = to_log_row({"match_id": 5, "player_id": 9, "player_name": "Chase Adams", "match_date": "2026-10-14",
                        "minutes": 80, "shots": 2, "shots_on": 1, "fouls_drawn": 3, "yellow": 1, "source": "espn"})
        self.assertEqual(r["player_key"], "chase adams"); self.assertEqual(r["sot"], 1)
        self.assertEqual(r["fouls_won"], 3); self.assertEqual(r["yellow_cards"], 1); self.assertEqual(r["event_id"], "5")
    def test_skips_no_minutes(self):
        self.assertIsNone(to_log_row({"match_id": 1, "player_name": "A", "match_date": "2026-01-01", "minutes": 0}))
        self.assertIsNone(to_log_row({"match_id": 1, "player_name": "", "match_date": "2026-01-01", "minutes": 90}))
    def test_espn_without_minutes_kept(self):
        r = to_log_row({'match_id': 7, 'player_name': 'B', 'match_date': '2026-10-01', 'minutes': None, 'source': 'espn', 'shots': 1})
        self.assertIsNotNone(r)
if __name__ == "__main__":
    unittest.main()
