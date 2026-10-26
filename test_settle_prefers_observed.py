import netrattler_settlement_v16_final as s

def test_prefers_row_with_observed_stat():
    leg = {"player": "Federico Valverde", "match": "FC Barcelona vs Real Madrid CF", "category": "shots", "line": 0.5,
           "match_date": "2026-10-25"}
    apif = {"player_name": "Federico Valverde", "team": "Real Madrid", "match_date": "2026-10-25", "shots": None, "sot": None}
    espn = {"player_name": "Federico Valverde", "team": "Real Madrid", "opponent": "Barcelona", "match_date": "2026-10-25",
            "shots": 0, "sot": 0}
    st, _ = s.settle_player_market(leg, [apif, espn], None)
    assert st == "loss"
