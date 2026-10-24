import netrattler_stats_match_cards as c


def _e(odds, extra=False):
    ent = [("combo", {"match": "Lazio vs Parma", "tip": "BTTS + Over 2.5", "odds": odds})]
    if extra:
        ent.append(("btts", {"match": "Lazio vs Parma", "tip": "YES", "odds": 1.8}))
    return ent


def test_price_move_does_not_change_signature():
    assert c._card_signature(_e(2.73)) == c._card_signature(_e(2.82))


def test_new_market_changes_signature():
    assert c._card_signature(_e(2.73)) != c._card_signature(_e(2.73, extra=True))
