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

def test_partial_rosters_do_not_void_absent_player():
    leg = {"player": "Nicht Dabei", "match": "Ajax vs PSV", "category": "shots", "line": 0.5, "match_date": "2026-10-25"}
    # 9+9 names are not a complete two-team roster, and these rows lack
    # exact home/away fixture identity. Absence must remain unconfirmed.
    stats = _rows("Ajax", 9) + _rows("PSV", 9)
    st, _ = s.settle_player_market(leg, stats, None)
    assert st == "pending"

def test_pending_when_match_not_covered():
    leg = {"player": "Nicht Dabei", "match": "Ajax vs PSV", "category": "shots", "line": 0.5, "match_date": "2026-10-25"}
    st, _ = s.settle_player_market(leg, _rows("Ajax", 3), None)
    assert st == "pending"


def test_adjacent_day_needs_exact_player_both_teams_and_unique_fixture():
    leg = {"player": "Milton Celiz", "match": "Instituto vs Deportivo Riestra", "category": "sot", "line": 1,
           "match_date": "2026-10-26"}
    row = {"player_name": "Milton Céliz", "team": "Deportivo Riestra", "opponent": "Instituto",
           "match_date": "2026-10-27", "match_id": "espn-123", "sot": 1}
    assert s.settle_player_market(leg, [row], None)[0] == "win"
    assert s.find_player_stat(leg, [dict(row, opponent=None)]) is None
    assert s.find_player_stat(leg, [dict(row, opponent="Other")]) is None
    assert s.find_player_stat(leg, [dict(row, player_name="Other Celiz")]) is None
    assert s.find_player_stat(leg, [row, dict(row, match_id="espn-456")]) is None
    assert s.find_player_stat(leg, [dict(row, match_date="2026-10-28")]) is None


def test_no_separate_settlement_reports_even_with_emergency_flag(monkeypatch):
    from unittest.mock import Mock
    send = Mock()
    monkeypatch.setattr(s, "telegram", send)
    monkeypatch.setenv("SETTLEMENT_ALLOW_SEPARATE_RESULT_UPDATE", "true")
    row = {"tip_id": "test", "status": "loss", "market_group": "builder", "tip_payload": {}}
    s.send_group_reports([row], [], [])
    s.send_roi_report([])
    assert not s.edit_original_tip(row)
    send.assert_not_called()


def test_lost_builder_with_open_legs_is_rechecked():
    row = {"market_group": "builder", "status": "loss", "tip_date": s.TODAY_S,
           "legs_payload": [{"status": "loss"}, {"status": "pending"}],
           "tip_payload": {"tip_id": "b1", "telegram_msg_id": "123"}}
    assert len(s.refreshable_closed_builders([row])) == 1
    assert s.refreshable_closed_builders([dict(row, legs_payload=[{"status": "loss"}])]) == []


def test_changed_leg_results_do_not_inherit_old_edit_success():
    base = {"settlement_id": "s1", "tip_id": "t1", "status": "loss", "telegram_msg_id": "1", "telegram_chat_id": "-1"}
    old = dict(base, legs_payload=[{"status": "pending"}], raw={"telegram_edit_ok": True, "telegram_edit_attempts": 4})
    new = dict(base, legs_payload=[{"status": "win"}])
    assert s.preserve_telegram_edit_receipts([new], [old]) == 0
    assert "raw" not in new


def test_failed_new_edit_clears_previous_success(monkeypatch):
    from unittest.mock import Mock
    store = Mock(return_value=True)
    monkeypatch.setattr(s, "sb_patch", store)
    row = {"settlement_id": "s1", "raw": {"telegram_edit_ok": True}}
    s._save_tip_edit_receipt(row, False)
    assert row["raw"]["telegram_edit_ok"] is False
    assert store.call_args.args[3]["raw"]["telegram_edit_ok"] is False
