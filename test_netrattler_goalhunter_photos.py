#!/usr/bin/env python3
"""Offline Goal Hunter photo fallback regressions; no live HTTP requests."""
import io
import unittest
from unittest.mock import patch

from PIL import Image
import netrattler_stats_match_cards as cards


def _png_bytes():
    out = io.BytesIO()
    # Production rejects images <80px and grey placeholders; use a coloured gradient.
    im = Image.new("RGB", (120, 120), "#4477bb")
    for x in range(120):
        for y in range(120):
            im.putpixel((x, y), (40 + x, 90 + y // 2, 180 - x // 2))
    im.save(out, format="PNG")
    return out.getvalue()


class FakeResponse:
    def __init__(self, data=None, body=b"", status=200):
        self._data = data or {}
        self.content = body
        self.status_code = status
        self.ok = 200 <= status < 300

    def json(self):
        return self._data


class GoalHunterPhotoTests(unittest.TestCase):
    def setUp(self):
        cards._PLAYER_CACHE.clear()

    def test_fotmob_exact_player_photo_and_team_specific_cache(self):
        pixels = _png_bytes()
        seen = []
        def get(url, **kwargs):
            seen.append(url)
            if "search/suggest" in url:
                return FakeResponse({"players": [
                    {"name": "Joao Felix", "id": 120, "info": "Another Club"},
                    {"name": "Joao Felix", "id": 999, "info": "AC Milan"},
                    {"name": "Joao Felix Jr", "id": 555, "info": "AC Milan"},
                ]})
            if url.endswith("/999.png"):
                return FakeResponse(body=pixels)
            if "thesportsdb" in url:
                return FakeResponse(status=403)
            if "wikipedia.org" in url:
                return FakeResponse({"query": {"pages": {}}})
            return FakeResponse(status=404)
        with patch.object(cards.requests, "get", side_effect=get):
            photo = cards._player_photo("Joao Felix", "AC Milan")
            self.assertEqual(photo, pixels)
            self.assertEqual(cards._player_photo("Joao Felix", "AC Milan"), pixels)
        self.assertEqual(sum("/999.png" in x for x in seen), 1)
        self.assertFalse(any("/120.png" in x for x in seen))

    def test_official_fpl_headshot_requires_matching_team(self):
        pixels = _png_bytes()
        cards._FPL_BOOTSTRAP["loaded"] = False
        cards._FPL_BOOTSTRAP["data"] = {}
        def get(url, **kwargs):
            if "bootstrap-static" in url:
                return FakeResponse({"teams": [{"id": 1, "name": "Arsenal"}],
                                     "elements": [{"first_name": "Bukayo", "second_name": "Saka",
                                                   "team": 1, "photo": "12345.jpg"}]})
            if "p12345.png" in url:
                return FakeResponse(body=pixels)
            return FakeResponse(status=404)
        try:
            with patch.object(cards.requests, "get", side_effect=get):
                self.assertEqual(cards._player_photo("Bukayo Saka", "Arsenal"), pixels)
                self.assertEqual(cards._player_photo("Bukayo Saka", "Chelsea"), b"")
        finally:
            cards._FPL_BOOTSTRAP["loaded"] = False
            cards._FPL_BOOTSTRAP["data"] = {}

    def test_unverified_wrong_player_is_not_pasted(self):
        def get(url, **kwargs):
            if "search/suggest" in url:
                return FakeResponse({"players": [{"name": "Different Player",
                                                  "id": 999, "info": "AC Milan"}]})
            if "thesportsdb" in url:
                return FakeResponse({"player": [{"strPlayer": "John Example",
                    "strSport": "Basketball", "strThumb": "https://bad.invalid/wrong.png"}]})
            if "wikipedia.org" in url:
                return FakeResponse({"query": {"pages": {}}})
            return FakeResponse(status=404)
        with patch.object(cards.requests, "get", side_effect=get) as mocked:
            self.assertEqual(cards._player_photo("John Example", "AC Milan"), b"")
        self.assertFalse(any("bad.invalid" in x.args[0] for x in mocked.call_args_list))

    def test_images_must_be_valid_and_legacy_player_suffix_is_removed(self):
        requested = []
        def get(url, **kwargs):
            requested.append((url, kwargs.get("params")))
            if "search/suggest" in url:
                return FakeResponse({"players": [{"name": "Joao Felix", "id": 999}]})
            if url.endswith("999.png"):
                return FakeResponse(body=b"<html>not an image</html>")
            if "thesportsdb" in url or "wikipedia.org" in url:
                return FakeResponse({"query": {"pages": {}}})
            return FakeResponse(status=404)
        with patch.object(cards.requests, "get", side_effect=get):
            self.assertEqual(cards._player_photo("Joao Felix Player's"), b"")
        self.assertEqual(next(params["term"] for url, params in requested
                              if "search/suggest" in url), "Joao Felix")


if __name__ == "__main__":
    unittest.main()
