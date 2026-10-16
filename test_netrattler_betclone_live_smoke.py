#!/usr/bin/env python3
import unittest
from datetime import datetime, timezone
import netrattler_betclone_live_smoke as smoke


class SmokeTests(unittest.TestCase):
    def test_exact_fixture_full_market_counts_only(self):
        today = datetime.now(timezone.utc).date().isoformat()
        now = datetime.now(timezone.utc).isoformat()
        base = {"home_team": "Arsenal", "away_team": "Chelsea",
                "match_date": today, "captured_date": today, "market": "1x2"}
        ref, shadow = [], []
        for name, ref_odds, x_odds in (("home", 2.0, 2.03),
                                      ("draw", 3.2, 3.25),
                                      ("away", 3.8, 3.9)):
            ref.append(dict(base, source="bwin", selection=name,
                            odds=ref_odds, raw={"captured_at": now}))
            shadow.append(dict(base, source="1xbet_platform", selection=name,
                               odds=x_odds, imported_at=now))
        summary = smoke.summarize(ref, shadow)
        self.assertEqual(summary["complete_markets_1x2"], 1)
        self.assertEqual(summary["corroborated_x1_selections"], 3)

    def test_other_match_or_partial_market_never_counts(self):
        today = datetime.now(timezone.utc).date().isoformat()
        now = datetime.now(timezone.utc).isoformat()
        base = {"home_team": "Arsenal", "away_team": "Chelsea",
                "match_date": today, "captured_date": today,
                "market": "1x2"}
        ref = [dict(base, source="bwin", selection=s,
                    odds=p, raw={"captured_at": now})
               for s, p in (("home", 2.0), ("draw", 3.2), ("away", 3.8))]
        shadow = [dict(base, source="1xbet_platform", selection="home",
                       odds=2.01, imported_at=now),
                  dict(base, source="1xbet_platform", selection="draw",
                       odds=3.22, imported_at=now)]
        self.assertEqual(smoke.summarize(ref, shadow)["complete_markets_1x2"], 0)
        shadow.append(dict(base, source="1xbet_platform", selection="away",
                           odds=3.85, imported_at=now, home_team="Liverpool"))
        self.assertEqual(smoke.summarize(ref, shadow)["complete_markets_1x2"], 0)


if __name__ == "__main__":
    unittest.main()
