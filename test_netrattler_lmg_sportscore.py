"""SportScore football widget: strict offline parser regression tests.

No network, Telegram, Supabase, or persistent database access.
"""
import unittest

from netrattler_lmg_external_sources import (
    parse_sportscore, sportscore_discovery_report, pair_exact, provider_enabled
)

def event(**overrides):
    row={"home":"Demo United","away":"Demo City",
         "home_score":"1","away_score":"1",
         "status":"live","status_text":"72'",
         "time":"2026-11-23T18:00:00+00:00",
         "competition":"Demo League",
         "url":"https://sportscore.com/football/match/demo-united-vs-demo-city/xyz/"}
    row.update(overrides)
    return row

class SportScoreOfflineTests(unittest.TestCase):
    def test_exact_real_schema_one_qualified_fixture(self):
        found=parse_sportscore({"matches":[event()]})
        self.assertEqual(len(found),1)
        row=found[0]
        self.assertEqual(row["source"],"sportscore")
        self.assertEqual((row["hg"],row["ag"],row["minute"]),(1,1,72))
        self.assertEqual(row["league"],"Demo League")
        self.assertEqual(row["source_fixture_id"],
                         "football/match/demo-united-vs-demo-city/xyz")
        self.assertEqual(row["kickoff"].utcoffset().total_seconds(),0)

    def test_never_guess_clock_or_timezone_or_outside_host(self):
        cases=[
            {"status_text":"2nd half"},
            {"status_text":None},
            {"time":"2026-11-23 18:00:00"},
            {"time":"18:00"},
            {"url":"https://other.example/football/match/foo"},
            {"url":"/other/match/foo"},
            {"url":""},
            {"home_score":"--"},
            {"away_score":"1:0"},
            {"home":"Demo City"},
            {"status":"finished"},
            {"status_text":"86'"},
        ]
        for change in cases:
            with self.subTest(change=change):
                self.assertEqual(parse_sportscore({"matches":[event(**change)]}),[])

    def test_public_api_may_have_no_live_or_full_identity(self):
        payload={"matches":[
            event(status="finished",status_text="FT"),
            event(status="upcoming",status_text=""),
            event(status_text="Second half"),
            event(),
        ]}
        report=sportscore_discovery_report(payload)
        self.assertEqual(report["total_matches"],4)
        self.assertEqual(report["live_matches"],2)
        self.assertEqual(report["with_explicit_clock"],1)
        self.assertEqual(report["strictly_matchable"],1)
        self.assertEqual(report["telegram_messages"],0)
        self.assertEqual(report["sqlite_writes"],0)

    def test_attribution_not_wired_to_telegram(self):
        report=sportscore_discovery_report({"matches":[]})
        self.assertEqual(report["attribution_url"],"https://sportscore.com/")
        self.assertEqual(report["telegram_messages"],0)
        self.assertFalse(provider_enabled("sportscore",{"LMG_EXTERNAL_SOURCES_SHADOW":"true"}))

    def test_pair_requires_exact_time_score_clock_and_unique_primary(self):
        secondary=parse_sportscore({"matches":[event()]})
        fx=dict(secondary[0])
        fx["fixture_id"]=987654321
        self.assertEqual(pair_exact([fx],secondary)["paired"][0]["fotmob_id"],987654321)
        self.assertEqual(pair_exact([{**fx,"hg":2}],secondary)["paired"],[])
        self.assertEqual(pair_exact([{**fx,"minute":81}],secondary)["paired"],[])
        self.assertEqual(pair_exact([fx,{**fx,"fixture_id":12}],secondary)["paired"],[])

if __name__=="__main__":
    unittest.main()
