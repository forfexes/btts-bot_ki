#!/usr/bin/env python3
import unittest
from netrattler_betclone_status import summarize


class BetCloneStatusTests(unittest.TestCase):
    def setUp(self):
        self.audit = {
            "checked_at_utc": "2026-10-16T10:00:00+00:00",
            "catalogue": {
                "1xbet": {"bookmakers": ["1xBet", "22bet"]},
                "altenar": {"bookmakers": ["Rabona"]},
                "betby": {"bookmakers": ["Betfury", "20bet"]},
            },
            "catalogue_total_listed_entries": 5,
            "sites": [
                {"platform": "altenar", "brand": "Rabona", "state": "blocked", "verified_odds": 0},
                {"platform": "betby", "brand": "Betfury", "state": "html_no_verified_odds", "verified_odds": 0},
                {"platform": "betby", "brand": "20bet", "state": "public_structured_odds_candidate", "verified_odds": 3},
            ],
            "unverified_candidate_probe_results": [
                {"platform": "1xbet", "brand": "22bet", "state": "unverified_domain_with_odds_needs_review",
                 "verified_odds": 10000},
            ],
        }

    def test_no_homepage_candidate_promoted_to_verified_feed(self):
        s = summarize(self.audit)
        self.assertEqual(s["families_with_verified_production_odds"], 0)
        self.assertEqual(s["families_with_shadow_feed"], 1)
        self.assertEqual(s["platforms"]["betby"]["structured_homepage_price_candidates"], 3)
        self.assertFalse(s["platforms"]["betby"]["validated_production_odds_feed"])
        self.assertEqual(s["platforms"]["1xbet"]["integration_status"],
                         "raw_shadow_unlabelled_markets")
        self.assertEqual(s["curated_homepages_checked"], 3)
        self.assertEqual(s["unverified_candidate_domains_checked"], 1)
        self.assertEqual(s["listed_bookmaker_entries"], 5)

    def test_independent_sources_not_counted_as_betclone_platforms(self):
        s = summarize(self.audit)
        self.assertIn("bwin", s["separate_verified_collectors_not_attributed_to_betclone"])
        self.assertIn("kambi", s["separate_verified_collectors_not_attributed_to_betclone"])
        self.assertNotIn("bwin", s["platforms"])
        self.assertEqual(s["family_count"], 3)

    def test_stale_catalogue_must_fail_closed(self):
        self.audit["catalogue_total_listed_entries"] = 390
        with self.assertRaises(ValueError):
            summarize(self.audit)

    def test_invalid_payload_must_fail_closed(self):
        self.audit["sites"] = "untrusted"
        with self.assertRaises(ValueError):
            summarize(self.audit)


if __name__ == "__main__":
    unittest.main()
