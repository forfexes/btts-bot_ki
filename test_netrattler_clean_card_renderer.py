"""Hermetic image QA; no network, Telegram, Supabase, or new live tips."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import os

import pytest
from PIL import Image, ImageDraw

from netrattler_clean_card_renderer import render_qa_card, _logo
from netrattler_clean_master_builder import W, H, SOURCE_MAP, render_clean_master

NOW = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)


def _asset():
    # Synthetic shape used ONLY in watermarked sandbox tests.
    icon = Image.new("RGBA", (120, 140), (0, 0, 0, 0))
    ImageDraw.Draw(icon).polygon(((60, 7), (104, 107), (60, 125), (12, 107)),
                                 fill=(224, 28, 32, 255))
    return icon


def _metadata():
    return {"category": "over", "classification": "owner-derived_clean_QA_NOT_user_original",
            "production_approved": False, "logo_backplates": False,
            "floating_crest_slots": [
                {"center_x": 250, "center_y": 456, "max_width": 194, "max_height": 195},
                {"center_x": 872, "center_y": 456, "max_width": 194, "max_height": 195}],
            "blank_slots": {
                f"stat_{j}": {"x": 555, "y": 638 + (j-1)*142 + 24,
                                "width": 388, "height": 66}
                for j in (1, 2, 3)}}


def _record():
    return {"home": "QA Home", "away": "QA Away", "home_id": "aa", "away_id": "bb",
            "home_crest": _asset(), "away_crest": _asset(),
            "fixture_id": "SANDBOX-987",
            "kickoff": NOW + timedelta(hours=1), "bookmaker": "QA only",
            "quote_id": "QA-receipt-987", "quote_observed_at": NOW-timedelta(minutes=1),
            "bookmaker_odds": 1.87, "price_estimated": False,
            "selection": "OVER 2.5", "stats": {}}


def _plate():
    out = BytesIO()
    Image.new("RGB", (W, H), (5, 18, 34)).save(out, "PNG")
    return out.getvalue()


def test_all_ten_categories_render_sandbox_without_legacy_stickers():
    for family in sorted(SOURCE_MAP):
        meta = _metadata()
        meta["category"] = family
        png = render_qa_card(_plate(), meta, _record(), now=NOW)
        with Image.open(BytesIO(png)) as im:
            assert im.format == "PNG" and im.size == (W, H)
            assert im.getpixel((155, 356)) == (5, 18, 34)
            assert im.getpixel((767, 356)) == (5, 18, 34)
            assert im.getpixel((250, 456))[0] > 100
            assert im.getpixel((872, 456))[0] > 100
            assert any(im.getpixel((x, y)) != (5, 18, 34)
                       for x in range(730, 768) for y in range(678, 716))


@pytest.mark.parametrize("family", sorted(SOURCE_MAP))
def test_actual_owner_derived_plate_in_sandbox_only(family):
    # Unlike the synthetic fixture above this uses the real repo's
    # original artwork, but the preview ALWAYS has a sandbox watermark.
    plate, meta = render_clean_master(family)
    png = render_qa_card(plate, meta, _record(), now=NOW)
    with Image.open(BytesIO(png)) as im:
        assert im.format == "PNG"
        assert im.size == (W, H)
        im.verify()
    preview_dir = os.getenv("NETRATTLER_CARD_QA_PREVIEW_DIR")
    if preview_dir:
        outdir = Path(preview_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / (family + "_SANDBOX_NOT_APPROVED.png")).write_bytes(png)


def test_missing_or_fake_assets_fail_closed():
    record = _record()
    for key, bad in (("home_crest", None),
                     ("away_crest", Image.new("RGB", (80, 80), "red")),
                     ("price_estimated", True),
                     ("quote_id", ""),
                     ("home_id", "bb"),
                     ("quote_observed_at", NOW-timedelta(minutes=16)),
                     ("kickoff", NOW-timedelta(seconds=1)),
                     ("bookmaker_odds", float("nan"))):
        edited = dict(record, **{key: bad})
        with pytest.raises(ValueError):
            render_qa_card(_plate(), _metadata(), edited, now=NOW)


def test_no_runtime_approval_or_unsupported_master():
    for edit in ({"production_approved": True},
                 {"classification": "original_approved"},
                 {"category": "builder"},
                 {"logo_backplates": True}):
        with pytest.raises(ValueError):
            render_qa_card(_plate(), dict(_metadata(), **edit), _record(), now=NOW)


def test_lookahead_stats_and_anonymous_statistics_rejected():
    record = _record()
    record["stats"] = {"stat_1": {"value": "3", "source": "provider",
                                   "event_id": "match-id", "observed_at": NOW+timedelta(minutes=1)}}
    with pytest.raises(ValueError, match="Look-ahead"):
        render_qa_card(_plate(), _metadata(), record, now=NOW)
    record["stats"]["stat_1"].pop("source")
    with pytest.raises(ValueError, match="provider"):
        render_qa_card(_plate(), _metadata(), record, now=NOW)


def test_too_small_logo_is_not_scaled_into_an_artificial_badge():
    with pytest.raises(ValueError):
        _logo(Image.new("RGBA", (10, 10), (240, 10, 20, 255)), 194, 195)
