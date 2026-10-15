import unittest
from netrattler_post_run_check import evaluate


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

    def test_incomplete(self):
        ok, _ = evaluate({"status": "in_progress"})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
