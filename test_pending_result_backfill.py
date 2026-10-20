import unittest, netrattler_pending_result_backfill as m

class T(unittest.TestCase):
    def test_pair_and_day(self):
        row = {"tip_id": "over25_2026-10-10_94443", "message_text": "💎 <b>Burapha United vs Customs United</b>\n📍"}
        self.assertEqual(m.tip_pair(row), ("Burapha United", "Customs United"))
        self.assertEqual(m.tip_day(row), "2026-10-10")

    def test_team_match(self):
        self.assertTrue(m.team_match("Arsenal", "Arsenal FC"))
        self.assertTrue(m.team_match("Sao Luiz", "São Luiz"))
        self.assertFalse(m.team_match("Manchester United", "Manchester City"))

    def test_plan_and_select(self):
        tips = [{"tip_id": "over15_ht_2026-10-10_1", "market": "over15_ht", "message_text": "<b>Arsenal vs Leeds United</b>"}]
        p = m.plan(tips)
        self.assertEqual(set(p), {"2026-10-09", "2026-10-10", "2026-10-11"})
        rows = [{"home_team": "Arsenal", "away_team": "Leeds United"}, {"home_team": "Chelsea", "away_team": "Leeds United"}]
        sel = m.select_rows(rows, p["2026-10-10"])
        self.assertEqual(len(sel), 1)
        self.assertTrue(sel[0][1])

if __name__ == "__main__":
    unittest.main()
