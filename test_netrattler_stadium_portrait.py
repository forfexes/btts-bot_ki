"""Offline contract for pinned owner stadium and strict regular rendering."""
import io
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image, ImageDraw
import netrattler_stadium_portrait as stadium
import netrattler_premium_telegram_adapter as adapter

def fixture_crest():
    im=Image.new("RGBA",(100,100),(0,0,0,0))
    ImageDraw.Draw(im).polygon([(50,2),(97,48),(50,98),(2,48)],fill=(40,100,190,255))
    return im

def test_master_is_exact_and_missing_fails(tmp_path):
    with pytest.raises(ValueError,match="master_missing"):
        stadium.load_master(tmp_path/"missing.png")
    fake=tmp_path/"fake.png"
    Image.new("RGB",stadium.DIMENSIONS).save(fake)
    with pytest.raises(ValueError,match="sha256_mismatch"):
        stadium.load_master(fake)

@pytest.mark.parametrize("market",sorted(stadium.REGULAR))
def test_layout_keeps_header_and_source_geometry(market):
    # Synthetic art only in isolated geometry unit test, never approved master.
    original=Image.new("RGB",stadium.DIMENSIONS,(5,22,40))
    with patch.object(stadium,"load_master",return_value=original):
        payload=stadium.render_regular(market,"QA - KEIN ECHTER TIPP",
            {"commence_time":"2026-11-25T18:00:00Z","probability":60},
            "QA HOME","QA AWAY",fixture_crest(),fixture_crest(),1.8)
    with Image.open(io.BytesIO(payload)) as im:
        assert im.size==stadium.DIMENSIONS
        assert im.crop((0,0,1122,265)).tobytes()==original.crop((0,0,1122,265)).tobytes()

def test_strict_adapter_never_fetches_assets_when_master_missing():
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"1"}), patch.object(stadium,"master_ready",return_value=False):
        with pytest.raises(ValueError,match="not_visually_approved"):
            adapter.render([("btts",{})],"2026-11-25",crest_provider=lambda _: pytest.fail("Unexpected fetch"))

def test_real_master_if_uploaded():
    if not stadium.MASTER.is_file():
        pytest.skip("Exact owner PNG still needs repository upload")
    assert stadium.load_master().size==stadium.DIMENSIONS
