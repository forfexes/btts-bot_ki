import unittest
from netrattler_post_run_check import evaluate, coverage_warnings, production_jobs_for_coverage


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

    def test_skipped_gate_is_not_failure(self):
        ok, msg = evaluate({"name": "NETRATTLER AI Tipp Bot", "status": "completed",
                            "conclusion": "skipped", "event": "push", "html_url": "https://example.test/s"})
        self.assertTrue(ok)
        self.assertIn("UEBERSPRUNGEN", msg)

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

    def test_match_limit_exhausted_is_not_failure(self):
        log = '\n'.join(
            ['MASTER BUILDER normalized=370 · matches=6 · same-match≥2=6 · generated=3']
            + ['MASTER BUILDER Spiel-Limit erreicht: X'] * 3
            + ['Builder Engine: 0 Builder aus 1747 Props gesendet',
               'Coverage: builder=no_candidates'])
        self.assertEqual(coverage_warnings(log), [])

    def test_mixed_limit_and_duplicates_is_not_failure(self):
        log = '\n'.join(
            ['MASTER BUILDER normalized=175 · matches=6 · same-match≥2=3 · generated=5']
            + ['MASTER BUILDER Spiel-Limit erreicht: X'] * 3
            + ['MASTER BUILDER duplicate skipped: nb_1', 'MASTER BUILDER duplicate skipped: nb_2',
               'Builder Engine: 0 Builder aus 614 Props gesendet',
               'Coverage: builder=no_candidates'])
        self.assertEqual(coverage_warnings(log), [])

    def test_mixed_partial_still_warns(self):
        log = '\n'.join(
            ['MASTER BUILDER normalized=175 · generated=5']
            + ['MASTER BUILDER Spiel-Limit erreicht: X'] * 2
            + ['MASTER BUILDER duplicate skipped: nb_1',
               'Builder Engine: 0 Builder aus 614 Props gesendet'])
        self.assertEqual(coverage_warnings(log), ['Builder Engine sent zero builders'])

    def test_partial_deduplication_still_warns(self):
        log = '\\n'.join([
            'MASTER BUILDER normalized=476 · generated=3',
            'MASTER BUILDER duplicate skipped: nb_1',
            'Builder Engine: 0 Builder gesendet',
        ])
        self.assertEqual(coverage_warnings(log), ['Builder Engine sent zero builders'])

    def test_confirmed_model_builders_count_as_group_delivery(self):
        log = '\n'.join([
            'Builder Engine: 0 Builder aus 246 Props gesendet',
            'Modell-Builder: 11 gesendet und mit Telegram-Receipt bestaetigt',
            'Coverage: builder=no_candidates, corners=no_candidates',
        ])
        self.assertEqual(coverage_warnings(log), ['No candidates: corners'])

    def test_unconfirmed_or_zero_model_sends_do_not_mask_empty_group(self):
        for line in ('Modell-Builder: 0 gesendet und mit Telegram-Receipt bestaetigt',
                     'Modell-Builder: 11 versendet, Receipt fehlt'):
            self.assertEqual(coverage_warnings('Builder Engine: 0 Builder gesendet\n' + line),
                             ['Builder Engine sent zero builders'])

    def test_gated_builder_pool_is_data_gap_not_failure(self):
        log = ('MASTER BUILDER reject diagnostics: normalize_rejected=37\n'
               'MASTER BUILDER normalized=0 · matches=0 · generated=0\n'
               'Builder Engine: 0 Builder aus 37 Props gesendet\n'
               'Coverage: builder=no_candidates')
        self.assertEqual(coverage_warnings(log), [])

    def test_single_leg_after_gates_is_data_gap_not_failure(self):
        log = ('MASTER BUILDER reject diagnostics: normalize_rejected=129\n'
               'MASTER BUILDER normalized=1 \u00b7 matches=1 \u00b7 same-match\u22652=0 \u00b7 generated=0\n'
               'Builder Engine: 0 Builder aus 130 Props gesendet\n'
               'Coverage: builder=no_candidates')
        self.assertEqual(coverage_warnings(log), [])

    def test_quality_stopped_builders_are_data_gap_not_failure(self):
        log = ('MASTER BUILDER normalized=272 \u00b7 matches=12 \u00b7 same-match\u22652=11 \u00b7 generated=4\n'
               'MASTER BUILDER Spiel-Limit erreicht: A\n'
               'MASTER BUILDER Spiel-Limit erreicht: B\n'
               'Builder-Karte Qualit\u00e4tsstopp: missing_verified_combo_quote\n'
               'MASTER BUILDER send failed/no message_id: C\n'
               'Builder-Karte Qualit\u00e4tsstopp: missing_verified_combo_quote\n'
               'MASTER BUILDER send failed/no message_id: D\n'
               'Builder Engine: 0 Builder aus 3531 Props gesendet\n'
               'Coverage: builder=no_candidates')
        self.assertEqual(coverage_warnings(log), [])

    def test_unexplained_send_failure_still_warns(self):
        log = ('MASTER BUILDER normalized=272 \u00b7 matches=12 \u00b7 same-match\u22652=11 \u00b7 generated=2\n'
               'MASTER BUILDER send failed/no message_id: C\n'
               'MASTER BUILDER send failed/no message_id: D\n'
               'Builder Engine: 0 Builder aus 3531 Props gesendet')
        self.assertEqual(coverage_warnings(log), ['Builder Engine sent zero builders'])

    def test_green_preflight_skipped_telegram_is_not_coverage_failure(self):
        jobs = [
            {'id': 101, 'name': 'Premium source and Telegram send-path QA (NO TELEGRAM)',
             'status': 'completed', 'conclusion': 'success'},
            {'id': 102, 'name': 'run-bot',
             'status': 'completed', 'conclusion': 'skipped'},
        ]
        self.assertEqual(production_jobs_for_coverage(jobs), [])

    def test_actual_successful_production_must_still_be_inspected(self):
        delivery = {'id': 102, 'name': 'run-bot',
                    'status': 'completed', 'conclusion': 'success'}
        self.assertEqual(production_jobs_for_coverage([
            {'id': 101, 'name': 'Premium source and Telegram send-path QA (NO TELEGRAM)',
             'status': 'completed', 'conclusion': 'success'},
            delivery,
        ]), [delivery])

    def test_failed_or_unknown_production_may_not_be_masked(self):
        for status in ('failure', 'cancelled', 'timed_out', None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                production_jobs_for_coverage([
                    {'id': 102, 'name': 'run-bot',
                     'status': 'completed', 'conclusion': status}])
        with self.assertRaisesRegex(ValueError, 'not uniquely'):
            production_jobs_for_coverage([
                {'id': 101, 'name': 'Premium source and Telegram send-path QA (NO TELEGRAM)',
                 'status': 'completed', 'conclusion': 'success'}])

    def test_skipped_telegram_run_never_fetches_nonexistent_logs(self):
        import io
        import json
        from unittest.mock import patch
        from netrattler_post_run_check import fetch_job_logs
        jobs = {'jobs': [
            {'id': 101, 'name': 'Premium source and Telegram send-path QA (NO TELEGRAM)',
             'status': 'completed', 'conclusion': 'success'},
            {'id': 102, 'name': 'run-bot',
             'status': 'completed', 'conclusion': 'skipped'},
        ]}
        response = io.BytesIO(json.dumps(jobs).encode())
        with patch.dict('os.environ', {
                'GITHUB_TOKEN': 'QA_TOKEN', 'GITHUB_REPOSITORY': 'forfexes/btts-bot_ki'}), \
             patch('netrattler_post_run_check.urllib.request.urlopen',
                   return_value=response) as get_jobs, \
             patch('netrattler_post_run_check.urllib.request.build_opener',
                   side_effect=AssertionError('No skipped job logs may be fetched')):
            self.assertEqual(fetch_job_logs({'id': 45482120876}), '')
            get_jobs.assert_called_once()

    def test_successful_qa_only_run_reports_truth_not_telegram_delivery(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import netrattler_post_run_check as monitor
        event = {'workflow_run': {
            'id': 45482120876, 'name': 'NETRATTLER AI Tipp Bot',
            'status': 'completed', 'conclusion': 'success',
            'html_url': 'https://example.test/qa-only'}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'event.json'
            path.write_text(json.dumps(event))
            with patch.dict('os.environ', {'GITHUB_EVENT_PATH': str(path)}), \
                 patch.object(monitor, 'fetch_job_logs', return_value=''):
                self.assertEqual(monitor.main(), 0)

    def test_incomplete(self):
        ok, _ = evaluate({"status": "in_progress"})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()


class DeferredBuilderGateTests(unittest.TestCase):
    def test_gate_deferred_builders_are_not_a_zero_builder_alert(self):
        import netrattler_post_run_check as m
        log = ("MASTER BUILDER normalized=129 · matches=8 · same-match≥2=7 · generated=2\n"
               "BUILDER_CARD_DEFERRED: missing_verified_photo\n"
               "MASTER BUILDER send failed/no message_id: A\n"
               "BUILDER_CARD_DEFERRED: missing_confirmed_kickoff\n"
               "MASTER BUILDER send failed/no message_id: B\n"
               "Builder Engine: 0 Builder gesendet\n")
        self.assertEqual(m.coverage_warnings(log), [])
