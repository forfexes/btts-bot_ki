#!/usr/bin/env python3
"""Fail-closed browser probe rules for BetClone operator web pages."""
import unittest
import netrattler_betclone_browser_probe as probe


class BrowserProbeTests(unittest.TestCase):
    def test_curated_unblocked_homepages_only(self):
        self.assertEqual(len(probe.CANDIDATES), 14)
        self.assertEqual(len({brand for _, brand, _ in probe.CANDIDATES}), len(probe.CANDIDATES))
        self.assertEqual({family for family, _, _ in probe.CANDIDATES},
                         {"altenar", "betby", "betconstruct", "first", "igate", "inplaynet", "softswiss"})
        self.assertTrue(all(url.startswith("https://") for _, _, url in probe.CANDIDATES))
        self.assertIn(("igate", "spinlynx", "https://spinlynx.com/"), probe.CANDIDATES)
        self.assertIn(("altenar", "vegas.hu", "https://vegas.hu/"), probe.CANDIDATES)
        self.assertFalse(any(brand in {"rabona", "efbet", "n1bet", "goldenbet"}
                             for _, brand, _ in probe.CANDIDATES))

    def test_cross_origin_diagnostics_strip_private_url_components(self):
        self.assertEqual(
            probe.public_response_host_only("https://user:secret@api.example.com/v1/odds?token=private"),
            "api.example.com",
        )
        self.assertIsNone(probe.public_response_host_only("javascript:alert(1)"))
        self.assertIsNone(probe.public_response_host_only("http://api.example.com/odds"))

    def test_first_party_requests_only(self):
        page = "https://www.vbet.com/"
        self.assertTrue(probe.is_first_party_response(page, "https://www.vbet.com/api/events"))
        self.assertTrue(probe.is_first_party_response(page, "https://api.vbet.com/v1/football"))
        self.assertFalse(probe.is_first_party_response(page, "https://vbet.com.attacker.invalid/api"))
        self.assertFalse(probe.is_first_party_response(page, "https://cdn.example.org/odds"))

    def test_public_redirected_origin_not_unrelated_json_hosts(self):
        redirected_page = "https://spinlynx36.com/"
        self.assertTrue(probe.is_first_party_response(redirected_page, "https://api.spinlynx36.com/football"))
        self.assertFalse(probe.is_first_party_response(redirected_page, "https://spinlynx36.com.fake.example/api"))
        self.assertEqual(probe.first_party_sports_link(redirected_page, ["/sports?session=private"]),
                         "https://spinlynx36.com/sports")

    def test_only_existing_public_first_party_sports_links_are_followed(self):
        page = "https://www.tonybet.com/"
        hrefs = ["https://other.example/sports", "javascript:alert(1)",
                 "/casino", "https://tonybet.com/sport/live?token=secret#abc"]
        self.assertEqual(probe.first_party_sports_link(page, hrefs),
                         "https://tonybet.com/sport/live")
        self.assertIsNone(probe.first_party_sports_link(page, ["/casino", "/login"]))
        self.assertIsNone(probe.first_party_sports_link(
            page, ["https://tonybet.com.attacker.invalid/sports"]))

    def test_access_denial_remains_denied_even_if_http_200(self):
        self.assertTrue(probe.is_denied(403, ""))
        self.assertTrue(probe.is_denied(200, "Just a moment - verify you are human"))
        self.assertTrue(probe.is_denied(200, "CAPTCHA challenge"))
        self.assertFalse(probe.is_denied(200, "Football odds - Chelsea vs Arsenal"))


if __name__ == "__main__":
    unittest.main()
