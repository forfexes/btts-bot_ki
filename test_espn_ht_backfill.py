import unittest, netrattler_espn_ht_backfill as m

def ev(done=True, h=(1, 2), a=(0, 1)):
    return {"competitions": [{"status": {"type": {"completed": done}}, "competitors": [
        {"homeAway": "home", "linescores": [{"value": h[0]}, {"value": h[1]}]},
        {"homeAway": "away", "linescores": [{"value": a[0]}, {"value": a[1]}]}]}]}

class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(m.ht_from_event(ev()), (1, 0))
    def test_not_completed(self):
        self.assertIsNone(m.ht_from_event(ev(done=False)))
    def test_missing_linescore(self):
        e = ev(); e["competitions"][0]["competitors"][0]["linescores"] = []
        self.assertIsNone(m.ht_from_event(e))

if __name__ == "__main__":
    unittest.main()
