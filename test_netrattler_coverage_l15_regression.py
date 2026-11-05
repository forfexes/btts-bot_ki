"""Regression tests for L10/L15 builder selection and coverage accounting."""
from netrattler_builder_engine import LEG_HISTORY, PropLeg, norm, weak_leg
from netrattler_coverage_watchdog_v37 import build_report


def _leg():
    return PropLeg("Sample Player", "A", "A vs B", "L", "Shots 1+", "shots", 1, 1.8, .7, "pinnacle")


def test_l15_rejects_when_l10_passes(monkeypatch):
    monkeypatch.setenv("NETRATTLER_BUILDER_MIN_HIT", "0.70")
    monkeypatch.setenv("NETRATTLER_BUILDER_MIN_L15_HIT", "0.60")
    leg = _leg()
    key = (norm(leg.player), leg.category)
    try:
        LEG_HISTORY[key] = [1] * 8 + [0] * 2 + [0] * 5
        assert weak_leg(leg) is True  # L10=8/10, L15=8/15
        LEG_HISTORY[key] = [1] * 10 + [0] * 5
        assert weak_leg(leg) is False  # L10=10/10, L15=10/15
    finally:
        LEG_HISTORY.pop(key, None)


def test_l15_not_required_with_only_ten_games(monkeypatch):
    monkeypatch.setenv("NETRATTLER_BUILDER_MIN_HIT", "0.70")
    monkeypatch.setenv("NETRATTLER_BUILDER_MIN_L15_HIT", "0.90")
    leg = _leg()
    key = (norm(leg.player), leg.category)
    try:
        LEG_HISTORY[key] = [1] * 8 + [0] * 2
        assert weak_leg(leg) is False
    finally:
        LEG_HISTORY.pop(key, None)


def test_external_candidate_counts_do_not_fake_filtered_tips():
    report = build_report(extra_counts={"corners": 5, "scorer": 3})
    assert report["before_filter"]["corners"] == 5
    assert report["after_filter"]["corners"] == 0


def test_external_explicit_after_filter_preserved():
    report = build_report(extra_counts={"corners": 5}, after_filter={"corners": [{}, {}]})
    assert report["before_filter"]["corners"] == 5
    assert report["after_filter"]["corners"] == 2
