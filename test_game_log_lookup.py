import btts_bot as b


def rows(team, dates):
    return [{"team": team, "match_date": d, "shots": 1} for d in dates]


def test_keys_accents_and_nicknames():
    assert b._game_log_key("Raúl Moro") == "raul moro"
    assert b._game_log_key_variants("Kike Barja") == ["kike barja", "enrique barja"]
    assert b._game_log_key_variants("Salas, Kike")[-1] == "enrique salas"


def test_transfer_merged():
    r = rows("Saint-Etienne", [f"2026-0{m}-10" for m in range(1, 6)]) + rows("Sevilla", ["2026-09-01", "2026-10-18"])
    got = b._merge_player_history(r, 20)
    assert len(got) == 7 and got[0]["team"] == "Sevilla"


def test_namesakes_overlapping_refused():
    r = rows("Atlas", ["2026-08-01", "2026-10-22"]) + rows("Sevilla", ["2026-09-15", "2026-10-18"])
    assert b._merge_player_history(r, 20) == []


def test_limit_newest_first():
    r = rows("A", [f"2026-01-{d:02d}" for d in range(1, 29)])
    got = b._merge_player_history(r, 20)
    assert len(got) == 20 and got[0]["match_date"] == "2026-01-28"
