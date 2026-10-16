#!/usr/bin/env python3
"""Regression: Chromium remains bounded, and ESPN 400 cannot corrupt fixtures."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import netrattler_playwright_runtime as runtime


class BrowserRuntimeTests(unittest.TestCase):
    def make_bot(self, response):
        get = Mock(return_value=response)
        bot = SimpleNamespace(
            ESPN_LEAGUE_IDS={"Premier League": ("soccer", "eng.1"),
                             "Saudi Pro League": ("soccer", "sau.1")},
            ESPN_CACHE={},
            _AF_BULK_FIXTURES={"Saudi Pro League": [
                {"home": "Saudi A", "away": "Saudi B", "source": "api_football"}]},
            requests=SimpleNamespace(get=get), get_local_time=lambda x: "local",
            log=Mock(),
            scrape_with_playwright=Mock(return_value="<html>ok</html>"),
            fetch_espn_fixtures=lambda *args: ["old"],
        )
        return bot, get

    def test_espn_400_does_not_start_browser_or_parse_error_json(self):
        response = SimpleNamespace(ok=False, status_code=400, json=Mock(side_effect=AssertionError("must not parse 400")))
        bot, get = self.make_bot(response)
        runtime.install(bot)
        result = bot.fetch_espn_fixtures("Saudi Pro League", "2026-10-16")
        self.assertEqual(result[0]["source"], "api_football")
        self.assertEqual(bot.fetch_espn_fixtures("Saudi Pro League", "2026-10-16"), result)
        self.assertEqual(get.call_count, 1)
        response.json.assert_not_called()
        bot.scrape_with_playwright._ntr_browser_stats["used"] == 0

    def test_espn_valid_json_keeps_future_match_with_correct_teams(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        event = {
            "id": "33", "date": future,
            "competitions": [{"status": {"type": {"name": "STATUS_SCHEDULED"}},
                              "competitors": [
                                  {"homeAway": "away", "team": {"displayName": "Chelsea", "id": "8"}},
                                  {"homeAway": "home", "team": {"displayName": "Arsenal", "id": "1"}},
                              ]}],
        }
        response = SimpleNamespace(ok=True, status_code=200, json=lambda: {"events": [event]})
        bot, get = self.make_bot(response)
        runtime.install(bot)
        out = bot.fetch_espn_fixtures("Premier League", future[:10])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["home"], out[0]["away"]), ("Arsenal", "Chelsea"))
        self.assertEqual(out[0]["source"], "espn")
        self.assertEqual(get.call_count, 1)

    def test_espn_filters_finished_and_past_without_browser(self):
        past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        event = {"id": "33", "date": past, "competitions": [
            {"status": {"type": {"name": "STATUS_FINAL"}}, "competitors": [
                {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                {"homeAway": "away", "team": {"displayName": "Chelsea"}},
            ]}]}
        bot, _ = self.make_bot(SimpleNamespace(ok=True, status_code=200,
                                               json=lambda: {"events": [event]}))
        runtime.install(bot)
        self.assertEqual(bot.fetch_espn_fixtures("Premier League", past[:10]), [])

    def test_browser_is_enabled_and_limited_to_two_public_pages(self):
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=400))
        original = bot.scrape_with_playwright
        with (patch.dict("os.environ", {"NETRATTLER_PLAYWRIGHT_ENABLED": "true",
                                       "NETRATTLER_PLAYWRIGHT_MAX_PAGES": "2",
                                       "NETRATTLER_PLAYWRIGHT_BUDGET_SEC": "30"}),
              patch.object(runtime.importlib.util, "find_spec", return_value=object())):
            runtime.install(bot)
        self.assertTrue(bot.PLAYWRIGHT_AVAILABLE)
        self.assertEqual(bot.scrape_with_playwright("https://example.org/one"), "<html>ok</html>")
        self.assertEqual(bot.scrape_with_playwright("https://example.org/two"), "<html>ok</html>")
        self.assertIsNone(bot.scrape_with_playwright("https://example.org/three"))
        self.assertIsNone(bot.scrape_with_playwright("file:///etc/passwd"))
        self.assertEqual(original.call_count, 2)
        self.assertEqual(original.call_args.kwargs["timeout"], 8000)
        self.assertEqual(bot.log.call_count, 1)
        # Only hosts and outcomes are logged, never page paths or query tokens.
        summary = bot.log.call_args.args[0]
        self.assertIn("hosts=example.org:2", summary)
        self.assertIn("useful=2 empty=0", summary)
        self.assertNotIn("/one", summary)
        self.assertNotIn("/two", summary)
        runtime.install(bot)
        self.assertEqual(original.call_count, 2)

    def test_browser_budget_telemetry_tracks_empty_without_leaking_urls(self):
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=400))
        bot.scrape_with_playwright = Mock(side_effect=[None, "<html>ok</html>"])
        with (patch.dict("os.environ", {
                "NETRATTLER_PLAYWRIGHT_ENABLED": "true",
                "NETRATTLER_PLAYWRIGHT_MAX_PAGES": "2",
                "NETRATTLER_PLAYWRIGHT_BUDGET_SEC": "30"}),
              patch.object(runtime.importlib.util, "find_spec", return_value=object())):
            runtime.install(bot)
        secret_url = "https://sports.example.org/public?q=private"
        self.assertIsNone(bot.scrape_with_playwright(secret_url))
        self.assertIsNotNone(bot.scrape_with_playwright("https://stats.example.org/"))
        self.assertIsNone(bot.scrape_with_playwright("https://elsewhere.example/"))
        msg = bot.log.call_args.args[0]
        self.assertIn("sports.example.org:1", msg)
        self.assertIn("stats.example.org:1", msg)
        self.assertIn("useful=1 empty=1", msg)
        self.assertNotIn("q=private", msg)
        self.assertNotIn("/public", msg)


    def test_fbref_failed_advanced_stats_circuits_across_leagues(self):
        """Two failing leagues cannot trigger repeated blocked source attempts."""
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=403))
        class AdvancedPropsManager:
            _requests = 0
            def scrape_fbref_advanced_stats(self, league):
                AdvancedPropsManager._requests += 1
                return {}
        bot.AdvancedPropsManager = AdvancedPropsManager
        with patch.dict("os.environ", {"NETRATTLER_FBREF_MAX_FAILED_LEAGUES": "2"}):
            runtime.install(bot)
        obj = AdvancedPropsManager()
        self.assertEqual(obj.scrape_fbref_advanced_stats("Bundesliga"), {})
        self.assertEqual(obj.scrape_fbref_advanced_stats("Serie A"), {})
        self.assertEqual(obj.scrape_fbref_advanced_stats("La Liga"), {})
        self.assertEqual(AdvancedPropsManager._requests, 2)
        self.assertEqual(bot.log.call_count, 1)
        runtime.install(bot)
        self.assertEqual(obj.scrape_fbref_advanced_stats("Ligue 1"), {})
        self.assertEqual(AdvancedPropsManager._requests, 2)

    def test_fbref_browser_not_used_after_upstream_access_denial(self):
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=403))
        original = bot.scrape_with_playwright
        with (patch.dict("os.environ", {
                "NETRATTLER_PLAYWRIGHT_ENABLED": "true",
                "NETRATTLER_PLAYWRIGHT_MAX_PAGES": "4"}),
              patch.object(runtime.importlib.util, "find_spec", return_value=object())):
            runtime.install(bot)
        self.assertIsNone(bot.scrape_with_playwright("https://fbref.com/en/comps/9/"))
        self.assertIsNone(bot.scrape_with_playwright("https://www.fbref.com/en/comps/9/"))
        self.assertEqual(original.call_count, 0)
        self.assertEqual(bot.scrape_with_playwright._ntr_browser_stats["used"], 0)
        # Valid publicly accessible sites remain eligible.
        self.assertEqual(bot.scrape_with_playwright("https://example.org/"), "<html>ok</html>")
        self.assertEqual(original.call_count, 1)

    def test_valid_fbref_advanced_source_does_not_trip_circuit(self):
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=403))
        class AdvancedPropsManager:
            _requests = 0
            def scrape_fbref_advanced_stats(self, league):
                AdvancedPropsManager._requests += 1
                if AdvancedPropsManager._requests % 2 == 0:
                    return {"Player": {"shots_per90": 2.0}}
                return {}
        bot.AdvancedPropsManager = AdvancedPropsManager
        runtime.install(bot)
        obj = AdvancedPropsManager()
        self.assertEqual(obj.scrape_fbref_advanced_stats("Bundesliga"), {})
        self.assertIn("Player", obj.scrape_fbref_advanced_stats("Serie A"))
        self.assertEqual(obj.scrape_fbref_advanced_stats("La Liga"), {})
        self.assertIn("Player", obj.scrape_fbref_advanced_stats("Ligue 1"))
        self.assertEqual(AdvancedPropsManager._requests, 4)
        bot.log.assert_not_called()

    def test_browser_disabled_by_default(self):
        bot, _ = self.make_bot(SimpleNamespace(ok=False, status_code=403))
        with (patch.dict("os.environ", {"NETRATTLER_PLAYWRIGHT_ENABLED": "false"}),
              patch.object(runtime.importlib.util, "find_spec", return_value=object())):
            runtime.install(bot)
        self.assertFalse(bot.PLAYWRIGHT_AVAILABLE)
        self.assertIsNone(bot.scrape_with_playwright("https://example.org"))
        self.assertEqual(bot.scrape_with_playwright._ntr_browser_stats["used"], 0)


if __name__ == "__main__":
    unittest.main()
