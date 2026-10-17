#!/usr/bin/env python3
"""Regression for the Altenar widget parser (pure logic, no network).

Shapes mirror what netrattler_altenar_schema_probe.py actually observed on
the public Vegas.hu/biahosted.com GetTopEvents endpoint (2026-10-16).
"""
import unittest

import netrattler_keyless_odds as k


def _payload(**overrides):
    base = {
        "sports": [{"id": 66, "name": "Labdarugas", "iconName": "soccer"},
                   {"id": 67, "name": "Kosarlabda", "iconName": "basketball"}],
        "champs": [{"id": 3062, "name": "OTP Bank Liga"}],
        "competitors": [{"id": 47889, "name": "MTK Budapest"},
                        {"id": 47892, "name": "Vasas FC"}],
        "markets": [{"id": 1781359938, "name": "1X2 - Odds+", "headerName": "1X2",
                     "typeId": 1, "oddIds": [1, 2, 3]}],
        "odds": [
            {"id": 1, "competitorId": 47889, "name": "MTK Budapest", "price": 1.85,
             "typeId": 1, "oddStatus": 0},
            {"id": 2, "name": "Dontetlen", "price": 3.40, "typeId": 2, "oddStatus": 0},
            {"id": 3, "competitorId": 47892, "name": "Vasas FC", "price": 4.20,
             "typeId": 3, "oddStatus": 0},
        ],
        "events": [{
            "id": 17668679, "name": "MTK Budapest vs. Vasas FC", "sportId": 66,
            "champId": 3062, "status": 0, "startDate": "2026-10-20T18:00:00Z",
            "marketIds": [1781359938], "competitorIds": [47889, 47892],
        }],
    }
    base.update(overrides)
    return base


class AltenarRowsTests(unittest.TestCase):
    def test_complete_1x2_market_produces_three_rows(self):
        rows = k._altenar_rows(_payload(), bookmaker="altenar_vegas.hu")
        self.assertEqual(len(rows), 3)
        by_sel = {r["selection"]: r for r in rows}
        self.assertEqual(set(by_sel), {"home", "draw", "away"})
        self.assertEqual(by_sel["home"]["home_team"], "MTK Budapest")
        self.assertEqual(by_sel["home"]["away_team"], "Vasas FC")
        self.assertEqual(by_sel["home"]["odds"], 1.85)
        self.assertEqual(by_sel["draw"]["odds"], 3.4)
        self.assertEqual(by_sel["away"]["odds"], 4.2)
        for row in rows:
            self.assertEqual(row["source"], "altenar_platform")
            self.assertEqual(row["market"], "1x2")

    def test_non_football_sport_is_skipped(self):
        payload = _payload()
        payload["events"][0]["sportId"] = 67  # basketball
        self.assertEqual(k._altenar_rows(payload, bookmaker="altenar_vegas.hu"), [])

    def test_incomplete_market_missing_draw_is_rejected(self):
        payload = _payload()
        payload["odds"] = [o for o in payload["odds"] if o["typeId"] != 2]
        self.assertEqual(k._altenar_rows(payload, bookmaker="altenar_vegas.hu"), [])

    def test_suspended_odd_status_is_excluded(self):
        payload = _payload()
        payload["odds"][1]["oddStatus"] = 1  # suspended draw price
        self.assertEqual(k._altenar_rows(payload, bookmaker="altenar_vegas.hu"), [])

    def test_non_1x2_market_header_is_ignored(self):
        payload = _payload()
        payload["markets"][0]["headerName"] = "Over/Under 2.5"
        self.assertEqual(k._altenar_rows(payload, bookmaker="altenar_vegas.hu"), [])

    def test_non_scheduled_event_status_is_skipped(self):
        payload = _payload()
        payload["events"][0]["status"] = 3  # e.g. suspended/cancelled
        self.assertEqual(k._altenar_rows(payload, bookmaker="altenar_vegas.hu"), [])

    def test_falls_back_to_splitting_event_name_without_competitor_ids(self):
        payload = _payload()
        payload["events"][0]["competitorIds"] = []
        rows = k._altenar_rows(payload, bookmaker="altenar_vegas.hu")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["home_team"], "MTK Budapest")
        self.assertEqual(rows[0]["away_team"], "Vasas FC")

    def test_malformed_payload_returns_no_rows(self):
        self.assertEqual(k._altenar_rows(None, bookmaker="x"), [])
        self.assertEqual(k._altenar_rows({}, bookmaker="x"), [])

    def test_altenar_platform_is_registered_in_collectors(self):
        names = dict(k.COLLECTORS)
        self.assertIn("altenar_platform", names)



