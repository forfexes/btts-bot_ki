"""No network: verify identity, live clock, observed line prices and stats."""
import datetime as dt
import unittest

from netrattler_lmg_free import fixtures_from_espn, metrics_from_espn, pulse_prices

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,18,13,0,tzinfo=UTC)


def fixture():
    return {"fixture_id":1234, "minute":60, "home":"Lecce", "away":"Roma",
            "hg":0, "ag":3, "home_id":"10","away_id":"20",
            "kickoff":dt.datetime(2026,11,18,12,tzinfo=UTC), "league":"Serie A"}


def board():
    return {"leagues":[{"name":"Serie A"}], "events":[{
        "id":"1234","date":"2026-11-18T12:00:00Z",
        "status":{"period":2,"displayClock":"60:44","type":{"state":"in"}},
        "competitions":[{"competitors":[
            {"homeAway":"home","score":"0","team":{"id":"10","displayName":"Lecce"}},
            {"homeAway":"away","score":"3","team":{"id":"20","displayName":"Roma"}}]}]}]}


def pulse():
    return {"eventId":"x", "home":"Lecce", "away":"Roma", "live":True,
            "startTime":"2026-11-18T12:00:00Z",
            "markets":[{"canonicalMarket":"total_goals","period":"fulltime","line":"3.5",
                        "selections":[{"name":"Over 3.5","decimal":"1.85"}]},
                       {"canonicalMarket":"total_goals","period":"first_half","line":"4.5",
                        "selections":[{"name":"Over 4.5","decimal":"2.0"}]}]}


class FreeFeedTests(unittest.TestCase):
    def test_live_match_and_minute(self):
        rows=fixtures_from_espn(board())
        self.assertEqual((len(rows),rows[0]["minute"],rows[0]["hg"],rows[0]["ag"]),(1,60,0,3))
        altered=board()
        altered["events"][0]["status"]["period"]=1
        self.assertEqual(fixtures_from_espn(altered),[])

    def test_missing_score_is_never_zero(self):
        altered=board()
        altered["events"][0]["competitions"][0]["competitors"][0]["score"]=None
        self.assertEqual(fixtures_from_espn(altered),[])

    def test_real_espn_stats(self):
        payload={"boxscore":{"teams":[
            {"team":{"id":"10"},"statistics":[{"name":"totalShots","value":10},
                                                 {"name":"shotsOnTarget","value":4},
                                                 {"name":"cornerKicks","value":3}]},
            {"team":{"id":"20"},"statistics":[{"name":"totalShots","value":12},
                                                 {"name":"shotsOnTarget","value":5},
                                                 {"name":"cornerKicks","value":4}]}]}}
        metrics=metrics_from_espn(payload,fixture())
        self.assertEqual(metrics["sot"],9)
        self.assertEqual(metrics["tier"],"PREMIUM")
        payload["boxscore"]["teams"][1]["statistics"]=[]
        self.assertIsNone(metrics_from_espn(payload,fixture()))

    def test_real_odds_exact_line(self):
        self.assertEqual(pulse_prices([pulse()],fixture(),NOW),{3.5:1.85})
        self.assertEqual(pulse_prices([{**pulse(),"live":False}],fixture(),NOW),{})
        self.assertEqual(pulse_prices([{**pulse(),"away":"Other"}],fixture(),NOW),{})
        self.assertEqual(pulse_prices([pulse(),pulse()],fixture(),NOW),{})

    def test_no_second_half_or_mismatched_kickoff(self):
        bad=pulse()
        bad["markets"][0]["period"]="second_half"
        self.assertEqual(pulse_prices([bad],fixture(),NOW),{})
        bad=pulse()
        bad["startTime"]="2026-11-18T14:00:00Z"
        self.assertEqual(pulse_prices([bad],fixture(),NOW),{})


if __name__ == "__main__":
    unittest.main()
