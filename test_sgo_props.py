import netrattler_sgo_props as sgo


def test_american_to_decimal():
    assert sgo.american_to_decimal("+1150") == 12.5
    assert sgo.american_to_decimal("-145") == 1.69
    assert sgo.american_to_decimal("x") is None and sgo.american_to_decimal("0") is None


def test_parse_event_best_book_and_line():
    ev = {"teams": {"home": {"teamID": "H", "names": {"long": "Charlotte FC"}}, "away": {"teamID": "A", "names": {"long": "CF Montréal"}}},
          "status": {"startsAt": "2026-10-28T23:30:00.000Z"},
          "players": {"ALEXIS_SANCHEZ_1_MLS": {"name": "Alexis Sanchez", "teamID": "A"}},
          "odds": {
              "shots_onGoal-ALEXIS_SANCHEZ_1_MLS-game-ou-over": {
                  "statID": "shots_onGoal", "playerID": "ALEXIS_SANCHEZ_1_MLS", "periodID": "game", "betTypeID": "ou", "sideID": "over",
                  "byBookmaker": {"betmgm": {"odds": "+150", "overUnder": "1.5", "available": True},
                                  "fanduel": {"odds": "+170", "overUnder": "1.5", "available": True}}},
              "tackles-ALEXIS_SANCHEZ_1_MLS-game-ou-under": {
                  "statID": "tackles", "playerID": "ALEXIS_SANCHEZ_1_MLS", "periodID": "game", "betTypeID": "ou", "sideID": "under",
                  "byBookmaker": {"betmgm": {"odds": "+150", "overUnder": "1.5"}}}}}
    rows = sgo.parse_event(ev, "MLS")
    assert len(rows) == 1
    r = rows[0]
    assert r["category"] == "sot" and r["line"] == 2.0 and r["odds"] == 2.7 and r["source"] == "sgo_fanduel"
    assert r["match"] == "Charlotte FC vs CF Montréal" and r["team"] == "CF Montréal"
