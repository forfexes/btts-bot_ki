import netrattler_apifootball_results as a
import netrattler_pending_result_backfill as b

R = [{"fixture": {"id": 7, "status": {"short": "FT"}}, "goals": {"home": 3, "away": 1},
      "teams": {"home": {"name": "MAFCO"}, "away": {"name": "Big Bullets"}},
      "score": {"halftime": {"home": 1, "away": 0}}, "league": {"name": "Super League", "country": "Malawi"}},
     {"fixture": {"id": 8, "status": {"short": "NS"}}, "goals": {"home": None, "away": None},
      "teams": {"home": {"name": "X"}, "away": {"name": "Y"}}, "score": {}, "league": {}}]


def test_parse_only_finished():
    rows = a.parse_fixtures(R, "2026-10-18")
    assert len(rows) == 1 and rows[0]["home_score"] == 3 and rows[0]["ht_home"] == 1 and rows[0]["source"] == "apifootball"


def test_unmatched_and_select():
    rows = a.parse_fixtures(R, "2026-10-18")
    wanted = [("MAFCO", "Big Bullets", False), ("Foo Town", "Bar City", False)]
    assert b.unmatched(rows, wanted) == [("Foo Town", "Bar City", False)]
    assert len(b.select_rows(rows, wanted)) == 1
