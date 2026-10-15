import unittest
from unittest.mock import Mock, patch
from netrattler_betclone_probe import count_structured_odds, probe_one


class TestBetcloneProbe(unittest.TestCase):
    def test_valid_market_payload(self):
        self.assertEqual(count_structured_odds({"markets": [{"outcomes": [{"name": "BTTS Yes", "odds": 1.88}]}]}), 1)

    def test_unrelated_numbers_do_not_count(self):
        self.assertEqual(count_structured_odds({"events": [{"id": 123, "start": 2026}]}), 0)

    @patch("netrattler_betclone_probe.requests.get")
    def test_html_is_not_verified_feed(self, get):
        get.return_value = Mock(status_code=200, content=b"<html>odds 1.90</html>",
            text="<html>odds 1.90</html>", headers={"Content-Type": "text/html"}, url="https://example.com/")
        self.assertEqual(probe_one("example", "example", "https://example.com/")["odds_rows"], 0)

    @patch("netrattler_betclone_probe.requests.get")
    def test_blocked_site(self, get):
        get.return_value = Mock(status_code=403, content=b"access denied",
            text="access denied", headers={"Content-Type": "text/html"}, url="https://example.com/")
        self.assertEqual(probe_one("example", "example", "https://example.com/")["status"], "blocked_or_restricted")


if __name__ == "__main__":
    unittest.main()
