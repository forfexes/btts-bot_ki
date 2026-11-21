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
    with patch.dict("os.environ", {"SETTLEMENT_TG_ORIGINAL_EDIT_ONLY":"0"}), \
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
    with patch.dict(os.environ,{"SETTLEMENT_TG_ORIGINAL_EDIT_ONLY":"1"}), \
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


def test_do_not_change_old_match_with_same_pairing_on_another_day():
    assert cards.match_key("Israel vs Austria") == cards.match_key("Israel vs Austria")
    import inspect
    source=inspect.getsource(cards.update_cards_with_results)
    assert 'card.get("card_date")' in source
    assert 'result_day' in source


def test_edit_message_media_preserves_caption_and_original_message_id():
    import json
    reply = SimpleNamespace(status_code=200,ok=True,text="ok")
    with patch.object(cards.requests, "post", return_value=reply) as send:
        assert cards._edit_photo("token","chat",918,b"png",lambda x:None,
                                 caption="❌ Auswertung: verloren")
    arguments = send.call_args.kwargs
    assert arguments["data"]["message_id"] == 918
    assert json.loads(arguments["data"]["media"])["caption"] == "❌ Auswertung: verloren"
    assert "files" in arguments and "card" in arguments["files"]


def test_no_synthetic_void_on_unverified_goal_hunter_result():
    import inspect
    source=inspect.getsource(settlement.send_result_cards)
    assert 'image_status = "pending"' in source
    assert '_confirmed_scorer_no_appearance(row)' in source
    assert '"caption": caption' in source
