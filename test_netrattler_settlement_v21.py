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

    def test_recovered_summary_preserves_scores_from_json_text(self):
        import json
        row = {
            "status": "loss", "market_group": "over25", "profit": -1.0,
            "match_result": json.dumps({
                "home_score": 1, "away_score": 0,
                "raw": {"home_score_ht": 0, "away_score_ht": 0},
            }),
        }
        summary = mod.format_direct_summary(row)
        self.assertIn("Full-Time Score: <b>1-0</b>", summary)
        self.assertIn("Half-Time Score: <b>0-0</b>", summary)
        self.assertIn("❌ X", summary)

    def test_rate_limited_edit_waits_for_telegram_and_retries(self):
        throttled = FakeResponse({"parameters": {"retry_after": 4}}, status=429)
        success = FakeResponse({"ok": True})
        with patch.object(mod, "TG_TOKEN", "test-token"), \
             patch.dict(os.environ, {"SETTLEMENT_TG_EDIT_GAP_SEC": "0"}), \
             patch.object(mod.requests, "post", side_effect=[throttled, success]) as post, \
             patch.object(mod.time, "sleep") as sleep:
            self.assertTrue(mod.telegram_edit("-1001", 55, "Original + ✅ V"))
        self.assertEqual(post.call_count, 2)
        sleep.assert_any_call(5)

    def test_idempotent_original_edit_counts_not_modified_as_success(self):
        unchanged = FakeResponse({}, status=400)
        unchanged.text = '{"description":"Bad Request: message is not modified"}'
        with patch.object(mod, "TG_TOKEN", "test-token"), \
             patch.dict(os.environ, {"SETTLEMENT_TG_EDIT_GAP_SEC": "0"}), \
             patch.object(mod.requests, "post", return_value=unchanged):
            self.assertTrue(mod.telegram_edit("-1001", 55, "Already settled"))

    def test_recover_recent_settled_originals_not_only_newly_closed(self):
        def old(tid, raw=None, mid=44):
            return {
                "settlement_id": tid, "status": "win", "market_group": "over25",
                "tip_date": mod.TODAY_S, "settled_at": mod.NOW.isoformat(),
                "raw": raw or {"result_source": "test"},
                "profit": 1.0, "reason": "Over 2.5",
                "tip_payload": {
                    "match": "A vs B", "message_text": "Original Tip",
                    "telegram_chat_id": "123", "telegram_msg_id": mid,
                },
            }
        needs_replay = old("retry-me")
        already_edited = old("done", {"telegram_edit_ok": True})
        no_message = old("no-message", mid=None)
        fresh = old("fresh")
        patch_log = []
        with patch.dict(os.environ, {"SETTLEMENT_TG_REPLAY_MAX": "10"}), \
             patch.object(mod, "edit_original_tip", return_value=True) as edit, \
             patch.object(mod, "sb_patch", side_effect=lambda *args: patch_log.append(args) or True):
            successes, attempted = mod.retry_unedited_originals(
                [needs_replay, already_edited, no_message, fresh], [fresh])
        self.assertEqual((successes, attempted), (1, 1))
        self.assertEqual(edit.call_count, 1)
        self.assertTrue(needs_replay["raw"]["telegram_edit_ok"])
        self.assertEqual(needs_replay["raw"]["telegram_edit_attempts"], 1)
        self.assertEqual(needs_replay["raw"]["result_source"], "test")
        self.assertEqual(len(patch_log), 1)

    def test_failed_edit_is_retryable_and_attempt_count_is_durable(self):
        row = {
            "settlement_id": "failed", "status": "loss", "market_group": "btts",
            "tip_date": mod.TODAY_S, "settled_at": mod.NOW.isoformat(),
            "raw": {"telegram_edit_attempts": 2},
            "tip_payload": {
                "match": "A vs B", "message_text": "Original",
                "telegram_chat_id": "123", "telegram_msg_id": 55,
            },
        }
        with patch.object(mod, "edit_original_tip", return_value=False), \
             patch.object(mod, "sb_patch", return_value=True):
            self.assertEqual(mod.retry_unedited_originals([row], []), (0, 1))
        self.assertEqual(row["raw"]["telegram_edit_attempts"], 3)
        self.assertFalse(row["raw"].get("telegram_edit_ok"))

    @staticmethod
    def _legacy_prop_builder(*, estimated=False, sent=True, message_id="321"):
        legs = [
            {"player": "Player A", "team": "A", "match": "A vs B",
             "league": "Test", "market": "1+ shots", "category": "shots",
             "line": 1, "odds": 1.72, "probability": 0.7, "source": "pinnacle"},
            {"player": "Player B", "team": "B", "match": "A vs B",
             "league": "Test", "market": "1+ SOT", "category": "sot",
             "line": 1, "odds": 1.75, "probability": 0.7, "source": "pinnacle"},
        ]
        return {
            "source": "NETRATTLER_BUILDER_ENGINE", "telegram_sent": sent,
            "telegram_msg_id": message_id,
            "builder_id": "old-master-builder",
            "style": "PLAYER PROP BUILDER", "variant": "2L",
            "market_group": "builder", "match_date": mod.TODAY_S,
            "estimated_odds": estimated, "total_odds": 0 if estimated else 3.01,
            "stake": 0 if estimated else 0.5,
            "leg_count": len(legs), "legs": legs,
        }

    def test_legacy_master_builder_text_can_be_recovered_with_real_legs(self):
        original = mod.recover_legacy_builder_text(self._legacy_prop_builder())
        self.assertIn("Player A", original)
        self.assertIn("Player B", original)
        self.assertIn("3.01", original)
        self.assertIn("\n", original)

    def test_legacy_same_game_builder_does_not_invent_combo_price(self):
        original = mod.recover_legacy_builder_text(self._legacy_prop_builder(estimated=True))
        self.assertIn("Player A", original)
        self.assertIn("live beim Bookmaker prüfen", original)
        self.assertNotIn("0.00", original)
        self.assertNotIn("Gesamt-Quote: <b>3.01", original)
        self.assertIn("\n", original)

    def test_unsent_or_unverified_legacy_builder_is_not_reconstructed(self):
        self.assertEqual(mod.recover_legacy_builder_text(self._legacy_prop_builder(sent=False)), "")
        self.assertEqual(mod.recover_legacy_builder_text(self._legacy_prop_builder(message_id="")), "")
        missing_leg = self._legacy_prop_builder()
        missing_leg["legs"][0].pop("source")
        self.assertEqual(mod.recover_legacy_builder_text(missing_leg), "")

    def test_legacy_builder_original_message_is_edited_with_result(self):
        payload = self._legacy_prop_builder()
        settlement = {
            "tip_id": payload["builder_id"], "status": "loss",
            "market_group": "builder", "profit": -0.5,
            "tip_payload": payload, "reason": "1 Leg verloren",
            "match_result": {"home_score": 1, "away_score": 0},
            "legs_payload": [
                {"status": "win", "leg": payload["legs"][0], "reason": "getroffen"},
                {"status": "loss", "leg": payload["legs"][1], "reason": "verfehlt"},
            ],
        }
        edits = []
        with patch.dict(mod.GROUPS, {"builder": "-100123"}), \
             patch.object(mod, "telegram_edit", side_effect=lambda *args: edits.append(args) or True), \
             patch.object(mod, "telegram") as send:
            self.assertTrue(mod.edit_original_tip(settlement))
        send.assert_not_called()
        self.assertEqual(edits[0][:2], ("-100123", "321"))
        self.assertIn("Player A", edits[0][2])
        self.assertIn("Player B", edits[0][2])
        self.assertIn("Leg-Auswertung", edits[0][2])
        self.assertIn("❌ X", edits[0][2])

    def test_legacy_builder_recovery_is_eligible_on_later_run(self):
        payload = self._legacy_prop_builder()
        old = {
            "settlement_id": "old-legacy-builder", "status": "win",
            "market_group": "builder", "tip_date": mod.TODAY_S,
            "settled_at": mod.NOW.isoformat(), "profit": 0.5,
            "tip_payload": payload, "raw": {},
        }
        with patch.object(mod, "edit_original_tip", return_value=True) as edit, \
             patch.object(mod, "sb_patch", return_value=True):
            self.assertEqual(mod.retry_unedited_originals([old], []), (1, 1))
        edit.assert_called_once()
        self.assertTrue(old["raw"]["telegram_edit_ok"])

    def test_recent_player_game_log_is_used_for_builder_settlement(self):
        tip = {
            "market_group": "builder", "match_date": mod.TODAY_S,
            "legs": [{"player": "Player A", "match": "A vs B",
                      "market": "1+ shots", "category": "shots", "line": 1}],
        }
        real_row = {
            "match_date": mod.TODAY_S, "player_name": "Player A",
            "home_team": "A", "away_team": "B", "shots": 2,
            "minutes": 90, "source": "confirmed-game-log",
        }
        queried = []
        def table_rows(table, params, **_kwargs):
            queried.append(table)
            return [dict(real_row)] if table == "player_game_log" else []
        with patch.object(mod, "sb_get_paged", side_effect=table_rows):
            rows = mod.load_player_stats([tip])
        self.assertIn("player_game_log", queried)
        self.assertEqual(len(rows), 1)
        leg = dict(tip["legs"][0], match_date=mod.TODAY_S)
        self.assertEqual(mod.settle_player_market(leg, rows, None)[0], "win")

    def test_player_stats_missing_metric_must_not_be_scored_zero(self):
        leg = {
            "match_date": mod.TODAY_S, "match": "A vs B",
            "player": "Player A", "market": "Shots 1+",
            "category": "shots", "line": 1,
        }
        missing = {
            "match_date": mod.TODAY_S, "player_name": "Player A",
            "home_team": "A", "away_team": "B", "sot": 2, "shots": None,
            "minutes": 80,
        }
        self.assertEqual(mod.settle_player_market(leg, [missing], None)[0], "pending")
        missing["shots"] = 0
        self.assertEqual(mod.settle_player_market(leg, [missing], None)[0], "loss")
        missing["minutes"] = 0
        self.assertEqual(mod.settle_player_market(leg, [missing], None)[0], "pending")

    def test_player_stats_require_exact_fixture_or_verifiable_match(self):
        leg = {
            "match_date": mod.TODAY_S, "match": "A vs B",
            "player": "Player A", "market": "Shots 1+",
            "category": "shots", "line": 1,
        }
        unverifiable = {
            "match_date": mod.TODAY_S, "player_name": "Player A",
            "shots": 2, "minutes": 90,
        }
        self.assertIsNone(mod.find_player_stat(leg, [unverifiable]))
        wrong_fixture = dict(unverifiable, home_team="C", away_team="D")
        self.assertIsNone(mod.find_player_stat(leg, [wrong_fixture]))

    def test_score_assist_needs_both_stats_to_declare_loss(self):
        leg = {
            "match_date": mod.TODAY_S, "match": "A vs B",
            "player": "Player A", "category": "score_assist",
            "market": "Goal or assist 1+", "line": 1,
        }
        row = {
            "match_date": mod.TODAY_S, "player_name": "Player A",
            "home_team": "A", "away_team": "B", "minutes": 90,
            "goals": 0, "assists": None,
        }
        self.assertEqual(mod.settle_player_market(leg, [row], None)[0], "pending")
        row["goals"] = 1
        self.assertEqual(mod.settle_player_market(leg, [row], None)[0], "win")
        row["goals"], row["assists"] = 0, 0
        self.assertEqual(mod.settle_player_market(leg, [row], None)[0], "loss")

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