def _events_payload():
    """Shape of the public GetEvents listing (no headerName, typeId-coded)."""
    return {
        "sports": [{"id": 66, "iconName": "soccer"}],
        "champs": [{"id": 3062, "name": "OTP Bank Liga"}],
        "competitors": [{"id": 1, "name": "Nyiregyhaza"}, {"id": 2, "name": "Honved"}],
        "markets": [
            {"id": 10, "name": "1X2", "typeId": 1, "oddIds": [101, 102, 103]},
            {"id": 11, "name": "Golok szama", "typeId": 18, "sv": "2.5", "oddIds": [111, 112]},
            {"id": 12, "name": "Golok szama", "typeId": 18, "sv": "3.5", "oddIds": [121, 122]},
            {"id": 13, "name": "Mindket csapat", "typeId": 29, "oddIds": [131, 132]},
            {"id": 14, "name": "1X2 - Odds+", "typeId": 20135, "oddIds": [141, 142, 143]},
            {"id": 15, "name": "Ketesely", "typeId": 10, "oddIds": [151, 152, 153]},
        ],
        "odds": [
            {"id": 101, "typeId": 1, "price": 2.05, "oddStatus": 0},
            {"id": 102, "typeId": 2, "price": 3.6, "oddStatus": 0},
            {"id": 103, "typeId": 3, "price": 3.5, "oddStatus": 0},
            {"id": 111, "typeId": 12, "price": 1.68, "oddStatus": 0},
            {"id": 112, "typeId": 13, "price": 2.2, "oddStatus": 0},
            {"id": 121, "typeId": 12, "price": 2.4, "oddStatus": 0},
            {"id": 122, "typeId": 13, "price": 1.55, "oddStatus": 0},
            {"id": 131, "typeId": 74, "price": 1.57, "oddStatus": 0},
            {"id": 132, "typeId": 76, "price": 2.3, "oddStatus": 0},
            {"id": 141, "typeId": 1, "price": 2.5, "oddStatus": 0},
            {"id": 142, "typeId": 2, "price": 4.0, "oddStatus": 0},
            {"id": 143, "typeId": 3, "price": 4.0, "oddStatus": 0},
            {"id": 151, "typeId": 9, "price": 1.3, "oddStatus": 0},
            {"id": 152, "typeId": 10, "price": 1.3, "oddStatus": 0},
            {"id": 153, "typeId": 11, "price": 1.7, "oddStatus": 0},
        ],
        "events": [{"id": 17668677, "sportId": 66, "champId": 3062, "status": 0,
                    "startDate": "2026-10-17T12:30:00Z", "competitorIds": [1, 2],
                    "marketIds": [10, 11, 12, 13, 14, 15]}],
    }


class AltenarGetEventsTests(unittest.TestCase):
    def test_full_listing_maps_1x2_totals_and_btts(self):
        rows = k._altenar_rows(_events_payload(), bookmaker="altenar_vegas.hu")
        got = {(r["market"], r["selection"]): r["odds"] for r in rows}
        self.assertEqual(got, {
            ("1x2", "home"): 2.05, ("1x2", "draw"): 3.6, ("1x2", "away"): 3.5,
            ("totals_2_5", "over_2_5"): 1.68, ("totals_2_5", "under_2_5"): 2.2,
            ("btts", "yes"): 1.57, ("btts", "no"): 2.3,
        })

    def test_boosted_odds_plus_and_other_lines_excluded(self):
        rows = k._altenar_rows(_events_payload(), bookmaker="altenar_vegas.hu")
        self.assertNotIn(2.5, [r["odds"] for r in rows])   # Odds+ promo price
        self.assertNotIn(2.4, [r["odds"] for r in rows])   # 3.5 line not gated
        self.assertNotIn(1.3, [r["odds"] for r in rows])   # double chance not mapped

    def test_incomplete_btts_market_dropped(self):
        payload = _events_payload()
        payload["odds"][8]["oddStatus"] = 1  # "no" suspended
        markets = {r["market"] for r in k._altenar_rows(payload, bookmaker="x")}
        self.assertNotIn("btts", markets)
        self.assertIn("1x2", markets)

    def test_markets_match_corroboration_gate_vocabulary(self):
        import netrattler_odds_cache_guard as g
        rows = k._altenar_rows(_events_payload(), bookmaker="x")
        for market in {r["market"] for r in rows}:
            self.assertIn(market, g.X1_CROSS_CHECK_MARKETS)
            sels = {r["selection"] for r in rows if r["market"] == market}
            self.assertEqual(sels, set(g.X1_CROSS_CHECK_MARKETS[market]))

