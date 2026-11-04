"""Regression tests for L15 builder gate and coverage accounting."""
from netrattler_builder_engine import LEG_HISTORY, PropLeg, norm, weak_leg
from netrattler_coverage_watchdog_v37 import build_report


def test_builder_rejects_weak_l15_despite_strong_l10(monkeypatch):
    monkeypatch.delenv("NETRATTLER_BUILDER_MIN_L15_HIT", raising=False)
    leg = PropLeg("Sample Player", "A", "A vs B", "L", "Shots 1+", "shots", 1, 1.8, .7, "pinnacle")
    key = (norm(leg.player), leg.category)
    try:
        LEG_HISTORY[key] = [1] * 10 + [0] * 5
        assert weak_leg(leg) is False  # L15 10/15 >= 60%
        LEG_HISTORY[key] = [1] * 10 + [0] * 5
        monkeypatch.setenv("NETRATTLER_BUILDER_MIN_L15_HIT", "0.70")
        assert weak_leg(leg) is True
    finally:
        LEG_HISTORY.pop(key, None)


def test_external_candidate_counts_do_not_fake_filtered_tips():
    report = build_report(extra_counts={"corners": 5, "scorer": 3})
    assert report["before_filter"]["corners"] == 5
    assert report["after_filter"]["corners"] == 0
    assert report["problems"]["corners"] == "filtered_out"


def test_external_explicit_after_filter_preserved():
    report = build_report(extra_counts={"corners": 5}, after_filter={"corners": [{}, {}]})
    assert report["before_filter"]["corners"] == 5
    assert report["after_filter"]["corners"] == 2
