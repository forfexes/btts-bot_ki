import unittest
from unittest.mock import Mock, patch
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


    def test_failed_backup_fetch_never_voids(self):
        listed = Mock(ok=True, json=lambda: [{"tip_id": "t1"}])
        failed = Mock(ok=False, status_code=503)
        with patch.multiple(m, SB="https://test.invalid", SK="test", APPLY=True), \
             patch.object(m.requests, "get", side_effect=[listed, failed]), \
             patch.object(m.requests, "post") as post, \
             patch.object(m.requests, "patch") as update:
            self.assertEqual(m.run(), 0)
            post.assert_not_called()
            update.assert_not_called()

    def test_incomplete_backup_fetch_never_voids(self):
        listed = Mock(ok=True, json=lambda: [{"tip_id": "t1"}])
        incomplete = Mock(ok=True, status_code=200, json=lambda: [])
        with patch.multiple(m, SB="https://test.invalid", SK="test", APPLY=True), \
             patch.object(m.requests, "get", side_effect=[listed, incomplete]), \
             patch.object(m.requests, "post") as post, \
             patch.object(m.requests, "patch") as update:
            self.assertEqual(m.run(), 0)
            post.assert_not_called()
            update.assert_not_called()

    def test_wrong_backup_identity_never_voids(self):
        listed = Mock(ok=True, json=lambda: [{"tip_id": "t1"}])
        wrong = Mock(ok=True, status_code=200, json=lambda: [{"tip_id": "t2"}])
        with patch.multiple(m, SB="https://test.invalid", SK="test", APPLY=True), \
             patch.object(m.requests, "get", side_effect=[listed, wrong]), \
             patch.object(m.requests, "post") as post, \
             patch.object(m.requests, "patch") as update:
            self.assertEqual(m.run(), 0)
            post.assert_not_called()
            update.assert_not_called()

    def test_verified_backup_allows_void(self):
        listed = Mock(ok=True, json=lambda: [{"tip_id": "t1"}])
        full = Mock(ok=True, json=lambda: [{"tip_id": "t1", "status": "pending"}])
        with patch.multiple(m, SB="https://test.invalid", SK="test", APPLY=True), \
             patch.object(m.requests, "get", side_effect=[listed, full]), \
             patch.object(m.requests, "post", return_value=Mock(ok=True)) as post, \
             patch.object(m.requests, "patch", return_value=Mock(ok=True)) as update:
            self.assertEqual(m.run(), 1)
            post.assert_called_once()
            update.assert_called_once()

if __name__ == "__main__":
    unittest.main()
