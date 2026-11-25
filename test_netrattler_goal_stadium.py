"""Isolated Goal Hunter QA; no credentials and no real betting tip."""
import io
import os
from pathlib import Path
from PIL import Image, ImageDraw
import pytest
from netrattler_goal_stadium import render_goal
from netrattler_stadium_portrait import load_master, DIMENSIONS

def fixture_asset(label, size=(200,240)):
    im=Image.new("RGBA",size,(0,0,0,0))
    d=ImageDraw.Draw(im)
    # Deliberately abstract QA geometry, never an authentic asset or live tip.
    d.polygon([(15,20),(size[0]-15,30),(size[0]-30,size[1]-30),(25,size[1]-18)],fill=(65,120,210,255))
    d.text((30,80),label,fill=(255,255,255,255))
    out=io.BytesIO(); im.save(out,format="PNG"); return out.getvalue()

def record():
    return {"match":"QA HOME vs QA AWAY","team":"QA HOME","player":"OFFLINE QA - KEIN TIPP",
            "_kickoff":"2026-11-25T18:00:00Z","bookmaker":"QA_ONLY",
            "odds":3.0,"probability":40,"goals_per_game":.5}

def test_exact_master_goal(monkeypatch):
    for key in ("NETRATTLER_SCORER_MIN_PROB","NETRATTLER_SCORER_MIN_ODDS","NETRATTLER_SCORER_MIN_EDGE"):
        monkeypatch.delenv(key,raising=False)
    kwargs={"crest_provider":lambda name:fixture_asset(name),"player_provider":lambda name,team:fixture_asset("QA PHOTO")}
    raw=render_goal(record(),**kwargs)
    won=render_goal(record(),**kwargs,result={"marks":{"0":"won"},"ft":"2-1"})
    original=load_master()
    with Image.open(io.BytesIO(raw)) as im, Image.open(io.BytesIO(won)) as done:
        assert im.size==done.size==DIMENSIONS
        for area in ((0,0,1122,265),(0,1100,1122,1160),(0,1300,1122,1402)):
            assert im.crop(area).tobytes()==original.crop(area).tobytes()
        assert im.crop((0,0,1122,1170)).tobytes()==done.crop((0,0,1122,1170)).tobytes()
        assert im.crop((0,1170,1122,1295)).tobytes()!=done.crop((0,1170,1122,1295)).tobytes()
    if os.getenv("GOAL_QA_DIR"):
        p=Path(os.environ["GOAL_QA_DIR"]);p.mkdir(parents=True,exist_ok=True)
        (p/"goal-OFFLINE-QA.png").write_bytes(raw)

@pytest.mark.parametrize("change",[{"team":"WRONG CLUB"},{"_kickoff":""},{"synthetic":True},{"bookmaker":"ESPN"},{"fairOdds":9},{"probability":0}])
def test_bad_data_fails_before_assets(change):
    def fail(*args): pytest.fail("Unverified data requested assets")
    with pytest.raises(ValueError):
        render_goal({**record(),**change},crest_provider=fail,player_provider=fail)
