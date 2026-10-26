import netrattler_settlement_v16_final as s


def test_roi_text_needs_priced_base():
    st = {"bets": 30, "priced": 3, "profit": 5.0, "roi": 40.0, "wins": 10, "losses": 20}
    assert "n/a" in s.roi_text(st)
    st["priced"] = 30
    assert "+40.0%" in s.roi_text(st)
