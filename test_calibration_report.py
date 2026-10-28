import netrattler_calibration_report as cr


def test_summarize_detects_overconfident_model():
    rows = [{"probability": 70, "odds": 2.0, "status": "win" if i < 5 else "loss"} for i in range(10)]
    s = cr.summarize(cr.points(rows))
    assert s["n"] == 10 and s["model"] == 70.0 and s["real"] == 50.0
    assert s["best_model_weight"] == 0.0 and s["brier_market"] < s["brier_model"]


def test_ignores_bad_rows():
    assert cr.points([{"probability": None, "odds": 2, "status": "win"}, {"probability": 60, "odds": 1.0, "status": "win"},
                      {"probability": 60, "odds": 2, "status": "pending"}]) == []
