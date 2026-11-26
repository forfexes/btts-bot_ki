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
    assert "_cmid = send_telegram(_cmsg, group_corners)" not in source
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


def test_wrong_fixture_day_blocks_before_render():
    cards=Mock()
    tip={"match":"QA HOME vs QA AWAY","oddsYes":2.56,"bookmaker":"Pinnacle",
         "commence_time":"2099-11-25T23:30:00Z"}
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-25") is None
    cards.render_card.assert_not_called()
    cards._send_photo.assert_not_called()
    cards.render_card.return_value=_master_png()
    cards._send_photo.return_value=123
    assert send_regular(cards,"QA","QA","over25",tip,"2099-11-26")==123


def test_builder_pool_keeps_complete_quote_and_club_evidence():
    import ast
    from pathlib import Path
    source = Path("btts_bot.py").read_text()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "_ntr_collect_prop")
    ns = {"_NTR_BUILDER_PROP_POOL": [], "normalize_team_name": lambda x: str(x or "").lower()}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<pool>", "exec"), ns)
    collect = ns["_ntr_collect_prop"]
    evidence = dict(fixture_id="f1", home_id="h1", away_id="a1",
                    player_id="p1", player_team_id="h1", quote_id="q1",
                    quote_observed_at="2099-11-26T18:00:00Z",
                    quote_observed=True, odds_observed=True, price_estimated=False)
    args = ("QA Player", "QA Home", "QA Home vs QA Away", "QA", "Shots 2+")
    collect(*args, category="shots", line=2, odds=1.8, source="Pinnacle",
            kickoff="2099-11-26T19:00:00Z", source_receipt=evidence)
    collect(*args, category="shots", line=2, odds=2.1, source="anonymous")
    row, = ns["_NTR_BUILDER_PROP_POOL"]
    assert row["odds"] == 1.8 and row["source"] == "Pinnacle"
    assert all(row[k] == v for k, v in evidence.items())
    collect("QA Player", "QA Away", "QA Home vs QA Away", "QA", "Shots 2+",
            category="shots", line=2, odds=1.9, source="Pinnacle")
    assert len(ns["_NTR_BUILDER_PROP_POOL"]) == 2
    assert row["team"] == "QA Home"


def test_builder_normalization_prefers_original_receipt(monkeypatch):
    from netrattler_builder_engine import normalize_prop, deduplicate_props
    monkeypatch.setenv("NETRATTLER_BUILDER_STRICT_EDGE", "false")
    base = dict(player="QA Athlete", team="QA Home", match="QA Home vs QA Away",
                market="Shots 2+", category="shots", line=2, odds=1.8,
                source="Pinnacle", probability=0.8)
    verified = dict(base, fixture_id="f1", home_id="h1", away_id="a1",
                    player_id="p1", player_team_id="h1", quote_id="q1",
                    quote_observed_at="2099-11-26T18:00:00Z",
                    commence_time="2099-11-26T19:00:00Z", odds_observed=True)
    leg = normalize_prop(verified)
    assert leg is not None and leg.player_team_id == "h1"
    assert leg.kickoff == verified["commence_time"]
    selected, = deduplicate_props([verified, dict(base, odds=2.1)])
    assert selected.quote_id == "q1" and selected.odds == 1.8


def test_corner_photo_failure_never_sends_legacy_text(monkeypatch):
    import sys
    from types import SimpleNamespace
    source = Path("btts_bot.py").read_text()
    tree = ast.parse(source)
    branches = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "corners_tips and group_corners"]
    assert len(branches) == 1
    block = compile(ast.Module(body=branches, type_ignores=[]), "<corner-transport>", "exec")
    for original_only in ("0", "1"):
        monkeypatch.setenv("NETRATTLER_ORIGINAL_ONLY", original_only)
        for failed in (False, True):
            send = Mock(side_effect=RuntimeError("render failed") if failed else None,
                        return_value=None)
            monkeypatch.setitem(sys.modules, "netrattler_corner_cards",
                                SimpleNamespace(send_corner_card=send))
            tip = {"match": "Watford FC vs Blackburn Rovers FC", "time": "Zeit nicht bestätigt"}
            namespace = dict(corners_tips=[tip], group_corners="QA",
                             TELEGRAM_TOKEN="QA", target_date="2099-11-26",
                             log=Mock(), send_telegram=Mock(), mark_tip_sent=Mock(),
                             format_corners_message=Mock(), save_to_supabase=Mock())
            exec(block, namespace)
            send.assert_called_once()
            for name in ("send_telegram", "mark_tip_sent", "format_corners_message", "save_to_supabase"):
                namespace[name].assert_not_called()
            assert tip["time"] == "Zeit nicht bestätigt"
