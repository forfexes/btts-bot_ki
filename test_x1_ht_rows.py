import unittest
import netrattler_keyless_odds as k

class T(unittest.TestCase):
    def test_ht_rows(self):
        g = {"I": 5, "O1": "Alpha FC", "O2": "Beta FC", "S": 1900000000, "L": "L"}
        sub = {"GE": [{"G": 4, "E": [[{"T": 9, "P": 1.5, "C": 2.7}], [{"T": 10, "P": 1.5, "C": 1.45}]]},
                      {"G": 21, "E": [[{"T": 180, "C": 3.1}, {"T": 181, "C": 1.35}]]},
                      {"G": 1, "E": [[{"T": 1, "C": 2.0}]]}]}
        rows = k._x1_ht_rows(g, sub, "https://22bet.com")
        m = {(r["market"], r["selection"]): r["odds"] for r in rows}
        self.assertEqual(m, {("totals_ht_1_5", "over_1_5"): 2.7, ("totals_ht_1_5", "under_1_5"): 1.45,
                             ("btts_ht", "yes"): 3.1, ("btts_ht", "no"): 1.35})
    def test_placeholder_teams_skipped(self):
        self.assertEqual(k._x1_ht_rows({"O1": "Home", "O2": "Away"}, {"GE": []}, "https://22bet.com"), [])

if __name__ == "__main__":
    unittest.main()
