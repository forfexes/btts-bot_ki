"""Original user-chosen Corner Sniper artwork and Telegram delivery regression."""
import io
import pytest
from unittest.mock import patch
from PIL import Image,ImageDraw
import netrattler_corner_cards as corner
import netrattler_stats_match_cards as cards
from netrattler_corner_template import MASTER,render_corner_template,review_corner_png,validate_corner


def badge():
    pic=Image.new("RGB",(96,96),"#214A6D")
    ImageDraw.Draw(pic).ellipse((12,12,84,84),fill="#E3BD43")
    buf=io.BytesIO();pic.save(buf,"PNG");return buf.getvalue()


def valid_pick():
    return {
        "match":"Beispiel FC vs Test United","league":"Testliga",
        "tip":"Über 9,5 Ecken","_source":"test_only","odds":1.83,
        "probability":79,"expected_corners":11.2,"h2h_matches":4,
        "home_avg_corners":6.0,"away_avg_corners":5.2,
        "home_corners_l10":6.4,"home_corners_l15":6.7,
        "away_corners_l10":5.0,"away_corners_l15":5.3,
        "h2h_avg_corners":11.0,"corner_hits_l10":"8/10 (80%)",
        "corner_hits_l15":"12/15 (80%)","confidence":"HOCH",
        "_kickoff":"2026-11-21T17:30:00+00:00",
    }


def test_original_corner_image_is_exact_master_and_neon_art():
    assert MASTER.is_file()
    with Image.open(MASTER) as img:
        assert img.size == (1122,1402)
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"}), \
         patch.object(cards,"_badge_bytes",return_value=badge()):
        raw=render_corner_template(valid_pick(),"2026-11-21")
        win=render_corner_template(valid_pick(),"2026-11-21",{"marks":{"0":"win"}})
    with Image.open(io.BytesIO(raw)) as img:
        assert img.size == (1122,1402) and img.format == "PNG"
    assert review_corner_png(raw) == []
    assert review_corner_png(win) == []
    assert raw != win  # In-image Telegram settlement changes original message.


def test_direct_corner_send_passes_pixel_qa_and_stores_original_message():
    tip=valid_pick()
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"}), \
         patch.object(cards,"_badge_bytes",return_value=badge()), \
         patch.object(cards,"attach_h2h_api",return_value=0), \
         patch.object(cards,"_send_photo",return_value=12345) as send, \
         patch.object(cards,"save_card",return_value=True) as save:
        assert corner.send_corner_card("token","chat",tip,"2026-11-21")==12345
    assert send.call_count==1
    assert save.call_args.args[1]==12345


def test_corner_missing_metrics_block_telegram_without_fabricating():
    tip=valid_pick();tip.pop("home_corners_l15")
    with patch.object(cards,"_badge_bytes",return_value=badge()), \
         patch.object(cards,"attach_h2h_api",return_value=0), \
         patch.object(cards,"_send_photo") as send:
        assert corner.send_corner_card("token","chat",tip,"2026-11-21") is None
        send.assert_not_called()
    tip=valid_pick();tip.pop("_kickoff")
    with patch.object(cards,"_badge_bytes",return_value=badge()):
        assert "missing_confirmed_kickoff" in validate_corner(tip,"2026-11-21",cards)
    tip=valid_pick();tip.pop("_source")
    with patch.object(cards,"_badge_bytes",return_value=badge()):
        assert "missing_real_bookmaker_quote" in validate_corner(tip,"2026-11-21",cards)


def test_legacy_screenshot_never_sends_in_production_without_clean_master():
    with patch.dict("os.environ",{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"1"}), \
         patch.object(cards,"_badge_bytes",return_value=badge()), \
         patch.object(cards,"attach_h2h_api",return_value=0), \
         patch.object(cards,"_send_photo") as send:
        with pytest.raises(ValueError,match="corner_original_overpainted"):
            render_corner_template(valid_pick(),"2026-11-21")
        assert corner.send_corner_card("token","chat",valid_pick(),"2026-11-21") is None
        send.assert_not_called()


def test_blank_master_not_accepted_as_final_corner_image():
    with Image.open(MASTER) as m:
        buf=io.BytesIO()
        m.save(buf,"PNG")
    bad=review_corner_png(buf.getvalue())
    assert bad and any("unchanged_placeholder" in v for v in bad)
    buf=io.BytesIO()
    Image.new("RGB",(30,30)).save(buf,"PNG")
    assert review_corner_png(buf.getvalue())==["wrong_corner_png_geometry"]
