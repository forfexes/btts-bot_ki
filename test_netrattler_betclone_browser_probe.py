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

    def test_hosted_schema_diagnostics_are_bounded_and_value_free(self):
        payload = {
            "events": [{
                "eventId": "PRIVATE MATCH NAME",
                "markets": [{"marketName": "Sensitive match description",
                             "selections": [{"name": "Confidential Player",
                                             "decimalOdds": 2.25}]}]
            }]
        }
        result = probe.sports_json_shape_signals(payload)
        self.assertGreater(result["events"], 0)
        self.assertGreater(result["markets"], 0)
        self.assertGreater(result["selections"], 0)
        self.assertGreater(result["prices"], 0)
        self.assertNotIn("PRIVATE MATCH NAME", str(result))
        self.assertNotIn("Confidential Player", str(result))

    def test_price_requires_ancestral_event_market_and_selection(self):
        full = {"eventId": 999, "markets": [{
            "marketName": "Anytime scorer",
            "outcomes": [{"label": "Yes", "decimalOdds": 1.9}]
        }]}
        partial = {"marketName": "Unrelated market", "odds": 2.2}
        a = probe.sports_json_shape_signals(full)
        b = probe.sports_json_shape_signals(partial)
        self.assertEqual(a["priced_complete_context"], 1)
        self.assertEqual(a["priced_with_market"], 1)
        self.assertEqual(a["priced_with_event"], 1)
        self.assertEqual(b["priced_with_market"], 1)
        self.assertEqual(b["priced_with_event"], 0)
        self.assertEqual(b["priced_complete_context"], 0)

    def test_numeric_price_eligibility_distinguishes_schema_from_actual_odds(self):
        base = {"events": [{"markets": [{"outcomes": [{"name": "Over",
                 "price": {"value": 1.9}}, {"name": "Under", "price": "1.84"}]}]}]}
        signs = probe.sports_json_shape_signals(base)
        self.assertEqual(signs["prices"], 2)
        self.assertEqual(signs["plausible_decimal_price_fields"], 1)
        self.assertEqual(signs["plausible_decimal_full_context"], 1)
        self.assertEqual(signs["full_context_label_name"], 1)
        self.assertEqual(signs["full_context_price_price"], 1)
        self.assertEqual(signs["full_context_label_outcomename"], 0)
        no = probe.sports_json_shape_signals({"eventId": "x", "market": "win",
                                               "name": "yes", "price": "0.45"})
        self.assertEqual(no["plausible_decimal_price_fields"], 0)
        self.assertEqual(no["priced_complete_context"], 1)
        self.assertEqual(probe.sports_json_shape_signals(
            {"eventId": 1, "market": "goals", "name": "over", "price": True}
        )["plausible_decimal_price_fields"], 0)

    def test_irrelevant_private_json_does_not_create_sportsbook_evidence(self):
        result = probe.sports_json_shape_signals({
            "api_key": "private", "account": {"user_email": "someone@example.test"},
            "tokens": [234.5, 42], "available_balance": 999,
        })
        self.assertTrue(all(value == 0 for value in result.values()))

    def test_unavailable_response_body_is_not_read_as_zero_odds(self):
        class LostBody:
            def json(self):
                raise Exception("Response.json: No resource with given identifier found")
        class PublicOdds:
            def json(self):
                return {"eventId": 5, "market": "Total Goals",
                        "selections": [{"label": "Over", "odds": 1.8}]}
        self.assertIsNone(probe.public_response_price_count(LostBody()))
        self.assertEqual(probe.public_response_price_count(PublicOdds()), 1)

    def test_only_observed_platform_hosted_json_may_be_inspected(self):
        self.assertTrue(probe.is_observed_public_platform_host(
            "inplaynet", "https://sportservice.inplaynet.tech/v1/sports"))
        self.assertTrue(probe.is_observed_public_platform_host(
            "altenar", "https://hu-sb2frontend-altenar2.biahosted.com/public"))
        self.assertFalse(probe.is_observed_public_platform_host(
            "inplaynet", "https://sportservice.inplaynet.tech.evil.invalid/odds"))
        self.assertFalse(probe.is_observed_public_platform_host(
            "altenar", "https://sportservice.inplaynet.tech/odds"))
        self.assertFalse(probe.is_observed_public_platform_host(
            "betby", "https://sportservice.inplaynet.tech/odds"))
        self.assertFalse(probe.is_observed_public_platform_host(
            "inplaynet", "http://sportservice.inplaynet.tech/odds"))

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
