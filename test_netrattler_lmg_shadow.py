"""Offline tests for bounded, non-betting shadow live-data collection."""
import datetime as dt
import unittest
from unittest.mock import Mock, patch

import netrattler_lmg_shadow as shadow


class ShadowSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.observed=dt.datetime(2026,11,18,19,17,tzinfo=dt.timezone.utc)
        self.fx={"source":"fotmob","fixture_id":6148609,"minute":77,
                 "kickoff":self.observed-dt.timedelta(minutes=80),
                 "home":"BK Häcken (W)","away":"Manchester City (W)",
                 "hg":0,"ag":1}
        self.stats={"shots":25,"sot":10,"corners":4,
                    "teams":{"home":{"shots":6,"sot":1,"corners":0},
                             "away":{"shots":19,"sot":9,"corners":4}}}

    def test_real_live_observation_and_baseline(self):
        r=shadow.build_snapshot(self.fx,self.stats,"fotmob",self.observed)
        self.assertEqual(r["slot"],2)
        self.assertEqual(r["fixture_id"],6148609)
        self.assertEqual(r["baseline_send"],True)
        self.assertEqual(r["data_provider"],"fotmob")
        self.assertEqual(r["home_shots"],6)
        self.assertEqual(r["away_sot"],9)
        self.assertEqual(r["collected_at"],self.observed.isoformat())
        self.assertIsNone(r["candidate_send"])
        self.assertIsNone(r["home_xg"])

    def test_missing_live_stats_remain_missing_not_zero(self):
        r=shadow.build_snapshot(self.fx,None,observed_at=self.observed)
        self.assertFalse(r["stats_available"])
        self.assertIsNone(r["baseline_send"])
        self.assertIsNone(r["home_shots"])
        self.assertIsNone(r["data_provider"])

    def test_if_both_xg_appears_capture_both_only(self):
        rows=self.stats | {"teams":{
            "home":{**self.stats["teams"]["home"],"xg":0.62},
            "away":{**self.stats["teams"]["away"],"xg":2.57}}}
        r=shadow.build_snapshot(self.fx,rows,"fotmob",self.observed)
        self.assertEqual(r["away_xg"],2.57)
        del rows["teams"]["away"]["xg"]
        r=shadow.build_snapshot(self.fx,rows,"fotmob",self.observed)
        self.assertIsNone(r["home_xg"])
        self.assertIsNone(r["away_xg"])

    def test_below_premium_remains_baseline_standard(self):
        rows={"shots":13,"sot":5,"teams":{
              "home":{"shots":5,"sot":2},"away":{"shots":8,"sot":3}}}
        r=shadow.build_snapshot(self.fx,rows,"fotmob",self.observed)
        self.assertTrue(r["baseline_send"])
        self.assertIsNone(r["candidate_send"])

    def test_no_fabricated_espn_stats_or_crosswalk(self):
        r=shadow.build_snapshot(self.fx,self.stats,"espn",self.observed)
        self.assertEqual(r["provider"],"fotmob")
        self.assertEqual(r["data_provider"],"espn")
        with self.assertRaisesRegex(ValueError,"provider_proof"):
            shadow.build_snapshot(self.fx,self.stats,None,self.observed)
        with self.assertRaisesRegex(ValueError,"unverified_provider"):
            shadow.build_snapshot(self.fx,self.stats,"besoccer",self.observed)

    def test_conflicting_totals_and_impossible_shots_rejected(self):
        with self.assertRaisesRegex(ValueError,"totals_conflict"):
            shadow.build_snapshot(self.fx,{**self.stats,"shots":99},"fotmob",self.observed)
        fake={**self.stats, "teams":{
            "home":{**self.stats["teams"]["home"],"sot":20},
            "away":self.stats["teams"]["away"]}}
        with self.assertRaisesRegex(ValueError,"impossible_live_shot"):
            shadow.build_snapshot(self.fx,fake,"fotmob",self.observed)

    def test_wrong_minute_identity_and_naive_time_rejected(self):
        for minute in (64,86):
            with self.assertRaisesRegex(ValueError,"invalid_live_minute"):
                shadow.build_snapshot({**self.fx,"minute":minute},None,observed_at=self.observed)
        with self.assertRaisesRegex(ValueError,"timezone_required"):
            shadow.build_snapshot({**self.fx,"kickoff":dt.datetime(2026,11,18,18)},None,
                                  observed_at=self.observed)
        with self.assertRaisesRegex(ValueError,"kickoff_out_of_range"):
            shadow.build_snapshot({**self.fx,"kickoff":self.observed-dt.timedelta(days=3)},
                                  None,observed_at=self.observed)

    def test_maximum_four_snapshots_and_stable_bins(self):
        self.assertEqual([shadow.build_snapshot({**self.fx,"minute":n},
             None,observed_at=self.observed)["slot"] for n in (65,70,75,80,85)],
             [0,1,2,3,3])

    def test_disabled_never_calls_database(self):
        with patch.object(shadow,"_database",side_effect=AssertionError("database called")):
            self.assertEqual(shadow.write_snapshots([{}])["status"],"disabled")
            self.assertEqual(shadow.settle_snapshots()["status"],"disabled")

    def test_idempotent_insert_and_retention(self):
        row=shadow.build_snapshot(self.fx,self.stats,"fotmob",self.observed)
        ok=Mock()
        get_response=Mock(headers={"Content-Range":"0-0/2"})
        with patch.object(shadow,"_database",return_value=("https://db/test",{})), \
             patch.object(shadow.requests,"delete",return_value=ok) as delete, \
             patch.object(shadow.requests,"get",return_value=get_response), \
             patch.object(shadow.requests,"post",return_value=ok) as post:
            result=shadow.write_snapshots([row],enabled=True,now=self.observed)
        self.assertEqual(result["status"],"saved")
        self.assertEqual(result["existing"],2)
        self.assertIn("ignore-duplicates",post.call_args.kwargs["headers"]["Prefer"])
        self.assertEqual(post.call_args.kwargs["json"],[row])
        self.assertEqual(post.call_args.kwargs["params"]["on_conflict"],
                         "provider,fixture_id,slot")
        self.assertIn("collected_at",delete.call_args.kwargs["params"])

    def test_full_storage_skips_write(self):
        row=shadow.build_snapshot(self.fx,None,observed_at=self.observed)
        ok=Mock()
        get_response=Mock(headers={"Content-Range":"0-0/4500"})
        with patch.object(shadow,"_database",return_value=("https://db/test",{})), \
             patch.object(shadow.requests,"delete",return_value=ok), \
             patch.object(shadow.requests,"get",return_value=get_response), \
             patch.object(shadow.requests,"post",side_effect=AssertionError("write forbidden")):
            result=shadow.write_snapshots([row],enabled=True,now=self.observed)
        self.assertEqual(result["status"],"capacity_limit")

    def test_batch_duplicate_mismatch_refused(self):
        row=shadow.build_snapshot(self.fx,None,observed_at=self.observed)
        another=dict(row,home_goals=7)
        with self.assertRaisesRegex(ValueError,"conflicting_same_batch"):
            shadow.write_snapshots([row,another],enabled=True)
        with self.assertRaisesRegex(ValueError,"exceeds_maximum"):
            shadow.write_snapshots([row]*17,enabled=True)

    def test_final_result_only_exact_verified_fixture(self):
        row=shadow.build_snapshot(self.fx,self.stats,"fotmob",self.observed)
        feed={"leagues":[{"matches":[{
            "id":6148609,"home":{"name":self.fx["home"],"score":0},
            "away":{"name":self.fx["away"],"score":2},
            "status":{"finished":True,"cancelled":False,"scoreStr":"0 - 2",
                      "utcTime":self.fx["kickoff"].isoformat()}}]}]}
        self.assertEqual(shadow._finished(feed,row),(0,2))
        feed["leagues"][0]["matches"][0]["away"]["name"]="Different"
        self.assertIsNone(shadow._finished(feed,row))
        feed["leagues"][0]["matches"][0]["away"]["name"]=self.fx["away"]
        feed["leagues"][0]["matches"][0]["status"]["finished"]=False
        self.assertIsNone(shadow._finished(feed,row))

if __name__=="__main__":
    unittest.main()
