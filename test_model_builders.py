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
