import netrattler_settlement_v16_final as s


def _row(**k):
    base = {"fixture_id": 1, "player_id": 9, "player_name": "Rodri", "team": "Manchester City", "match_date": "2026-10-23",
            "minutes": 90, "shots": 2, "shots_on": 1, "fouls_committed": 3, "fouls_drawn": 1, "yellow": 1, "red": 0, "tackles": 4, "passes": 70}
    base.update(k)
    return s._normalize_apif_row(base)


def _leg(category, line):
    return {"player": "Rodri", "category": category, "line": line, "match": "Manchester City vs AEK Athens",
            "market": f"Rodri {category} Over {line - 0.5}", "date": "2026-10-23", "_table": "tips"}


def _settle(category, line, **k):
    rows = s._aggregate_player_rows([_row(**k)], {s.norm("Rodri")})
    return s.settle_player_market(_leg(category, line), rows, None)


def test_tackles_win_and_loss():
    assert _settle("tackles", 4.0)[0] == "win"
    assert _settle("tackles", 5.0)[0] == "loss"


def test_fouls_and_fouls_won():
    assert _settle("fouls", 3.0)[0] == "win"
    assert _settle("fouls_won", 2.0)[0] == "loss"


def test_sot_and_cards_from_apif_names():
    assert _settle("sot", 1.0)[0] == "win"
    assert _settle("yellow_cards", 1.0)[0] == "win"


def test_wrong_team_or_date_stays_pending():
    assert _settle("tackles", 1.0, team="Real Madrid")[0] == "pending"
    assert _settle("tackles", 1.0, match_date="2026-10-22")[0] == "pending"
