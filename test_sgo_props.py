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


def test_sgo_observed_bookmaker_price_survives_real_odds_builder_guard():
    import netrattler_builder_engine as engine
    assert engine.is_bookmaker_source("sgo_fanduel")
    assert engine.is_bookmaker_source("sgo_draftkings")
    assert not engine.is_bookmaker_source("sgo_")
    assert not engine.is_bookmaker_source("model_line_fouls")
    row = {
        "player": "Alexis Sanchez", "team": "CF Montréal",
        "match": "Charlotte FC vs CF Montréal", "league": "MLS",
        "category": "sot", "line": 2.0, "odds": 2.7,
        "source": "sgo_fanduel", "market": "shots_onGoal Over 1.5",
        "model_prob": 0.45,
    }
    leg = engine.normalize_prop(row)
    assert leg is not None and leg.odds == 2.7 and leg.source == "sgo_fanduel"
    assert engine.normalize_prop(dict(row, odds=0)) is None
    assert engine.normalize_prop(dict(row, estimated_odds=True)) is None
    assert engine.normalize_prop(dict(row, source="model_line_fouls")) is None
