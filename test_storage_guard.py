import netrattler_storage_guard as g

def test_decide():
    assert g.decide(327) == "ok"
    assert g.decide(425) == "warn"
    assert g.decide(470) == "trim"
