import io,os
from pathlib import Path
from PIL import Image,ImageDraw
import pytest
from netrattler_stadium_portrait import load_master,DIMENSIONS
from netrattler_remaining_stadium import render_corner,render_ticket,render_live,TICKET_TITLES,LIVE_TITLES

def crest(name):
    im=Image.new("RGBA",(160,160),(0,0,0,0));d=ImageDraw.Draw(im)
    d.polygon([(15,20),(145,25),(135,145),(20,130)],fill=(sum(map(ord,name))%200+20,80,200,255))
    d.text((30,60),name[:10],fill="white")
    out=io.BytesIO();im.save(out,format="PNG");return out.getvalue()

def leg(i=0):
    return {"match":f"QA HOME {i} vs QA AWAY {i}","market":"btts","selection":"YES",
            "bookmaker":"QA_ONLY","odds":1.8,"odds_observed":True,"probability":.6,
            "commence_time":"2026-11-25T18:00:00Z","event_id":str(i)}

def inspect(payload,name):
    with Image.open(io.BytesIO(payload)) as im:
        assert im.size==DIMENSIONS
        orig=load_master()
        for rect in ((0,0,1122,265),(0,1300,1122,1402)):
            assert im.crop(rect).tobytes()==orig.crop(rect).tobytes()
    if os.getenv("REMAINING_QA_DIR"):
        p=Path(os.environ["REMAINING_QA_DIR"]);p.mkdir(exist_ok=True,parents=True)
        (p/(name+"-OFFLINE-QA.png")).write_bytes(payload)

def test_corner():
    tip={**leg(),"selection":"QA ONLY OVER 9.5","expected_corners":10.1,"home_corners_l10":5,"home_corners_l15":5.2,"away_corners_l10":4.3,"away_corners_l15":4.1,"corner_hits_l10":"6/10","corner_hits_l15":"9/15"}
    inspect(render_corner(tip,crest_provider=crest),"corner")
    with pytest.raises(ValueError):render_corner({**tip,"expected_corners":None},crest_provider=crest)

@pytest.mark.parametrize("kind",sorted(TICKET_TITLES))
@pytest.mark.parametrize("count",[2,7,12])
def test_formula_ticket(kind,count):
    pages,info=render_ticket(kind,[leg(i) for i in range(count)],crest_provider=crest,ticket_id="OFFLINE-QA")
    assert len(pages)==(count+2)//3
    assert info["real_bookmaker_combined_odds"] is None
    assert info["ev_percent_using_real_ticket_only"] is None
    assert info["individual_prices_observed"]
    for i,page in enumerate(pages):inspect(page,f"{kind}-{count}-{i+1}")

def test_invalid_legs():
    with pytest.raises(ValueError):render_ticket("combo",[leg(0),leg(0)],crest_provider=crest,ticket_id="QA")
    with pytest.raises(ValueError):render_ticket("combo",[leg(0),{**leg(1),"synthetic":True}],crest_provider=crest,ticket_id="QA")

@pytest.mark.parametrize("kind",sorted(LIVE_TITLES))
def test_live(kind):
    fixture={"home":"QA HOME","away":"QA AWAY","minute":45 if kind=="live_halftime" else 85,"hg":1,"ag":1,"fixture_verified":True}
    inspect(render_live(kind,fixture,crest_provider=crest,metrics={"shots":(7,6),"xg":(.9,.8)}),kind)
    with pytest.raises(ValueError):render_live(kind,{**fixture,"fixture_verified":False},crest_provider=crest,metrics={"shots":(7,6)})
