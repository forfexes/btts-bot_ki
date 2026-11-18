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
    with patch.object(cards, "_sb", return_value=("https://example.test/netrattler_match_cards",{})), \
         patch.object(cards.requests, "get", return_value=SimpleNamespace(ok=True,json=lambda:sample)), \
         patch.object(cards.requests, "patch", side_effect=lambda *args,**kwargs: patches.append(kwargs["json"]) or SimpleNamespace(ok=True)), \
         patch.object(cards.requests, "post", return_value=SimpleNamespace(ok=True)), \
         patch.object(cards, "_edit_photo", return_value=True) as sent, \
         patch.object(cards, "render_card", return_value=b"rendered_png"), \
         patch.object(cards.time, "sleep", return_value=None):
        assert cards.update_cards_with_results("token",results) == 2
    assert sent.call_count == 2
    assert [p["result"]["marks"]["0"] for p in patches] == ["win","loss"]


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
