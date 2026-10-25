import netrattler_storage_guard as g

def test_decide():
    assert g.decide(327) == "ok"
    assert g.decide(425) == "warn"
    assert g.decide(470) == "trim"


def test_trim_keep_days_tiers():
    assert g.trim_keep_days(455) == g.TRIM_KEEP_DAYS
    assert g.trim_keep_days(480) == 2
    assert g.trim_keep_days(545) == 1
