"""Offline tests for the BetClone deep probe (no internet)."""
import http.server
import json
import os
import threading
import unittest

import netrattler_betclone_deep_probe as dp


class Pure(unittest.TestCase):
    def test_path_template_drops_query_and_ids(self):
        h, p = dp.path_template("https://api-h-c7818b61-608.sptpub.com/api/v2/prematch/brand/2103509236163162112/en/1729480000?token=SECRET")
        self.assertEqual(h, "api-h-c7818b61-608.sptpub.com")
        self.assertEqual(p, "/api/v2/prematch/brand/{n}/en/{n}")
        self.assertNotIn("SECRET", p)

    def test_price_signals_altenar_like(self):
        payload = {"events": [{"id": 1, "name": "A vs B"}],
                   "odds": [{"id": 11, "typeId": 1, "price": 1.85, "oddStatus": 0},
                            {"id": 12, "typeId": 2, "price": 3.4, "oddStatus": 0}]}
        s = dp.price_signals(payload)
        self.assertEqual(s["priced"], 2)
        self.assertIn(s["sample"]["price"], {"1.85", "3.4"})

    def test_ids_and_years_are_not_prices(self):
        self.assertEqual(dp.price_signals({"events": [{"id": 123456, "start": 2026, "value": 2}]})["priced"], 0)

    def test_sample_never_contains_secret_keys(self):
        s = dp.safe_sample({"id": 1, "price": 1.9, "sessionToken": "x", "userId": 5, "authHeader": "y"})
        self.assertEqual(set(s), {"id", "price"})

    def test_targets_skip_integrated_1xbet(self):
        fams = {f for f, _, _ in dp.targets()}
        self.assertNotIn("1xbet", fams)
        self.assertIn("betby", fams)
        self.assertTrue(all(f == "betby" for f, _, _ in dp.targets("betby")))

    def test_decimal_paths_find_any_price_key_name(self):
        payload = [{"IdPartido": 7, "Mercados": [{"Id": 1, "Cotizacion": "1.85"}, {"Id": 2, "Cotizacion": 2.4}],
                    "Year": 2026, "Count": 3}]
        self.assertEqual(dp.decimal_key_paths(payload), {"[].Mercados[].Cotizacion": 2})

    def test_skeleton_is_small_and_secret_free(self):
        sk = dp.skeleton({"data": [{"a": 1, "odds": [{"k": "1.9"}]}], "sessionToken": "x"})
        self.assertNotIn("sessionToken", sk)
        self.assertEqual(sk["data"][1], "<1>")

    def test_denial(self):
        self.assertTrue(dp.is_denied(403, ""))
        self.assertTrue(dp.is_denied(200, "Just a moment... checking your browser"))
        self.assertFalse(dp.is_denied(200, "Football · Premier League"))


PAGE = b"""<html><body><a href='/sports'>Sports</a><a href='/promo/bonus'>Bonus</a></body></html>"""
SPORTS = b"""<html><body><button>Football</button><div id=o></div>
<script>setTimeout(function(){fetch('/api/v1/prematch/42?lang=en').then(r=>r.json()).then(j=>{document.getElementById('o').textContent=j.events.length})},300)</script>
</body></html>"""
ODDS = json.dumps({"events": [{"id": 42, "name": "A vs B", "markets": [{"id": 1, "name": "1X2", "outcomes": [
    {"id": 1, "name": "1", "odds": 1.9}, {"id": 2, "name": "X", "odds": 3.3}, {"id": 3, "name": "2", "odds": 4.2}]}]}]}).encode()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/v1/prematch/"):
            body, ctype = ODDS, "application/json"
        elif self.path.startswith("/sports"):
            body, ctype = SPORTS, "text/html"
        else:
            body, ctype = PAGE, "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS", "1") == "1", "browser tests disabled")
class Browser(unittest.TestCase):
    def test_follows_sports_link_and_records_priced_endpoint(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("playwright missing")
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        try:
            with sync_playwright() as pw:
                b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    # plain-http local page: the https link filter falls back to the public /sports path
                    row = dp.probe_brand(b, "test", "local", url, settle_s=1.0)
                finally:
                    b.close()
        finally:
            srv.shutdown()
        self.assertEqual(row["status"], "rendered")
        self.assertEqual(row["sports_path"], "/sports")
        best = row["endpoints"][0]
        self.assertEqual(best["path"], "/api/v1/prematch/{n}")
        self.assertEqual(best["max_priced"], 3)
        self.assertTrue(row.get("football_clicked"))


if __name__ == "__main__":
    unittest.main()
