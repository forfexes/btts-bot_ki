import unittest, netrattler_settlement_v16_final as m

class T(unittest.TestCase):
    def test_adjacent_day_with_both_teams(self):
        tip = {"home_team": "Andorra", "away_team": "Faroe Islands", "match_date": "2026-10-11", "market": "over25"}
        res = [{"match_date": "2026-10-12", "home_team": "Andorra", "away_team": "Faroe Islands", "home_score": 2, "away_score": 1, "source": "fotmob"}]
        r = m._find_result_strict(tip, res)
        self.assertIsNotNone(r)
        self.assertEqual((r["home_score"], r["away_score"]), (2, 1))

    def test_other_teams_not_matched(self):
        tip = {"home_team": "Andorra", "away_team": "Faroe Islands", "match_date": "2026-10-11"}
        res = [{"match_date": "2026-10-12", "home_team": "Spain", "away_team": "Faroe Islands", "home_score": 2, "away_score": 1}]
        self.assertIsNone(m._find_result_strict(tip, res))

if __name__ == "__main__":
    unittest.main()
