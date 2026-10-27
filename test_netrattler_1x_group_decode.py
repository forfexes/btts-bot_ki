"""Offline regression: V2 player-log 404 must not break the read-only group decoder."""
import requests
from unittest.mock import patch
from netrattler_1x_group_decode import load_player_logs


def test_v2_success_does_not_query_main():
    with patch("netrattler_1x_group_decode.fetch", return_value=[{"player_name": "A"}]) as fetch:
        assert load_player_logs("v2", "v2key", "main", "mainkey", {"select": "player_name"}) == [{"player_name": "A"}]
        fetch.assert_called_once_with("v2", "v2key", "player_game_log", {"select": "player_name"})


def test_v2_404_uses_main():
    response = requests.Response()
    response.status_code = 404
    missing = requests.HTTPError("Not Found", response=response)
    expected = [{"player_name": "B"}]
    with patch("netrattler_1x_group_decode.fetch", side_effect=[missing, expected]) as fetch:
        assert load_player_logs("v2", "v2key", "main", "mainkey", {"select": "player_name"}) == expected
        assert fetch.call_count == 2
        fetch.assert_any_call("main", "mainkey", "player_game_log", {"select": "player_name"})


def test_v2_non_404_is_not_silenced():
    response = requests.Response()
    response.status_code = 401
    with patch("netrattler_1x_group_decode.fetch", side_effect=requests.HTTPError("Unauthorized", response=response)) as fetch:
        try:
            load_player_logs("v2", "v2key", "main", "mainkey", {"select": "player_name"})
        except requests.HTTPError:
            pass
        else:
            raise AssertionError("HTTP 401 must remain a failure")
        fetch.assert_called_once()
