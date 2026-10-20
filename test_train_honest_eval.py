"""Offline: honest temporal holdout + no_skill flag + reported-only player labels."""
import os, unittest
import numpy as np, pandas as pd
os.environ.setdefault("NETRATTLER_XGB_ESTIMATORS", "40")
os.environ.setdefault("NETRATTLER_PLAYER_XGB_ESTIMATORS", "40")
import train_model as tm

def frame(n, signal):
    rng = np.random.default_rng(1)
    X = rng.normal(size=(n, len(tm.FEATURE_COLS)))
    p = 1 / (1 + np.exp(-(signal * X[:, 0])))
    df = pd.DataFrame(X, columns=tm.FEATURE_COLS)
    df["t"] = (rng.random(n) < p).astype(int)
    return df

class T(unittest.TestCase):
    def test_signal_has_skill(self):
        _, meta = tm.train_model(frame(3000, 2.0), "t", "unit_signal_model")
        self.assertFalse(meta["no_skill"])
        self.assertLess(meta["brier_score"], meta["base_brier"])
        self.assertEqual(meta["eval"], "temporal_holdout_20pct")

    def test_noise_flagged_no_skill(self):
        _, meta = tm.train_model(frame(3000, 0.0), "t", "unit_noise_model")
        self.assertTrue(meta["no_skill"])

    def test_player_label_only_where_reported(self):
        n = 600
        rng = np.random.default_rng(2)
        d = pd.DataFrame({c: rng.random(n) for c in tm.PLAYER_FEATURE_COLS})
        d["games_prior"] = 3
        d["tackles"] = rng.integers(0, 4, n).astype(float)
        d["tackles__reported"] = True
        d.loc[: n // 2, "tackles__reported"] = False   # half the rows: source did not report tackles
        d.loc[: n // 2, "tackles"] = 0.0               # ...and were zero-filled
        _, meta = tm.train_player_prop_model(d, "tackles", 0.5, "unit_tackles_model")
        self.assertLessEqual(meta["training_samples"], n - n // 2)
        self.assertGreater(meta["positive_rate"], 0.5)  # zero-filled rows no longer drag the rate down

if __name__ == "__main__":
    unittest.main()
