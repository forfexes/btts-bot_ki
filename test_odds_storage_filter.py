import netrattler_odds_harvester as h

def test_main_lines_kept_alt_lines_dropped():
    keep = ["1x2", "btts", "double_chance", "totals_2_5", "totals_1_5", "totals_3_5", "totals_ht_1_5", "totals_ht_0_5", "corners_over_9_5"]
    drop = ["totals_2_75", "totals_3_0", "totals_2_25", "totals_3_25", "totals_ht_1_25", "totals_ht_1_0", "totals_ht_0_75"]
    for m in keep:
        assert h._storage_worthy({"market": m}), m
    for m in drop:
        assert not h._storage_worthy({"market": m}), m
