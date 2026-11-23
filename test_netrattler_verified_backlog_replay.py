"""Offline recovery of previously verified NETRATTLER settlements.

Nothing in this file may send an actual Telegram message or mark any
unknown/pending sporting outcome as win/loss/void.
"""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

import netrattler_settlement_v16_final as mod


def row(name, days_ago, *, state="win", raw=None):
    return {
        "settlement_id":name, "tip_id":name,"status":state,
        "market_group":"btts",
        "tip_date":(mod.TODAY-timedelta(days=days_ago)).isoformat(),
        "settled_at":mod.NOW.isoformat(),
        "tip_payload":{"telegram_msg_id":12345,"telegram_chat_id":"QA_ONLY",
                       "message_text":"Original verified ticket", "market":"btts"},
        "raw":raw or {},
    }


class BacklogSameOriginalMessageQA(unittest.TestCase):
    def _check(self, rows, env, limit="10"):
        calls=[]
        with patch.dict(os.environ,{
                "SETTLEMENT_TG_REPLAY_DAYS":"7",
                "SETTLEMENT_TG_BACKLOG_REPLAY_DAYS":env,
                "SETTLEMENT_TG_REPLAY_MAX":limit}), \
             patch.object(mod,"edit_original_tip",
                          side_effect=lambda r:calls.append(r["tip_id"]) or True), \
             patch.object(mod,"_save_tip_edit_receipt") as receipts, \
             patch.object(mod,"telegram_send",
                          side_effect=AssertionError("Forbidden new result post")):
            got=mod.retry_unedited_originals(rows,[])
        self.assertEqual(receipts.call_count,len(calls))
        return got,calls

    def test_bounded_backlog_only_with_verified_result(self):
        rows=[
            row("recent",2),
            row("backlog",75),
            row("too_old",160),
            row("pending",72,state="pending"),
            row("void_without_proof",76,state="void"),
            row("acknowledged",75,raw={"telegram_edit_ok":True}),
            row("expired",75,raw={"telegram_edit_attempts":2}),
            row("gone",75,raw={"telegram_edit_error":"-123 400 message to edit not found"}),
        ]
        (ok,attempts),calls=self._check(rows,"120")
        self.assertEqual((ok,attempts),(2,2))
        self.assertEqual(set(calls),{"recent","backlog"})

    def test_default_is_short_safe_replay(self):
        (ok,attempts),calls=self._check(
            [row("recent",2),row("old",75)],"0")
        self.assertEqual((ok,attempts),(1,1))
        self.assertEqual(calls,["recent"])

    def test_recent_tip_beats_old_backfill_with_newer_settled_at(self):
        # Production #45109371189 wasted 50 calls on September message IDs.
        # The real tip date must outrank a bulk backfill's recent settled_at.
        older=row("september_backfill",67)
        older["settled_at"]="2026-11-23T04:20:00+00:00"
        newest=row("recent_live_tip",1)
        newest["settled_at"]="2026-11-22T19:00:00+00:00"
        (ok,attempts),calls=self._check([older,newest],"120",limit="1")
        self.assertEqual((ok,attempts),(1,1))
        self.assertEqual(calls,["recent_live_tip"])

    def test_persistent_telegram_400_cannot_be_retried(self):
        (ok,attempts),calls=self._check([
            row("uneditable",1,raw={
                "telegram_edit_error":"400 message can't be edited"}),
            row("not_found",1,raw={
                "telegram_edit_error":"400 message to edit not found"}),
        ],"120")
        self.assertEqual((ok,attempts),(0,0))
        self.assertFalse(calls)


if __name__=="__main__":
    unittest.main(verbosity=2)
