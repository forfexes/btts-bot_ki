"""Regression: user's original artwork is the only permitted design reference.

The eleven improvised SVG mockups are REJECTED, never production masters.
They remain in a quarantined folder only to preserve change history.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REJECTED = ROOT / "assets" / "new_premium_designs"
ORIGINAL = ROOT / "assets" / "original_templates"
REQUIRED_ORIGINALS = (
    "NETRATTLER_BTTS_originalkarte.png",
    "NETRATTLER_BUILDER_4_originalkarte.png",
    "NETRATTLER_COMBO_7_originalkarte.png",
    "NETRATTLER_COMBO_9_originalkarte.png",
    "NETRATTLER_GOAL_HUNTER_originalkarte.png",
)
PRODUCTION_MODULES = (
    "netrattler_premium_telegram_adapter.py",
    "netrattler_original_template_renderer.py",
    "netrattler_premium_verified_cards.py",
    "netrattler_premium_compact.py",
)


def test_user_original_artwork_remains_authoritative():
    assert all((ORIGINAL / name).is_file() for name in REQUIRED_ORIGINALS)
    assert (ROOT / "assets" / "netrattler_template_corner_original.webp").is_file()


def test_rejected_mockups_never_enter_production_renderers():
    for module in PRODUCTION_MODULES:
        source = (ROOT / module).read_text(encoding="utf-8")
        assert "new_premium_designs" not in source, module
    assert (REJECTED / "REJECTED_NOT_FOR_PRODUCTION.md").is_file()


def test_all_rejected_mockups_are_explicitly_quarantined():
    expected = {
        "over", "btts_halftime", "over_halftime", "match_result",
        "player_props", "fouls_cards", "var", "last_minute_goal",
        "late_goals", "live_halftime", "cross_mix",
    }
    assert {p.stem for p in REJECTED.glob("*.svg")} == expected
    for path in REJECTED.glob("*.svg"):
        data = path.read_text(encoding="utf-8")
        assert "NEW DESIGN / QA ONLY" in data, path


def test_unapproved_premium_renderer_is_blocked_by_default(monkeypatch):
    monkeypatch.delenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS", raising=False)
    from netrattler_premium_telegram_adapter import render
    import pytest
    with pytest.raises(ValueError, match="premium_master_not_visually_approved"):
        render([], "2026-11-22", crest_provider=lambda _: None)
