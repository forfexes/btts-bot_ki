import ast
from io import BytesIO
from PIL import ImageDraw
from netrattler_stadium_portrait import load_master
from pathlib import Path
from unittest.mock import Mock
from netrattler_strict_delivery import send_regular,scorer_eligible,verified_regular_payload

def test_wrong_player_and_post_shrink_probability():
    assert not scorer_eligible({"match":"Bolton Wanderers FC vs West Bromwich Albion FC","player":"Felix Horn Myhre","team":"","odds":5.2,"probability":22,"_source":"Pinnacle"})[0]
    assert not scorer_eligible({"match":"Bolton Wanderers FC vs West Bromwich Albion FC","player":"QA ONLY","team":"Bolton Wanderers FC","odds":5.2,"probability":22,"_source":"Pinnacle"})[0]

def test_missing_source_or_kickoff_never_sends():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"probability":56,"time":"21:50"}
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25") is None
    assert send_regular(cards,"QA","QA","over25",{**tip,"bookmaker":"Pinnacle"},"2099-11-25") is None
    cards.render_card.assert_not_called()
    cards._send_photo.assert_not_called()

def test_photo_receipt_only():
    cards=Mock()
    cards.render_card.return_value=_master_png()
    cards._send_photo.return_value=123
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle","commence_time":"2099-11-25T18:00:00Z"}
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25")==123
    cards.save_card.assert_called_once()
    cards._send_photo.return_value=True
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25") is None

def test_actual_bot_has_no_original_mode_text_fallback():
    source=Path("btts_bot.py").read_text()
    tree=ast.parse(source)
    for node in (n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="send_top_tips"):
        code=ast.get_source_segment(source,node)
        assert "msg_id = send_regular" in code
    assert 'if not _smid and env("NETRATTLER_ORIGINAL_ONLY", "0") != "1"' in source
    assert 'if not _cmid and env("NETRATTLER_ORIGINAL_ONLY", "0") != "1"' in source
    assert 'an_drop_post_shrink_' in source


def _master_png(alter_header=False, blank=False, incomplete=False):
    image=load_master()
    if not blank:
        draw=ImageDraw.Draw(image)
        draw.rectangle((250,450,350,550),fill=(255,0,255))
        if not incomplete:
            draw.rectangle((250,850,350,950),fill=(255,0,255))
    if alter_header:
        ImageDraw.Draw(image).rectangle((0,0,50,50),fill=(255,0,255))
    out=BytesIO()
    image.save(out,format="PNG")
    return out.getvalue()

def test_outgoing_invalid_or_altered_png_never_sends():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle",
         "commence_time":"2099-11-25T18:00:00Z"}
    assert verified_regular_payload(_master_png())
    for payload in (b"not PNG",_master_png(True),_master_png(blank=True),_master_png(incomplete=True)):
        assert not verified_regular_payload(payload)
        cards.render_card.return_value=payload
        assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25") is None
    cards._send_photo.assert_not_called()
    cards.save_card.assert_not_called()


def test_already_started_fixture_never_renders_or_sends():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle",
         "commence_time":"2000-01-01T18:00:00Z"}
    assert send_regular(cards,"QA","QA","over25",tip,"2000-01-01") is None
    cards.render_card.assert_not_called()
    cards._send_photo.assert_not_called()
    cards.save_card.assert_not_called()


def test_conflicting_kickoff_evidence_blocks_before_render():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle",
         "commence_time":"2099-11-25T18:00:00Z",
         "kickoff_utc":"2099-11-25T19:00:00Z"}
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25") is None
    cards.render_card.assert_not_called()
    cards._send_photo.assert_not_called()

def test_equivalent_timezone_offsets_do_not_conflict():
    cards=Mock()
    cards.render_card.return_value=_master_png()
    cards._send_photo.return_value=123
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle",
         "commence_time":"2099-11-25T18:00:00Z",
         "kickoff_utc":"2099-11-25T19:00:00+01:00"}
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25")==123
