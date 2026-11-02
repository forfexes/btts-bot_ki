import netrattler_settlement_v16_final as st


def _row(tid, status="win"):
    return {"tip_id": tid, "market_group": "builder", "status": status, "tip_date": st.TODAY.isoformat(),
            "tip_payload": {"home": "A", "away": "B", "match": "A vs B", "telegram_msg_id": "12", "style": "NATE ALT-LINE"},
            "legs_payload": [
                {"status": "win", "leg": {"player": "X", "market": "2+ Schüsse"}, "reason": "ok · 3 · Linie 2"},
                {"status": "loss", "leg": {"player": "Y", "market": "1+ Fouls"}, "reason": "x · 0 · Linie 1"}]}


def test_format_has_legs_and_no_roi_or_source_names():
    text = st.format_builder_result(_row("t1", "loss"))
    assert "X" in text and "Y" in text and "1/2 Beine" in text
    assert "ROI" not in text and "Profit" not in text and "Nate" not in text and "NATE" not in text


def test_sends_once_and_remembers(monkeypatch):
    sent, marks = [], []
    monkeypatch.setattr(st, "_sent_builder_results", lambda: set())
    monkeypatch.setattr(st, "_remember_builder_results", lambda ids: marks.extend(ids))
    monkeypatch.setattr(st, "telegram_send", lambda chat, text: sent.append(text) or True)
    monkeypatch.setattr(st, "learned_chat", lambda g, rows: "chat")
    monkeypatch.setattr(st.time, "sleep", lambda s: None)
    n = st.send_builder_results([], [_row("t1"), _row("t2", "loss"), {**_row("t3"), "status": "pending"}])
    assert n == 2 and sorted(marks) == ["t1", "t2"] and len(sent) == 1
    assert "RESULT SETTLEMENT · BUILDER" in sent[0]
    # schon gemeldete werden nicht nochmal gesendet
    monkeypatch.setattr(st, "_sent_builder_results", lambda: {"t1", "t2"})
    sent.clear()
    assert st.send_builder_results([], [_row("t1"), _row("t2")]) == 0 and not sent
