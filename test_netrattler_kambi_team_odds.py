#!/usr/bin/env python3
from __future__ import annotations

import netrattler_kambi_team_odds as kambi


def test_parse_explicit_team_markets():
    offer = {
        "betOffers": [
            {
                "criterion": {"label": "Match Result"},
                "outcomes": [
                    {"label": "1", "odds": 1850},
                    {"label": "X", "odds": 3600},
                    {"label": "2", "odds": 4300},
                ],
            },
            {
                "criterion": {"label": "Both Teams To Score"},
                "outcomes": [{"label": "Yes", "odds": 1910}, {"label": "No", "odds": 1890}],
            },
            {
                "criterion": {"label": "Total Goals"},
                "outcomes": [
                    {"label": "Over 2.5", "line": 2500, "odds": 1970},
                    {"label": "Under 2.5", "line": 2500, "odds": 1830},
                ],
            },
            {
                "criterion": {"label": "1st Half Total Goals"},
                "outcomes": [{"label": "Over 1.5", "line": 1500, "odds": 2200}],
            },
        ]
    }
    out = kambi.parse_offer(offer)
    assert out["home_win"] == 1.85
    assert out["draw"] == 3.6
    assert out["away_win"] == 4.3
    assert out["btts_yes"] == 1.91
    assert out["over_25"] == 1.97
    assert out["over_15_ht"] == 2.2


def test_no_synthetic_combo_from_separate_legs():
    offer = {
        "betOffers": [
            {"criterion": {"label": "Both Teams To Score"}, "outcomes": [{"label": "Yes", "odds": 1800}]},
            {"criterion": {"label": "Total Goals"}, "outcomes": [{"label": "Over 2.5", "line": 2500, "odds": 1900}]},
        ]
    }
    out = kambi.parse_offer(offer)
    assert out["btts_yes"] == 1.8
    assert out["over_25"] == 1.9
    assert "btts_over25_yes" not in out


def main():
    test_parse_explicit_team_markets()
    test_no_synthetic_combo_from_separate_legs()
    print("OK: multi-brand Kambi explicit team markets")


if __name__ == "__main__":
    main()
