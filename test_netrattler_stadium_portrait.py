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


def _sample():
    return {"match":"QA HOME vs QA AWAY","league":"OFFLINE TEST - KEIN ECHTER TIPP",
            "bookmaker":"QA_TEST_SOURCE","oddsYes":1.8,"odds_observed":True,
            "probability":0.643,"commence_time":"2026-11-25T18:00:00Z"}

def _crest_bytes(_):
    out=io.BytesIO()
    fixture_crest().save(out,format="PNG")
    return out.getvalue()

@pytest.mark.parametrize("market",sorted(stadium.REGULAR))
def test_strict_actual_master_adapter_and_settlement(market,monkeypatch):
    assert stadium.master_ready(), "Exact source image required"
    monkeypatch.setenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS","1")
    item={**_sample(),"selection":"1" if market=="1x2" else "YES",
          "tip_eligible":True,"settlement_rule_verified":True}
    observed=[]
    draw=stadium._label
    def capture(d,xy,value,*args,**kwargs):
        observed.append(str(value))
        return draw(d,xy,value,*args,**kwargs)
    with patch.object(stadium,"_label",side_effect=capture), patch.object(adapter,"render_verified_png",side_effect=AssertionError("legacy artwork")):
        raw=adapter.render([(market,item)],"2026-11-25",crest_provider=_crest_bytes)
        assert "MODELL  64.3%" in observed
        assert "25.11.2026 · 19:00 Uhr" in observed
        assert "AUSWERTUNG: OFFEN" in observed
        closed=adapter.render([(market,item)],"2026-11-25",crest_provider=_crest_bytes,result={"marks":{"0":"won"},"ft":"2-1"})
        assert "AUSWERTUNG: GEWONNEN" in observed
    with Image.open(io.BytesIO(raw)) as im, Image.open(io.BytesIO(closed)) as done:
        assert im.size==done.size==stadium.DIMENSIONS
        assert im.crop((0,0,1122,265)).tobytes()==stadium.load_master().crop((0,0,1122,265)).tobytes()
        # Preserve the original artwork in the former invented frame and footer areas.
        original = stadium.load_master()
        for area in ((205,280,250,310),(48,680,90,715),(72,826,120,850),
                     (72,982,120,1008),(72,1170,120,1195),(0,1300,1122,1402)):
            assert im.crop(area).tobytes() == original.crop(area).tobytes()
            assert done.crop(area).tobytes() == original.crop(area).tobytes()
        assert "@prophunter" not in observed
        assert im.crop((0,0,1122,1170)).tobytes()==done.crop((0,0,1122,1170)).tobytes()
        assert im.crop((0,1170,1122,1295)).tobytes()!=done.crop((0,1170,1122,1295)).tobytes()
    # Test artefacts are deliberately labelled as non-publishable QA examples.
    import os
    directory=os.getenv("NETRATTLER_STADIUM_QA_PREVIEW_DIR")
    if directory:
        path=Path(directory)
        path.mkdir(parents=True,exist_ok=True)
        (path/(market+"-OFFLINE-QA.png")).write_bytes(raw)

@pytest.mark.parametrize("change",[{"synthetic":True},{"odds_observed":False},{"oddsYes":0},{"bookmaker":"ESPN"},{"probability":float("nan")},{"selection":"NO"}])
def test_strict_actual_master_refuses_bad_payload(change,monkeypatch):
    monkeypatch.setenv("NETRATTLER_BLOCK_OVERPAINTED_MASTERS","1")
    with pytest.raises(ValueError):
        adapter.render([("btts",{**_sample(),**change})],"2026-11-25",crest_provider=_crest_bytes)
