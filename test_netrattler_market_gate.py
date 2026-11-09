import netrattler_market_gate as g
def test_blocks_losing_group():
    rows=[{"market":"over15_ht","status":"loss","odds":"2.5"}]*30+[{"market":"over15_ht","status":"win","odds":"2.5"}]*10
    rows+= [{"market":"corners","status":"win","odds":"2.5"}]*50
    b=g.blocked_groups(rows)
    assert ("corners","2-3") not in b
def test_small_sample_not_blocked():
    assert not g.blocked_groups([{"market":"1x2","status":"loss","odds":"2.0"}]*10)
def test_soft_shrink_not_block():
    rows=[{"market":"over15_ht","status":"loss","odds":"2.5"}]*30+[{"market":"over15_ht","status":"win","odds":"2.5"}]*10
    assert not g.blocked_groups(rows)
    g._CACHE=set(); g._RATES=g.group_rates(rows)
    assert g.adjust_probability("","","over15_ht",2.5,0.6) < 0.6
