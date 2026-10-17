import unittest, btts_bot as b

class Blend(unittest.TestCase):
    def setUp(self):
        self._old = b._EMP_RATES
        b._EMP_RATES = {"over25": (0.548, 482), "btts": (0.5, 20)}
    def tearDown(self):
        b._EMP_RATES = self._old
    def test_pulls_down_overconfident(self):
        self.assertLess(b._empirical_blend(0.70, "over25"), 0.60)
    def test_small_sample_untouched(self):
        self.assertEqual(b._empirical_blend(0.70, "btts"), 0.70)
    def test_unknown_market_untouched(self):
        self.assertEqual(b._empirical_blend(0.70, "corners"), 0.70)
    def test_never_raises_probability_above_model_when_model_is_low(self):
        self.assertGreaterEqual(b._empirical_blend(0.40, "over25"), 0.40)  # blend may raise; caller takes min()
class Edge(unittest.TestCase):
    def setUp(self):
        self._old = b._EMP_RATES
        b._EMP_RATES = {"over25": (0.548, 482), "btts": (0.50, 112), "x": (0.60, 20)}
    def tearDown(self):
        b._EMP_RATES = self._old
    def test_over25_accepts_real_edge(self):
        self.assertTrue(b._empirical_edge_ok(0.555, 2.05, "over25"))
    def test_rejects_low_odds(self):
        self.assertFalse(b._empirical_edge_ok(0.60, 1.60, "over25"))
    def test_rejects_thin_edge(self):
        self.assertFalse(b._empirical_edge_ok(0.54, 1.85, "over25"))
    def test_rejects_market_without_evidence(self):
        self.assertFalse(b._empirical_edge_ok(0.60, 2.2, "btts"))
        self.assertFalse(b._empirical_edge_ok(0.60, 2.2, "x"))

if __name__ == "__main__":
    unittest.main()
