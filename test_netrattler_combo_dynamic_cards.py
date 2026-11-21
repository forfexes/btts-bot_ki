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

@pytest.mark.parametrize("n", [3, 7, 9, 12])
def test_actual_telegram_card_route_uses_full_verified_owner_combo(n, monkeypatch):
    import netrattler_stats_match_cards as cards
    monkeypatch.setattr(cards, "_badge_bytes", badge)
    entry = {
        "match": "Home 0 vs Away 0", "market": "combo", "probability": 40,
        "bookmaker": "TEST_QA_ONLY", "combined_odds_observed": True,
        "combined_quote_id": "SYNTHETIC_QA_ONLY",
        "combined_odds": 12.5, "stake": 0.5, "confidence": "HIGH",
        "legs": [
            {"match": f"Home {i} vs Away {i}", "market": "Over 2.5",
             "odds": 1.8}
            for i in range(n)
        ],
    }
    output = cards.render_card([("combo", entry)], "2026-11-21")
    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (W, H + _owner_canvas(n)[1])
        source_n = 7 if n <= 7 else 9
        with Image.open(ROOT / f"NETRATTLER_COMBO_{source_n}_originalkarte.png") as source:
            from PIL import ImageChops
            source = source.convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
            # Owner's crown/header remain unchanged; only the baked
            # 7/9 TIPPS ribbon changes when the real leg count differs.
            upper = 280 if n == source_n else 190
            assert ImageChops.difference(
                image.convert("RGB").crop((0, 0, W, upper)),
                source.crop((0, 0, W, upper))
            ).getbbox() is None
            if n != source_n:
                assert ImageChops.difference(
                    image.convert("RGB").crop((360,208,768,268)),
                    source.crop((360,208,768,268))
                ).getbbox() is not None


def test_actual_telegram_combo_route_rejects_unconfirmed_ticket(monkeypatch):
    import netrattler_stats_match_cards as cards
    monkeypatch.setattr(cards, "_badge_bytes", badge)
    item = {
        "match": "Home 0 vs Away 0", "market": "combo",
        "probability": 40, "bookmaker": "TEST_QA_ONLY",
        "combined_odds": 12.5, "stake": 0.5, "confidence": "HIGH",
        "legs": legs(3),
    }
    with pytest.raises(ValueError, match="verified bookmaker ticket"):
        cards.render_card([("combo", item)], "2026-11-21")


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
                result.crop((0,0,W,190)).convert("RGB"),
                original.crop((0,0,W,190))).getbbox() is None
            assert ImageChops.difference(
                result.crop((360,208,768,268)).convert("RGB"),
                original.crop((360,208,768,268))).getbbox() is not None

def test_owner_combo_infers_multigame_model_probability_from_leg_formulas(monkeypatch):
    import netrattler_combo_owner_original as owner
    data = legs(3)
    for row, p in zip(data, [0.8, 0.6, 0.5]):
        row["model_probability"] = p
    drawn = []
    real_label = owner._label
    def inspect(draw, value, *args, **kwargs):
        drawn.append(str(value))
        return real_label(draw, value, *args, **kwargs)
    monkeypatch.setattr(owner, "_label", inspect)
    output = render_combo(data, combined_odds=None, probability=None,
                          ev=None, confidence="HIGH", crest_provider=badge)
    assert output.startswith(bytes((137,80,78,71,13,10,26,10)))
    assert "24.0%" in drawn
    assert "BERECHNET" in drawn
    assert "QUOTE UNBESTÄTIGT" in drawn


def test_same_game_builder_needs_joint_or_conditional_evidence(monkeypatch):
    import netrattler_combo_owner_original as owner
    rows=legs(3)
    for row, p in zip(rows,[0.8,0.6,0.5]):
        row.update(home="Same Home",away="Same Away",model_probability=p)
    with pytest.raises(ValueError,match="joint or independent formula"):
        render_combo(rows,combined_odds=None,probability=None,
                     ev=None,confidence="HIGH",crest_provider=badge)
    rows[0]["conditional_probabilities"]=[0.7,0.6]
    observed=[]
    real_label=owner._label
    def inspect(draw,value,*args,**kwargs):
        observed.append(str(value))
        return real_label(draw,value,*args,**kwargs)
    monkeypatch.setattr(owner,"_label",inspect)
    output=render_combo(rows,combined_odds=None,probability=None,
                        ev=None,confidence="HIGH",crest_provider=badge)
    assert output.startswith(bytes((137,80,78,71,13,10,26,10)))
    assert "33.6%" in observed

