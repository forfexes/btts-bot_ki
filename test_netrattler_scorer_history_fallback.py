#!/usr/bin/env python3
"""Contract tests: no bookmaker-implied stats, no ambiguous player ID, exact L30."""
import unittest
from unittest.mock import patch

import netrattler_scorer_history_fallback as scorer


class ScorerHistoryTests(unittest.TestCase):
    def setUp(self):
        scorer._RECENT_CACHE.clear()

    def test_recent_actual_l30_goal_stats(self):
        rows = [
            {"player_id": "42", "player_name": "João Félix", "event_id": str(i),
             "match_date": "2026-10-01", "goals": n, "minutes": 85}
            for i, n in enumerate((1, 0, 2, 0, 1))
        ]
        class Response:
            ok = True
            def json(self): return rows
        with patch.object(scorer.requests, "get", return_value=Response()) as get:
            data = scorer.recent_goals("João Félix", "https://example.supabase.co", "token")
            self.assertEqual(data["goals"]["avg"], 0.8)
            self.assertEqual(data["goals"]["hit_rate"], 60)
            self.assertEqual(data["goals"]["games"], 5)
            params = get.call_args.kwargs["params"]
            self.assertEqual(params["player_name"], "ilike.João Félix")
            self.assertEqual(params["limit"], "30")
            scorer.recent_goals("João Félix", "https://example.supabase.co", "token")
            self.assertEqual(get.call_count, 1)

    def test_rejects_ambiguous_name_and_wildcards(self):
        rows = [
            {"player_id": "11" if i < 2 else "12", "player_name": "Sam Lee",
             "event_id": str(i), "goals": 1, "minutes": 80}
            for i in range(4)
        ]
        class Response:
            ok = True
            def json(self): return rows
        with patch.object(scorer.requests, "get", return_value=Response()) as get:
            self.assertEqual(scorer.recent_goals("Sam Lee", "https://example.com", "token"), {})
            self.assertEqual(scorer.recent_goals("Sam%Lee", "https://example.com", "token"), {})
            self.assertEqual(get.call_count, 1)

    def test_excludes_bench_duplicated_and_wrong_player(self):
        rows = [
            {"player_id": "7", "player_name": "Kai Smith", "event_id": "a", "goals": 1, "minutes": 80},
            {"player_id": "7", "player_name": "Kai Smith", "event_id": "a", "goals": 1, "minutes": 80},
            {"player_id": "7", "player_name": "Kai Smith", "event_id": "b", "goals": 3, "minutes": 0},
            {"player_id": "7", "player_name": "Kai Smith", "event_id": "c", "goals": 1, "minutes": 90},
            {"player_id": "7", "player_name": "Different", "event_id": "d", "goals": 2, "minutes": 90},
        ]
        class Response:
            ok = True
            def json(self): return rows
        with patch.object(scorer.requests, "get", return_value=Response()):
            self.assertEqual(scorer.recent_goals("Kai Smith", "https://example.com", "token"), {})

    def test_install_preserves_valid_aggregate(self):
        class Bot:
            SUPABASE_URL = "https://example.com"
            SUPABASE_KEY = "token"
            @staticmethod
            def get_supabase_player_avg_stats(_name):
                return {"goals": {"avg": 0.1, "games": 15}}
        bot = Bot()
        scorer.install(bot)
        with patch.object(scorer, "recent_goals", side_effect=AssertionError("must not fetch")):
            self.assertEqual(bot.get_supabase_player_avg_stats("Sam Lee")["goals"]["avg"], 0.1)

    def test_install_uses_history_when_goal_stat_missing(self):
        class Bot:
            SUPABASE_URL = "https://example.com"
            SUPABASE_KEY = "token"
            @staticmethod
            def get_supabase_player_avg_stats(_name): return {"shots": {"avg": 2.2, "games": 10}}
        bot = Bot()
        scorer.install(bot)
        def _ntr_history_scorers_from_quotes():
            def _one():
                return bot.get_supabase_player_avg_stats("Sam Lee")
            return _one()

        with patch.object(scorer, "recent_goals", return_value={"goals": {"avg": 0.5, "games": 10}}) as query:
            data = _ntr_history_scorers_from_quotes()
            self.assertEqual(data["goals"]["avg"], 0.5)
            self.assertEqual(data["shots"]["avg"], 2.2)
            self.assertEqual(query.call_count, 1)
            # Player-prop pipelines must not cause another Supabase history lookup.
            other = bot.get_supabase_player_avg_stats("Sam Lee")
            self.assertNotIn("goals", other)
            self.assertEqual(query.call_count, 1)


if __name__ == "__main__":
    unittest.main()
