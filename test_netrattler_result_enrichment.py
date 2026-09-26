#!/usr/bin/env python3
from __future__ import annotations

import netrattler_result_enrichment as enrich


def test_fotmob_status_and_scores():
    match = {
        "home": {"name": "A", "score": 2},
        "away": {"name": "B", "score": 1},
        "status": {"finished": True},
    }
    assert enrich._fotmob_finished(match) is True
    assert enrich._fotmob_scores(match) == (2, 1)

    fallback = {
        "home": {"name": "A"},
        "away": {"name": "B"},
        "status": {"reason": {"long": "Full Time"}, "scoreStr": "4 - 2"},
    }
    assert enrich._fotmob_finished(fallback) is True
    assert enrich._fotmob_scores(fallback) == (4.0, 2.0)


def test_current_fotmob_player_stats_shape():
    payload = {
        "content": {
            "playerStats": {
                "9": {
                    "name": "Test Player",
                    "teamName": "A",
                    "stats": [{
                        "stats": {
                            "Shots total": {"key": "totalShots", "stat": {"value": 4}},
                            "Shots on target": {"key": "shotsOnTarget", "stat": {"value": 2}},
                            "Was fouled": {"key": "wasFouled", "stat": {"value": 3}},
                        }
                    }],
                }
            }
        }
    }
    rows = enrich._fotmob_players(payload, "123", "2026-09-25", "A", "B")
    assert len(rows) == 1, rows
    assert rows[0]["player_name"] == "Test Player"
    assert rows[0]["shots"] == 4
    assert rows[0]["shots_on_target"] == 2
    assert rows[0]["fouls_won"] == 3


def main():
    test_fotmob_status_and_scores()
    test_current_fotmob_player_stats_shape()
    print("OK: settlement result enrichment parser")


if __name__ == "__main__":
    main()
