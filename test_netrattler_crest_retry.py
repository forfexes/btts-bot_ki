from io import BytesIO
from types import SimpleNamespace
from PIL import Image, ImageDraw
import netrattler_stats_match_cards as cards
import netrattler_flags

def png(opaque=False):
    im=Image.new("RGBA",(80,80),(255,255,255,255) if opaque else (0,0,0,0))
    ImageDraw.Draw(im).rectangle((15,15,65,65),fill=(40,80,200,255))
    b=BytesIO()
    im.save(b,format="PNG")
    return b.getvalue()

def setup(monkeypatch):
    monkeypatch.setattr(cards,"_LOGO_CACHE",{})
    monkeypatch.setattr(cards,"_BADGE_CACHE",{})
    monkeypatch.setattr(netrattler_flags,"flag_url",lambda *_:"")
    for name in ("_crest_from_index","_fl_logo","_wikidata_logo","_apifootball_logo","_allsports_logo","_sofascore_logo","_espn_logo","_wiki_badge"):
        monkeypatch.setattr(cards,name,lambda *_:"")
    monkeypatch.setattr(cards,"_search_badge",lambda *_:("",False))

def test_bad_cached_url_and_opaque_source_fall_through(monkeypatch):
    setup(monkeypatch)
    cards._LOGO_CACHE["qaclub"]="https://qa.invalid/stale"
    monkeypatch.setattr(cards,"_crest_from_index",lambda *_:"https://qa.invalid/opaque")
    monkeypatch.setattr(cards,"_espn_logo",lambda *_:"https://qa.invalid/good")
    calls=[]
    good=png()
    def get(url,**kwargs):
        calls.append(url)
        return SimpleNamespace(ok=not url.endswith("stale"),content=png(True) if url.endswith("opaque") else good)
    monkeypatch.setattr(cards.requests,"get",get)
    assert cards._badge_bytes("QA Club")==good
    assert calls==["https://qa.invalid/stale","https://qa.invalid/opaque","https://qa.invalid/good"]
    assert cards._LOGO_CACHE["qaclub"]=="https://qa.invalid/good"
    assert cards._badge_bytes("QA Club")==good
    assert len(calls)==3

def test_total_failure_is_not_cached(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(cards,"_crest_from_index",lambda *_:"https://qa.invalid/photo")
    good=png()
    responses=iter([SimpleNamespace(ok=False,content=b""),SimpleNamespace(ok=True,content=good)])
    monkeypatch.setattr(cards.requests,"get",lambda *_a,**_k:next(responses))
    assert cards._badge_bytes("QA Club")==b""
    assert not cards._BADGE_CACHE and not cards._LOGO_CACHE
    assert cards._badge_bytes("QA Club")==good
