import pytest
import netrattler_player_club as pc
from netrattler_visual_gate import club_same


@pytest.mark.parametrize("player,squad,ok", [
    ("Luis Eduardo Soares 'Cuiabano' da Silva", "Cuiabano", True),
    ("Pedro Henrique Cardoso de Lima", "Pedro Lima", True),
    ("Agustin Sant'Anna", "A. Sant'Anna", True),
    ("Agustín Sant'Anna", "Agustin Santanna", True),  # accents/apostrophes ignored
    ("Gustavo Marques", "Gustavo Marques Silva", True),
    ("Pedro Henrique Cardoso de Lima", "Pedro", False),
    ("Pedro Henrique Cardoso de Lima", "Pedro Costa", False),
    ("Joao Silva", "Pedro Silva", False),
    ("Hassani Dotson", "Hassani Dotson", True),
])
def test_names_match(player, squad, ok):
    assert pc.names_match(player, squad) is ok


FX = [{"teams": {"home": {"id": 1, "name": "Vasco DA Gama"}, "away": {"id": 2, "name": "Internacional"}}}]


def _squads(monkeypatch, data):
    monkeypatch.setattr(pc, "squad_names", lambda tid: tuple(data[int(tid)]))


def test_nickname_resolves_to_exactly_one_side(monkeypatch):
    _squads(monkeypatch, {1: ["Cuiabano", "Rayan"], 2: ["Alan Patrick"]})
    assert pc.club_from_squads("Luis Eduardo Soares 'Cuiabano' da Silva", "Vasco DA Gama", "Internacional", FX, club_same) == "Vasco DA Gama"


def test_club_change_found_via_current_squad(monkeypatch):
    _squads(monkeypatch, {1: ["Rayan"], 2: ["Alan Patrick", "Gustavo Prado"]})
    assert pc.club_from_squads("Gustavo Prado", "Vasco DA Gama", "Internacional", FX, club_same) == "Internacional"


def test_ambiguous_or_unknown_stays_blocked(monkeypatch):
    _squads(monkeypatch, {1: ["Pedro Lima"], 2: ["Pedro Lima"]})
    assert pc.club_from_squads("Pedro Henrique Cardoso de Lima", "Vasco DA Gama", "Internacional", FX, club_same) == ""
    _squads(monkeypatch, {1: ["Rayan"], 2: ["Alan Patrick"]})
    assert pc.club_from_squads("Somebody Else", "Vasco DA Gama", "Internacional", FX, club_same) == ""
    assert pc.club_from_squads("Cuiabano", "Vasco DA Gama", "Internacional", [], club_same) == ""


def test_gate_falls_back_to_squads_when_log_empty(monkeypatch):
    import netrattler_visual_gate as g
    g.club_for_player.cache_clear()
    monkeypatch.setattr(g, "_club_from_log", lambda *a: "")
    monkeypatch.setattr(g, "_day_fixtures", lambda d: tuple(FX) if d == "2026-11-28" else ())
    _squads(monkeypatch, {1: ["Cuiabano"], 2: []})
    assert g.club_for_player("Luis Eduardo Soares 'Cuiabano' da Silva", "Vasco DA Gama vs Internacional", "2026-11-27") == "Vasco DA Gama"
