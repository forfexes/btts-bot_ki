from datetime import datetime, timezone, timedelta
import netrattler_coverage_watchdog as w

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)

def iso(h):
    return (NOW - timedelta(hours=h)).isoformat()

def test_fresh_sources_ok():
    latest = {s: iso(1) for s in w.EXPECTED_SOURCES}
    assert w.stale_sources(latest, NOW) == []

def test_missing_and_stale_reported():
    latest = {s: iso(1) for s in w.EXPECTED_SOURCES}
    latest["bwin"] = iso(30)
    del latest["kambi"]
    bad = w.stale_sources(latest, NOW)
    assert any(b.startswith("bwin") for b in bad) and any(b.startswith("kambi") for b in bad)

def test_missing_markets():
    assert w.missing_markets({"1x2": 5, "btts": 0, "totals_2_5": 3}) == ["btts"]
