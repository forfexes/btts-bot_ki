#!/usr/bin/env python3
"""Offline regression checks for NETRATTLER SAFE ROLLBACK STEP 1.

No network calls are required. The test protects the production contracts that
regressed in V37: core-market picks must not be killed by runtime/max-edge,
REAL_ODDS_ONLY stays enforced, corner selections keep their exact line, Supabase
integer fields are normalized, and real Kambi-style player props still reach the
Builder pool when strict-edge mode is disabled.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_core_safe_filter(bot):
    bot.get_bet365_quote_any_source = lambda tip, odds_data=None: (None, "none")

    cases = [
        ("1x2", 60.0, 3.00, "1"),       # would previously hit above_max
        ("btts", 61.0, 1.90, "YES"),
        ("over25", 61.0, 1.90, "YES"),
        ("btts_ht", 40.0, 2.90, "BTTS HT"),
        ("over15_ht", 44.0, 2.70, "Over 1.5 HT"),
    ]
    for market, probability, odds, tip_text in cases:
        row = {
            "match": "Home vs Away",
            "market": market,
            "tip": tip_text,
            "selection": tip_text,
            "probability": probability,
            "odds": odds,
            "oddsYes": odds,
            "_no_real_odds": False,
            "_source": "pinnacle",
        }
        kept = bot.filter_tips_legacy_safe([row], market)
        assert len(kept) == 1, (market, kept)

    # REAL_ODDS_ONLY remains mandatory.
    no_quote = {
        "match": "Home vs Away", "market": "btts", "tip": "YES",
        "probability": 70, "odds": 0, "oddsYes": 0,
        "_no_real_odds": True,
    }
    assert bot.filter_tips_legacy_safe([no_quote], "btts") == []

    # A genuinely low-edge tip still must not pass.
    low_edge = {
        "match": "Home vs Away", "market": "btts", "tip": "YES",
        "probability": 58, "odds": 1.70, "oddsYes": 1.70,
        "_no_real_odds": False, "_source": "pinnacle",
    }
    assert bot.filter_tips_legacy_safe([low_edge], "btts") == []


def test_corner_combo_contract(bot):
    combo = bot.generate_multi_combo_bets([
        {
            "match": "A vs B", "market": "corners", "tip": "Over 7.5 Ecken",
            "selection": "Over 7.5 Ecken", "line": 7.5, "probability": 73,
            "odds": 2.55, "confidence": 3, "_no_real_odds": False,
        },
        {
            "match": "C vs D", "market": "btts", "tip": "YES",
            "probability": 60, "odds": 1.85, "confidence": 3,
            "_no_real_odds": False,
        },
        {
            "match": "E vs F", "market": "over25", "tip": "YES",
            "probability": 60, "odds": 1.90, "confidence": 3,
            "_no_real_odds": False,
        },
    ], 3)
    assert combo is not None
    corner = next(x for x in combo["tips"] if x["market"] == "corners")
    assert corner["line"] == 7.5
    assert corner["selection"] == "Over 7.5 Ecken"
    message = bot.format_combo_telegram_message(combo)
    assert "Over 7.5 Ecken @ 2.55" in message
    assert "· Corners @ 2.55" not in message


def test_supabase_integer_normalization(bot):
    captured = []

    class Response:
        ok = True
        status_code = 201
        text = ""

        @staticmethod
        def json():
            return []

    def fake_post(*args, **kwargs):
        captured.append(kwargs.get("json", {}))
        return Response()

    bot.SUPABASE_URL = "https://example.supabase.co"
    bot.SUPABASE_KEY = "test-key"
    bot.requests.post = fake_post
    bot.log_tip_for_ml = lambda *args, **kwargs: True

    assert bot.save_to_supabase({
        "tip_id": "regression-1", "date": "2026-09-19", "market": "btts",
        "match": "A vs B", "tip": "YES", "probability": 59.0, "confidence": 3.0,
    })
    assert captured[-1]["probability"] == 59
    assert isinstance(captured[-1]["probability"], int)

    assert bot.save_to_supabase({
        "tip_id": "regression-2", "date": "2026-09-19", "market": "combo_multi",
        "match": "A/B/C", "tip": "Multi", "probability": 31.44,
        "confidence": 3, "builder_total_legs": 3.0,
    })
    assert captured[-1]["probability"] == 31
    assert captured[-1]["builder_total_legs"] == 3


def test_builder_compat(builder):
    rows = []
    for i in range(624):
        rows.append({
            "player": f"Player {i}",
            "team": "A" if i % 2 == 0 else "B",
            "match": f"Team {i // 40}A vs Team {i // 40}B",
            "league": "Test",
            "market": "Shots on Target",
            "category": "sot",
            "line": 0.5,
            "odds": 1.80 + (i % 10) * 0.05,
            "source": "kambi_ub",
            "probability": 0,
            "hit_rate": 0,
            "games": 0,
        })

    os.environ.pop("NETRATTLER_BUILDER_STRICT_EDGE", None)
    normalized = builder.deduplicate_props(rows)
    assert len(normalized) == 624
    assert all(x.edge == 0.0 for x in normalized)

    os.environ["NETRATTLER_BUILDER_STRICT_EDGE"] = "true"
    strict = builder.deduplicate_props(rows)
    assert len(strict) == 0
    os.environ.pop("NETRATTLER_BUILDER_STRICT_EDGE", None)


def main():
    bot = load_module("btts_bot_regression", ROOT / "btts_bot.py")
    builder = load_module("builder_regression", ROOT / "netrattler_builder_engine.py")
    test_core_safe_filter(bot)
    test_corner_combo_contract(bot)
    test_supabase_integer_normalization(bot)
    test_builder_compat(builder)
    print("OK: NETRATTLER SAFE ROLLBACK STEP 1 regression suite passed")


if __name__ == "__main__":
    main()
