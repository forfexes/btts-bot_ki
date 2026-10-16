#!/usr/bin/env python3
"""Regression: a stale daily cache must not cause duplicate combo posts.

The source file is large and initializes external adapters at import time.
Compile only the actual is_duplicate_combo functions for hermetic tests.
"""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


def implementations():
    source = Path(__file__).with_name("btts_bot.py").read_text(encoding="utf-8")
    module = ast.parse(source, filename="btts_bot.py")
    definitions = [node for node in module.body
                   if isinstance(node, ast.FunctionDef) and node.name == "is_duplicate_combo"]
    if not definitions:
        raise AssertionError("production combo dedupe missing")
    return [compile(ast.Module(body=[node], type_ignores=[]),
                    "btts_bot.py", "exec") for node in definitions]


class ComboRaceGuardTests(unittest.TestCase):
    def check(self, response=None, *, in_cache=False, connected=True, error=None):
        for code in implementations():
            with self.subTest(code=code.co_firstlineno):
                api = Mock()
                if error:
                    api.get.side_effect = error
                else:
                    api.get.return_value = response
                cache = {"combo_combo_test"} if in_cache else set()
                globals_ = {
                    "requests": api, "_SENT_TIPS_CACHE": cache,
                    "_PREFETCHED_DUP_DATES": {"2026-10-16"},
                    "SUPABASE_URL": "https://project.supabase.co" if connected else "",
                    "SUPABASE_KEY": "dummy" if connected else "",
                    "log": Mock(),
                }
                exec(code, globals_)
                result = globals_["is_duplicate_combo"]("combo_test", "2026-10-16")
                yield result, cache, api

    def test_stale_cache_miss_detects_late_database_insert(self):
        resp = Mock(ok=True)
        resp.json.return_value = [{"id": 456}]
        for result, cache, api in self.check(resp):
            self.assertTrue(result)
            self.assertIn("combo_combo_test", cache)
            api.get.assert_called_once()

    def test_fresh_combo_gets_through(self):
        resp = Mock(ok=True)
        resp.json.return_value = []
        for result, cache, api in self.check(resp):
            self.assertFalse(result)
            self.assertNotIn("combo_combo_test", cache)
            api.get.assert_called_once()

    def test_same_run_cache_hit_has_no_network_call(self):
        for result, cache, api in self.check(in_cache=True):
            self.assertTrue(result)
            api.get.assert_not_called()

    def test_db_error_fails_closed(self):
        for response in [Mock(ok=False, status_code=503), Mock(ok=False, status_code=401)]:
            for result, cache, api in self.check(response):
                self.assertTrue(result)
                api.get.assert_called_once()

    def test_db_timeout_fails_closed(self):
        for result, cache, api in self.check(error=TimeoutError("timeout")):
            self.assertTrue(result)
            api.get.assert_called_once()

    def test_unconfigured_offline_mode_does_not_require_network(self):
        for result, cache, api in self.check(connected=False):
            self.assertFalse(result)
            api.get.assert_not_called()

    def test_successful_combo_is_cached_during_same_run(self):
        source = Path(__file__).with_name("btts_bot.py").read_text(encoding="utf-8")
        self.assertIn('_SENT_TIPS_CACHE.add(f"combo_{_combo_tip_id}")', source)


if __name__ == "__main__":
    unittest.main()
