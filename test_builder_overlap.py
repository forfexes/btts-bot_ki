import netrattler_builder_engine as e

S = ("salas", "m", "shots", 1.5); R = ("ruben", "m", "sot", 1.5); K = ("koch", "m", "shots", 1.5)
A = ("agoume", "m", "shots", 1.5); G = ("raul", "m", "sot", 1.5)


def test_superset_is_duplicate():
    assert e.legsets_overlap(frozenset({S, R, K}), frozenset({S, R, K, G}))


def test_two_of_three_shared_is_duplicate():
    assert e.legsets_overlap(frozenset({A, S, K}), frozenset({S, R, K}))


def test_half_shared_kept():
    assert not e.legsets_overlap(frozenset({S, G}), frozenset({S, R}))


def test_disjoint_kept():
    assert not e.legsets_overlap(frozenset({S, R}), frozenset({K, G}))
