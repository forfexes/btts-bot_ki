import netrattler_model_builders as mb


def leg(player, p=80, line=2, match="A vs B"):
    return {"player": player, "match": match, "market": f"{player} {line}+ Fouls", "category": "fouls",
            "line": float(line), "probability": p, "source": "model_line_fouls", "series": [3, 2, 2, 3, 2, 1, 2, 3, 2, 2]}


def test_builds_three_leg_when_joint_high_enough():
    z = leg("Z", 86); z["category"] = "sot"
    picks = mb.build([leg("X", 90), leg("Y", 88), z], "2026-10-28")
    assert any(p["size"] == 3 for p in picks) and all(p["fair"] > 1 for p in picks)


def test_rejects_low_joint_and_non_model_rows():
    assert mb.build([leg("X", 60), leg("Y", 60)], "d") == []
    r = leg("X", 95); r["source"] = "kambi"
    assert mb.build([r, leg("Y", 95)], "d") == []


def test_message_flags_no_bookmaker_quote():
    p = mb.build([leg("X", 90), leg("Y", 90)], "d")[0]
    m = mb.message(p, "d")
    assert "keine Buchmacherquote" in m and "L10:" in m and "faire Quote" in m


def test_mixes_categories():
    rows = [leg("A", 90), leg("B", 89), leg("C", 88)]
    for r, c in zip(rows, ("shots", "shots", "shots")):
        r["category"] = c
    rows.append({**leg("D", 80), "category": "fouls"})
    picks = mb.build(rows, "d")
    assert all(sum(1 for l in p["legs"] if l["category"] == "shots") <= 2 for p in picks)


def test_foul_builders_only_foul_categories_and_cross():
    rows = []
    for m in ("A vs B", "C vs D", "E vs F"):
        for pl in ("p1", "p2", "p3"):
            rows.append({**leg(pl + m[0], 85, match=m)})
        rows.append({**leg("sh" + m[0], 95, match=m), "category": "shots"})
    picks = mb.build_fouls(rows, "d")
    assert picks and all(l["category"] in mb.FOUL_CATS for p in picks for l in p["legs"])
    assert any(p["match"] == "Cross-Match" for p in picks)
    assert "FOUL BUILDER" in mb.message(picks[0], "d")


class _Response:
    def __init__(self, ok=True, rows=None, status_code=200):
        self.ok = ok
        self._rows = [{"builder_id": "new"}] if rows is None else rows
        self.status_code = status_code

    def json(self):
        return self._rows


def _one_pick(monkeypatch):
    p = mb.build([leg("X", 95), leg("Y", 94)], "2026-10-28")[0]
    monkeypatch.setattr(mb, "build", lambda rows, day: [p])
    monkeypatch.setattr(mb, "build_fouls", lambda rows, day: [])
    monkeypatch.setenv("NETRATTLER_MODEL_BUILDERS", "on")
    return p


def test_model_builder_db_failure_never_sends(monkeypatch):
    _one_pick(monkeypatch)
    sent = []
    monkeypatch.setattr(mb.requests, "post", lambda *a, **kw: _Response(ok=False, status_code=503))
    monkeypatch.setattr(mb.requests, "patch", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no patch")))
    assert mb.run([], "2026-10-28", sent.append, "https://db.invalid", "key") == 0
    assert sent == []


def test_model_builder_existing_reservation_never_resends(monkeypatch):
    _one_pick(monkeypatch)
    sent = []
    monkeypatch.setattr(mb.requests, "post", lambda *a, **kw: _Response(rows=[]))
    assert mb.run([], "2026-10-28", sent.append, "https://db.invalid", "key") == 0
    assert sent == []


def test_model_builder_records_receipt_for_original_edit(monkeypatch):
    import json
    _one_pick(monkeypatch)
    monkeypatch.setenv("TELEGRAM_GROUP_STATS", "-100987")
    monkeypatch.delenv("TELEGRAM_GROUP_BUILDER", raising=False)
    monkeypatch.delenv("TELEGRAM_GROUP_PLAYER_PROPS", raising=False)
    captured = {}
    def post(*args, **kw):
        captured["reservation"] = json.loads(kw["data"])
        return _Response()
    def patch(*args, **kw):
        captured["patch"] = json.loads(kw["data"])
        captured["params"] = kw["params"]
        return _Response()
    monkeypatch.setattr(mb.requests, "post", post)
    monkeypatch.setattr(mb.requests, "patch", patch)
    assert mb.run([], "2026-10-28", lambda msg: 12345, "https://db.invalid", "key") == 1
    assert captured["reservation"]["telegram_sent"] is False
    assert "keine Buchmacherquote" in captured["reservation"]["message_text"]
    assert captured["patch"]["telegram_sent"] is True
    assert captured["patch"]["telegram_msg_id"] == "12345"
    assert captured["patch"]["telegram_chat_id"] == "-100987"
    assert captured["patch"]["message_text"] == captured["reservation"]["message_text"]


def test_model_builder_failed_send_stays_reserved_without_fake_receipt(monkeypatch):
    _one_pick(monkeypatch)
    monkeypatch.setattr(mb.requests, "post", lambda *a, **kw: _Response())
    patches = []
    monkeypatch.setattr(mb.requests, "patch", lambda *a, **kw: patches.append(kw))
    assert mb.run([], "2026-10-28", lambda msg: None, "https://db.invalid", "key") == 0
    assert patches == []


def test_model_builder_actual_chat_receipt_overrides_config(monkeypatch):
    _one_pick(monkeypatch)
    monkeypatch.setenv("TELEGRAM_GROUP_STATS", "-100wrong")
    captured = {}
    monkeypatch.setattr(mb.requests, "post", lambda *a, **kw: _Response())
    def patch(*args, **kw):
        captured.update(json.loads(kw["data"]))
        return _Response()
    import json
    monkeypatch.setattr(mb.requests, "patch", patch)
    receipt = {"message_id": 987, "chat_id": "-100actual", "text": "actual text"}
    assert mb.run([], "2026-10-28", lambda msg: receipt, "https://db.invalid", "key") == 1
    assert captured["telegram_chat_id"] == "-100actual"
    assert captured["message_text"] == "actual text"
