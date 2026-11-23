"""Offline five-owner-reference QA: preserve sources and reject screenshot ghosts."""
from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from PIL import Image, ImageChops

from netrattler_clean_master_builder import W, H, _source
from netrattler_five_owner_reference_qa import SPECS, build, export


@pytest.mark.parametrize("family", sorted(SPECS))
def test_each_owner_family_clean_blank(family, tmp_path):
    src, title, labels = SPECS[family]
    hash_before = hashlib.sha256(src.read_bytes()).hexdigest()
    png, info = build(family)
    with Image.open(BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (W, H)
        cleaned = image.convert("RGB")
        source = _source(src).convert("RGB")
        # Immutable identity is the crown brand, NOT the sample betting data.
        assert ImageChops.difference(cleaned.crop((0,0,W,110)),
                                     source.crop((0,0,W,110))).getbbox() is None
        # The old screenshot must not still be visible behind the margins:
        # all original data below the crown is reconstructed as clean art.
        for box in ((0, 165, 75, 1230), (1047, 165, W, 1230)):
            old = list(source.crop(box).getdata())
            new = list(cleaned.crop(box).getdata())
            same = sum(a == b for a,b in zip(old,new))
            assert same / len(old) < 0.01
        image.verify()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == hash_before
    assert info["source_sha256"] == hash_before
    assert info["source_reference"].endswith(src.name)
    assert info["category"] == family
    assert info["production_approved"] is False
    assert info["human_visual_approved"] is False
    assert info["telegram_android_qa_approved"] is False
    assert info["owner_original_source_unmodified"] is True
    assert info["logo_backplates"] is False
    assert len(info["floating_crest_slots"]) == 2
    assert len(info["blank_slots"]) == 3


def test_export_all_five_source_artworks_without_mutation(tmp_path):
    reports = export(tmp_path)
    assert len(reports) == 5
    assert len(list(tmp_path.glob("*_SOURCE_DERIVED_SANDBOX.png"))) == 5
    assert (tmp_path/"manifest.json").exists()
    assert {x["owner_reference_family"] for x in reports} == set(SPECS)
    assert all(x["production_approved"] is False for x in reports)


def test_unknown_families_fail_closed():
    for family in ("last_minute_goal","fake","over",""):
        with pytest.raises(ValueError,match="five original"):
            build(family)
