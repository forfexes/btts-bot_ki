"""Missing score feeds are never automatic bookmaker VOID evidence."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import netrattler_stale_pending_void as m


class StaleAuditOnlyTests(unittest.TestCase):
    def test_cutoff_and_filter(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(m.cutoff_iso(now, 7).startswith("2026-10-13T12:00"))
        f = m.stale_filter("2026-10-13T12:00:00+00:00")
        self.assertEqual(f["status"], "eq.pending")
        self.assertTrue(f["created_at"].startswith("lt."))

    def test_disabled_by_default(self):
        self.assertFalse(m.APPLY)

    def test_never_writes_even_when_legacy_apply_flag_is_forced(self):
        listed = Mock(ok=True, json=lambda: [{"tip_id": "t1"}])
        for apply in (False, True):
            with self.subTest(apply=apply), \
                 patch.multiple(m, SB="https://test.invalid", SK="test", APPLY=apply), \
                 patch.object(m.requests, "get", return_value=listed) as get, \
                 patch.object(m.requests, "post") as post, \
                 patch.object(m.requests, "patch") as update:
                self.assertEqual(m.run(), 1)
                get.assert_called_once()
                post.assert_not_called()
                update.assert_not_called()

    def test_missing_credentials_is_read_only(self):
        with patch.multiple(m, SB="", SK="", APPLY=True), \
             patch.object(m.requests, "get") as get, \
             patch.object(m.requests, "post") as post, \
             patch.object(m.requests, "patch") as update:
            self.assertEqual(m.run(), 0)
            get.assert_not_called()
            post.assert_not_called()
            update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
