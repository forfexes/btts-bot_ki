#!/usr/bin/env python3
"""Pure-logic checks for the Altenar keyless reachability probe (no network)."""
import unittest

import netrattler_altenar_keyless_probe as probe


class AltenarKeylessProbeTests(unittest.TestCase):
    def test_endpoint_is_the_observed_public_widget_host(self):
        self.assertTrue(probe.ENDPOINT.startswith("https://hu-sb2frontend-altenar2.biahosted.com/"))

    def test_params_carry_no_token_or_credential_looking_fields(self):
        for key in probe.PARAMS:
            self.assertNotRegex(key.lower(), r"token|secret|password|auth")

    def test_params_integration_matches_observed_brand(self):
        self.assertEqual(probe.PARAMS["integration"], "vegas.hu")


if __name__ == "__main__":
    unittest.main()
