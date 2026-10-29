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


def _profile(name, fouls, won, match="A vs B"):
    return {"source": "foul_profile", "player": name, "team": "A", "match": match, "league": "L", "kickoff": "k",
            "fouls": fouls, "fouls_won": won}


def test_ladder_two_players_both_stats_with_tiers():
    rows = [_profile("Caicedo", [3, 2, 4, 2, 3, 2, 5, 2, 3, 2], [2, 3, 2, 2, 4, 2, 3, 2, 2, 3]),
            _profile("McConnell", [2, 3, 2, 3, 2, 2, 4, 2, 3, 2], [3, 2, 2, 4, 2, 3, 2, 2, 3, 2]),
            _profile("Other", [0, 1, 0, 1, 0, 1, 0, 0, 1, 0], [1, 0, 1, 0, 1, 0, 0, 1, 0, 0])]
    lad = mb.build_ladders(rows, "d")
    assert len(lad) == 1 and lad[0]["size"] == 4
    names = {l["player"] for l in lad[0]["legs"]}
    assert names == {"Caicedo", "McConnell"}
    ts = [t for t, _ in lad[0]["tiers"]]
    assert ts[0] == 2 and all(lad[0]["tiers"][i][1] > lad[0]["tiers"][i + 1][1] for i in range(len(ts) - 1))
    m = mb.message(lad[0], "d")
    assert "Leiter" in m and "2+ bei allen Beinen" in m and "faire Quote" in m


def test_dedupe_overlap_prefers_ladder_over_subset_builders():
    rows = [leg(f"p{i}", 92 - i, match="A vs B") for i in range(6)]
    rows += [_profile(f"p{i}", [3, 2, 3, 2, 3, 2, 3, 2, 3, 2], [3, 2, 3, 2, 3, 2, 3, 2, 3, 2]) for i in range(2)]
    allp = mb.dedupe_overlap(mb.build_ladders(rows, "d") + mb.build_fouls(rows, "d") + mb.build(rows, "d"))
    a_vs_b = [p for p in allp if p["match"] == "A vs B"]
    assert a_vs_b[0]["style"] == "MODEL FOULS LADDER"


def _prof2(player, match, **series):
    d = {"source": "foul_profile", "player": player, "team": "T", "match": match, "league": "L", "kickoff": "k"}
    d.update(series)
    return d


def test_shot_ladder_and_cards_and_seven_legs():
    import netrattler_model_builders as mb
    rows = []
    for i, m in enumerate(("A vs B", "C vs D")):
        for j in range(4):
            rows.append(_prof2(f"P{i}{j}", m, fouls=[2, 3, 2, 2, 3, 2, 2, 3, 2, 2], fouls_won=[2, 2, 3, 2, 2, 3, 2, 2, 2, 3],
                               shots=[2, 3, 2, 4, 2, 3, 2, 2, 3, 2], sot=[1, 1, 2, 1, 1, 1, 2, 1, 1, 1],
                               yellow=[1, 1, 1, 0, 1, 1, 1, 0, 1, 1]))
    lad = mb.build_ladders(rows, "2026-10-28")
    assert lad and lad[0]["size"] == 4 and lad[0]["extra_lines"] and "7 Beine" in lad[0]["extra_lines"][0]
    sh = mb.build_shot_ladders(rows, "2026-10-28")
    assert any(p["style"] == "MODEL SHOT LADDER" for p in sh) and any(p["style"] == "MODEL SOT LADDER" for p in sh)
    cd = mb.build_cards(rows, "2026-10-28")
    assert cd and cd[0]["size"] == 2 and cd[0]["legs"][0]["odds"] == 0
    assert "7 Beine" in mb.message(lad[0], "2026-10-28")


def test_weak_leg_filter_and_leg_reuse():
    import netrattler_builder_engine as be
    from dataclasses import fields
    assert hasattr(be, "weak_leg") and hasattr(be, "leg_hit_rate")
    be.LEG_HISTORY[(be.norm("Test Spieler"), "shots")] = [0, 1, 0, 1, 2, 0, 1, 0, 1, 2]
    leg = type("L", (), {"player": "Test Spieler", "category": "shots", "line": 1.0})()
    assert be.leg_hit_rate(leg) == 0.6 and be.weak_leg(leg)
    be.LEG_HISTORY[(be.norm("Test Spieler"), "shots")] = [2, 3, 2, 4, 2, 3, 2, 3, 2, 2]
    assert not be.weak_leg(leg)
    be.LEG_HISTORY.clear()
