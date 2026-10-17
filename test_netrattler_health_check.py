import unittest
from unittest.mock import patch, Mock
import netrattler_health_check as health


class GitHubWorkflowTests(unittest.TestCase):
    @patch.object(health, 'GITHUB_TOKEN', 'test-token')
    @patch.object(health.requests, 'get')
    def test_latest_failed_run_alerts_even_after_success(self, get):
        get.return_value = Mock(ok=True, json=lambda: {"workflow_runs": [
            {"name": "NETRATTLER Offline Sandbox Hardtest", "created_at": "2026-10-17T14:00:00Z",
             "status": "completed", "conclusion": "failure"},
            {"name": "NETRATTLER Offline Sandbox Hardtest", "created_at": "2026-10-17T13:00:00Z",
             "status": "completed", "conclusion": "success"},
        ]})
        issues = health.check_github()
        self.assertTrue(any("letzter Lauf fehlgeschlagen" in issue for issue in issues))


class HealthSourceTests(unittest.TestCase):
    @patch.object(health, 'SUPABASE_URL', '')
    @patch.object(health, 'SUPABASE_KEY', '')
    def test_missing_credentials_returns_consistent_shape(self):
        issues, size, total, sources = health.check_supabase()
        self.assertIn('Supabase-Zugang fehlt', issues)
        self.assertIsNone(size)
        self.assertIsNone(total)
        self.assertEqual(sources, 0)

    @patch.object(health, 'SUPABASE_URL', 'https://example.supabase.co')
    @patch.object(health, 'SUPABASE_KEY', 'test-only-key')
    @patch.object(health, '_sb')
    @patch.object(health, '_count', return_value=0)
    @patch.object(health, '_newest', return_value='2026-10-17T00:00:00Z')
    def test_source_health_http_error_reported(self, newest, count, sb):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        newest.return_value = now
        sb.side_effect = [Mock(ok=False, status_code=404), Mock(ok=False, status_code=503)]
        issues, _, _, _ = health.check_supabase()
        self.assertTrue(any('source_health: HTTP 503' in x for x in issues))

    @patch.object(health, 'SUPABASE_URL', 'https://example.supabase.co')
    @patch.object(health, 'SUPABASE_KEY', 'test-only-key')
    @patch.object(health, '_sb')
    @patch.object(health, '_count', return_value=0)
    @patch.object(health, '_newest')
    def test_source_health_empty_success_not_http_error(self, newest, count, sb):
        from datetime import datetime, timezone
        newest.return_value = datetime.now(timezone.utc).isoformat()
        sb.side_effect = [Mock(ok=False, status_code=404), Mock(ok=True, json=lambda: [])]
        issues, _, _, _ = health.check_supabase()
        self.assertFalse(any('source_health: HTTP' in x for x in issues))


if __name__ == '__main__':
    unittest.main()
