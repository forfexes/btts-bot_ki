from datetime import date
import netrattler_settlement_v16_final as s


def test_stale_no_result_voids():
    assert s.stale_no_result("pending", {}, "2026-10-17", date(2026, 10, 24))
    assert s.stale_no_result("pending", None, "2026-10-20", date(2026, 10, 24))


def test_recent_or_with_result_untouched():
    assert not s.stale_no_result("pending", {}, "2026-10-23", date(2026, 10, 24))
    assert not s.stale_no_result("pending", {"home_score": 1}, "2026-10-10", date(2026, 10, 24))
    assert not s.stale_no_result("win", {}, "2026-10-10", date(2026, 10, 24))


def test_reason_counts_as_genuine_void():
    assert s._genuine_void_reason("void: kein Ergebnis nach 3 Tagen verfuegbar (Liga ohne Datenquelle)")
