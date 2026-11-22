"""Real temporary SQLite regression tests; no network, Git push, or Telegram."""
import datetime as dt
import os
import tempfile
import unittest
from unittest.mock import patch

import netrattler_lmg_store as store


class GoalHunterSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "LMG_SQLITE_PATH": os.path.join(self.temp.name, "data", "goal_hunter.sqlite3"),
            "LMG_SQLITE_SYNC": "false",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        store.init()
        self.fx = {"fixture_id": 123456, "home": "Home FC", "away": "Away FC",
                   "minute": 72, "hg": 1, "ag": 1, "source": "fotmob"}

    def test_reserve_send_settle_persists_and_rejects_duplicate(self):
        self.assertEqual(store.reserve_alert(self.fx, {"tier":"PREMIUM",
                        "next_goal_side":"home"}), "123456")
        self.assertIsNone(store.reserve_alert(self.fx, {"tier":"STANDARD"}))
        self.assertEqual(store.pending(), [])
        self.assertEqual(store.status()["alerts"], {"reserved":1})
        store.mark_sent("123456", 321123)
        rows = store.pending()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["telegram_message_id"], 321123)
        self.assertEqual(rows[0]["signal_tier"], "PREMIUM")
        with self.assertRaisesRegex(RuntimeError, "not_reserved"):
            store.mark_sent("123456", 9999)
        rows[0]["next_goal_result"] = "won"
        store.mark_settled(rows[0], (2,1), True)
        self.assertEqual(store.pending(), [])
        self.assertEqual(store.status()["alerts"], {"won":1})
        store.init()  # reopening must not erase rows
        self.assertEqual(store.status()["alerts"], {"won":1})
        self.assertIsNone(store.reserve_alert(self.fx))

    def test_original_crest_sources_survive_sqlite_state_and_schema_reinit(self):
        original={**self.fx,"home_logo_id":4201,
                  "away_logo_url":"https://a.espncdn.com/i/teamlogos/soccer/500/99.png"}
        with patch.dict(os.environ,{"LMG_OWNER_CLEAN_RELEASED":"1"}):
            self.assertEqual(store.reserve_alert(original),"123456")
        store.mark_sent("123456",918)
        before=store.pending()[0]
        self.assertEqual(before["message_kind"],"owner_clean_png")
        self.assertEqual(before["home_logo_source"],"4201")
        self.assertEqual(before["away_logo_source"],original["away_logo_url"])
        store.init()  # never discard existing team identity or card version
        after=store.pending()[0]
        self.assertEqual(after["message_kind"],"owner_clean_png")
        self.assertEqual(after["home_logo_source"],"4201")
        self.assertEqual(after["away_logo_source"],original["away_logo_url"])

    def test_shadow_deduplicated_and_correctly_settled(self):
        timestamp = dt.datetime.now(dt.timezone.utc)
        row = {"provider":"fotmob","fixture_id":123456,"slot":1,
               "collected_at":timestamp.isoformat(),
               "home":"Home FC","away":"Away FC","minute":72,
               "home_goals":1,"away_goals":1}
        a=store.write_snapshots([row],enabled=True,now=timestamp)
        b=store.write_snapshots([row],enabled=True,now=timestamp)
        self.assertEqual((a["inserted"], b["inserted"]),(1,0))
        self.assertEqual(len(store.pending_snapshots(timestamp)),1)
        self.assertEqual(store.settle_snapshot("fotmob",123456,(2,1),timestamp),1)
        self.assertEqual(store.settle_snapshot("fotmob",123456,(2,1),timestamp),0)
        self.assertEqual(store.pending_snapshots(timestamp),[])

    def test_reject_conflicts_and_capacity_limit(self):
        timestamp=dt.datetime.now(dt.timezone.utc)
        row={"provider":"fotmob","fixture_id":123456,"slot":1,
             "collected_at":timestamp.isoformat()}
        with self.assertRaisesRegex(ValueError,"conflicting_same_batch"):
            store.write_snapshots([row,{**row,"minute":80}],enabled=True,now=timestamp)
        with patch.object(store,"MAX_SHADOW_ROWS",0):
            outcome=store.write_snapshots([row],enabled=True,now=timestamp)
        self.assertEqual(outcome["status"],"capacity_limit")

    def test_failed_git_sync_never_looks_successful(self):
        with patch.dict(os.environ,{"LMG_SQLITE_SYNC":"true",
                                    "LMG_STATE_WORKTREE":self.temp.name}):
            with self.assertRaisesRegex(RuntimeError,"worktree_missing|unexpected_path"):
                store.reserve_alert({**self.fx,"fixture_id":777777})

    def test_api_daily_budget_and_one_hour_cooldown_are_persistent(self):
        start=dt.datetime(2026,11,19,0,0,tzinfo=dt.timezone.utc)
        self.assertTrue(store.reserve_source_calls("api_football",now=start))
        self.assertFalse(store.reserve_source_calls("api_football",
                         now=start+dt.timedelta(minutes=59)))
        for hour in range(1,12):
            self.assertTrue(store.reserve_source_calls("api_football",
                            now=start+dt.timedelta(hours=hour)))
        self.assertFalse(store.reserve_source_calls("api_football",
                         now=start+dt.timedelta(hours=12)))
        # UTC-day rollover permits new calls, without reusing yesterday's budget.
        self.assertTrue(store.reserve_source_calls("api_football",
                        now=start+dt.timedelta(days=1)))
        store.init()
        self.assertFalse(store.reserve_source_calls("api_football",
                         now=start+dt.timedelta(days=1,minutes=30)))

    def test_api_budget_invalid_requests_are_rejected(self):
        for kwargs in (
            {"source":"unknown"},
            {"source":"api_football","max_per_day":100},
            {"source":"api_football","cooldown_seconds":300},
            {"source":"api_football","count":0},
        ):
            with self.assertRaises(ValueError):
                store.reserve_source_calls(**kwargs)

    def test_no_supabase_required_for_local_sqlite(self):
        with patch.dict(os.environ,{"SUPABASE_URL":"","SUPABASE_KEY":"",
                                    "SUPABASE_SERVICE_ROLE_KEY":""}):
            self.assertEqual(store.reserve_alert(self.fx), "123456")
            store.mark_sent("123456",333)
            self.assertEqual(len(store.pending()),1)


if __name__=="__main__":
    unittest.main()
