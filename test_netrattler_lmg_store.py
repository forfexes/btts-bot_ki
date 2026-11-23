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

    def test_deep_stats_persist_with_real_timestamp_and_no_supabase(self):
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        row={"provider":"fotmob","fixture_id":123456,
             "observed_at":now,"discovery_minute":70,
             "shots":20,"shots_on_target":7,"corners":5,
             "home_xg":1.15,"away_xg":0.71,
             "home_shots":12,"away_shots":8,"home_sot":5,"away_sot":2,
             "home_corners":3,"away_corners":2}
        with patch.dict(os.environ,{"SUPABASE_URL":"","SUPABASE_KEY":""}):
            a=store.write_deep_observations([row])
            b=store.write_deep_observations([row])
        self.assertEqual((a["inserted"],b["inserted"]),(1,0))
        with store._connect() as conn:
            got=conn.execute("SELECT * FROM deep_stats_observations").fetchone()
        self.assertEqual(got["discovery_minute"],70)
        self.assertEqual(got["shots"],20)
        self.assertEqual(got["shots_on_target"],7)
        self.assertEqual(got["home_xg"],1.15)
        self.assertEqual((got["home_shots"],got["away_shots"]),(12,8))
        self.assertEqual((got["home_sot"],got["away_sot"]),(5,2))
        self.assertEqual((got["home_corners"],got["away_corners"]),(3,2)
        store.init()
        with store._connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM deep_stats_observations").fetchone()[0],1)

    def test_deep_schema_migrates_without_erasing_existing_rows(self):
        import sqlite3
        with store._connect() as conn:
            conn.execute("DROP TABLE deep_stats_observations")
            conn.execute("""
              CREATE TABLE deep_stats_observations (
                provider TEXT, fixture_id INTEGER, observed_at TEXT,
                discovery_minute INTEGER, shots INTEGER, shots_on_target INTEGER,
                corners INTEGER, home_xg REAL, away_xg REAL,
                PRIMARY KEY(provider, fixture_id, observed_at)
              )
            """)
            conn.execute("""INSERT INTO deep_stats_observations
                VALUES ('fotmob',17,'2026-11-23T12:00:00+00:00',72,20,7,5,1.15,0.71)""")
        store.init()
        with store._connect() as conn:
            row=conn.execute("SELECT * FROM deep_stats_observations").fetchone()
        self.assertEqual(row["shots"],20)
        self.assertEqual(row["home_xg"],1.15)
        self.assertIsNone(row["home_shots"])
        self.assertIsNone(row["away_sot"])

    def test_deep_stats_batch_bound_is_enforced(self):
        with self.assertRaisesRegex(ValueError,"batch_exceeds_limit"):
            store.write_deep_observations([{}]*21)

    def test_no_supabase_required_for_local_sqlite(self):
        with patch.dict(os.environ,{"SUPABASE_URL":"","SUPABASE_KEY":"",
                                    "SUPABASE_SERVICE_ROLE_KEY":""}):
            self.assertEqual(store.reserve_alert(self.fx), "123456")
            store.mark_sent("123456",333)
            self.assertEqual(len(store.pending()),1)


if __name__=="__main__":
    unittest.main()
