import unittest
from netrattler_post_run_check import evaluate, coverage_warnings


class PostRunTests(unittest.TestCase):
    def test_success(self):
        ok, msg = evaluate({"name": "Bookie Market Audit", "status": "completed",
                            "conclusion": "success", "html_url": "https://example.test/run"})
        self.assertTrue(ok)
        self.assertIn("OK:", msg)

    def test_failure(self):
        ok, msg = evaluate({"name": "AI Tipp Bot", "status": "completed",
                            "conclusion": "failure", "html_url": "https://example.test/run"})
        self.assertFalse(ok)
        self.assertIn("RUN-FEHLER", msg)

    def test_cancelled_push_is_not_failure(self):
        ok, msg = evaluate({"name": "NETRATTLER AI Tipp Bot",
                            "status": "completed", "conclusion": "cancelled",
                            "event": "push", "html_url": "https://example.test/old"})
        self.assertTrue(ok)
        self.assertIn("PUSH-TEST ABGEBROCHEN", msg)

    def test_cancelled_scheduled_run_still_warns(self):
        ok, msg = evaluate({"name": "NETRATTLER AI Tipp Bot",
                            "status": "completed", "conclusion": "cancelled",
                            "event": "schedule"})
        self.assertFalse(ok)
        self.assertIn("RUN-FEHLER", msg)

    def test_cancelled_manual_run_still_warns(self):
        ok, _ = evaluate({"name": "NETRATTLER AI Tipp Bot",
                          "status": "completed", "conclusion": "cancelled",
                          "event": "workflow_dispatch"})
        self.assertFalse(ok)

    def test_silent_coverage_failure(self):
        log = '[WARN] Coverage: btts=no_candidates, scorer=no_candidates, corners=no_candidates'
        self.assertEqual(coverage_warnings(log), ['No candidates: btts, scorer, corners'])

    def test_builder_warning(self):
        self.assertEqual(coverage_warnings('Builder Engine: 0 Builder gesendet'), ['Builder Engine sent zero builders'])

    def test_all_generated_builders_already_sent_is_not_failure(self):
        log = '\\n'.join([
            'MASTER BUILDER normalized=476 · matches=10 · generated=3',
            'MASTER BUILDER duplicate skipped: nb_1',
            'MASTER BUILDER duplicate skipped: nb_2',
            'MASTER BUILDER duplicate skipped: nb_3',
            'Builder Engine: 0 Builder aus 599 Props gesendet',
            'Coverage: builder=no_candidates, scorer=no_candidates',
        ])
        self.assertEqual(coverage_warnings(log), ['No candidates: scorer'])

    def test_partial_deduplication_still_warns(self):
        log = '\\n'.join([
            'MASTER BUILDER normalized=476 · generated=3',
            'MASTER BUILDER duplicate skipped: nb_1',
            'Builder Engine: 0 Builder gesendet',
        ])
        self.assertEqual(coverage_warnings(log), ['Builder Engine sent zero builders'])

    def test_incomplete(self):
        ok, _ = evaluate({"status": "in_progress"})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
