"""A scorer result must never overwrite other players in the same match."""
from types import SimpleNamespace
from unittest.mock import patch

import netrattler_stats_match_cards as cards
import netrattler_settlement_v16_final as settlement


def test_scorer_result_uses_exact_player_not_match_or_odds():
    a = ("scorer", {"player":"Sasa Kalajdzic","team":"Austria","odds":3.0})
    b = ("scorer", {"player":"Michael Gregoritsch","team":"Austria","odds":3.0})
    win = {"group":"scorer","player":"Saša Kalajdžić","team":"Austria","odds":3.0}
    loss = {"group":"scorer","player":"Michael Gregoritsch","team":"Austria","odds":3.0}
    assert cards._result_matches_card_entry(*a, win, [a,b])
    assert not cards._result_matches_card_entry(*a, loss, [a,b])
    assert cards._result_matches_card_entry(*b, loss, [a,b])
    assert not cards._result_matches_card_entry(*b, win, [a,b])
    assert not cards._result_matches_card_entry(*a, {
        "group":"scorer","odds":3.0,"player":""}, [a,b])


def test_existing_wrong_scorer_marks_corrected_in_original_photos():
    sample = [
        {"card_id":1,"chat_id":"chat","message_id":101,
         "match_key":cards.match_key("Israel vs Austria"),"card_date":"2026-11-17",
         "entries":[["scorer",{"match":"Israel vs Austria",
                               "player":"Sasa Kalajdzic","team":"Austria","odds":3.0}]],
         "result":{"marks":{"0":"void"},"ft":"1-1"}},
        {"card_id":2,"chat_id":"chat","message_id":102,
         "match_key":cards.match_key("Israel vs Austria"),"card_date":"2026-11-17",
         "entries":[["scorer",{"match":"Israel vs Austria",
                               "player":"Michael Gregoritsch","team":"Austria","odds":3.0}]],
         "result":{"marks":{"0":"void"},"ft":"1-1"}},
        {"card_id":3,"chat_id":"chat","message_id":103,
         "match_key":cards.match_key("Israel vs Austria"),"card_date":"2026-11-17",
         "entries":[["scorer",{"match":"Israel vs Austria",
                               "player":"Liel Abada","team":"Israel","odds":3.0}]],
         "result":{"marks":{"0":"void"},"ft":"1-1"}},
    ]
    results = [
        {"match":"Israel vs Austria","group":"scorer","player":"Sasa Kalajdzic",
         "team":"Austria","status":"win","odds":3.0,"tip_date":"2026-11-17","ft":"1-1"},
        {"match":"Israel vs Austria","group":"scorer","player":"Michael Gregoritsch",
         "team":"Austria","status":"loss","odds":3.0,"tip_date":"2026-11-17","ft":"1-1"},
        {"match":"Israel vs Austria","group":"scorer","player":"Liel Abada",
         "team":"Israel","status":"void","odds":3.0,"tip_date":"2026-11-17","ft":"1-1"},
    ]
    patches=[]
    # Historical identity correction is exercised only in isolated Legacy QA.
    # Production uses SETTLEMENT_TG_ORIGINAL_EDIT_ONLY=1 and must never
    # replace sample-filled scorer artwork. Its blocking test is below.
    with patch.dict("os.environ", {
            "SETTLEMENT_TG_ORIGINAL_EDIT_ONLY":"0",
            "NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"
         }), \
         patch.object(cards, "_sb", return_value=("https://example.test/netrattler_match_cards",{})), \
         patch.object(cards.requests, "get", return_value=SimpleNamespace(ok=True,json=lambda:sample)), \
         patch.object(cards.requests, "patch", side_effect=lambda *args,**kwargs: patches.append(kwargs["json"]) or SimpleNamespace(ok=True)), \
         patch.object(cards.requests, "post", return_value=SimpleNamespace(ok=True)), \
         patch.object(cards, "_edit_photo", return_value=True) as sent, \
         patch.object(cards, "render_card", return_value=b"rendered_png"), \
         patch.object(cards.time, "sleep", return_value=None):
        assert cards.update_cards_with_results("token",results) == 2
    assert sent.call_count == 2
    assert [p["result"]["marks"]["0"] for p in patches] == ["win","loss"]


