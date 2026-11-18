"""Visual regression for the ordinary NETRATTLER AI Telegram match-card group.

This is separate from PROP BUILDER, GOAL HUNTER, COMBO and CORNER SNIPER.
Synthetic local data; this test never sends a Telegram message.
"""
import io
from unittest.mock import patch

from PIL import Image

import netrattler_stats_match_cards as cards


def _entries():
    # Values are test-only, not betting recommendations.
    return [("btts", {
        "match": "Test United vs Example City",
        "league": "Example League",
        "time_local": "19:00",
        "odds": 2.37,
        "fairOdds": 2.19,
        "probability": 46,
        "p_home": 37,
        "p_draw": 26,
        "p_away": 37,
        "exp_goals_home": 1.3,
        "exp_goals_away": 1.3,
        "homeForm": "WDLWD",
        "awayForm": "LWDWL",
        "h2h_matches": 10,
        "h2h_btts": "7/10",
        "h2h_avg_goals": 2.5,
        "avg_goals_home": 1.2,
        "avg_goals_away": 0.9,
    })]


def _render(result=None):
    # Keep network and crest provenance out of offline visual regression.
    with patch.object(cards, "_paste_badge", return_value=None):
        return cards.render_bis_card(_entries(), "2026-11-21", result)


def test_ai_match_card_is_own_blue_gold_dashboard_with_original_stats():
    raw = _render()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        assert im.format == "PNG"
        assert im.size == (1200, 1120)
        rgb = im.convert("RGB")
        # Distinctively golden 'AI' masthead at the right end of silver logo.
        logo = rgb.crop((600, 13, 1050, 100))
        gold_pixels = sum(1 for r, g, b in logo.getdata()
                          if r > 170 and g > 120 and r > b * 1.5)
        assert gold_pixels > 100
        # Four complete, bright cyan-framed statistical panels at the bottom.
        for x in (24, 318, 612, 906):
            patch = rgb.crop((x, 605, min(x + 70, 1170), 665))
            cyan = sum(1 for r, g, b in patch.getdata()
                       if b > 120 and g > 110 and b > r * 1.3)
            assert cyan > 12


def test_ai_card_settlement_remains_inside_original_image():
    raw = _render({"marks":{"0":"win"}, "ft":"2-1"})
    assert raw != _render()
    with Image.open(io.BytesIO(raw)) as im:
        assert im.size == (1200, 1120)


def test_ai_match_card_dispatch_remains_separate_from_specialist_templates(monkeypatch):
    monkeypatch.setenv("NETRATTLER_CARD_LAYOUT", "bis")
    marker = b"ai_match_card"
    monkeypatch.setattr(cards, "render_bis_card", lambda entries, day, result=None: marker)
    assert cards.render_card(_entries(), "2026-11-21") == marker
    with patch.object(cards,"render_corner_card",create=True):
        # A dedicated corner template is dispatched before the general layout.
        from netrattler_corner_cards import render_corner_card
        monkeypatch.setattr("netrattler_corner_cards.render_corner_card",
                            lambda *args: b"corner_card")
        assert cards.render_card([("corners",{"match":"A vs B"})],"2026-11-21")==b"corner_card"


def test_ai_group_accepts_qualified_real_odds_without_optional_xg(monkeypatch):
    tip={"match":"Real FC vs Test United","league":"Example",
         "oddsYes":2.45,"probability":54,"_source":"observed_bookmaker",
         "_no_real_odds":False}
    assert len(cards.select_cards({"over25":[tip]}))==1
    # No imaginary xG/Poisson, and missing statistics remain a dash.
    with patch.object(cards, "_paste_badge", return_value=None):
        image=cards.render_bis_card([("over25",tip)], "2026-11-18")
    with Image.open(io.BytesIO(image)) as img:
        assert img.size == (1200, 1120)
    assert "exp_goals_home" not in tip
    assert "exp_goals_away" not in tip


def test_ai_group_retains_exact_odds_and_rejects_fake_sources():
    ok={"match":"Real FC vs Test United","oddsYes":2.45,
        "probability":54,"_source":"observed_bookmaker"}
    assert len(cards.select_cards({"over25":[ok]}))==1
    for field,value in (("_no_real_odds",True),("synthetic",True),
                        ("estimated_odds",True)):
        row=dict(ok,**{field:value})
        assert cards.select_cards({"over25":[row]})==[]
    assert cards.select_cards({"over25":[{**ok,"_source":""}]})==[]
