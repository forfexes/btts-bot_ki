"""Tests for dynamic COMBO rows and no-placeholder crest policy."""
import io
import pytest
from PIL import Image
from netrattler_combo_dynamic_cards import render_combo
from netrattler_combo_owner_original import W, H, ROOT, _owner_canvas

def badge(_):
    b = io.BytesIO()
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(b, "PNG")
    return b.getvalue()

def legs(n):
    return [{"home":f"Home {i}", "away":f"Away {i}",
             "market":"Over 2.5", "odds":1.8} for i in range(n)]

def owner_ticket(n):
    return {"combined_odds_observed":True,
            "combined_quote_id":"SYNTHETIC_QA_TICKET",
            "bookmaker":"TEST_BOOK_ONLY"} if n in (7,9) else {}

@pytest.mark.parametrize("n", range(3, 13))
def test_exact_rows_and_height(n):
    raw = render_combo(legs(n), combined_odds=3.2, probability=40.0,
                       ev=28.0, confidence="HIGH", crest_provider=badge,
                       **owner_ticket(n))
    im = Image.open(io.BytesIO(raw))
    _, shift = _owner_canvas(n)
    assert im.size == (W, H + shift)

@pytest.mark.parametrize("n", [0, 2, 13])
def test_reject_invalid_counts(n):
    with pytest.raises(ValueError):
        render_combo(legs(n), combined_odds=3.2, probability=40,
                     ev=28, confidence="HIGH", crest_provider=badge)

def test_missing_crest_fails_closed():
    with pytest.raises(ValueError, match="Wappen"):
        render_combo(legs(7), combined_odds=3.2, probability=40,
                     ev=28, confidence="HIGH", crest_provider=lambda _: None,
                     **owner_ticket(7))

def test_missing_odds_fails_closed():
    rows=legs(9)
    rows[0]["odds"]=None
    with pytest.raises(ValueError, match="Einzelquote"):
        render_combo(rows, combined_odds=3.2, probability=40,
                     ev=28, confidence="HIGH", crest_provider=badge,
                     **owner_ticket(9))

@pytest.mark.parametrize("n",range(3,13))
def test_original_combo_can_render_with_calculated_leg_odds(n):
    image=render_combo(legs(n),combined_odds=None,probability=40,
                       ev=None,confidence="HIGH",crest_provider=badge)
    assert Image.open(io.BytesIO(image)).size == (W, H + _owner_canvas(n)[1])

@pytest.mark.parametrize("n",(3,4,5,6,8,10,11,12))
def test_original_only_mode_uses_real_combos_not_a_generic_fallback(n,monkeypatch):
    monkeypatch.setenv("NETRATTLER_ORIGINAL_ONLY","1")
    raw=render_combo(legs(n),combined_odds=None,probability=40,
                     ev=None,confidence="HIGH",crest_provider=badge)
    with Image.open(io.BytesIO(raw)) as result:
        source_n=7 if n<=7 else 9
        with Image.open(ROOT/f"NETRATTLER_COMBO_{source_n}_originalkarte.png") as original:
            original=original.convert("RGB").resize((W,H),Image.Resampling.LANCZOS)
            from PIL import ImageChops
            assert ImageChops.difference(
                result.crop((0,0,W,280)).convert("RGB"),
                original.crop((0,0,W,280))).getbbox() is None
