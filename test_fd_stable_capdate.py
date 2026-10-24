import import_football_data_sources_v14 as m
def test_cap_date_is_match_date():
    rows = m.odds_rows_from_match({"match_id": "x", "match_date": "2025-03-02", "odd_home": 2.0, "odd_draw": 3.0, "odd_away": 3.5})
    assert rows and all(r["captured_date"] == "2025-03-02" for r in rows)
