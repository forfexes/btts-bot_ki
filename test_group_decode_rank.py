from netrattler_1x_group_decode import rank_groups, clear_winner

def test_rare_stats_do_not_win_on_raw_brier():
    # goals/assists almost always 0 -> tiny Brier but base rate <3% -> skipped
    agg = {"7": {"goals": [500, 5.0, 5.0], "fouls_committed": [500, 100.0, 250.0]}}
    rk = rank_groups(agg)["7"]
    assert [r[1] for r in rk] == ["fouls_committed"]

def test_clear_winner_needs_n_gap_and_skill():
    good = [(0.30, "shots", 400, .5), (0.10, "sot", 400, .4)]
    assert clear_winner(good) == "shots"
    assert clear_winner([(0.30, "shots", 20, .5)]) is None           # n too small
    assert clear_winner([(0.30, "shots", 400, .5), (0.28, "sot", 400, .4)]) is None  # no gap
    assert clear_winner([(0.01, "shots", 400, .5)]) is None          # no skill
