import btts_bot as b

def test_over25_bands():
    f = b.odds_band_policy_ok
    assert f("over25", 66, 1.80) and f("over25", 66, 2.30) and f("over25", 61, 2.30)
    assert not f("over25", 66, 2.00)      # 1.9-2.2 Verlustzone
    assert not f("over25", 61, 1.85)      # 60-65 nur bei hoher Quote
    assert f("btts", 66, 2.00)            # andere Maerkte unberuehrt

def test_policy_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NETRATTLER_ODDS_BAND_POLICY", "false")
    assert b.odds_band_policy_ok("over25", 66, 2.0)
