import unittest
from datetime import date

import netrattler_odds_retention as r


class RetentionTests(unittest.TestCase):
    def test_cutoff_is_20_days(self):
        self.assertEqual(r.cutoff(date(2026, 10, 17)), "2026-09-27")

    def test_historical_training_source_never_deleted(self):
        self.assertNotIn("football_data_co_uk", r.LIVE_SOURCES)

    def test_default_retention(self):
        self.assertEqual(r.RETENTION_DAYS, 20)


if __name__ == "__main__":
    unittest.main()
