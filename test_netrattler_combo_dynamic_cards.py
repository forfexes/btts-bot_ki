"""Tests for dynamic COMBO rows and no-placeholder crest policy."""
import io
import pytest
from PIL import Image
from netrattler_combo_dynamic_cards import render_combo

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

@pytest.mark.parametrize("n", range(3, 11))
def test_exact_rows_and_height(n):
    raw = render_combo(legs(n), combined_odds=3.2, probability=40.0,
                       ev=28.0, confidence="HIGH", crest_provider=badge,
                       **owner_ticket(n))
    im = Image.open(io.BytesIO(raw))
    assert im.size == ((1122,1402) if n in (7,9)
                       else (1100,290 + 114*n + 315))

@pytest.mark.parametrize("n", [0, 2, 11])
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

@pytest.mark.parametrize("n",(7,9))
def test_original_combo_can_render_with_calculated_leg_odds(n):
    image=render_combo(legs(n),combined_odds=None,probability=40,
                       ev=28,confidence="HIGH",crest_provider=badge)
    assert Image.open(io.BytesIO(image)).size == (1122,1402)

@pytest.mark.parametrize("n",(3,4,5,6,8,10))
def test_generic_combo_never_replaces_owner_artwork_in_production(n,monkeypatch):
    monkeypatch.setenv("NETRATTLER_ORIGINAL_ONLY","1")
    with pytest.raises(ValueError,match="Original-COMBO"):
        render_combo(legs(n),combined_odds=3.2,probability=40,
                     ev=28,confidence="HIGH",crest_provider=badge)
