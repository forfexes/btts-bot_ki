import unittest
from unittest import mock
import netrattler_odds_harvester as h

class R:
    ok = True
    def __init__(s, d): s.d = d
    def json(s): return s.d

class T(unittest.TestCase):
    def test_period1_total_becomes_ht(self):
        mu = [{"type": "matchup", "id": 1, "startTime": "2026-10-21T18:00:00Z", "league": {"name": "L"},
               "participants": [{"alignment": "home", "name": "A"}, {"alignment": "away", "name": "B"}]}]
        mk = [{"matchupId": 1, "type": "total", "period": 1,
               "prices": [{"designation": "over", "points": 1.5, "price": -120},
                          {"designation": "under", "points": 1.5, "price": 100}]},
              {"matchupId": 1, "type": "moneyline", "period": 1, "prices": [{"designation": "home", "price": 200}]}]
        with mock.patch.object(h.requests, "get", side_effect=[R(mu), R(mk)]):
            rows = h.collect_pinnacle("2026-10-21")
        self.assertEqual({r["market"] for r in rows}, {"totals_ht_1_5"})
        self.assertEqual(len(rows), 2)

if __name__ == "__main__":
    unittest.main()
