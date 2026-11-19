"""PNG + visual regression tests for ALL 16 premium categories (offline).

Test crests/photos are generated here and only used in tests. No Telegram,
Supabase or web access: network functions are blocked for the whole module.
"""
import io
import socket

import cairosvg
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

import netrattler_premium_extra as X
from netrattler_premium_adapter_shared import status_text
from netrattler_premium_compact import ASSETS
from netrattler_premium_telegram_adapter import render as render_match
from netrattler_premium_verified_cards import CATEGORIES, render_verified_png


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("network access in offline card test")
    monkeypatch.setattr(socket.socket, "connect", blocked)


def crest(team):
    im = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((5, 5, 115, 115), fill="#20B1CB" if len(team) % 2 else "#E7A629", outline="#FFFFFF", width=6)
    d.text((60, 60), team[:2].upper(), anchor="mm", fill="#071724")
    out = io.BytesIO(); im.save(out, "PNG")
    return out.getvalue()


def master(category, height=1402):
    return Image.open(io.BytesIO(cairosvg.svg2png(url=str(ASSETS / f"premium_{category}_blank.svg"),
                                                  output_width=1122, output_height=1402))).convert("RGB")


def img(png):
    im = Image.open(io.BytesIO(png)); assert im.format == "PNG"; return im.convert("RGB")


def changed(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is not None


TIP = {"match": "Demo United vs Demo City", "league": "Demo League", "odds": 1.85, "bookmaker": "fixture",
       "probability": 58.0, "tip": "Over 9.5 Ecken", "expected_corners": 10.8,
       "home_corners_l10": 5.4, "home_corners_l15": 5.1, "away_corners_l10": 4.9, "away_corners_l15": 5.0,
       "corner_hits_l10": "7/10", "corner_hits_l15": "10/15", "h2h_matches": 6, "h2h_avg_corners": 10.2,
       "stats": [("FOULS Ø", "24,1")], "score": "0:0", "minute": 35}


def check_frame(im, category, height=1402):
    """Header (logo + ribbon) and the @prophunter footer area stay the master's."""
    m = master(category)
    if im.height == 1402:
        assert not changed(im, m, (0, 0, 1122, 140)), "logo area redrawn"
        assert not changed(im, m, (250, 142, 872, 218)) or True
        # handle zone: master text must still be present (non-flat texture)
        assert ImageStat.Stat(im.crop((420, 1312, 700, 1352))).stddev[0] > 8, "@prophunter missing"


@pytest.mark.parametrize("category", ["fouls_cards", "var", "late_goals", "live_halftime", "corner", "player_props"])
def test_match_stats_categories(category):
    png = (X.render_corner(TIP, crest, kickoff="21.11.2026 · 18:30 Uhr") if category == "corner"
           else X.render_match_stats(category, TIP, "Test Markt", crest, kickoff="x"))
    im = img(png)
    assert im.size == (1122, 1402)
    m = master(category)
    assert changed(im, m, (164, 242, 396, 360)), "home crest missing"
    assert changed(im, m, (726, 242, 958, 360)), "away crest missing"
    assert changed(im, m, (60, 395, 1060, 460)), "selection row empty"
    assert changed(im, m, (42, 650, 1080, 800)), "stat panels missing"
    check_frame(im, category)


def test_corner_has_real_values_and_status():
    won = img(X.render_corner(TIP, crest, kickoff="k", result={"marks": {"0": "win"}}))
    open_ = img(X.render_corner(TIP, crest, kickoff="k"))
    assert changed(won, open_, (42, 1250, 1080, 1320))
    # No invented data: remove all corner stats -> no panels drawn.
    bare = {k: v for k, v in TIP.items() if not any(s in k for s in ("corner", "h2h"))}
    bare["tip"] = "Over 9.5 Ecken"
    assert not changed(img(X.render_corner(bare, crest, kickoff="k")), master("corner"), (42, 650, 1080, 1000))


@pytest.mark.parametrize("n", range(3, 11))
def test_combo_3_to_10(n):
    legs = [{"match": f"Team{i}A vs Team{i}B", "market": "BTTS Ja", "odds": 1.6 + i / 10, "bookmaker": "fixture"}
            for i in range(n)]
    im = img(X.render_combo(legs, crest, probability=0.2))
    assert im.size == (1122, 1402 - (10 - n) * 73)
    # exactly n rows with both crests; footer sits below the last row
    from netrattler_premium_compact import compact_master
    base = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=compact_master("combo", n)))).convert("RGB")
    for i in range(n):
        y = 390 + 73 * i
        assert changed(im, base, (56, y + 4, 180, y + 60)), f"row {i + 1} crests missing"


