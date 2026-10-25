import btts_bot as b

def test_live_status_marks():
    assert b._live_status(0, lambda i: (True, "")).startswith("❌")
    assert b._live_status(2, lambda i: (i == 0, "Rest 400")).startswith("✅ 1/2")
    assert b._live_status(1, lambda i: (False, "")).startswith("❌ 0/1")

def test_live_status_exception_is_bad():
    def boom(i): raise RuntimeError("x")
    assert b._live_status(1, boom).startswith("❌")

def test_empty_quota_is_warning():
    t = b._live_status(1, lambda i: (True, "Rest 0"))
    assert t.startswith("⚠️") and "leer" in t
    assert "1/1 geprueft" in b._live_status(1, lambda i: (True, ""))
