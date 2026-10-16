#!/usr/bin/env python3
"""Regression tests for daily TheSportsDB cache and outage circuit breaker."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import netrattler_thesportsdb_guard as guard


def make_bot(response):
    day = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    events = [
        {"dateEvent": day, "idLeague": "101", "strStatus": "Not Started",
         "strHomeTeam": "Arsenal", "strAwayTeam": "Chelsea",
         "strTime": "18:00:00", "idEvent": "42"},
        {"dateEvent": day, "idLeague": "202", "strStatus": "",
         "strHomeTeam": "Celtic", "strAwayTeam": "Rangers",
         "strTime": "17:00:00", "idEvent": "43"},
        {"dateEvent": day, "idLeague": "101", "strStatus": "Match Finished",
         "strHomeTeam": "Other", "strAwayTeam": "Other2",
         "strTime": "15:00:00", "idEvent": "44"},
        {"dateEvent": day, "idLeague": "101", "strStatus": "",
         "strHomeTeam": "NoKickoff", "strAwayTeam": "Time",
         "strTime": "not-a-time", "idEvent": "45"},
    ]
    resp = SimpleNamespace(ok=response, status_code=503 if not response else 200,
                           json=lambda: {"events": events})
    get = Mock(return_value=resp)
    bot = SimpleNamespace(
        requests=SimpleNamespace(get=get),
        THESPORTSDB_FIXTURES_CACHE={},
        THESPORTSDB_LEAGUE_IDS={"Premier League": 101, "Scottish": 202},
        get_local_time=lambda iso: "local-" + iso,
        log=Mock(),
        fetch_thesportsdb_fixtures=lambda *_: ["original"],
    )
    return bot, get, day


class DayCacheTests(unittest.TestCase):
    def setUp(self):
        guard._DAY_CACHE.clear()
        guard._WARNED.clear()

    def test_one_fetch_for_multiple_leagues_and_repeated_calls(self):
        bot, get, day = make_bot(True)
        guard.install(bot)
        home = bot.fetch_thesportsdb_fixtures("Premier League", day)
        away = bot.fetch_thesportsdb_fixtures("Scottish", day)
        self.assertEqual([x["match_id"] for x in home], ["42"])
        self.assertEqual([x["match_id"] for x in away], ["43"])
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Premier League", day), home)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["timeout"], 5.0)
        guard.install(bot)
        self.assertEqual(get.call_count, 1)

    def test_network_failure_circuits_for_entire_day(self):
        bot, get, day = make_bot(False)
        guard.install(bot)
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Premier League", day), [])
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Scottish", day), [])
        self.assertEqual(get.call_count, 1)
        self.assertEqual(bot.log.call_count, 1)

    def test_fails_closed_on_malformed_response(self):
        bot, get, day = make_bot(True)
        get.return_value = SimpleNamespace(ok=True, json=lambda: {"events": "bad"})
        guard.install(bot)
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Premier League", day), [])
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Scottish", day), [])
        self.assertEqual(get.call_count, 1)

    def test_unknown_league_does_not_make_request(self):
        bot, get, day = make_bot(True)
        guard.install(bot)
        self.assertEqual(bot.fetch_thesportsdb_fixtures("Unknown", day), [])
        self.assertEqual(get.call_count, 0)


if __name__ == "__main__":
    unittest.main()
