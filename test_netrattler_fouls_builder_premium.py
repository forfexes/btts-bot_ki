"""Hermetic original-only Fouls Builder QA: no network or Telegram sending."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

import netrattler_foul_props as props
from netrattler_fouls_builder_premium import prepare_quoted_builder


NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
HOME = ["Joe Willock", "William Osula", "Bruno Guimaraes", "A Home",
        "B Home", "C Home", "D Home", "E Home", "F Home",
        "G Home", "H Home"]
AWAY = ["Arsenal One", "Arsenal Two", "Arsenal Three", "Arsenal Four",
        "Arsenal Five", "Arsenal Six", "Arsenal Seven", "Arsenal Eight",
        "Arsenal Nine", "Arsenal Ten", "Arsenal Eleven"]


def evidence():
    fixture = {
        "fixture_id": 80001, "home_team_id": 10, "away_team_id": 20,
        "home": "Newcastle United", "away": "Arsenal", "league": "Premier League",
        "status": "NS", "kickoff": (NOW + timedelta(minutes=80)).isoformat(),
    }
    lineup = {
        "source": "api_football", "confirmed": True,
        "confirmed_at": (NOW - timedelta(minutes=8)).isoformat(),
        "fixture_id": 80001,
        "home": {"team_id": 10, "starters": HOME[:]},
        "away": {"team_id": 20, "starters": AWAY[:]},
    }
    series = [3, 2, 2, 4, 3, 2, 1, 4, 2, 2, 3, 4, 2, 1, 3]
    profiles = []
    for name in HOME[:3] + AWAY[:2]:
        team = "Arsenal" if name.startswith("Arsenal") else "Newcastle United"
        profiles.append({
            "player": name, "team": team,
            "match": "Newcastle United vs Arsenal",
            "source": "foul_profile", "history_order": "latest_first",
            "fouls": series[:], "fouls_won": series[:],
            "minutes_series": [90] * 15,
        })
    quote = {
        "observed": True, "quote_source": "bookmaker_direct",
        "bookmaker": "QA Sportsbook", "quote_id": "TEST-QUOTE-1",
        "fixture_id": 80001, "home_team_id": 10, "away_team_id": 20,
        "observed_at": (NOW - timedelta(minutes=2)).isoformat(),
        "combined_decimal_odds": 61.0,
        "legs": [
            {"player": "Joe Willock", "team_id": 10,
             "market": "fouls_committed", "threshold": 2, "selection_id": "qa-1"},
            {"player": "William Osula", "team_id": 10,
             "market": "fouls_committed", "threshold": 3, "selection_id": "qa-2"},
            {"player": "Bruno Guimaraes", "team_id": 10,
             "market": "fouls_won", "threshold": 2, "selection_id": "qa-3"},
            {"player": "Arsenal One", "team_id": 20,
             "market": "fouls_won", "threshold": 3, "selection_id": "qa-4"},
        ],
    }
    return fixture, lineup, profiles, quote


class OriginalFoulsBuilderQA(unittest.TestCase):
    def setUp(self):
        self.fixture, self.lineup, self.profiles, self.quote = evidence()

    def go(self):
        return prepare_quoted_builder(self.fixture, self.lineup,
                                      self.profiles, self.quote, now=NOW)

    def test_valid_single_match_builder_is_still_not_published(self):
        out = self.go()
        self.assertEqual(out["legs_count"], 4)
        self.assertEqual(out["combined_decimal_odds"], 61.0)
        self.assertEqual(out["combined_quote_id"], "TEST-QUOTE-1")
        self.assertEqual(out["stake_units"], 1)
        self.assertEqual(out["combined_implied_probability"], round(100 / 61, 3))
        self.assertIsNone(out["combined_model_probability"])
        self.assertIsNone(out["combined_model_edge"])
        self.assertFalse(out["published"])
        self.assertEqual(out["render_status"], "OWNER_FOULS_ORIGINAL_REQUIRED")
        self.assertEqual(out["legs"][0]["L10"], 9)
        self.assertEqual(out["legs"][0]["L15"], 13)
        self.assertEqual(out["legs"][0]["per90_l15"], round(sum(
            [3,2,2,4,3,2,1,4,2,2,3,4,2,1,3])/15, 2))

    def test_alternate_stored_foul_categories_remain_distinct(self):
        out = self.go()
        self.assertEqual(out["legs"][0]["market"], "fouls_committed")
        self.assertEqual(out["legs"][2]["market"], "fouls_won")
        self.assertNotEqual(out["legs"][0]["market_label"], out["legs"][2]["market_label"])

    def test_konsa_wrong_club_screenshot_leg_is_rejected(self):
        self.quote["legs"][3]["player"] = "Ezri Konsa"
        self.profiles.append({
            "player": "Ezri Konsa", "team": "Aston Villa",
            "match": "Aston Villa vs Newcastle United", "source": "foul_profile",
            "history_order": "latest_first", "fouls_won": [4] * 15,
        })
        with self.assertRaisesRegex(ValueError, "player_not_in_confirmed_team_lineup"):
            self.go()

    def test_quote_player_team_id_must_be_on_fixture_side(self):
        self.quote["legs"][3]["team_id"] = 300
        with self.assertRaisesRegex(ValueError, "another_fixture"):
            self.go()

    def test_lineup_must_be_confirmed_and_complete_11_per_team(self):
        self.lineup["confirmed"] = False
        with self.assertRaisesRegex(ValueError, "confirmed_starting_eleven"):
            self.go()
        self.lineup["confirmed"] = True
        self.lineup["away"]["starters"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete_starting_eleven"):
            self.go()

    def test_lineup_event_id_cannot_be_reused_for_other_game(self):
        self.lineup["fixture_id"] += 1
        with self.assertRaisesRegex(ValueError, "wrong_lineup_fixture"):
            self.go()

    def test_lineup_team_id_and_duplicate_name_are_blocked(self):
        self.lineup["home"]["team_id"] = 777
        with self.assertRaisesRegex(ValueError, "lineup_team_identity"):
            self.go()
        self.lineup["home"]["team_id"] = 10
        self.lineup["home"]["starters"][5] = "Joe Willock"
        with self.assertRaisesRegex(ValueError, "ambiguous_starting_eleven"):
            self.go()

    def test_quote_from_wrong_event_or_wrong_teams_is_blocked(self):
        for field, value in (("fixture_id", 90001),
                             ("home_team_id", 200), ("away_team_id", 300)):
            with self.subTest(field=field):
                quote = deepcopy(self.quote)
                quote[field] = value
                with self.assertRaisesRegex(ValueError, "ticket_fixture_mismatch"):
                    prepare_quoted_builder(self.fixture, self.lineup,
                                           self.profiles, quote, now=NOW)

    def test_quote_is_bookmaker_combined_ticket_not_multiplied_single_odds(self):
        for changes in (
            {"observed": False}, {"quote_source": "screenshot"},
            {"quote_source": "model"}, {"bookmaker": "calculated"},
            {"quote_id": ""}, {"combined_decimal_odds": None},
            {"combined_decimal_odds": float("nan")},
            {"combined_decimal_odds": 0.0},
        ):
            with self.subTest(changes=changes):
                quote = dict(self.quote, **changes)
                with self.assertRaises(ValueError):
                    prepare_quoted_builder(self.fixture, self.lineup,
                                           self.profiles, quote, now=NOW)

    def test_stale_quote_and_future_market_are_rejected(self):
        self.quote["observed_at"] = (NOW - timedelta(minutes=21)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale_or_future_bookmaker"):
            self.go()
        self.quote["observed_at"] = (NOW + timedelta(minutes=2)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale_or_future_bookmaker"):
            self.go()

    def test_fixture_must_not_have_started(self):
        self.fixture["status"] = "LIVE"
        with self.assertRaisesRegex(ValueError, "already_started"):
            self.go()
        self.fixture["status"] = "NS"
        self.fixture["kickoff"] = (NOW - timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "prematch_window"):
            self.go()

    def test_missing_l15_history_fails_closed_not_zero_filled(self):
        self.profiles[0]["fouls"] = self.profiles[0]["fouls"][:10]
        with self.assertRaisesRegex(ValueError, "l15_history_missing"):
            self.go()

    def test_history_order_and_missing_observation_are_blocked(self):
        self.profiles[0]["history_order"] = "unknown"
        with self.assertRaisesRegex(ValueError, "history_order"):
            self.go()
        self.profiles[0]["history_order"] = "latest_first"
        self.profiles[0]["fouls"][4] = None
        with self.assertRaisesRegex(ValueError, "invalid_observed_foul"):
            self.go()

    def test_wrong_market_semantics_and_nonbookmaker_line(self):
        self.quote["legs"][2]["market"] = "fouls_committed"
        self.quote["legs"][3]["market"] = "fouls_committed"
        with self.assertRaisesRegex(ValueError, "both_foul_directions"):
            self.go()
        self.quote["legs"][2]["market"] = "fouls_won"
        self.quote["legs"][3]["market"] = "fouls_won"
        self.quote["legs"][2]["threshold"] = 1
        with self.assertRaisesRegex(ValueError, "unsupported_foul_line"):
            self.go()

    def test_duplicate_player_and_selection_rejected(self):
        self.quote["legs"][1]["player"] = "Joe Willock"
        with self.assertRaisesRegex(ValueError, "duplicate_player"):
            self.go()
        self.quote["legs"][1]["player"] = "William Osula"
        self.quote["legs"][1]["selection_id"] = "qa-1"
        with self.assertRaisesRegex(ValueError, "duplicate_player_or_selection"):
            self.go()

    def test_profile_must_match_club_and_exact_fixture(self):
        self.profiles[0]["team"] = "Manchester United"
        with self.assertRaisesRegex(ValueError, "player_history_or_fixture"):
            self.go()
        self.profiles[0]["team"] = "Newcastle United"
        self.profiles[0]["match"] = "Newcastle United vs Aston Villa"
        with self.assertRaisesRegex(ValueError, "player_history_or_fixture"):
            self.go()

    def test_foul_profile_producer_preserves_15_observations(self):
        rows = [{
            "minutes": 90, "fouls_committed": 2, "fouls_won": 3,
            "shots": 2, "sot": 1, "tackles": 1,
        } for _ in range(15)]
        prof = props.foul_profiles({"Test Player": rows}, "Newcastle United",
                                   "Newcastle United vs Arsenal",
                                   "Premier League", "2026-11-22")
        self.assertEqual(len(prof), 1)
        self.assertEqual(len(prof[0]["fouls"]), 15)
        self.assertEqual(len(prof[0]["fouls_won"]), 15)
        self.assertEqual(prof[0]["history_order"], "latest_first")
        self.assertEqual(len(prof[0]["minutes_series"]), 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
