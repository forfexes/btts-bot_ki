import importlib.util
import pathlib
import unittest
import os
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

    def test_builder_team_markets_settle_from_enriched_match_stats(self):
        result = {
            "home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1,
            "match_date": "2026-07-01",
            "raw": {
                "home_corners": 7, "away_corners": 4,
                "home_cards": 2, "away_cards": 1,
                "home_shots": 15, "away_shots": 8,
                "home_sot": 6, "away_sot": 3,
                "home_score_ht": 1, "away_score_ht": 0,
            },
        }
        checks = [
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "A", "market": "Team Corners 5+", "category": "team_corners", "line": 5}, "win"),
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "Total", "market": "Match Corners 10+", "category": "match_corners", "line": 10}, "win"),
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "Both Teams", "market": "Both Teams to Receive a Card", "category": "team_cards", "line": 1}, "win"),
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "Total", "market": "Match SOT 8+", "category": "match_sot", "line": 8}, "win"),
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "Total", "market": "2nd Half Goals 2+", "category": "half_goals_2nd", "line": 2}, "win"),
            ({"match": "A vs B", "match_date": "2026-07-01", "player": "1X", "market": "Double Chance 1X", "category": "double_chance", "line": 0.5}, "win"),
        ]
        for leg, expected in checks:
            with self.subTest(category=leg["category"]):
                status, _ = mod.settle_player_market(leg, [], result)
                self.assertEqual(status, expected)

    def test_multi_combo_summary_keeps_all_eleven_legs(self):
        settlement = {
            "status": "win", "market_group": "combo_multi", "profit": 2.0,
            "match_result": {},
            "legs_payload": [
                {"status": "win", "leg": {"market": f"Leg {i}"}, "reason": "ok"}
                for i in range(1, 12)
            ],
        }
        text = mod.format_direct_summary(settlement)
        self.assertIn("Leg 11", text)

    def test_sofascore_parser(self):
        payload = {"events": [{"status": {"type": "finished"}, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
                                "homeScore": {"current": 2, "period1": 1}, "awayScore": {"current": 1, "period1": 0}}]}
        with patch.object(mod, "RESULT_USE_SOFASCORE", True), \
             patch.object(mod.requests, "get", return_value=FakeResponse(payload)):
            rows = mod._sofascore_results("2026-07-01")
        self.assertEqual((rows[0]["home_score"], rows[0]["away_score"]), (2, 1))

    def test_same_post_success_edits_original_with_vx_result(self):
        settlement = {
            "tip_id": "t-success", "status": "win", "market_group": "btts",
            "profit": 0.8, "profit_units": 0.8, "reason": "BTTS getroffen",
            "tip_payload": {
                "market": "btts", "match": "A vs B",
                "telegram_chat_id": "123", "telegram_msg_id": 44,
                "message_text": "Original tip",
            },
            "match_result": {"home_score": 1, "away_score": 1, "raw": {}},
        }
        calls = []
        def fake_edit(chat_id, message_id, text):
            calls.append((str(chat_id), int(message_id), text))
            return True
        with patch.dict(os.environ, {"SETTLEMENT_ALLOW_SEPARATE_RESULT_UPDATE": "false"}), \
             patch.dict(mod.GROUPS, {"btts": "123"}), \
             patch.object(mod, "telegram_edit", side_effect=fake_edit), \
             patch.object(mod, "telegram", return_value=True) as send_mock:
            self.assertTrue(mod.edit_original_tip(settlement))
            send_mock.assert_not_called()
        self.assertEqual(calls[0][0:2], ("123", 44))
        self.assertIn("Original tip", calls[0][2])
        self.assertTrue("✅" in calls[0][2] or " V" in calls[0][2])

    def test_same_post_default_does_not_send_separate_result(self):
        settlement = {
            "tip_id": "t-1", "status": "win", "market_group": "btts",
            "profit": 0.8, "profit_units": 0.8, "reason": "BTTS getroffen",
            "tip_payload": {
                "market": "btts", "match": "A vs B",
                "telegram_chat_id": "123", "telegram_msg_id": 44,
                "message_text": "Original tip",
            },
            "match_result": {"home_score": 1, "away_score": 1, "raw": {}},
        }
        with patch.dict(os.environ, {"SETTLEMENT_ALLOW_SEPARATE_RESULT_UPDATE": "false"}), \
             patch.dict(mod.GROUPS, {"btts": "123"}), \
             patch.object(mod, "telegram_edit", return_value=False), \
             patch.object(mod, "telegram", return_value=True) as send_mock:
            self.assertFalse(mod.edit_original_tip(settlement))
            send_mock.assert_not_called()

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