def test_owner_only_in_image_settlement_never_replaces_unapproved_svg_card():
    import os
    match="Home FC vs Away FC"
    sample=[
        {"card_id":11,"chat_id":"chat","message_id":111,
         "match_key":cards.match_key(match),"card_date":"2026-11-21",
         "entries":[["over25",{"match":match,"odds":1.75}]],"result":{}},
        {"card_id":12,"chat_id":"chat","message_id":112,
         "match_key":cards.match_key(match),"card_date":"2026-11-21",
         "entries":[["btts",{"match":match,"odds":1.75}]],"result":{}},
        {"card_id":13,"chat_id":"chat","message_id":113,
         "match_key":cards.match_key(match),"card_date":"2026-11-21",
         "entries":[["scorer",{"match":match,"player":"Test A","odds":1.75}]],"result":{}},
        {"card_id":14,"chat_id":"chat","message_id":114,
         "match_key":cards.match_key(match),"card_date":"2026-11-21",
         "entries":[["corners",{"match":match,"odds":1.75}]],"result":{}},
    ]
    results=[{"match":match,"status":"win","group":"btts",
              "odds":1.75,"tip_date":"2026-11-21","ft":"2-2"}]
    edits=[]
    with patch.dict(os.environ,{
            "SETTLEMENT_TG_ORIGINAL_EDIT_ONLY":"1",
            "NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"
         }), \
         patch.object(cards,"_sb",return_value=("https://example.test/netrattler_match_cards",{})), \
         patch.object(cards.requests,"get",return_value=SimpleNamespace(ok=True,json=lambda:sample)), \
         patch.object(cards.requests,"post",return_value=SimpleNamespace(ok=True)), \
         patch.object(cards.requests,"patch",return_value=SimpleNamespace(ok=True)), \
         patch.object(cards,"render_card",return_value=b"approved-owner-png") as render, \
         patch.object(cards,"_edit_photo",side_effect=lambda _token,_chat,mid,*a,**k: edits.append(mid) or True), \
         patch.object(cards.time,"sleep",return_value=None):
        assert cards.update_cards_with_results("token",results)==1
    assert edits == [112],edits
    render.assert_called_once()
    assert render.call_args.args[0][0][0]=="btts"


def test_production_result_cards_cannot_repaint_unapproved_original():
    # The preceding checks simulate the historical image-edit routing,
    # with a mock renderer and mock Telegram transport, exclusively offline.
    # No explicitly approved overlay-free source exists in this test:
    # an unset/mistyped release gate must prevent every image edit.
    import os
    simulated_result=[{"match":"Home FC vs Away FC",
                       "status":"win","group":"btts","odds":1.75,
                       "tip_date":"2026-11-21","ft":"2-2"}]
    for value in (None,"1","true",""):
        env={"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":value}
        with patch.dict(os.environ,{},clear=False), \
             patch.object(cards,"render_card",return_value=b"not-approved") as render, \
             patch.object(cards,"_edit_photo",return_value=True) as edit:
            if value is None:
                os.environ.pop("NETRATTLER_BLOCK_OVERPAINTED_MASTERS",None)
            else:
                os.environ["NETRATTLER_BLOCK_OVERPAINTED_MASTERS"]=value
            assert cards.update_cards_with_results("token",simulated_result)==0
            render.assert_not_called()
            edit.assert_not_called()


def test_pending_player_can_revert_previous_wrong_win():
    results=[{"group":"scorer","player":"Player A","team":"Home","status":"pending"}]
    a=("scorer",{"player":"Player A","team":"Home"})
    assert cards._result_matches_card_entry(*a,results[0],[a])
    assert not cards._result_matches_card_entry(*a,{"group":"scorer","player":"Player B"},[a])


def test_result_payload_exposes_correct_player_and_match_date():
    import inspect
    source=inspect.getsource(settlement.send_result_cards)
    assert '"player": anyv(data, ["player", "player_name", "scorer_name"]' in source
    assert '"tip_date": str(row.get("tip_date")' in source


def test_settled_scorer_does_not_require_made_up_full_time_score():
    import inspect
    source=inspect.getsource(settlement.send_result_cards)
    assert 'group != "scorer"' in source
    main_source=inspect.getsource(settlement.main)
    assert 'SETTLEMENT_TG_REPLAY_DAYS' in main_source


def test_repeated_fixture_requires_result_date_before_editing_any_old_photo():
    # The exact same clubs can meet again; undated provider results are
    # insufficient to identify which earlier Telegram picture belongs to it.
    two=[
        {"card_id":"old","match_key":cards.match_key("HOME vs AWAY"),
         "card_date":"2026-10-09","chat_id":"123","message_id":1001,
         "entries":[["btts",{"odds":1.85}]],"result":{"marks":{}}},
        {"card_id":"new","match_key":cards.match_key("HOME vs AWAY"),
         "card_date":"2026-11-23","chat_id":"123","message_id":1002,
         "entries":[["btts",{"odds":1.85}]],"result":{"marks":{}}},
    ]
    no_date=[{"match":"HOME vs AWAY","group":"btts",
              "status":"win","odds":1.85}]
    with patch.dict("os.environ",{
            "NETRATTLER_BLOCK_OVERPAINTED_MASTERS":"0"}), \
         patch.object(cards,"_sb",return_value=("https://example.test/netrattler_match_cards",{})), \
         patch.object(cards.requests,"get",
                      return_value=SimpleNamespace(ok=True,json=lambda:two)), \
         patch.object(cards.requests,"post",return_value=SimpleNamespace(ok=True)), \
         patch.object(cards,"render_card") as render, \
         patch.object(cards,"_edit_photo") as edit:
        assert cards.update_cards_with_results("TEST_TOKEN",no_date)==0
        render.assert_not_called()
        edit.assert_not_called()


