#!/usr/bin/env python3
from __future__ import annotations

import netrattler_fotmob_results as fotmob


def test_parse_daily_payload():
    payload = {
        "leagues": [{
            "name": "Premier League",
            "matches": [
                {
                    "id": 101,
                    "home": {"name": "Arsenal", "score": 2},
                    "away": {"name": "Chelsea", "score": 1},
                    "status": {"finished": True},
                },
                {
                    "id": 102,
                    "home": {"name": "Liverpool"},
                    "away": {"name": "Everton"},
                    "status": {"finished": False},
                },
                {
                    "id": 103,
                    "home": {"name": "Fulham"},
                    "away": {"name": "Leeds"},
                    "status": {"reason": {"long": "Full Time"}, "scoreStr": "3 - 3"},
                },
            ],
        }]
    }
    rows = fotmob.parse_daily_payload(payload, "2026-09-25")
    assert len(rows) == 2, rows
    assert rows[0]["home_score"] == 2 and rows[0]["away_score"] == 1
    assert rows[1]["home_score"] == 3 and rows[1]["away_score"] == 3
    assert all(row["source"] == "fotmob" and row["status"] == "finished" for row in rows)


def test_halftime_from_detail():
    ev = lambda **k: k
    d = {"content": {"matchFacts": {"events": {"events": [
        ev(type="Goal", time=12, homeScore=1, awayScore=0),
        ev(type="Goal", time=44, homeScore=1, awayScore=1),
        ev(type="Goal", time=70, homeScore=2, awayScore=1),
    ]}}}}
    assert fotmob.halftime_from_detail(d) == (1, 1)
    d2 = {"content": {"matchFacts": {"events": {"events": [
        ev(type="Card", time=30), ev(type="Goal", time=60, homeScore=1, awayScore=0)]}}}}
    assert fotmob.halftime_from_detail(d2) == (0, 0)
    d3 = {"content": {"matchFacts": {"events": {"events": [
        ev(type="Half", halfStrKey="HT", homeScore=2, awayScore=0)]}}}}
    assert fotmob.halftime_from_detail(d3) == (2, 0)
    assert fotmob.halftime_from_detail({"content": {}}) is None
    assert fotmob.halftime_from_detail(None) is None


def main():
    test_parse_daily_payload()
    test_halftime_from_detail()
    print("OK: FotMob completed-result parser")


if __name__ == "__main__":
    main()
