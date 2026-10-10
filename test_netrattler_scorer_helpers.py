import btts_bot as b
def main():
    f = b._ntr_is_anytime_scorer_special
    assert f({"market": "Goalscorer", "category": "goals", "player": "A B"}) in (True, False)
    assert not f({"market": "First Goalscorer", "player": "A B"})
    assert not f({"market": "To Score or Assist", "player": "A B"})
    assert not f({"market": "Last Goalscorer", "player": "A B"})
    print("OK: scorer helper regression")
main()
