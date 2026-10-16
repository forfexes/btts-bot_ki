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


if __name__ == "__main__":
    unittest.main()
