import unittest
import netrattler_odds_harvester as h
import netrattler_keyless_odds as k

def offer(label, outs):
    return {"criterion": {"label": label}, "outcomes": outs}

class T(unittest.TestCase):
    def test_kambi_exact_combo(self):
        ev = {"id": 1, "homeName": "Alpha FC", "awayName": "Beta FC", "start": "2026-10-25T15:00:00Z"}
        offers = [offer("Both Teams To Score and Total Goals", [
            {"label": "Yes & Over 2.5", "type": "OT_UNTYPED", "odds": 2100, "status": "OPEN"},
            {"label": "No & Under 2.5", "type": "OT_UNTYPED", "odds": 3000, "status": "OPEN"}]),
            offer("Both Teams To Score", [{"type": "OT_YES", "odds": 1800, "status": "OPEN"}])]
        rows = h._kambi_rows("ub", ev, offers, "L")
        m = {(r["market"], r["selection"]): r["odds"] for r in rows}
        self.assertEqual(m[("btts_over_2_5", "yes")], 2.1)
        self.assertEqual(m[("btts", "yes")], 1.8)
        self.assertEqual(len([r for r in rows if r["market"] == "btts_over_2_5"]), 1)

    def test_kambi_ignores_half_and_other_lines(self):
        ev = {"id": 2, "homeName": "A FC", "awayName": "B FC", "start": "2026-10-25T15:00:00Z"}
        offers = [offer("Both Teams To Score and Total Goals 1st half", [{"label": "Yes & Over 2.5", "odds": 9000, "status": "OPEN"}]),
                  offer("Both Teams To Score and Total Goals", [{"label": "Yes & Over 3.5", "odds": 4000, "status": "OPEN"}])]
        self.assertEqual([r for r in h._kambi_rows("ub", ev, offers, "L") if r["market"].startswith("btts_over")], [])

    def test_bwin(self):
        self.assertEqual(k._bwin_market("Both Teams to Score and Total Goals", "Yes & Over 2.5", "a", "b"), ("btts_over_2_5", "yes", 2.5))
        self.assertIsNone(k._bwin_market("Both Teams to Score and Total Goals", "Yes & Over 3.5", "a", "b"))
        self.assertEqual(k._bwin_market("Both Teams to Score", "Yes", "a", "b"), ("btts", "yes", None))

if __name__ == "__main__":
    unittest.main()
