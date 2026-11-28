import io
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import netrattler_master_cards as M


def _crest(color=(190, 30, 50, 255)):
    im = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((10, 10, 210, 210), fill=color)
    return im


def _photo():
    im = Image.new("RGB", (400, 400), (30, 60, 120))
    ImageDraw.Draw(im).ellipse((130, 70, 270, 210), fill=(225, 190, 160))
    return im


H, A, P = _crest(), _crest((30, 80, 190, 255)), _photo()
BASE = dict(title="BTTS", stats=[("A", "1"), ("B", "2"), ("C", "3")], tip="BTTS – JA", odds=1.85, prob=61)


def _size(png):
    return Image.open(io.BytesIO(png)).size


def test_master_exists_and_is_exact_size():
    assert Image.open(M.MASTER).size == (1122, 1402)


def test_every_family_renders_at_master_size():
    assert _size(M.render_match(BASE, "FC A", "FC B", H, A)) == (1122, 1402)
    spec = dict(title="GOAL HUNTER", stats=[("T", "1")], tip="X", odds=2.6, prob=44)
    assert _size(M.render_player(spec, "Spieler", H, P)) == (1122, 1402)
    live = dict(title="LMG", home_goals=1, away_goals=1, minute=78, live_stats=[("S", 1, 2)], tip="O", odds=2.2, prob=45)
    assert _size(M.render_live(live, "A", "B", H, A)) == (1122, 1402)
    legs = [dict(player=f"P{i}", market="Schüsse über 1.5", odds=1.5, photo=P, crest=H, hits=[("L5", 4, 5)]) for i in range(6)]
    for n in range(2, 7):
        assert _size(M.render_builder(legs[:n], "A", "B", H, A)) == (1122, 1402)
    tips = [dict(match=f"T{i}A vs T{i}B", market="Über 2.5", odds=1.4, home_img=H, away_img=A) for i in range(10)]
    for n in range(3, 11):
        assert _size(M.render_combo(tips[:n])) == (1122, 1402)
    for n in range(2, 7):
        assert _size(M.render_combo(tips[:n], "cross_mix")) == (1122, 1402)


@pytest.mark.parametrize("bad", [dict(odds=None), dict(odds=0.5), dict(prob=None), dict(prob=0), dict(tip="")])
def test_missing_or_invalid_values_fail_closed(bad):
    with pytest.raises(ValueError):
        M.render_match({**BASE, **bad}, "A", "B", H, A)


def test_no_crest_no_photo_no_placeholder():
    with pytest.raises(ValueError, match="crest"):
        M.render_match(BASE, "A", "B", None, A)
    with pytest.raises(ValueError, match="photo"):
        M.render_player(dict(title="G", stats=[("T", "1")], tip="X", odds=2, prob=40), "S", H, None)
    with pytest.raises(ValueError):
        M.render_match(BASE, "A", "B", Image.new("RGBA", (50, 50), (0, 0, 0, 0)), A)


def test_leg_limits():
    legs = [dict(player="P", market="M", odds=1.5, photo=P, crest=H)] * 7
    for n in (0, 1, 7):
        with pytest.raises(ValueError):
            M.render_builder(legs[:n], "A", "B", H, A)
    tips = [dict(match="a vs b", market="m", odds=1.4, home_img=H, away_img=A)] * 11
    for n in (2, 11):
        with pytest.raises(ValueError):
            M.render_combo(tips[:n])
    with pytest.raises(ValueError):
        M.render_combo(tips[:1], "cross_mix")
    with pytest.raises(ValueError):
        M.render_combo(tips[:7], "cross_mix")


def test_builder_requires_real_single_quotes():
    legs = [dict(player="P", market="M", odds=None, photo=P, crest=H)] * 2
    with pytest.raises(ValueError, match="quote"):
        M.render_builder(legs, "A", "B", H, A)


def test_handle_is_never_drawn_into_the_image():
    src = Path(M.__file__).read_text(encoding="utf-8")
    assert not re.search(r'_text\([^)]*prophunter', src, re.I)
    assert "NETRATTLER AI" in src


def test_text_overflow_raises_instead_of_shrinking_to_unreadable():
    with pytest.raises(ValueError, match="too long"):
        M.render_match({**BASE, "tip": "X" * 400}, "A", "B", H, A)


def test_lmg_master_card_without_quote_renders_and_needs_stats():
    import netrattler_lmg_free as L
    from PIL import Image as I
    import io as _io
    def crest(_):
        im = I.new("RGBA", (120, 120), (0, 0, 0, 0))
        from PIL import ImageDraw as D
        D.Draw(im).ellipse((6, 6, 114, 114), fill=(40, 100, 190, 255))
        b = _io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
    fx = {"home": "A", "away": "B", "hg": 1, "ag": 1, "minute": 78}
    png = L._master_live_png(fx, {"teams": {"home": {"shots": 10, "sot": 4}, "away": {"shots": 5, "sot": 2}}}, crest)
    assert I.open(_io.BytesIO(png)).size == (1122, 1402)
    with pytest.raises(ValueError):
        L._master_live_png(fx, {"teams": {}}, crest)


def _png_bytes(kind):
    from PIL import Image as I, ImageDraw as D
    import io as _io
    im = I.new("RGBA", (300, 300), (0, 0, 0, 0))
    D.Draw(im).ellipse((10, 10, 290, 290), fill=(40, 100, 190, 255) if kind == "c" else (200, 150, 120, 255))
    b = _io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def test_builder_pick_renders_on_master(monkeypatch):
    from types import SimpleNamespace as NS
    import netrattler_stats_match_cards as cards
    import netrattler_original_template_renderer as R
    monkeypatch.setattr(cards, "_player_photo", lambda p, t: _png_bytes("p"))
    monkeypatch.setattr(cards, "_badge_bytes", lambda t: _png_bytes("c"))
    legs = [NS(match="FC Alpha vs Beta United", player=f"Spieler {i}", team="FC Alpha", category="shots",
               line=1.5, odds=1.5 + i / 10, series=[2] * 15, league="Liga", kickoff="2026-11-29T18:00:00Z")
            for i in range(3)]
    pick = NS(legs=legs, match_date="2026-11-29", joint_probability=0.31, status=None)
    png = R.render_builder(pick)
    assert I_open(png).size == (1122, 1402)
    legs[1].series = [2] * 10
    with pytest.raises(ValueError):
        R.render_builder(pick)


def I_open(b):
    import io as _io
    from PIL import Image as I
    return I.open(_io.BytesIO(b))
