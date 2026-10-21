import os
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "x")

def test_floors_not_loosened():
    import btts_bot as b
    # calibration of the last 60 days: 65-69% over25/btts hit ~56%, corners >=71% ~75%
    assert b.OVER25_MIN_PROB >= 65 and b.BTTS_MIN_PROB >= 65
    assert b.CORNER_MIN_PROB >= 70
    assert b.ONE_X_TWO_MIN_PROB >= 65
    assert b.OVER15_HT_MIN_PROB >= 60
