"""Regression tests for screenshot-derived prop ladders."""
from dataclasses import replace
import netrattler_builder_concepts_v2 as concepts
import netrattler_builder_engine as engine


def leg(player, match, category, line, odds=2.1):
    return engine.PropLeg(player=player, team="Home", match=match, league="Test",
                          market="Over", category=category, line=line, odds=odds,
                          probability=.8, source="22bet", quality=.9, edge=10.0)


def test_card_builders_require_real_quotes(monkeypatch):
    monkeypatch.setattr(engine, "_make_builder", lambda style, variant, legs, date, stake: (style, variant, legs))
    rows = [leg(f"Player {i}", "A vs B", "yellow_cards", .5) for i in range(4)]
    assert len(concepts._cards(rows, "2026-11-05")) == 3
    assert concepts._cards([replace(x, estimated=True) for x in rows], "2026-11-05") == []


def test_foul_ladder_keeps_verified_lines(monkeypatch):
    monkeypatch.setattr(engine, "_make_builder", lambda style, variant, legs, date, stake: (style, variant, legs))
    rows = [leg(f"Player {i}", "A vs B", "fouls", line) for i in range(4) for line in (.5, 1.5, 2.5)]
    picks = concepts._foul_ladder(rows, "2026-11-05")
    assert any(p[1] == "HIGH 4L" and all(x.line == 2.5 for x in p[2]) for p in picks)
    assert not any(p[1].startswith("LONGSHOT") for p in picks)


def test_cross_match_shots_do_not_synthesize_lines(monkeypatch):
    monkeypatch.setattr(engine, "_make_builder", lambda style, variant, legs, date, stake: (style, variant, legs))
    rows = [leg("One", "A vs B", "shots", line) for line in (.5, 1.5)]
    rows += [leg("Two", "C vs D", "shots", line) for line in (.5, 1.5)]
    picks = concepts._cross_shot_ladder(rows, "2026-11-05")
    assert {p[1] for p in picks} == {"LOW 2L", "MID 2L"}
    assert all(p[2][0].match != p[2][1].match for p in picks)
