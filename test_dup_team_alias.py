import btts_bot as bb
from netrattler_identity_hub import teams_match


def test_brest_alias_is_same_team():
    assert bb._dedupe_team_same(teams_match, "Brest", "Stade Brest 29")
    assert bb._dedupe_team_same(teams_match, "Stade Brest 29", "Brest")
    assert bb._dedupe_team_same(teams_match, "Lorient", "FC Lorient")


def test_different_teams_stay_different():
    assert not bb._dedupe_team_same(teams_match, "Real Madrid", "Real Sociedad")
    assert not bb._dedupe_team_same(teams_match, "Brest", "Brentford")
    assert not bb._dedupe_team_same(teams_match, "Inter", "Inter Miami")


def test_fixture_dedupe_with_aliases():
    bb._SENT_MATCHES.clear()
    bb._SENT_MATCHES[("2026-11-02", "btts")] = [("FC Lorient", "Stade Brest 29")]
    assert bb._fuzzy_sent_match("Lorient vs Brest", "btts", "2026-11-02")
    assert not bb._fuzzy_sent_match("Lorient vs Nice", "btts", "2026-11-02")
