import netrattler_builder_engine as e

S = ("salas", "m", "shots", 1.5); R = ("ruben", "m", "sot", 1.5); K = ("koch", "m", "shots", 1.5)
A = ("agoume", "m", "shots", 1.5); G = ("raul", "m", "sot", 1.5)


def test_superset_one_more_leg_allowed():
    assert not e.legsets_overlap(frozenset({S, R, K}), frozenset({S, R, K, G}))


def test_two_of_three_shared_is_duplicate():
    assert e.legsets_overlap(frozenset({A, S, K}), frozenset({S, R, K}))


def test_half_shared_kept():
    assert not e.legsets_overlap(frozenset({S, G}), frozenset({S, R}))


def test_disjoint_kept():
    assert not e.legsets_overlap(frozenset({S, R}), frozenset({K, G}))


F1 = ("fonseca", "m", "sot", 0.5); F2 = ("fonseca", "m", "sot", 1.5); F3 = ("fonseca", "m", "sot", 2.5)


def test_ladder_lines_allowed():
    assert not e.legsets_overlap(frozenset({F1, S, K}), frozenset({F2, S, K}))
    assert not e.legsets_overlap(frozenset({F2, S, K}), frozenset({F3, S, K}))


def test_same_tips_other_player_blocked():
    assert e.legsets_overlap(frozenset({F1, S, K}), frozenset({A, S, K}))


def test_identical_blocked():
    assert e.legsets_overlap(frozenset({F1, S}), frozenset({F1, S}))
