"""Actual PNG inspection (not a mocked return value)."""
from unittest.mock import patch
from io import BytesIO
from PIL import Image, ImageDraw
from netrattler_visual_review import review_png
from netrattler_card_visual_preview import generate
import pytest


@pytest.fixture(autouse=True)
def _synthetic_visual_review_only(monkeypatch):
    """Only pixel-inspection QA may render the historical screenshot plates."""
    monkeypatch.setenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS","0")


def _samples(tmp_path):
    generate(tmp_path)
    return {name: (tmp_path/name).read_bytes() for name in (
        "TEST_ONLY_builder_2leg.png","TEST_ONLY_builder_4leg.png",
        "TEST_ONLY_builder_6leg.png","TEST_ONLY_goal_hunter.png"
    )}


def test_all_four_real_png_previews_pass_actual_image_review(tmp_path):
    files = _samples(tmp_path)
    assert all(review_png(content,"builder",legs=int(name.split("_")[-1][0]))
               .passed for name,content in files.items() if "builder" in name)
    assert review_png(files["TEST_ONLY_goal_hunter.png"],"scorer").passed


def test_blank_and_wrong_size_images_are_blocked():
    raw = BytesIO()
    Image.new("RGB",(1200,970),"#070E17").save(raw, "PNG")
    report = review_png(raw.getvalue(),"builder",legs=2)
    assert not report.passed
    assert "player_name_1" in report.problems
    assert "bookmaker_quote" in report.problems
    assert "settlement_footer" in report.problems
    assert "footer_clipped" not in report.problems
    assert not review_png(b"garbage", "scorer").passed
    assert "dimensions" in review_png(raw.getvalue(),"builder",legs=6).problems


def test_actual_rendered_card_missing_text_is_rejected(tmp_path):
    files = _samples(tmp_path)
    raw=files["TEST_ONLY_builder_2leg.png"]
    im=Image.open(BytesIO(raw)).convert("RGB")
    ImageDraw.Draw(im).rectangle((369,411,744,448),fill="#07131B")
    buf=BytesIO()
    im.save(buf, "PNG")
    report=review_png(buf.getvalue(), "builder", legs=2)
    assert "player_name_1" in report.problems


def test_footer_crop_is_rejected(tmp_path):
    files=_samples(tmp_path)
    im=Image.open(BytesIO(files["TEST_ONLY_builder_6leg.png"]))
    out=BytesIO()
    im.crop((0,0,im.width,im.height-140)).save(out, "PNG")
    report=review_png(out.getvalue(),"builder",legs=6)
    assert not report.passed
    assert "master_dimensions" in report.problems
