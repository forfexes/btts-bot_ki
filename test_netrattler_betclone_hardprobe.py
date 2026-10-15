import unittest
from unittest.mock import patch
from netrattler_betclone_hardprobe import (
    CANDIDATES, PAGES, audit_odds_json, parse_catalogue_html, parse_extended_bookmakers, probe_homepage, valid_decimal
)


class TestHardprobe(unittest.TestCase):
    def test_ten_platform_families(self):
        self.assertEqual(len(PAGES), 10)
        self.assertTrue(all(CANDIDATES.get(p) for p in PAGES))

    def test_parse_first_bookmaker_table_and_deduplicate(self):
        html = "<table><tr><th>Bookmaker</th><th>Bonus</th></tr>" \
               "<tr><td><a href='https://finmart.pro/ref'>Vbet</a></td><td>100</td></tr>" \
               "<tr><td>Vbet</td><td>250</td></tr>" \
               "<tr><td>Efbet</td><td>-</td></tr></table>" \
               "<table><tr><td>Not a bookie</td></tr></table>"
        self.assertEqual(parse_catalogue_html(html), ["Vbet", "Efbet"])

    def test_parse_bookmaker_continuation_tables(self):
        html = "<table><tr><th>Bookmaker</th><th>Bonus</th></tr>" \
               "<tr><td><a href='https://finmart.pro/1'>A</a></td><td>1</td></tr></table>" \
               "<table><tr><td><a href='https://finmart.pro/2'>B</a></td><td>2</td></tr></table>" \
               "<table><tr><td>Advertisement</td></tr></table>"
        self.assertEqual(parse_catalogue_html(html), ["A", "B"])

    def test_historical_appendix_is_separate(self):
        names = ", ".join(["Betx101"] + [f"example{i} sportsbook" for i in range(20)])
        html = "<p>" + names + "</p>"
        self.assertEqual(len(parse_extended_bookmakers(html)), 21)

    def test_no_table_fails_closed(self):
        self.assertEqual(parse_catalogue_html("<h1>blocked</h1>"), [])

    def test_no_false_positives_from_marketing(self):
        self.assertEqual(audit_odds_json({"odds": 2.00, "name": "Best odds"}), {})

    def test_accept_structured_event_and_market(self):
        payload = {"eventId": "100", "markets": [{"marketName": "Both Teams to Score",
                    "selections": [{"name": "Yes", "odds": 1.88}]}]}
        self.assertEqual(audit_odds_json(payload).get("verified_prices"), 1)

    def test_reject_invalid_odds(self):
        self.assertFalse(valid_decimal("1.0"))
        self.assertFalse(valid_decimal(True))
        self.assertFalse(valid_decimal("not a number"))

    @patch("netrattler_betclone_hardprobe.fetch_public")
    def test_http_200_html_is_not_a_usable_feed(self, fetch):
        fetch.return_value = (200, "https://vbet.com/", "text/html", "<h1>Odds 1.88</h1>", 22)
        result = probe_homepage("betconstruct", "vbet", "https://vbet.com/")
        self.assertEqual(result["state"], "html_no_verified_odds")
        self.assertEqual(result["verified_odds"], 0)

    @patch("netrattler_betclone_hardprobe.fetch_public")
    def test_http_403_is_blocked(self, fetch):
        fetch.return_value = (403, "https://site.example/", "text/html", "Access denied", 15)
        self.assertEqual(probe_homepage("test", "brand", "https://site.example/")["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
