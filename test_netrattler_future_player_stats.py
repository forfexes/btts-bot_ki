"""Regression: future-dated finished rows must not enter observed L10/L15 player stats."""
import unittest
from datetime import date
from unittest.mock import patch, Mock

import netrattler_fplci_import as fplci
import netrattler_game_log_sync as sync
import netrattler_player_log as player_log
import netrattler_foul_props as foul


class FuturePlayerStatsTests(unittest.TestCase):
    def test_import_rejects_future_finished_match(self):
        def fake_csv(url):
            if url.endswith("/matches.csv"):
                return [
                    {"match_id": "past", "finished": "true", "kickoff_time": "2020-01-01T15:00:00Z",
                     "home_team": "1", "away_team": "2"},
                    {"match_id": "future", "finished": "true", "kickoff_time": "2099-01-01T15:00:00Z",
                     "home_team": "1", "away_team": "2"},
                ]
            if url.endswith("/playermatchstats.csv"):
                return [{"match_id": mid, "player_id": "42", "minutes_played": "90", "total_shots": "3"}
                        for mid in ("past", "future")]
            if url.endswith("/teams.csv"):
                return [{"id": "1", "code": "11", "name": "Home"},
                        {"id": "2", "code": "22", "name": "Away"}]
            if url.endswith("/players.csv"):
                return [{"player_id": "42", "web_name": "Example", "team_code": "11"}]
            return []
        with patch.object(fplci, "fetch_csv", side_effect=fake_csv):
            rows = fplci.rows_for("2026-2027", 1)
        self.assertEqual([r["match_id"] for r in rows], ["past"])

    def test_sync_rejects_future_date_even_when_minutes_and_shots_exist(self):
        base = {"player_name": "Example", "match_id": "event-1", "match_date": "2099-01-01",
                "minutes": 90, "shots": 3, "source": "fplci"}
        self.assertIsNone(sync.to_log_row(base))
        past = dict(base, match_date="2020-01-01")
        self.assertEqual(sync.to_log_row(past)["shots"], 3)

    def test_trim_does_not_select_future_as_last_game(self):
        rows = [
            {"player_key": "example", "match_date": "2026-10-28"},
            {"player_key": "example", "match_date": "2026-10-31"},
        ]
        kept = sync.trim_rows(rows, today=date(2026, 10, 29))
        self.assertEqual([r["match_date"] for r in kept], ["2026-10-28"])

    def test_foul_profile_rejects_future_stats(self):
        future = {"player_name": "Example", "team": "Home", "match_date": "2099-01-01",
                  "minutes": 90, "shots": 4}
        past = dict(future, match_date="2020-01-01")
        self.assertFalse(foul._played(future))
        self.assertTrue(foul._played(past))
        by = foul.player_rows([future, past], "home", lambda x: str(x or "").lower())
        self.assertEqual(len(by["Example"]), 1)
        self.assertEqual(by["Example"][0]["match_date"], "2020-01-01")

    def test_player_log_fetch_filters_future_rows_and_server_query(self):
        response = Mock(ok=True)
        response.json.return_value = [
            {"player_name": "Example", "match_date": "2099-01-01"},
            {"player_name": "Example", "match_date": "2020-01-01"},
        ]
        with patch.object(player_log, "PLAYERS_DB_URL", "https://example.invalid"), \
             patch.object(player_log, "PLAYERS_DB_KEY", "test-key"), \
             patch.object(player_log.requests, "get", return_value=response) as get:
            rows = player_log.fetch_l20_rows(["Fiorentina"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["match_date"], "2020-01-01")
        self.assertEqual(get.call_args.kwargs["params"]["match_date"],
                         f"lte.{date.today().isoformat()}")


if __name__ == "__main__":
    unittest.main()
