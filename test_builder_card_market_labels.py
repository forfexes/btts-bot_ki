from types import SimpleNamespace
from netrattler_builder_cards import builder_leg_label


def test_shots_and_shots_on_target_are_distinct():
    assert builder_leg_label(SimpleNamespace(category='shots', line=2.0)) == '2+ Shots (Schüsse gesamt)'
    assert builder_leg_label(SimpleNamespace(category='sot', line=1.5)) == '2+ Shots on Target (Schüsse aufs Tor)'
    assert builder_leg_label(SimpleNamespace(category='shots', line=1.0)) == '1+ Shots (Schüsse gesamt)'


def test_unknown_market_is_not_mislabelled():
    assert builder_leg_label(SimpleNamespace(category='custom', market='Exact market')) == 'Exact market'
