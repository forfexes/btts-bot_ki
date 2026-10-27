import netrattler_odds_api_budget as b


def _reset(used=0, rem=None):
    b._STATE.update({"used": used, "remaining": rem, "loaded": True, "dirty": False, "date": "2026-10-27"})


def test_is_paid():
    assert b.is_paid("https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?x=1")
    assert b.is_paid("https://api.the-odds-api.com/v4/sports/x/events/1/odds")
    assert not b.is_paid("https://api.the-odds-api.com/v4/sports")
    assert not b.is_paid("https://api.the-odds-api.com/v4/sports/x/events")
    assert not b.is_paid("https://example.com/odds")


def test_cap_and_reserve(monkeypatch=None):
    _reset(used=14); assert b.blocked() == ""
    _reset(used=15); assert "Tageslimit" in b.blocked()
    _reset(used=0, rem=25); assert "Restkontingent" in b.blocked()
    _reset(used=0, rem=26); assert b.blocked() == ""


def test_record_reads_headers():
    _reset()
    b.record({"x-requests-last": "3", "x-requests-remaining": "400"})
    assert b._STATE["used"] == 3 and b._STATE["remaining"] == 400 and b._STATE["dirty"]
