import btts_bot as b
def main():
    f = b._ntr_is_anytime_scorer_special
    assert f({"market": "Goalscorer", "category": "goals", "player": "A B"}) in (True, False)
    assert not f({"market": "First Goalscorer", "player": "A B"})
    assert not f({"market": "To Score or Assist", "player": "A B"})
    assert not f({"market": "Last Goalscorer", "player": "A B"})
    print("OK: scorer helper regression")
import netrattler_prop_sources as ps
def kambi():
    rows = [
        {"player": "A Striker", "category": "score", "market": "Anytime Goalscorer", "odds": 2.5, "source": "kambi_ub"},
        {"player": "B Striker", "category": "score", "market": "First Goalscorer", "odds": 7.0},
        {"player": "C Striker", "category": "score", "market": "To score 2 or more goals", "odds": 9.0},
        {"player": "D Striker", "category": "shots", "market": "Shots", "odds": 1.9},
    ]
    old = ps.fetch_kambi_player_props
    ps.fetch_kambi_player_props = lambda h, a, brand="ub": rows
    try:
        st = {}
        out = b._ntr_kambi_scorer_props([{"home": "X", "away": "Y"}], st, 5)
    finally:
        ps.fetch_kambi_player_props = old
    assert [o["player"] for o in out] == ["A Striker"], out
    assert out[0]["_source"] == "kambi_ub" and out[0]["odds"] == 2.5
main()
kambi()
