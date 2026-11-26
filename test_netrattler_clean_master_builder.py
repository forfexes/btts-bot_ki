"""Offline master QA: ten missing category drafts; Last Minute uses its own owner art."""
import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from netrattler_clean_master_builder import (
    H, W, SOURCE_MAP, render_clean_master, write_all, _source,
)

@pytest.mark.parametrize("category", sorted(SOURCE_MAP))
def test_clean_derived_master_preserves_crown_and_contains_no_sample_data(category):
    path = SOURCE_MAP[category]
    raw_before = hashlib.sha256(path.read_bytes()).hexdigest()
    png, metadata = render_clean_master(category)
    assert png.startswith(bytes((137,80,78,71,13,10,26,10)))
    with Image.open(io.BytesIO(png)) as result:
        assert result.size == (W, H)
        assert result.format == "PNG"
        source = _source(path)
        # Exact top user-original crown, not an approximate painted replacement.
        top = (0, 0, W, 110)
        # RGB comparison is deliberate: PIL's RGBA getbbox() can report
        # *no* differences when the alpha channel is identical everywhere,
        # even if the visible RGB pixels have completely changed.
        assert ImageChops.difference(result.convert("RGB").crop(top),
                                     source.convert("RGB").crop(top)).getbbox() is None
        # The original is a flattened betting screenshot; old team names,
        # quotes, odds and score labels must not survive in the outer strips
        # or in the market-title band after the clean derivation.
        result_rgb = result.convert("RGB")
        source_rgb = source.convert("RGB")
        for region in ((0, 165, 75, 1230),
                       (1047, 165, W, 1230),
                       (170, 118, W-170, 158)):
            old = source_rgb.crop(region)
            cleaned = result_rgb.crop(region)
            changed = ImageChops.difference(old, cleaned).convert("L")
            assert changed.getbbox() is not None
            # No untouched original screenshot pixels: this is a new,
            # source-derived background, not a live text-cover-up.
            original_pixels = list(old.getdata())
            clean_pixels = list(cleaned.getdata())
            same = sum(a == b for a, b in zip(original_pixels,clean_pixels))
            assert same / len(original_pixels) < 0.01, (category, region, same)

        # The sample data-bearing centre must be replaced, never left
        # readable underneath the QA plate.
        assert ImageChops.difference(result.convert("RGB").crop((120,300,1002,1250)),
                                     source.convert("RGB").crop((120,300,1002,1250))).getbbox() is not None
    assert hashlib.sha256(path.read_bytes()).hexdigest() == raw_before
    assert not metadata["production_approved"]
    assert metadata["classification"].startswith("owner-derived")
    assert metadata["category"] == category
    assert len(metadata["blank_slots"]) == 3
    assert metadata["logo_backplates"] is False
    assert [slot["center_x"] for slot in metadata["floating_crest_slots"]] == [250,872]
    with Image.open(io.BytesIO(png)) as check:
        # No gold frame/paste-on rings at either genuine team's alpha slot.
        for xx in (153,775):
            rr,gg,bb=check.convert("RGB").getpixel((xx,450))
            assert rr < 140 and gg < 180, (category,xx,rr,gg,bb)

def test_all_clean_derived_masters_have_distinct_labels(tmp_path):
    manifest = write_all(tmp_path)
    assert len(manifest) == len(SOURCE_MAP) == 10
    assert len(list(tmp_path.glob("*_CLEAN_DERIVED_QA.png"))) == 10
    # The real uploaded LAST MINUTE GOAL original must never be falsely
    # represented by a recoloured Corner Sniper reference.
    assert "last_minute_goal" not in SOURCE_MAP
    assert (tmp_path / "manifest.json").is_file()
    assert len({item["category"] for item in manifest}) == 10

def test_unknown_and_missing_sources_fail_closed(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="source mapping"):
        render_clean_master("unapproved_market_name")
    from netrattler_clean_master_builder import SOURCE_MAP
    monkeypatch.setitem(SOURCE_MAP, "var", tmp_path / "missing.webp")
    with pytest.raises(FileNotFoundError):
        render_clean_master("var")


def test_old_screenshot_body_cannot_leak_into_new_plate(tmp_path):
    from netrattler_clean_master_builder import render_clean_master_from_reference
    from PIL import ImageDraw
    a=Image.new("RGB",(W,H),(15,30,45)); b=a.copy()
    ImageDraw.Draw(b).rectangle((0,112,W-1,H-1),fill=(255,0,155))
    pa=tmp_path/"source_a.png"; pb=tmp_path/"source_b.png"
    a.save(pa); b.save(pb)
    x,_=render_clean_master_from_reference("builder",pa,"BUILDER",("A","B","C"))
    y,_=render_clean_master_from_reference("builder",pb,"BUILDER",("A","B","C"))
    assert x==y, "No pixels below the source masthead may enter the clean template"
