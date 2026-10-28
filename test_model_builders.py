import netrattler_model_builders as mb


def leg(player, p=80, line=2, match="A vs B"):
    return {"player": player, "match": match, "market": f"{player} {line}+ Fouls", "category": "fouls",
            "line": float(line), "probability": p, "source": "model_line_fouls", "series": [3, 2, 2, 3, 2, 1, 2, 3, 2, 2]}


def test_builds_three_leg_when_joint_high_enough():
    picks = mb.build([leg("X", 90), leg("Y", 88), leg("Z", 86)], "2026-10-28")
    assert any(p["size"] == 3 for p in picks) and all(p["fair"] > 1 for p in picks)


def test_rejects_low_joint_and_non_model_rows():
    assert mb.build([leg("X", 60), leg("Y", 60)], "d") == []
    r = leg("X", 95); r["source"] = "kambi"
    assert mb.build([r, leg("Y", 95)], "d") == []


def test_message_flags_no_bookmaker_quote():
    p = mb.build([leg("X", 90), leg("Y", 90)], "d")[0]
    m = mb.message(p, "d")
    assert "keine Buchmacherquote" in m and "L10:" in m and "faire Quote" in m
