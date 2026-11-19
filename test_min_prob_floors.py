import os
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "x")

def test_floors_not_loosened():
    import btts_bot as b
    # calibration of the last 60 days: 65-69% over25/btts hit ~56%, corners >=71% ~75%
    # over25 60-65 ist nur mit Quoten-Band-Policy (Quote >=2.20) erlaubt, siehe test_odds_band_policy
    assert b.OVER25_MIN_PROB >= 60 and b.BTTS_MIN_PROB >= 63
    # Quoten-Band gelockert (Quote <1.90 ab 58%); Verlustzone 1.90-2.19 bleibt gesperrt.
    assert b.odds_band_policy_ok("over25", 61, 1.85) is True
    assert b.odds_band_policy_ok("over25", 61, 2.05) is False
    assert b.CORNER_MIN_PROB >= 70
    assert b.ONE_X_TWO_MIN_PROB >= 58 and b.ONE_X_TWO_MIN_EDGE >= 0.05
    assert b.OVER15_HT_MIN_PROB >= 70
