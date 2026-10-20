import unittest, netrattler_settlement_v16_final as m

class T(unittest.TestCase):
    def test_const(self):
        self.assertEqual(m.MAX_SINGLE_ODDS, 100.0)
        self.assertEqual(m.MAX_COMBO_ODDS, 2000.0)

if __name__ == "__main__":
    unittest.main()
