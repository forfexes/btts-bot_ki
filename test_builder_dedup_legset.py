import netrattler_settlement_v16_final as s


def _row(tid, status, legs, date="2026-10-24"):
    return {"tip_id": tid, "market_group": "builder", "source_table": "netrattler_builder_picks",
            "tip_date": date, "status": status, "tip_payload": {"legs": legs}}


LEGS = [{"player": "Edan Diop", "market": "shots", "line": 1.5, "match": "Monaco vs Freiburg"}]


def test_same_legset_counts_once():
    rows = [_row("a", "loss", LEGS), _row("b", "loss", list(LEGS))]
    assert len(s.dedup_history(rows)) == 1


def test_different_day_or_legs_kept():
    other = [dict(LEGS[0], line=2.5)]
    rows = [_row("a", "loss", LEGS), _row("b", "loss", other), _row("c", "loss", LEGS, date="2026-10-25")]
    assert len(s.dedup_history(rows)) == 3


def test_closed_replaces_open():
    out = s.dedup_history([_row("a", "pending", LEGS), _row("b", "win", LEGS)])
    assert len(out) == 1 and out[0]["status"] == "win"
