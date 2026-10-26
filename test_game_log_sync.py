import unittest
import netrattler_game_log_sync as g


def fpl(**k):
    r = {"match_id": 1, "player_id": 355, "player_name": "Haaland", "team": "Man City", "match_date": "2025-09-01",
         "minutes": 90, "shots": 4, "shots_on": 2, "tackles": 1, "xg": 0.9, "source": None}
    r.update(k); return r

def espn(**k):
    r = {"match_id": 900, "player_id": 77, "player_name": "Erling Haaland", "team": "Manchester City",
         "match_date": "2025-09-01", "minutes": None, "shots": 4, "shots_on": 2, "tackles": None, "xg": None, "source": "espn"}
    r.update(k); return r


class T(unittest.TestCase):
    def test_maps_fields(self):
        r = g.to_log_row({"match_id": 5, "player_id": 9, "player_name": "Chase Adams", "match_date": "2026-10-14",
                          "minutes": 80, "shots": 2, "shots_on": 1, "fouls_drawn": 3, "yellow": 1, "source": "espn"})
        self.assertEqual(r["player_key"], "chase adams"); self.assertEqual(r["sot"], 1)
        self.assertEqual(r["fouls_won"], 3); self.assertEqual(r["event_id"], "2026-10-14:chase adams")

    def test_skips_no_minutes(self):
        self.assertIsNone(g.to_log_row({"match_id": 1, "player_name": "A", "match_date": "2026-01-01", "minutes": 0}))
        self.assertIsNone(g.to_log_row({"match_id": 1, "player_name": "", "match_date": "2026-01-01", "minutes": 90}))

    def test_espn_without_minutes_kept(self):
        self.assertIsNotNone(g.to_log_row(espn(player_name="B")))

    def test_same_match_merges_to_one_row(self):
        out = g.build_canonical([fpl(), espn()])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["player_name"], "Erling Haaland")
        self.assertEqual(out[0]["tackles"], 1); self.assertEqual(out[0]["minutes"], 90)

    def test_fpl_only_dates_use_espn_name_via_player_id(self):
        old = fpl(match_id=2, match_date="2025-08-20")  # kein ESPN-Spiel an dem Tag
        out = g.build_canonical([fpl(), espn(), old])
        self.assertEqual({r["player_key"] for r in out}, {"erling haaland"})
        self.assertEqual(len(out), 2)

    def test_different_players_same_surname_not_merged(self):
        a = fpl(player_id=1, player_name="Silva", team="Chelsea")
        b = espn(player_name="Bernardo Silva", team="Manchester City")
        out = g.build_canonical([a, b])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
