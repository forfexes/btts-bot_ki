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
@pytest.mark.parametrize("prob",[60,None])
def test_layout_keeps_header_and_passes_gate(market,prob):
    import netrattler_strict_delivery as gate
    tip={"commence_time":"2026-11-25T18:00:00Z","league":"QA LIGA"}
    if prob is not None:
        tip["probability"]=prob
    payload=stadium.render_regular(market,"QA - KEIN ECHTER TIPP",tip,
        "QA HOME","QA AWAY",fixture_crest(),fixture_crest(),1.8)
    with Image.open(io.BytesIO(payload)) as im:
        assert im.size==stadium.DIMENSIONS
        assert im.convert("RGB").crop((0,0,1122,225)).tobytes()==stadium.load_master().crop((0,0,1122,225)).tobytes()
    assert gate.verified_regular_payload(payload)

def test_strict_adapter_never_fetches_assets_when_master_missing():
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"1"}), patch.object(stadium,"master_ready",return_value=False):
        with pytest.raises(ValueError,match="not_visually_approved"):
            adapter.render([("btts",{})],"2026-11-25",crest_provider=lambda _: pytest.fail("Unexpected fetch"))

def test_real_master_if_uploaded():
    if not stadium.MASTER.is_file():
        pytest.skip("Exact owner PNG still needs repository upload")
    assert stadium.load_master().size==stadium.DIMENSIONS


def _sample():
    return {"match":"QA HOME vs QA AWAY","league":"OFFLINE TEST - KEIN ECHTER TIPP",
            "bookmaker":"QA_TEST_SOURCE","oddsYes":1.8,"odds_observed":True,
            "probability":0.643,"commence_time":"2026-11-25T18:00:00Z"}

def _crest_bytes(team):
    out=io.BytesIO()
    im=fixture_crest()
    if team == "QA AWAY":
        ImageDraw.Draw(im).rectangle((38,38,62,62),fill=(200,40,80,255))
    im.save(out,format="PNG")
    return out.getvalue()

@pytest.mark.parametrize("market",sorted(stadium.REGULAR))
def test_strict_actual_master_adapter_and_settlement(market,monkeypatch):
    import netrattler_strict_delivery as gate
    assert stadium.master_ready(), "Exact source image required"
    monkeypatch.setenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS","1")
    item={**_sample(),"selection":"1" if market=="1x2" else "YES",
          "tip_eligible":True,"settlement_rule_verified":True}
    with patch.object(adapter,"render_verified_png",side_effect=AssertionError("legacy artwork")):
        raw=adapter.render([(market,item)],"2026-11-25",crest_provider=_crest_bytes)
        closed=adapter.render([(market,item)],"2026-11-25",crest_provider=_crest_bytes,result={"marks":{"0":"won"},"ft":"2-1"})
    assert gate.verified_regular_payload(raw) and gate.verified_regular_payload(closed)
    assert raw!=closed
