from datetime import date
import netrattler_settlement_v16_final as s


def test_month_is_rolling_30_days_never_shorter_than_week(monkeypatch):
    monkeypatch.setattr(s, "TODAY", date(2026, 11, 1))
    assert s.period_start("month") == "2026-10-03"
    assert s.period_start("month") <= s.period_start("week")
