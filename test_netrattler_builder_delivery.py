#!/usr/bin/env python3
"""Offline regression: Telegram delivery must be reflected in stored builders."""
import json
import unittest
from unittest.mock import patch
import netrattler_builder_engine as engine


class _Get:
    ok = True
    def __init__(self, rows=None):
        self.rows = [] if rows is None else rows
    def json(self):
        return self.rows


class _Post:
    status_code = 201


class BuilderDeliveryTests(unittest.TestCase):
    def setUp(self):
        leg_a = engine.PropLeg("Player A", "A", "A vs B", "Test", "1+ shots", "shots",
                               .5, 1.72, .70, "kambi")
        leg_b = engine.PropLeg("Player B", "B", "A vs B", "Test", "1+ SOT", "sot",
                               .5, 1.75, .69, "kambi")
        self.pick = engine.BuilderPick("delivery-test", "TEST", "2L", [leg_a, leg_b],
                                       3.01, .1, False, "2026-10-16")
        self.rows = []

    def _run(self, result, *, existing=None):
        def save(*args, **kwargs):
            self.rows.append(json.loads(kwargs["data"]))
            return _Post()
        with (patch.object(engine, "deduplicate_props", return_value=[]),
              patch.object(engine, "build_builder_picks", return_value=[self.pick]),
              patch.object(engine.requests, "get", return_value=_Get(existing)),
              patch.object(engine.requests, "post", side_effect=save)):
            sent, _ = engine.run_builder_engine([], lambda _: result,
                                                supabase_url="https://supabase.invalid",
                                                supabase_key="test")
        return sent

    def test_numeric_message_id_is_recorded(self):
        self.assertEqual(self._run(12345), 1)
        self.assertEqual(len(self.rows), 1)
        self.assertIs(self.rows[0]["telegram_sent"], True)
        self.assertEqual(self.rows[0]["telegram_msg_id"], "12345")

    def test_telegram_api_result_records_chat_and_message(self):
        self.assertEqual(self._run({"ok": True, "result": {"message_id": 87,
                             "chat": {"id": -10012}}}), 1)
        self.assertEqual(self.rows[0]["telegram_chat_id"], "-10012")
        self.assertEqual(self.rows[0]["telegram_msg_id"], "87")

    def test_sent_builder_persists_original_editable_text_and_fallback_chat(self):
        with patch.dict(engine.os.environ, {"TELEGRAM_GROUP_BUILDER": "-10042"}):
            self.assertEqual(self._run(12345), 1)
        stored = self.rows[0]
        self.assertEqual(stored["telegram_msg_id"], "12345")
        self.assertEqual(stored["telegram_chat_id"], "-10042")
        self.assertIn("Player A", stored["message_text"])
        self.assertTrue(any(label in stored["message_text"] for label in ("Builder-Quote", "Gesamt-Quote")))

    def test_declined_or_missing_send_never_saves(self):
        for result in (None, False, 0, {"ok": False, "description": "blocked"},
                       {"ok": True, "result": {}}):
            with self.subTest(result=result):
                self.rows.clear()
                self.assertEqual(self._run(result), 0)
                self.assertEqual(self.rows, [])

    def test_existing_builder_is_not_resent(self):
        self.assertEqual(self._run(12345, existing=[{"builder_id": "delivery-test"}]), 0)
        self.assertEqual(self.rows, [])

    def test_old_direct_persist_does_not_claim_telegram_delivery(self):
        with (patch.object(engine.requests, "get", return_value=_Get()),
              patch.object(engine.requests, "post", side_effect=lambda *a, **kw:
                           self.rows.append(json.loads(kw["data"])) or _Post())):
            self.assertTrue(engine.persist_builder_pick(self.pick,
                            "https://supabase.invalid", "test"))
        self.assertFalse(self.rows[0].get("telegram_sent", False))


    def test_database_lookup_failure_blocks_duplicate_risk(self):
        class _FailedGet:
            ok = False
        with (patch.object(engine, "deduplicate_props", return_value=[]),
              patch.object(engine, "build_builder_picks", return_value=[self.pick]),
              patch.object(engine.requests, "get", return_value=_FailedGet()),
              patch.object(engine.requests, "post") as post):
            sent, _ = engine.run_builder_engine([], lambda _: 12345,
                          supabase_url="https://supabase.invalid", supabase_key="test")
        self.assertEqual(sent, 0)
        post.assert_not_called()

    def test_boolean_success_is_not_a_telegram_receipt(self):
        self.assertEqual(self._run(True), 0)
        self.assertEqual(self.rows, [])

    def test_alternate_real_props_add_distinct_builders(self):
        props = [
            engine.PropLeg(f"Player {i}", "Home", "Home vs Away",
                "Example League", "shots 1+", "shots" if i % 2 else "sot",
                1.0, 1.60, 0.72, "pinnacle", quality=0.8 - 0.01 * i,
                edge=1.5)
            for i in range(6)
        ]
        picks = engine._alternate_real_prop_builders(props, "2026-10-16")
        self.assertGreaterEqual(len(picks), 4)
        self.assertEqual(len({p.builder_id for p in picks}), len(picks))
        for pick in picks:
            self.assertEqual(len({leg.player for leg in pick.legs}), pick.leg_count)
            self.assertFalse(pick.estimated_odds)
            self.assertTrue(all(leg.source == "pinnacle" for leg in pick.legs))
            self.assertLessEqual(pick.total_odds, 18.0)

    def test_alternate_ignores_estimated_and_negative_edge(self):
        props = [
            engine.PropLeg(f"Player {i}", "Home", "Home vs Away",
                "Example League", "shots", "shots", 1.0, 1.6, 0.72,
                "pinnacle", quality=0.7, estimated=(i == 1),
                edge=-1 if i == 2 else 1)
            for i in range(3)
        ]
        self.assertEqual(engine._alternate_real_prop_builders(props, "2026-10-16"), [])


if __name__ == "__main__":
    unittest.main()
