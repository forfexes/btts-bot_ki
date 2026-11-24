"""Strict offline QA for NETRATTLER AI PREMIUM flexible 1–10 selection cards."""
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
import pytest
from netrattler_premium_flexible_renderer import CATEGORIES, render, validate


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "synthetic-master-only-for-tests.png"
    img = Image.new("RGB", (1080, 608), (17, 31, 59))
    ImageDraw.Draw(img).rectangle((30, 15, 1040, 110), fill=(214, 165, 46))
    img.save(path)
    return path


def _leg(i):
    return {"match": "QA MATCH " + str(i), "market": "QA VERIFIED MARKET",
            "bookmaker_odds": 1.8, "bookmaker": "OFFLINE TEST"}


@pytest.mark.parametrize("count", range(1, 11))
def test_every_length_preserves_pixels_and_separates_rows(source, count):
    typ = "single" if count == 1 else "builder"
    data = {"category": typ, "legs": [_leg(i) for i in range(count)], "stake_units": 1}
    if count > 1:
        data.update(combined_odds=2.5, combined_odds_observed=True,
                    combined_ticket_id="QA ONLY")
    image = render(source, data)
    with Image.open(source) as expected:
        assert image.crop((0, 0, 1080, expected.height)).tobytes() == expected.tobytes()
    assert image.width == 1080
    assert image.height > 608
    assert image.height < 3000


@pytest.mark.parametrize("category", sorted(CATEGORIES))
def test_all_categories_render_without_fallback(source, category):
    multi = category in {"builder", "combo", "cross_mix", "lottery"}
    data = {"category": category, "legs": [_leg(1), _leg(2)] if multi else [_leg(1)]}
    if multi:
        data.update(combined_odds=3.24, combined_odds_observed=True,
                    combined_ticket_id="QA ONLY")
    assert render(source, data).size[0] == 1080


def test_invalid_quotes_and_fabrication_rejected():
    data = {"category": "single", "legs": [_leg(1)]}
    for bad in (None, 1.0, float("nan")):
        data["legs"][0]["bookmaker_odds"] = bad
        with pytest.raises(ValueError):
            validate(data)
    data["legs"][0]["bookmaker_odds"] = 1.8
    data["legs"][0]["odds_calculated"] = True
    with pytest.raises(ValueError):
        validate(data)


def test_combined_quote_must_be_bookmaker_observed():
    data = {"category": "builder", "legs": [_leg(1), _leg(2)],
            "combined_odds": 3.24}
    with pytest.raises(ValueError, match="bookmaker ticket"):
        validate(data)


def test_unreadable_long_text_is_rejected(source):
    data = {"category": "single", "legs": [_leg(1)]}
    data["legs"][0]["market"] = "LONG STRING " * 200
    with pytest.raises(ValueError, match="overflow"):
        render(source, data)


def test_committed_exact_master_binary_and_live_dimensions():
    from netrattler_premium_flexible_renderer import MASTER_PATH, MASTER_SHA256
    import hashlib
    assert MASTER_PATH.is_file(), "Exact premium PNG missing from repository"
    assert hashlib.sha256(MASTER_PATH.read_bytes()).hexdigest() == MASTER_SHA256
    with Image.open(MASTER_PATH) as im:
        assert im.format == "PNG" and im.size == (1080, 608)


def test_real_master_all_categories_keep_header_identical():
    from netrattler_premium_flexible_renderer import MASTER_PATH
    with Image.open(MASTER_PATH) as original:
        top = original.convert("RGB").tobytes()
    for category in sorted(CATEGORIES):
        multi = category in {"builder", "combo", "cross_mix", "lottery"}
        for count in ((2, 5, 10) if multi else (1,)):
            data = {"category": category, "legs": [_leg(i) for i in range(count)]}
            if multi:
                data.update(combined_odds=3.24, combined_odds_observed=True,
                            combined_ticket_id="SYNTHETIC-QA-ONLY")
            rendered = render(MASTER_PATH, data)
            assert rendered.crop((0, 0, 1080, 608)).tobytes() == top
            assert rendered.width == 1080