class SmarketsTests(unittest.TestCase):
    def test_back_odds_from_best_offer(self):
        self.assertAlmostEqual(k._sm_back_odds({"offers": [{"price": 5291}, {"price": 5236}], "bids": [{"price": 5051}]}), 1.91, places=2)
        self.assertIsNone(k._sm_back_odds({"offers": []}))
        self.assertIsNone(k._sm_back_odds({"offers": [{"price": 10000}], "bids": [{"price": 9000}]}))

    def test_wide_or_one_sided_book_dropped(self):
        self.assertIsNone(k._sm_back_odds({"offers": [{"price": 1429}], "bids": [{"price": 1000}]}))  # 7.00 offer, 10.0 bid
        self.assertIsNone(k._sm_back_odds({"offers": [{"price": 5236}]}))

    def test_market_mapping(self):
        self.assertEqual(k._sm_market_key({"market_type": {"name": "BTTS"}})[0], "btts")
        self.assertEqual(k._sm_market_key({"market_type": {"name": "OVER_UNDER", "param": "2.5"}})[0], "totals_2_5")
        self.assertIsNone(k._sm_market_key({"market_type": {"name": "OVER_UNDER", "param": "3.5"}}))
        self.assertEqual(k._sm_market_key({"market_type": {"name": "FIRST_HALF_OVER_UNDER", "param": "1.5"}})[0], "totals_ht_1_5")

    def test_incomplete_or_broken_book_dropped(self):
        self.assertFalse(k._sm_complete("btts", {"yes": 1.9}))
        self.assertTrue(k._sm_complete("1x2", {"home": 1.91, "draw": 3.4, "away": 4.7}))
        self.assertFalse(k._sm_complete("1x2", {"home": 1.2, "draw": 1.5, "away": 2.0}))

    def test_vocabulary_matches_cache_guard(self):
        import netrattler_odds_cache_guard as g
        self.assertEqual(g._field_for_row({"market": "btts_ht", "selection": "yes"}), "btts_yes_ht")
        self.assertEqual(g._field_for_row({"market": "totals_ht_1_5", "selection": "over_1_5", "raw": {"line": 1.5}}), "over_15_ht")
        self.assertIn("smarkets", g.LIVE_HISTORY_SOURCES)
        self.assertIn("smarkets", dict(k.COLLECTORS))

    def test_exchange_quote_needs_peer(self):
        import netrattler_odds_cache_guard as g
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        d = now[:10]

        def r(src, odds, market="1x2", sel="home"):
            return {"source": src, "bookmaker": src, "home_team": "Persita", "away_team": "Bali", "match_date": d,
                    "captured_date": d, "market": market, "selection": sel, "odds": odds, "raw": {"captured_at": now}}
        self.assertEqual(g.best_observed_for_match("Persita", "Bali", [r("smarkets", 7.0), r("kambi", 4.91)])[0], {"home_win": 4.91})
        self.assertEqual(g.best_observed_for_match("Persita", "Bali", [r("smarkets", 5.1), r("kambi", 4.91)])[0], {"home_win": 5.1})
        self.assertEqual(g.best_observed_for_match("Persita", "Bali", [r("smarkets", 1.5, "btts_ht", "yes")])[0], {})


if __name__ == "__main__":
    unittest.main()
