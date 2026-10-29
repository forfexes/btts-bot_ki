import netrattler_storage_guard as g

def test_decide():
    assert g.decide(327) == "ok"
    assert g.decide(425) == "warn"
    assert g.decide(470) == "trim"


def test_trim_keep_days_tiers():
    assert g.trim_keep_days(455) == g.TRIM_KEEP_DAYS == 2
    assert g.trim_keep_days(480) == 1
    assert g.trim_keep_days(495) == 1


def test_measurement_error_fails_closed(monkeypatch):
    import pytest
    from unittest.mock import Mock
    monkeypatch.setattr(g, "SB", "https://example.invalid")
    monkeypatch.setattr(g, "KEY", "fake")
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: Mock(ok=False, status_code=500))
    with pytest.raises(RuntimeError, match="measurement failed"):
        g.run()


def test_missing_size_is_not_zero(monkeypatch):
    import pytest
    from unittest.mock import Mock
    monkeypatch.setattr(g, "SB", "https://example.invalid")
    monkeypatch.setattr(g, "KEY", "fake")
    r = Mock(ok=True)
    r.json.return_value = {}
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: r)
    with pytest.raises(RuntimeError, match="missing mb"):
        g.run()
