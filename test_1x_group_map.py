from netrattler_1x_group_map import GROUP_STAT, stat_for_group

def test_only_evidenced_groups_listed():
    for g, d in GROUP_STAT.items():
        assert d["n"] >= 40 and d["skill"] >= 0.30
    assert stat_for_group(3357) == "shots"
    assert stat_for_group("3217") == "offsides"
    assert stat_for_group(11591) is None      # negative skill: undecoded
    assert stat_for_group("x") is None
