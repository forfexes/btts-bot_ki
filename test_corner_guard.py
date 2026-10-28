import btts_bot


def test_no_corner_tip_without_team_stats(monkeypatch):
    monkeypatch.setenv("NETRATTLER_CORNER_REQUIRE_TEAM_STATS", "true")
    fx = {"home": "A", "away": "B"}  # keine API-Football-IDs
    assert btts_bot.analyze_corners_tip(fx, "MLS", "2026-10-29") is None
