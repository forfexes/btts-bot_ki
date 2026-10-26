import netrattler_settlement_v16_final as s

def test_pending_with_void_source_gets_void(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "sb_patch_in", lambda t, c, v, p: calls.append((t, c, list(v), p)) or len(v))
    existing = [
        {"settlement_id": "a", "tip_id": "1", "status": "pending", "source_table": "tips"},
        {"settlement_id": "b", "tip_id": "2", "status": "pending", "source_table": "tips"},
        {"settlement_id": "c", "tip_id": "1", "status": "win", "source_table": "tips"},
        {"settlement_id": "d", "tip_id": "1", "status": "pending", "source_table": "netrattler_builder_picks"},
    ]
    n = s.reconcile_pending_with_void_sources(existing, {"1"})
    assert n == 1 and existing[0]["status"] == "void" and existing[1]["status"] == "pending"
    assert existing[2]["status"] == "win" and existing[3]["status"] == "pending"
    assert calls and calls[0][2] == ["a"] and calls[0][3]["status"] == "void" and calls[0][3]["reason"].startswith("void: kein Ergebnis nach")
    # idempotent: zweiter Durchlauf aendert nichts
    assert s.reconcile_pending_with_void_sources(existing, {"1"}) == 0
