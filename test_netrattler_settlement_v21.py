import importlib.util
import pathlib
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).resolve().parent / "netrattler_settlement_v16_final.py"
spec = importlib.util.spec_from_file_location("settlement_v21", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = ""
    def json(self):
        return self._payload

class SettlementV21Tests(unittest.TestCase):
    def test_similarity_normalizes_club_tokens(self):
        self.assertGreaterEqual(mod.similarity("FC Bayern München", "Bayern Munich"), 0.5)

    def test_stable_settlement_id(self):
        tip = {"id": 12, "_table": "tips", "match_date": "2026-07-01"}
        self.assertEqual(mod.stable_settlement_id(tip), mod.stable_settlement_id(tip))

    def test_combo_is_one_tip(self):
        tip = {"id": 1, "_table": "tips", "market_group": "combo", "match_date": "2026-07-01",
               "match": "A vs B", "total_odds": 3.0, "stake": 0.5,
               "legs": [{"match": "A vs B", "market": "BTTS"}]}
        result = {"home_team": "A", "away_team": "B", "home_score": 1, "away_score": 1, "match_date": "2026-07-01"}
        settled = mod.settle_tip(tip, [result], [])
        self.assertEqual(settled["status"], "win")
        self.assertEqual(settled["leg_count"], 1)
        self.assertAlmostEqual(settled["profit"], 1.0)

    def test_sofascore_parser(self):
        payload = {"events": [{"status": {"type": "finished"}, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
                                "homeScore": {"current": 2, "period1": 1}, "awayScore": {"current": 1, "period1": 0}}]}
        with patch.object(mod.requests, "get", return_value=FakeResponse(payload)):
            rows = mod._sofascore_results("2026-07-01")
        self.assertEqual((rows[0]["home_score"], rows[0]["away_score"]), (2, 1))

    def test_espn_parser(self):
        payload = {"events": [{"competitions": [{"status": {"type": {"completed": True, "state": "post"}}, "competitors": [
            {"homeAway": "home", "score": "3", "team": {"displayName": "Home"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "Away"}}]}]}]}
        with patch.object(mod.requests, "get", return_value=FakeResponse(payload)):
            rows = mod._espn_results("2026-07-01")
        self.assertEqual(rows[0]["_result_table"], "ESPN")
        self.assertEqual(rows[0]["home_score"], 3)

    def test_openligadb_parser(self):
        payload = [{"matchIsFinished": True, "team1": {"teamName": "A"}, "team2": {"teamName": "B"},
                    "matchResults": [{"resultTypeID": 2, "pointsTeam1": 1, "pointsTeam2": 2}]}]
        with patch.object(mod.requests, "get", return_value=FakeResponse(payload)):
            rows = mod._openligadb_results("2026-07-01")
        self.assertEqual(rows[0]["away_score"], 2)

if __name__ == "__main__":
    unittest.main()
