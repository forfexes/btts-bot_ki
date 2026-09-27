#!/usr/bin/env python3
from __future__ import annotations

import netrattler_aiscore as aiscore


def test_h2h_summary_parser():
    text = (
        "Head to Head Record Last 5 , Arsenal Win 3 , Draw 1 , Lose 1 , "
        "Score Win Prob: 60.00% ,Asian Handicap Win%: 55.0% Total Goals Over%: 80.0% "
        "Last 5 , Chelsea Win 2 , Draw 2 , Lose 1 , Score Win Prob: 40.00% ,"
        "Asian Handicap Win%: 45.0% Total Goals Over%: 60.0% In the last 7 matches"
    )
    out = aiscore.extract_h2h_features_from_text(text, "Arsenal", "Chelsea")
    assert out["has_h2h"] is True
    assert out["h2h_n"] == 7
    assert out["home_last5_win_prob_pct"] == 60.0
    assert out["away_last5_over_pct"] == 60.0


def test_explicit_nested_odds_parser():
    payload = {
        "bookmaker": {"name": "ExampleBook"},
        "markets": [
            {
                "marketName": "Match Result 1X2",
                "outcomes": [
                    {"name": "1", "decimalOdds": 1.91},
                    {"name": "X", "decimalOdds": 3.55},
                    {"name": "2", "decimalOdds": 4.20},
                ],
            },
            {
                "marketName": "Both Teams To Score",
                "outcomes": [
                    {"name": "Yes", "price": 1.88},
                    {"name": "No", "price": 1.95},
                ],
            },
            {
                "marketName": "Total Goals Over/Under 2.5",
                "outcomes": [
                    {"name": "Over", "point": 2.5, "decimalValue": 1.97},
                    {"name": "Under", "point": 2.5, "decimalValue": 1.83},
                ],
            },
            {
                "marketName": "Total Corners",
                "outcomes": [
                    {"name": "Over", "line": 9.5, "odds": 1.90},
                    {"name": "Under", "line": 9.5, "odds": 1.90},
                ],
            },
        ],
    }
    rows = aiscore.extract_observed_odds_from_json(payload, "Arsenal", "Chelsea", "https://m.aiscore.com/test")
    keys = {(r["market"], r["selection"]) for r in rows}
    assert ("1x2", "home") in keys
    assert ("1x2", "draw") in keys
    assert ("1x2", "away") in keys
    assert ("btts", "yes") in keys
    assert ("totals_2_5", "over_2_5") in keys
    assert ("corners_9_5", "over_9_5") in keys
    assert all(r["observed"] is True and r["bookmaker"] == "ExampleBook" for r in rows)


def test_unknown_numbers_are_not_odds():
    payload = {
        "homeScore": 2,
        "awayScore": 1,
        "possession": 61,
        "probability": 0.73,
        "items": [{"name": "Arsenal", "value": 1.85}],
    }
    rows = aiscore.extract_observed_odds_from_json(payload, "Arsenal", "Chelsea")
    assert rows == []


def test_totals_require_exact_observed_line():
    payload = {
        "marketName": "Total Goals",
        "outcomes": [
            {"name": "Over", "decimalOdds": 1.85},
        ],
    }
    rows = aiscore.extract_observed_odds_from_json(payload, "A", "B")
    assert rows == []


def test_odds_history_shape():
    matches = [{
        "home": "Arsenal",
        "away": "Chelsea",
        "odds": [{
            "market": "btts",
            "selection": "yes",
            "line": None,
            "odds": 1.91,
            "bookmaker": "ExampleBook",
            "source_url": "https://m.aiscore.com/test",
        }],
    }]
    rows = aiscore.odds_history_rows(matches, "2026-09-27")
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "aiscore"
    assert row["market"] == "btts"
    assert row["selection"] == "yes"
    assert row["odds"] == 1.91
    assert row["raw"]["observed"] is True


def main():
    test_h2h_summary_parser()
    test_explicit_nested_odds_parser()
    test_unknown_numbers_are_not_odds()
    test_totals_require_exact_observed_line()
    test_odds_history_shape()
    print("OK: AiScore H2H + explicit observed-odds parser")


if __name__ == "__main__":
    main()
