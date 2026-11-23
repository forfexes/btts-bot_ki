"""SportScore SQLite shadow: pure offline fixtures, retention and send-safety tests."""
from __future__ import annotations
import datetime as dt
import os
import tempfile
import unittest
from unittest.mock import patch

import netrattler_lmg_sportscore_shadow as sm
import netrattler_lmg_store as store
from netrattler_lmg_external_sources import sportscore_discovery_report


def sample():
    return {"matches":[
        {"home":"Test Home","away":"Test Away","home_score":"1","away_score":"0",
         "status":"live","status_text":"72'","time":"20:00",
         "competition":"Test League",
         "url":"https://sportscore.com/football/match/test-home-test-away/123/"},
        {"home":"Next Home","away":"Next Away","home_score":"-","away_score":"-",
         "status":"upcoming","status_text":"","time":"21:00",
         "url":"https://sportscore.com/football/match/next-upcoming/456/"},
    ]}


class FakeResponse:
    def raise_for_status(self):
        return None
    def json(self):
        return sample()


class SportScoreSQLiteShadowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{
            "LMG_SQLITE_PATH":self.temp.name+"/goal_hunter.sqlite3",
            "LMG_SQLITE_SYNC":"false",
            "LMG_SPORTSCORE_SHADOW":"true",
            "LMG_SEND":"false",
        })
        env.start()
        self.addCleanup(env.stop)
        store.init()
        self.now=dt.datetime(2026,11,23,19,0,tzinfo=dt.timezone.utc)

    def test_live_only_with_real_identity_but_no_guessed_clock(self):
        items=sm.live_rows(sample(),self.now.isoformat())
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["home"],"Test Home")
        self.assertEqual(items[0]["source_time_text"],"20:00")
        self.assertNotIn("minute",items[0])
        self.assertEqual((items[0]["home_goals"],items[0]["away_goals"]),(1,0))

    def test_no_send_even_if_inadvertently_enabled(self):
        with patch.dict(os.environ,{"LMG_SEND":"true"}):
            with self.assertRaisesRegex(RuntimeError,"never_telegram"):
                sm.collect(get=lambda *a,**k:FakeResponse())

    def test_source_host_is_strictly_verified(self):
        rows=sample()
        rows["matches"][0]["url"]="https://unrelated.example/football/match/id"
        self.assertEqual(sm.live_rows(rows,self.now.isoformat()),[])

    def test_collect_one_documented_request_no_external_calls(self):
        calls=[]
        def fetch(*a,**k):
            calls.append((a,k))
            return FakeResponse()
        health,fixtures=sm.collect(get=fetch,now=self.now)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0][0],sm.API_URL)
        self.assertEqual(health["total_matches"],2)
        self.assertEqual(health["live_matches"],1)
        self.assertEqual(len(fixtures),1)

    def test_live_score_and_heartbeat_saved_without_supabase(self):
        health,fixtures=sm.collect(get=lambda *a,**k:FakeResponse(),now=self.now)
        report=sm.save(health,fixtures,now=self.now)
        self.assertEqual(report["telegram_messages"],0)
        self.assertIn("SportScore",report["attribution"])
        with store._connect() as conn:
            heart=conn.execute("SELECT * FROM source_discovery_heartbeat").fetchone()
            live=conn.execute("SELECT * FROM source_live_fixtures").fetchone()
        self.assertEqual(heart["live_matches"],1)
        self.assertEqual(heart["total_matches"],2)
        self.assertEqual(live["home"],"Test Home")
        self.assertEqual(live["home_goals"],1)
        self.assertEqual(live["source_time_text"],"20:00")

    def test_empty_live_still_records_health_but_no_fake_fixtures(self):
        payload={"matches":[{**sample()["matches"][0],"status":"finished"}]}
        health=sportscore_discovery_report(payload)
        fixtures=sm.live_rows(payload,self.now.isoformat())
        self.assertEqual(fixtures,[])
        sm.save(health,fixtures,now=self.now)
        with store._connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM source_live_fixtures").fetchone()[0],0)
            self.assertEqual(conn.execute(
                "SELECT live_matches FROM source_discovery_heartbeat").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()