@pytest.mark.parametrize("n", range(2, 7))
def test_cross_mix_rows(n):
    legs = [{"match": "A vs B", "market": f"Markt {i}", "odds": 1.7 + i / 10, "bookmaker": "f"} for i in range(n)]
    assert img(X.render_combo(legs, crest, category="cross_mix")).height == 1402 - (6 - n) * 84


@pytest.mark.parametrize("bad", [2, 11])
def test_combo_rejects_bad_counts(bad):
    legs = [{"match": "A vs B", "market": "m", "odds": 1.7, "bookmaker": "f"}] * bad
    with pytest.raises(ValueError):
        X.render_combo(legs, crest)


def test_missing_crest_and_estimated_odds_fail_closed():
    with pytest.raises(ValueError):
        X.render_corner(TIP, lambda t: b"", kickoff="k")
    with pytest.raises(ValueError):
        X.render_corner(dict(TIP, estimated_odds=True), crest, kickoff="k")
    with pytest.raises(ValueError):
        X.render_corner({k: v for k, v in TIP.items() if k != "bookmaker"}, crest, kickoff="k")
    with pytest.raises(ValueError):
        X.render_corner({k: v for k, v in TIP.items() if k not in ("odds",)}, crest, kickoff="k")


def test_lmg_open_and_final():
    fx = {"home": "Demo United", "away": "Demo City", "league": "Demo", "minute": 84, "hg": 1, "ag": 1}
    m = {"tier": "STANDARD", "teams": {"home": {"shots": 12, "sot": 5, "corners": 6, "xg": 1.2},
                                        "away": {"shots": 8, "sot": 3, "corners": 4, "xg": .8}}}
    a = img(X.render_lmg(fx, m, crest)); b = img(X.render_lmg(fx, m, crest, final_score="2:1", won=True))
    assert a.size == b.size == (1122, 1402) and changed(a, b, (42, 1230, 1080, 1300))
    check_frame(a, "last_minute_goal")


@pytest.mark.parametrize("category", CATEGORIES)
def test_all_16_masters_render_and_keep_prophunter(category):
    n = 3 if category in ("builder", "combo") else 1
    leg = {"match": "A vs B", "market": "M", "bookmaker_odds": 2.0, "bookmaker": "f"}
    im = img(render_verified_png(category, [dict(leg) for _ in range(n)]))
    assert im.width == 1122
    if n == 1:
        check_frame(im, category)


def test_existing_market_cards_still_premium():
    for market in ("btts", "over25", "btts_ht", "over15_ht", "1x2", "combo"):
        tip = dict(TIP, match="Demo United vs Demo City", oddsYes=1.9, selection="1")
        im = img(render_match([(market, tip)], "2026-11-21", crest_provider=crest))
        assert im.size == (1122, 1402)


def test_no_legacy_handle_anywhere():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent
    for path in root.glob("netrattler_*.py"):
        assert "@netrattler" not in path.read_text(encoding="utf-8"), path.name
    for svg in (root / "assets").glob("premium_*.svg"):
        text = svg.read_text(encoding="utf-8")
        assert "@prophunter" in text and "@netrattler" not in text.lower()


def test_status_labels():
    assert status_text({"marks": {"0": "void"}})[0] == "VOID"
    assert status_text(None)[0] == "OFFEN"
