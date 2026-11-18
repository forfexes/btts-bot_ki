"""Offline licensing/identity regression for Commons photo fallback."""
import unittest
from unittest.mock import patch
import netrattler_commons_photos as commons


class CommonsPhotoTests(unittest.TestCase):
    def setUp(self):
        commons.CACHE.clear()
        commons._REQUESTS = 0

    def test_only_exact_identity_and_public_domain_or_cc0(self):
        base = {"thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Lionel_Messi.jpg/450px-Lionel_Messi.jpg"}
        self.assertTrue(commons.is_usable("File:Lionel Messi training.jpg",
            {**base, "extmetadata": {"LicenseShortName": {"value": "CC0"}}}, "Lionel Messi"))
        self.assertFalse(commons.is_usable("File:Cristiano Ronaldo.jpg",
            {**base, "extmetadata": {"LicenseShortName": {"value": "CC0"}}}, "Lionel Messi"))
        self.assertFalse(commons.is_usable("File:Lionel Messi.jpg",
            {**base, "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}, "Lionel Messi"))
        self.assertFalse(commons.is_usable("File:Lionel Messi.jpg",
            {**base, "extmetadata": {"LicenseShortName": {"value": "CC0"}}} | {"thumburl": "https://bad.invalid/x.jpg"}, "Lionel Messi"))

    def test_unknown_player_never_uses_another_players_category(self):
        with patch.object(commons.requests, "get") as get:
            self.assertEqual(commons.commons_photo("Random Player"), "")
            get.assert_not_called()

    def test_unique_verified_file_is_returned_and_cached(self):
        item = {"title": "File:Lionel Messi football.jpg", "imageinfo": [{
            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/b/Messi.jpg/450px-Messi.jpg",
            "extmetadata": {"LicenseShortName": {"value": "Public Domain"}}}]}
        class Response:
            ok = True
            def json(self):
                return {"query": {"pages": [item]}}
        with patch.object(commons.requests, "get", return_value=Response()) as get:
            self.assertTrue(commons.commons_photo("Lionel Messi").startswith("https://upload.wikimedia.org"))
            self.assertEqual(commons.commons_photo("Lionel Messi"), commons.CACHE["lionel messi"])
            get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
