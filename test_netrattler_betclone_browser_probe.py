#!/usr/bin/env python3
"""Fail-closed browser probe rules for BetClone operator web pages."""
import unittest
import netrattler_betclone_browser_probe as probe


class BrowserProbeTests(unittest.TestCase):
    def test_curated_unblocked_homepages_only(self):
        self.assertEqual(len(probe.CANDIDATES), 4)
        self.assertEqual(len({brand for _, brand, _ in probe.CANDIDATES}), 4)
        self.assertTrue(all(url.startswith("https://") for _, _, url in probe.CANDIDATES))
        self.assertFalse(any(brand in {"rabona", "efbet", "n1bet", "goldenbet"}
                             for _, brand, _ in probe.CANDIDATES))

    def test_first_party_requests_only(self):
        page = "https://www.vbet.com/"
        self.assertTrue(probe.is_first_party_response(page, "https://www.vbet.com/api/events"))
        self.assertTrue(probe.is_first_party_response(page, "https://api.vbet.com/v1/football"))
        self.assertFalse(probe.is_first_party_response(page, "https://vbet.com.attacker.invalid/api"))
        self.assertFalse(probe.is_first_party_response(page, "https://cdn.example.org/odds"))

    def test_access_denial_remains_denied_even_if_http_200(self):
        self.assertTrue(probe.is_denied(403, ""))
        self.assertTrue(probe.is_denied(200, "Just a moment - verify you are human"))
        self.assertTrue(probe.is_denied(200, "CAPTCHA challenge"))
        self.assertFalse(probe.is_denied(200, "Football odds - Chelsea vs Arsenal"))


if __name__ == "__main__":
    unittest.main()
