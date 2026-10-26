import os, unittest
import netrattler_builder_guard as g

def row(**k):
    r = {"player": "Test Spieler", "market": "Player Shots Over 0.5", "category": "shots", "line": 0.5, "odds": 1.5,
         "match": "A vs B", "source": "kambi_ub", "probability": 0.8}
    r.update(k); return r

class T(unittest.TestCase):
    def setUp(self):
        os.environ.pop('NETRATTLER_BUILDER_ALLOW_UNMODELLED', None)
    def test_unmodelled_player_leg_rejected(self):
        self.assertIsNone(g.normalize_prop_safe(row()))
    def test_modelled_leg_accepted(self):
        leg = g.normalize_prop_safe(row(model_prob=0.80, probability=0.80, probability_source="player_history"))
        self.assertIsNotNone(leg); self.assertGreater(leg.edge, 0)
    def test_garbage_player_label(self):
        self.assertTrue(g._is_generic_player_label("Same amount of goals"))
        self.assertTrue(g._is_generic_player_label("Chase Adams Player's"))
        self.assertFalse(g._is_generic_player_label("Mamadou Sangare"))
if __name__ == "__main__":
    unittest.main()
