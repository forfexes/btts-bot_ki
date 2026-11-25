import ast
from pathlib import Path
from unittest.mock import Mock
from netrattler_strict_delivery import send_regular,scorer_eligible

def test_wrong_player_and_post_shrink_probability():
    assert not scorer_eligible({"match":"Bolton Wanderers FC vs West Bromwich Albion FC","player":"Felix Horn Myhre","team":"","odds":5.2,"probability":22,"_source":"Pinnacle"})[0]
    assert not scorer_eligible({"match":"Bolton Wanderers FC vs West Bromwich Albion FC","player":"QA ONLY","team":"Bolton Wanderers FC","odds":5.2,"probability":22,"_source":"Pinnacle"})[0]

def test_missing_source_or_kickoff_never_sends():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"probability":56,"time":"21:50"}
    assert send_regular(cards,"QA","QA","over25",tip,"2026-11-25") is None
    assert send_regular(cards,"QA","QA","over25",{**tip,"bookmaker":"Pinnacle"},"2026-11-25") is None
    cards.render_card.assert_not_called()
    cards._send_photo.assert_not_called()

def test_photo_receipt_only():
    cards=Mock()
    cards.render_card.return_value=b"QA"
    cards._send_photo.return_value=123
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle","commence_time":"2026-11-25T18:00:00Z"}
    assert send_regular(cards,"QA","QA","over25",tip,"2026-11-25")==123
    cards.save_card.assert_called_once()
    cards._send_photo.return_value=True
    assert send_regular(cards,"QA","QA","over25",tip,"2026-11-25") is None

def test_actual_bot_has_no_original_mode_text_fallback():
    source=Path("btts_bot.py").read_text()
    tree=ast.parse(source)
    for node in (n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="send_top_tips"):
        code=ast.get_source_segment(source,node)
        assert "msg_id = send_regular" in code
    assert 'if not _smid and env("NETRATTLER_ORIGINAL_ONLY", "0") != "1"' in source
    assert 'if not _cmid and env("NETRATTLER_ORIGINAL_ONLY", "0") != "1"' in source
    assert 'an_drop_post_shrink_' in source
