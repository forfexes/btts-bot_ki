import unittest, netrattler_settlement_v16_final as m

class T(unittest.TestCase):
    def test_const(self):
        self.assertEqual(m.MAX_SINGLE_ODDS, 100.0)
        self.assertEqual(m.MAX_COMBO_ODDS, 2000.0)
        self.assertEqual(m.MAX_OVER15_HT_ODDS, 4.5)

    def test_builder_labels(self):
        pl = {"legs": [{"match": "A vs B", "player": "X", "category": "shots", "line": 1}]}
        st = {"tip_payload": pl}
        self.assertEqual(m.match_label(st), "A vs B")
        self.assertEqual(m.report_market_text(pl), "X shots O1")


if __name__ == "__main__":
    unittest.main()
