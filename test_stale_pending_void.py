import unittest
from datetime import datetime, timezone
import netrattler_stale_pending_void as m

class T(unittest.TestCase):
    def test_cutoff(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(m.cutoff_iso(now, 7).startswith("2026-10-13T12:00"))
    def test_filter_only_pending(self):
        f = m.stale_filter("2026-10-13T12:00:00+00:00")
        self.assertEqual(f["status"], "eq.pending")
        self.assertTrue(f["created_at"].startswith("lt."))
    def test_default_dry_run(self):
        self.assertFalse(m.APPLY)

if __name__ == "__main__":
    unittest.main()
