import netrattler_clv as c

TIP = {"tip_id": "over25_2026-10-20_1", "market": "over25", "tip": "YES", "odds": "1.88", "date": "2026-10-20",
       "message_text": "💎 <b>Wolverhampton vs Portsmouth</b>\n..."}

def h(src, o, home="Wolverhampton Wanderers", away="Portsmouth", sel="over_2_5", mk="totals_2_5", d="2026-10-20"):
    return {"source": src, "market": mk, "selection": sel, "odds": o, "home_team": home, "away_team": away, "match_date": d}

def test_median_close_and_clv():
    hist = [h("bwin", 1.80), h("altenar_platform", 1.70), h("1xbet_platform", 1.90), h("bwin", 3.0, sel="under_2_5")]
    cl = c.closing_odds(TIP, hist)
    assert cl == 1.8
    assert c.clv_value("1.88", cl) == round(1.88 / 1.8 - 1, 4)

def test_wrong_match_day_market_ignored():
    assert c.closing_odds(TIP, [h("bwin", 1.8, home="Arsenal", away="Chelsea")]) is None
    assert c.closing_odds(TIP, [h("bwin", 1.8, d="2026-10-21")]) is None
    assert c.closing_odds(TIP, [h("football_data", 1.8)]) is None   # not an independent live source
    assert c.closing_odds(TIP, [h("bwin", 1.8, mk="btts", sel="yes")]) is None

def test_selection_map():
    assert c.tip_selection({"market": "1x2", "tip": "X"}) == ("1x2", "draw")
    assert c.tip_selection({"market": "btts", "tip": "YES"}) == ("btts", "yes")
    assert c.tip_selection({"market": "corners", "tip": "Over 7.5 Ecken"}) is None
    assert c.clv_value("abc", 1.8) is None and c.clv_value(2.0, None) is None

def test_implausible_gap_not_written():
    assert c.clv_value(3.0, 1.556) is None
    assert c.clv_value(2.0, 1.9) is not None
