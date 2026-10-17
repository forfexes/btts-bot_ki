"""Regression: accent/abbreviation-tolerant player_game_log lookup never mixes two players."""
import btts_bot as b


class _R:
    ok = True
    def __init__(self, rows): self._r = rows
    def json(self): return self._r


def _rows(name, key, n=5):
    return [{"player_key": key, "player_name": name, "match_date": f"2026-10-{i+1:02d}", "shots": 2, "sot": 1} for i in range(n)]


def _with(rows, fn):
    old = b.requests.get
    b.requests.get = lambda *a, **k: _R(rows)
    try:
        return fn()
    finally:
        b.requests.get = old


def test_fold():
    assert b._fold_player_name("Lasse Günther") == "lasse gunther"
    assert b._fold_player_name("Andreas Hanche-Olsen") == "andreas hanche olsen"
    assert b._fold_player_name("Łukasz Fabiański") == "lukasz fabianski"


def test_accent_variant_matches():
    rows = _rows("Lasse Günther", "lasse günther|elversberg")
    got = _with(rows, lambda: b._fuzzy_game_log_rows("Lasse Gunther"))
    assert len(got) == 5


def test_initial_matches_single_player():
    rows = _rows("Lasse Günther", "lasse günther|elversberg")
    assert len(_with(rows, lambda: b._fuzzy_game_log_rows("L. Gunther"))) == 5


def test_ambiguous_players_refused():
    rows = _rows("Lasse Günther", "k1") + _rows("Lars Günther", "k2")
    assert _with(rows, lambda: b._fuzzy_game_log_rows("L. Gunther")) == []


def test_different_first_name_not_matched():
    rows = _rows("Marius Wolf", "marius wolf|augsburg")
    assert _with(rows, lambda: b._fuzzy_game_log_rows("Hans Wolf")) == []


def test_flip_comma_name():
    import netrattler_prop_sources as m
    assert m.flip_comma_name("Gregoritsch, Michael") == "Michael Gregoritsch"
    assert m.flip_comma_name("Michael Gregoritsch") == "Michael Gregoritsch"
    assert m.flip_comma_name("") == ""
    assert m.flip_comma_name("Tim Skarke Player's") == "Tim Skarke"
    assert m.flip_comma_name("Skarke, Tim Player's") == "Tim Skarke"


def test_comma_name_fuzzy():
    rows = _rows("Lasse Günther", "lasse günther|elversberg")
    assert len(_with(rows, lambda: b._fuzzy_game_log_rows("Gunther, Lasse"))) == 5


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("OK player name fuzzy tests")
