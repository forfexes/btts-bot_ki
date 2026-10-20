import unittest
from datetime import datetime, timezone
import netrattler_model_quality as q

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
M = lambda **k: {"brier_score": 0.2374, "positive_rate": 0.504, "roc_auc": 0.62, "trained_at": "2026-10-18T10:00:00+00:00", **k}

class T(unittest.TestCase):
    def test_good(self):
        self.assertEqual(q.model_has_skill(M(), NOW), (True, "ok"))
    def test_json_string_meta(self):
        import json
        self.assertTrue(q.model_has_skill(json.dumps(json.dumps(M())), NOW)[0])
    def test_worse_than_base(self):  # btts_ht_model on 2026-10-18: 0.1586 vs base 0.1539
        ok, why = q.model_has_skill(M(brier_score=0.1586, positive_rate=0.19, roc_auc=0.642), NOW)
        self.assertFalse(ok); self.assertIn("not better", why)
    def test_leakage_auc(self):
        self.assertFalse(q.model_has_skill(M(brier_score=0.0281, positive_rate=0.067, roc_auc=0.955), NOW)[0])
    def test_stale(self):
        self.assertFalse(q.model_has_skill(M(trained_at="2026-07-16T16:00:59+00:00"), NOW)[0])
    def test_no_skill_flag(self):
        self.assertFalse(q.model_has_skill(M(no_skill=True), NOW)[0])
    def test_no_meta_is_legacy_allowed(self):
        self.assertTrue(q.model_has_skill(None, NOW)[0])


class PlayerLoaderGate(unittest.TestCase):
    def test_no_skill_player_model_rejected_and_not_retried(self):
        import base64, io, json, pickle
        import netrattler_ml_player as ml
        ml._MODEL_CACHE.clear(); ml._REJECTED.clear()
        buf = io.BytesIO(); pickle.dump({"model": object()}, buf)
        blob = base64.b64encode(buf.getvalue()).decode()
        good = json.dumps({"brier_score": 0.1461, "positive_rate": 0.204, "roc_auc": 0.742, "trained_at": datetime.now(timezone.utc).isoformat()})
        bad = json.dumps({"brier_score": 0.0563, "positive_rate": 0.059, "roc_auc": 0.667, "trained_at": datetime.now(timezone.utc).isoformat()})
        metas = {"player_shots_over15_model": good, "player_assist_over05_model": bad}
        calls = []
        class R:
            ok = True; status_code = 200; text = ""
            def __init__(self, rows): self._r = rows
            def json(self): return self._r
        def get(url, headers=None, params=None, timeout=None):
            calls.append(params.get("model_name"))
            f = params.get("model_name", "")
            names = f[3:].strip("()").split(",") if f.startswith("in.") else [f[3:]]
            return R([{"model_name": n, "model_data": blob, "meta": metas[n]} for n in names])
        orig = ml.requests.get
        ml.requests.get = get
        try:
            n = ml.load_player_models("https://x.supabase.co", "k", model_names=list(metas), batch_size=2)
            self.assertEqual(n, 1)
            self.assertIn("player_assist_over05_model", ml.player_model_load_status()["rejected"])
            before = len(calls)
            ml.load_player_models("https://x.supabase.co", "k", model_names=list(metas), batch_size=2)
            self.assertEqual(len(calls), before)  # rejected model is not re-downloaded
        finally:
            ml.requests.get = orig
            ml._MODEL_CACHE.clear(); ml._REJECTED.clear()


if __name__ == "__main__":
    unittest.main()
