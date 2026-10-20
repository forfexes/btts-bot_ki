import unittest, btts_bot as b

R = lambda bk, mk, sel, o: {"bookmaker": bk, "home_team": "Getafe CF", "away_team": "Rayo Vallecano", "market": mk, "selection": sel, "odds": o}

class T(unittest.TestCase):
    def test_median_and_floor(self):
        rows = [R("bwin", "btts_ht", "yes", 2.4), R("1x_melbet", "btts_ht", "yes", 2.6),
                R("kambi_ubse", "btts_ht", "yes", 1.1), R("bwin", "btts_over_2_5", "yes", 2.9),
                R("pinnacle", "totals_ht_1_5", "over_1_5", 2.7)]
        out = b._ntr_odds_history_special_quotes("Getafe", "Rayo Vallecano", rows=rows)
        self.assertEqual(out["btts_yes_ht"][0], 2.6)
        self.assertEqual(out["btts_over25_yes"][0], 2.9)
        self.assertEqual(out["over_15_ht"][0], 2.7)

    def test_other_match_ignored(self):
        rows = [R("bwin", "btts_ht", "yes", 2.4)]
        self.assertEqual(b._ntr_odds_history_special_quotes("Arsenal", "Chelsea", rows=rows), {})

if __name__ == "__main__":
    unittest.main()
