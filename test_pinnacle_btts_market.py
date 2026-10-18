import unittest
from unittest.mock import patch
import btts_bot as b


class _R:
    def __init__(self, js):
        self._js, self.ok = js, True
    def json(self):
        return self._js


def fake_get(url, **kw):
    if url.endswith("/markets/related/straight"):
        return _R([])
    if url.endswith("/related"):
        return _R([
            {"id": 11, "special": {"description": "Both Teams To Score & Match Result"}},
            {"id": 12, "special": {"description": "Both Teams To Score"}},
            {"id": 13, "special": {"description": "Both Teams To Score & Over 3.5"}},
            {"id": 14, "special": {"description": "Both Teams To Score - 1st Half"}},
        ])
    if url.endswith("/11/markets/straight"):
        return _R([{"period": 0, "prices": [{"designation": "home", "price": 5.3}, {"designation": "yes", "price": 6.0}]}])
    if url.endswith("/12/markets/straight"):
        return _R([{"period": 0, "prices": [{"designation": "yes", "price": 1.83}, {"designation": "no", "price": 2.0}]}])
    if url.endswith("/13/markets/straight"):
        return _R([{"period": 0, "prices": [{"designation": "yes", "price": 4.4}]}])
    if url.endswith("/14/markets/straight"):
        return _R([{"period": 1, "prices": [{"designation": "yes", "price": 3.6}]}])
    return _R([])


class PlainBtts(unittest.TestCase):
    def test_only_plain_btts_market_sets_btts_yes(self):
        b._PIN_ODDS_CACHE.clear() if hasattr(b._PIN_ODDS_CACHE, "clear") else None
        with patch.object(b.requests, "get", side_effect=fake_get):
            r = b.fetch_pinnacle_match_odds(987654)
        self.assertEqual(r["btts_yes"], 1.83)
        self.assertEqual(r["btts_yes_ht"], 3.6)  # period-1 market stays the half-time quote
        self.assertNotIn("btts_over25_yes", r)


if __name__ == "__main__":
    unittest.main()
