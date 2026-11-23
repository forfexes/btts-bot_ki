"""Source-specific player image IDs must never mix ESPN and API-Football."""
from unittest.mock import patch
from types import SimpleNamespace

import netrattler_espn_photo as e


def test_unique_id_includes_valid_short_api_football_ids():
    assert e.unique_id([{"player_id": "324164"}, {"player_id": "324164"}]) == "324164"
    assert e.unique_id([{"player_id": "324164"}, {"player_id": "580"}]) == ""
    assert e.unique_id([{"player_id": "502"}, {"player_id": "502"}]) == "502"
    assert e.unique_id([{"player_id": "0"}, {"player_id": None}]) == ""
    assert e.unique_id([{"player_id": "111111"}, {"player_id": "222222"}]) == ""
    assert e.unique_id([]) == ""


def test_single_word_name_skipped():
    assert e.espn_photo("Neymar") == ""


def test_lookup_filters_source_namespace_and_preserves_valid_id():
    e._CACHE.clear()
    response = SimpleNamespace(ok=True, json=lambda: [
        {"player_id": "502", "source": "apif+history"}])
    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co",
                                  "SUPABASE_KEY": "dummy_key"}, clear=False):
        with patch.object(e.requests, "get", return_value=response) as mocked:
            url = e.espn_photo("Joshua Kimmich")
    assert url == "https://media.api-sports.io/football/players/502.png"
    params = mocked.call_args.kwargs["params"]
    assert params["source"] == "like.apif*"
    assert "source" in params["select"]
    e._CACHE.clear()


def test_ambiguous_api_football_ids_fail_closed():
    e._CACHE.clear()
    response = SimpleNamespace(ok=True, json=lambda: [
        {"player_id": "502", "source": "apif"},
        {"player_id": "503", "source": "apif"}])
    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co",
                                  "SUPABASE_KEY": "dummy_key"}, clear=False):
        with patch.object(e.requests, "get", return_value=response):
            assert e.espn_photo("Joshua Kimmich") == ""
    e._CACHE.clear()
