"""Fail-closed policy contract for NETRATTLER release workflow.

No Telegram API, no Supabase and no live data. Repository owner variables
are intentionally not read or mocked into true in this test.
"""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parent / ".github" / "workflows" / "btts_tips.yml"


def workflow_parts():
    raw = WORKFLOW.read_text(encoding="utf-8")
    if "\n  run-bot:\n" not in raw or "\n  owner-card-preflight:\n" not in raw:
        raise AssertionError("Independent QA and production jobs required")
    start = raw.index("\n  owner-card-preflight:\n")
    boundary = raw.index("\n  run-bot:\n", start)
    return raw, raw[start:boundary], raw[boundary:]


class ProductionReleaseGate(unittest.TestCase):
    def test_qa_available_without_credentials(self):
        raw, preflight, live = workflow_parts()
        self.assertNotIn("if: " + "$" + "{{ false }}", preflight)
        for empty in ('TELEGRAM_TOKEN: ""', 'TELEGRAM_CHAT_ID: ""',
                      'SUPABASE_URL: ""', 'SUPABASE_KEY: ""'):
            self.assertIn(empty, preflight)
        for filename in ("test_netrattler_premium_flexible_renderer.py",
                         "test_netrattler_premium_mobile_pages.py",
                         "test_netrattler_premium_mobile_telegram_plan.py",
                         "test_netrattler_premium_live_bridge.py"):
            self.assertIn(filename, preflight)
        self.assertIn("NETRATTLER_OWNER_CARD_QA_PASS", preflight)

    def test_publish_requires_qa_and_owner_approval(self):
        raw, preflight, live = workflow_parts()
        cond = next((line for line in live.splitlines()
                     if line.strip().startswith("if: ")), "")
        self.assertTrue(cond, "Production job must have an explicit if")
        self.assertIn("needs.owner-card-preflight.result == 'success'", cond)
        self.assertIn("vars.NETRATTLER_TG_PRODUCTION_APPROVED == 'true'", cond)
        self.assertIn("github.event_name == 'schedule'", cond)
        self.assertIn("github.event_name == 'workflow_dispatch'", cond)
        self.assertIn("inputs.publish_telegram == true", cond)
        self.assertIn("github.ref == 'refs/heads/main'", cond)
        self.assertIn("vars.NETRATTLER_TG_PRODUCTION_APPROVED == ''", cond)
        self.assertIn("needs.owner-card-preflight.outputs.repository_approved == 'true'", cond)
        self.assertIn("github.event_name == 'push' && needs.owner-card-preflight.outputs.explicit_send == 'true'", cond)
        self.assertIn("python netrattler_owner_release.py", preflight)
        self.assertIn("needs: [owner-card-preflight]", live)

    def test_explicit_owner_push_policy(self):
        from netrattler_owner_release import approved, explicit_send, RECORD, SEND_MARKER, SCOPE
        record = {"approved": True, "scope": SCOPE, "request_id": "2026-11-25-test"}
        args = {"event_name": "push", "ref": "refs/heads/main",
                "message": SEND_MARKER, "changed": [RECORD]}
        self.assertTrue(approved(record))
        self.assertTrue(explicit_send(record, **args))
        self.assertFalse(approved({**record, "approved": "true"}))
        self.assertFalse(explicit_send({**record, "approved": False}, **args))
        for overrides in ({"event_name": "schedule"}, {"ref": "refs/heads/qa"},
                          {"message": "ordinary change"}, {"changed": []},
                          {"changed": ["btts_bot.py"]}):
            self.assertFalse(explicit_send(record, **{**args, **overrides}))

    def test_manual_release_defaults_off(self):
        raw, _, live = workflow_parts()
        block = re.search(r"^      publish_telegram:\s*\n"
                          r"(?:^        .+\n){1,8}", raw, re.M)
        self.assertIsNotNone(block)
        self.assertRegex(block.group(0), r"default:\s*false")
        self.assertRegex(block.group(0), r"type:\s*boolean")
        self.assertIn("NETRATTLER_BLOCK_OVERPAINTED_MASTERS:", live)
        self.assertIn("NETRATTLER_ORIGINAL_ONLY:", live)

    def test_original_art_safety_tests_still_mandatory(self):
        raw, _, live = workflow_parts()
        self.assertIn("Mandatory offline premium-card sandbox hardtest before Telegram", live)
        self.assertIn("test_netrattler_original_templates.py", live)
        self.assertIn('NETRATTLER_ORIGINAL_ONLY:   "1"', live)
        self.assertIn('NETRATTLER_BLOCK_OVERPAINTED_MASTERS: "1"', live)


if __name__ == "__main__":
    unittest.main()