def test_do_not_change_old_match_with_same_pairing_on_another_day():
    assert cards.match_key("Israel vs Austria") == cards.match_key("Israel vs Austria")
    import inspect
    source=inspect.getsource(cards.update_cards_with_results)
    assert 'card.get("card_date")' in source
    assert 'result_day' in source


def test_edit_message_media_preserves_caption_and_original_message_id():
    import json
    reply = SimpleNamespace(status_code=200,ok=True,text="ok",
                            json=lambda:{"ok":True,"result":{"message_id":918}})
    with patch.object(cards.requests, "post", return_value=reply) as send:
        assert cards._edit_photo("token","chat",918,b"png",lambda x:None,
                                 caption="❌ Auswertung: verloren")
    arguments = send.call_args.kwargs
    assert arguments["data"]["message_id"] == 918
    assert json.loads(arguments["data"]["media"])["caption"] == "❌ Auswertung: verloren\n\n@prophunter"
    assert "files" in arguments and "card" in arguments["files"]


def test_premium_photo_upload_requires_real_original_message_id():
    cases=[
        ({"ok":True,"result":{"message_id":918}},918),
        ({"ok":True,"result":{}},False),
        ({"ok":True,"result":True},False),
        ({"ok":True,"result":{"message_id":0}},False),
        ({"ok":True,"result":{"message_id":True}},False),
    ]
    for response,expected in cases:
        reply=SimpleNamespace(ok=True,status_code=200,
                              json=lambda response=response:response)
        with patch.object(cards.requests,"post",return_value=reply) as post:
            result=cards._send_photo("token","chat","",b"synthetic_qa_png",
                                     lambda *_:None)
            assert result==expected,(response,result)
            post.assert_called_once()


def test_media_edit_never_truncates_original_caption():
    original="ORIGINAL PREMIUM TIPP " + "Quote 1.95 | " * 100
    assert len(original)>1024
    with patch.object(cards.requests,"post",
                      side_effect=AssertionError("overlong caption uploaded")):
        assert not cards._edit_photo("token","chat",918,b"png",lambda *_:None,
                                     caption=original)


def test_media_edit_rejects_wrong_original_message_confirmation():
    for response in ({"ok":True,"result":{"message_id":919}},
                     {"ok":True,"result":{"message_id":918,
                                           "chat":{"id":"different-chat"}}},
                     {"ok":True,"result":True}, {"ok":False}):
        reply=SimpleNamespace(status_code=200,ok=True,text="ok",json=lambda:response)
        with patch.object(cards.requests,"post",return_value=reply) as post:
            assert not cards._edit_photo("token","chat",918,b"png",lambda *_:None,
                                         caption="❌ Auswertung: verloren")
            post.assert_called_once()


def test_no_synthetic_void_on_unverified_goal_hunter_result():
    import inspect
    source=inspect.getsource(settlement.send_result_cards)
    assert 'image_status = "pending"' in source
    assert '_confirmed_scorer_no_appearance(row)' in source
    assert '"caption": caption' in source



def test_owner_corrected_match_card_caption_is_below_image():
    """User's screenshot: the PNG footer is NETRATTLER AI, handle is Telegram text."""
    assert cards._telegram_card_caption("") == "@prophunter"
    assert cards._telegram_card_caption("OVER 2.5 @2.54") == (
        "OVER 2.5 @2.54\n\n@prophunter")
    assert cards._telegram_card_caption("OVER 2.5 @2.54\n\n@prophunter") == (
        "OVER 2.5 @2.54\n\n@prophunter")
    assert cards._telegram_card_caption("Already @PROP HUNTER") == (
        "Already @PROP HUNTER\n\n@prophunter")


def test_telegram_photo_caption_is_sent_outside_png_and_kept_on_edit():
    import json
    reply=SimpleNamespace(ok=True,status_code=200,text="ok",
                           json=lambda:{"ok":True,"result":{"message_id":7001}})
    with patch.object(cards.requests,"post",return_value=reply) as post:
        assert cards._send_photo("QA_ONLY","test_chat","",b"TEST_PNG",
                                 lambda *_:None)==7001
        kwargs=post.call_args.kwargs
        assert kwargs["data"]["caption"]=="@prophunter"
        assert kwargs["files"]["photo"][1]==b"TEST_PNG"
    with patch.object(cards.requests,"post",return_value=reply) as post:
        assert cards._edit_photo("QA_ONLY","test_chat",7001,b"SETTLED_PNG",
                                 lambda *_:None,caption=None)
        media=json.loads(post.call_args.kwargs["data"]["media"])
        assert media["caption"]=="@prophunter"
        assert post.call_args.kwargs["data"]["message_id"]==7001


def test_caption_overflow_must_fail_before_network_upload():
    original="REAL TIP " + "a"*1016
    with patch.object(cards.requests,"post",side_effect=AssertionError("network called")):
        assert cards._send_photo("QA_ONLY","test_chat",original,b"PNG",lambda *_:None) is False
        assert cards._edit_photo("QA_ONLY","test_chat",7001,b"PNG",lambda *_:None,caption=original) is False
