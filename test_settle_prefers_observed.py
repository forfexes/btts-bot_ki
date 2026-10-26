import netrattler_settlement_v16_final as s

def test_prefers_row_with_observed_stat():
    leg = {"player": "Federico Valverde", "match": "FC Barcelona vs Real Madrid CF", "category": "shots", "line": 0.5,
           "match_date": "2026-10-25"}
    apif = {"player_name": "Federico Valverde", "team": "Real Madrid", "match_date": "2026-10-25", "shots": None, "sot": None}
    espn = {"player_name": "Federico Valverde", "team": "Real Madrid", "opponent": "Barcelona", "match_date": "2026-10-25",
            "shots": 0, "sot": 0}
    st, _ = s.settle_player_market(leg, [apif, espn], None)
    assert st == "loss"


def _rows(team, n, day="2026-10-25"):
    return [{"player_name": f"{team} Spieler{i}", "team": team, "match_date": day, "shots": 1, "sot": 0} for i in range(n)]

def test_absent_player_void_when_match_covered():
    leg = {"player": "Nicht Dabei", "match": "Ajax vs PSV", "category": "shots", "line": 0.5, "match_date": "2026-10-25"}
    stats = _rows("Ajax", 9) + _rows("PSV", 9)
    st, _ = s.settle_player_market(leg, stats, None)
    assert st == "void"

def test_pending_when_match_not_covered():
    leg = {"player": "Nicht Dabei", "match": "Ajax vs PSV", "category": "shots", "line": 0.5, "match_date": "2026-10-25"}
    st, _ = s.settle_player_market(leg, _rows("Ajax", 3), None)
    assert st == "pending"
