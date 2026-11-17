import netrattler_espn_photo as e

def test_unique_id_and_placeholder_ids():
    assert e.unique_id([{"player_id": "324164"}, {"player_id": "324164"}]) == "324164"
    assert e.unique_id([{"player_id": "324164"}, {"player_id": "580"}]) == "324164"
    assert e.unique_id([{"player_id": "111111"}, {"player_id": "222222"}]) == ""
    assert e.unique_id([]) == ""

def test_single_word_name_skipped():
    assert e.espn_photo("Neymar") == ""
