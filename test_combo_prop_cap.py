import unittest, btts_bot as b

T = lambda m, mt, o, p: {"match": m, "market": mt, "odds": o, "probability": p, "tip": "x"}

class C(unittest.TestCase):
    def test_one_prop_leg_max(self):
        tips = [T(f"A{i} vs B{i}", "shots", 1.5, 90) for i in range(6)] + [T(f"C{i} vs D{i}", "over25", 1.9, 60) for i in range(4)]
        c = b.generate_multi_combo_bets(tips, 4)
        self.assertEqual(sum(1 for x in c["tips"] if x["market"] == "shots"), 0)
        self.assertTrue(all(x["market"] == "over25" for x in c["tips"]))

    def test_only_allowed_markets(self):
        tips = [T(f"M{i} vs N{i}", m, 1.8, 70) for i, m in enumerate(["1x2", "over25", "corners", "btts", "scorer", "btts_ht", "over15_ht", "combo"])]
        c = b.generate_multi_combo_bets(tips, 4)
        self.assertEqual({x["market"] for x in c["tips"]}, {"1x2", "over25", "corners", "btts"})
        self.assertIsNone(b.generate_multi_combo_bets(tips, 5))

    def test_name_not_duplicated(self):
        s = "Carlos Romero — Carlos Romero shots (Settled using Opta data) | Player's shots (Settled using Opta data) | Player Occurrence Line Over 0.5"
        self.assertEqual(b._clean_combo_leg_text(s), "Carlos Romero — Schüsse Über 0.5")

if __name__ == "__main__":
    unittest.main()
