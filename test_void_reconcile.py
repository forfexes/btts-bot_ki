import netrattler_settlement_v16_final as s

def test_bare_source_void_id_does_not_close_a_published_tip(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "sb_patch_in", lambda *args: calls.append(args))
    existing = [
        {"settlement_id": "a", "tip_id": "1", "status": "pending", "source_table": "tips"},
        {"settlement_id": "b", "tip_id": "2", "status": "pending", "source_table": "tips"},
    ]
    assert s.reconcile_pending_with_void_sources(existing, {"1"}) == 0
    assert all(row["status"] == "pending" for row in existing)
    assert not calls



def test_unpublished_builders_get_void(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "sb_patch_in", lambda t, c, v, p: calls.append((list(v), p)) or len(v))
    existing = [
        {"settlement_id": "x", "tip_id": "b1", "status": "pending", "source_table": "netrattler_builder_picks"},
        {"settlement_id": "y", "tip_id": "b2", "status": "pending", "source_table": "netrattler_builder_picks"},
    ]
    assert s.reconcile_unpublished_builders(existing, {"b1"}) == 1
    assert existing[0]["status"] == "void" and existing[1]["status"] == "pending"
    assert calls[0][0] == ["x"] and calls[0][1]["reason"].startswith("void:")


def test_msg_id_confirms_delivery():
    assert s.confirmed_builder_delivery({"telegram_sent": False, "telegram_msg_id": "123"})
    assert not s.confirmed_builder_delivery({"telegram_sent": True, "telegram_msg_id": None})
