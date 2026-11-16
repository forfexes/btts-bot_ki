import netrattler_matchup as m

def rows(h, a, hs, as_, n=8):
    return [{"home_team": h if i % 2 == 0 else a, "away_team": a if i % 2 == 0 else h,
             "home_score": hs if i % 2 == 0 else as_, "away_score": as_ if i % 2 == 0 else hs} for i in range(n)]

def test_defensive_pair_lowers_over25_and_leaky_pair_raises():
    data = rows("Aa", "Bb", 0, 1) + rows("Cc", "Dd", 3, 2)
    teams, mean = m.aggregate(data)
    assert mean > 0
    low = m.factor_from(teams[m.norm("Aa")], teams[m.norm("Bb")], mean, "over25")
    high = m.factor_from(teams[m.norm("Cc")], teams[m.norm("Dd")], mean, "over25")
    assert low < 1.0 < high
    assert m.factor_from(None, teams[m.norm("Bb")], mean, "over25") == 1.0
