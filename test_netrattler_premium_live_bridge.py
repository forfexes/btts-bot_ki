"""Offline integration: real-type source tips -> genuine transparent asset slots."""
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from netrattler_premium_live_bridge import (
    prepare_verified_ticket, verified_mobile_images,
    verified_telegram_payload_plan,
)


def _cutout(mode="RGBA", player=False):
    im=Image.new(mode, (160,180) if player else (120,120),
                 (0,0,0,0) if mode=="RGBA" else (200,205,210))
    d=ImageDraw.Draw(im)
    if mode=="RGBA":
        d.ellipse((18,8,im.width-18,im.height-8),fill=(232,166,32,255))
    buf=BytesIO()
    im.save(buf,format="PNG")
    return buf.getvalue()


def _single():
    return {"ticket_id":"TEST-SINGLE-1", "market":"btts",
            "match":"Club A vs Club B", "selection":"YES", "odds":1.82,
            "bookmaker":"BOOK-OBSERVED", "model_probability":57.2}


def _multi(n=10):
    t={"ticket_id":"TEST-BUILDER-1","category":"builder",
       "combined_odds":18.4,"combined_odds_observed":True,
       "combined_quote_id":"BOOKMAKER-RECEIPT-1"}
    t["legs"]=[
        {"match":f"Club A vs Club B","market_label":f"MARKT {i+1}: BTTS JA",
         "bookmaker_odds":1.82, "bookmaker":"OBSERVED SOURCE"}
        for i in range(n)
    ]
    return t


def _provider(_):
    return _cutout()


def test_single_existing_tip_renders_one_real_layout_page():
    pages=verified_mobile_images(_single(),crest_provider=_provider)
    assert len(pages)==1 and pages[0].width==1080


def test_multipage_real_layout_and_quote_label():
    pages=verified_mobile_images(_multi(),crest_provider=_provider)
    assert len(pages)==4
    assert all(image.width==1080 for image in pages)


def test_telegram_plan_prepared_without_network():
    plan=verified_telegram_payload_plan(_multi(),"FAKE-CHAT",crest_provider=_provider)
    assert plan.method=="sendMediaGroup"
    assert len(plan.files)==4


def test_missing_authentic_crest_fails_closed():
    with pytest.raises(ValueError,match="image bytes"):
        verified_mobile_images(_single(),crest_provider=lambda team:b"")


def test_opaque_crest_or_fake_square_not_allowed():
    with pytest.raises(ValueError,match="opaque"):
        verified_mobile_images(_single(),crest_provider=lambda team:_cutout("RGB"))


def test_estimated_individual_quote_refused():
    t=_single()
    t["odds_calculated"]=True
    with pytest.raises(ValueError,match="estimated"):
        verified_mobile_images(t,crest_provider=_provider)


def test_real_leg_combo_without_bookmaker_total_is_labelled_formula():
    t=_multi()
    t["combined_odds_observed"]=False
    with prepare_verified_ticket(t,crest_provider=_provider) as (converted,_):
        from netrattler_premium_flexible_renderer import combined_quote_info
        q=combined_quote_info(converted)
        assert not q["observed"]
        assert q["label"]=="BERECHNET – KEINE BUCHMACHERQUOTE"
        assert converted["combined_odds"]==round(1.82**10,4)
        assert converted["price_type"]=="calculated_from_leg_odds"
        assert q["scope"]=="shared_game_correlated"
    pages=verified_mobile_images(t,crest_provider=_provider)
    assert len(pages)==4

def test_fake_confirmed_bookmaker_receipt_stays_blocked():
    t=_multi()
    t["features"]={"builder_odds_estimated_from_legs":True}
    with pytest.raises(ValueError,match="Contradictory"):
        verified_mobile_images(t,crest_provider=_provider)


def test_wrong_player_club_refused_without_fetching_photo():
    t=_single()
    t.update(player="QA Player",team="Wrong Club")
    with pytest.raises(ValueError,match="Player's verified club"):
        verified_mobile_images(t,crest_provider=_provider,
                            player_provider=lambda *_: (_ for _ in ()).throw(AssertionError("fetch occurred")))


def test_real_player_requires_actual_transparent_cutout():
    t=_single()
    t.update(player="QA Player",team="Club A")
    pages=verified_mobile_images(t,crest_provider=_provider,
                                player_provider=lambda *_:_cutout(player=True))
    assert len(pages)==1
    with pytest.raises(ValueError,match="opaque"):
        verified_mobile_images(t,crest_provider=_provider,
                               player_provider=lambda *_:_cutout("RGB",player=True))


def test_var_unverified_rule_never_reaches_image_provider():
    t=_single()
    t.update(market="var", selection="YES",tip_eligible=False)
    with pytest.raises(ValueError,match="VAR settlement"):
        verified_mobile_images(t,crest_provider=lambda *_: (_ for _ in ()).throw(
            AssertionError("provider called without rule proof")))


def test_1x2_requires_real_choice():
    t=_single()
    t.update(market="1x2", selection="YES")
    with pytest.raises(ValueError,match="1X2 selection"):
        verified_mobile_images(t,crest_provider=_provider)


def test_ticket_identity_missing_rejected():
    t=_single()
    t.pop("ticket_id")
    with pytest.raises(ValueError,match="ticket_id"):
        verified_mobile_images(t,crest_provider=_provider)


def test_asset_temporary_files_are_cleaned():
    paths=[]
    def provider(team):
        return _cutout()
    with prepare_verified_ticket(_single(),crest_provider=provider) as (ticket,master):
        paths=[Path(ticket["legs"][0][key]) for key in ("home_logo","away_logo")]
        assert all(p.is_file() for p in paths)
    assert all(not p.exists() for p in paths)


def test_builder_selection_must_include_real_named_market():
    t=_multi(2)
    t["legs"][0].pop("market_label")
    t["legs"][0].update(market="btts",selection="YES")
    with prepare_verified_ticket(t,crest_provider=_provider) as (converted,_):
        assert "BTTS" in converted["legs"][0]["market"]
        assert converted["legs"][0]["market"] != "YES"
    t["legs"][0]["market"]="unrecognized_code"
    with pytest.raises(ValueError,match="market label"):
        verified_mobile_images(t,crest_provider=_provider)


def test_var_and_1x2_builder_legs_need_actual_market_evidence():
    t=_multi(2)
    t["legs"][0].pop("market_label")
    t["legs"][0].update(market="var",selection="YES")
    with pytest.raises(ValueError,match="VAR settlement"):
        verified_mobile_images(t,crest_provider=_provider)
    t["legs"][0].update(market="1x2",selection="YES")
    with pytest.raises(ValueError,match="1X2"):
        verified_mobile_images(t,crest_provider=_provider)
