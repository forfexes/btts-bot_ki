import math
import unittest
from unittest import mock

import netrattler_finishing_adjust as fr


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeRequests:
    """One page of rows, matching the finishing_radar.py fetch shape."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        if self.calls == 1:
            return _FakeResp(self.rows)
        return _FakeResp([])  # pagination stop


def _rows_for(name, team, goals_xg_pairs):
    rows = []
    for i, (g, x) in enumerate(goals_xg_pairs):
        rows.append({
            "player_key": name, "player_name": name, "team": team,
            "match_date": f"2026-09-{i + 1:02d}", "minutes": 90, "goals": g, "xg": x,
        })
    return rows


class TestFinishingAdjust(unittest.TestCase):
    def setUp(self):
        fr.reset()

    def test_no_data_returns_raw_prob_unchanged(self):
        req = _FakeRequests(_rows_for("Known Player", "Team A", [(1, 0.5)] * 8))
        fr.load(req, "https://x.supabase.co", "key")
        # Querying a player with no window history must never fabricate a value.
        self.assertEqual(fr.adjusted_prob_pct("Totally Unknown Player", 42.0), 42.0)

    def test_no_calibration_returns_raw_prob_unchanged(self):
        req = _FakeRequests([])  # empty dataset -> calibration impossible
        fr.load(req, "https://x.supabase.co", "key")
        self.assertEqual(fr.adjusted_prob_pct("Anyone", 50.0), 50.0)

    def test_overperformer_gets_pulled_down_toward_xg(self):
        # Player scored far more than xG in the window (lucky streak) plus a
        # large league sample at a modest base rate, so the naive goals-only
        # view (prob based on raw goals_per_game, computed by the caller) is
        # an overestimate; the finishing-radar blend must pull it DOWN, not
        # leave it untouched or push it further up.
        league_rows = []
        for p in range(40):
            league_rows += _rows_for(f"Filler {p}", "Team X", [(0, 0.2)] * 8)
        hot_player = _rows_for("Hot Striker", "Team A", [(1, 0.2)] * 8)  # 8 goals, xg 1.6
        req = _FakeRequests(league_rows + hot_player)
        fr.load(req, "https://x.supabase.co", "key")
        naive_prob = (1 - math.exp(-8 / 8.0 * 90 / 90)) * 100  # naive: ~1 goal/game -> ~63%
        adjusted = fr.adjusted_prob_pct("Hot Striker", naive_prob)
        self.assertLess(adjusted, naive_prob)

    def test_underperformer_gets_pulled_up_toward_xg(self):
        league_rows = []
        for p in range(40):
            league_rows += _rows_for(f"Filler {p}", "Team X", [(0.2, 0.2)] * 8)
        cold_player = _rows_for("Cold Striker", "Team A", [(0, 0.5)] * 8)  # 0 goals, xg 4.0
        req = _FakeRequests(league_rows + cold_player)
        fr.load(req, "https://x.supabase.co", "key")
        naive_prob = 0.0  # 0 goals in window -> naive goals-only view sees nothing
        adjusted = fr.adjusted_prob_pct("Cold Striker", naive_prob)
        self.assertGreater(adjusted, naive_prob)

    def test_load_is_idempotent_per_run(self):
        req = _FakeRequests(_rows_for("Player X", "Team A", [(1, 0.5)] * 8))
        fr.load(req, "https://x.supabase.co", "key")
        calls_after_first = req.calls
        fr.load(req, "https://x.supabase.co", "key")  # second call must be a no-op
        self.assertEqual(req.calls, calls_after_first)

    def test_network_failure_never_raises(self):
        class _Boom:
            def get(self, *a, **k):
                raise RuntimeError("network down")
        fr.load(_Boom(), "https://x.supabase.co", "key")  # must not raise
        self.assertEqual(fr.adjusted_prob_pct("Anyone", 33.0), 33.0)


if __name__ == "__main__":
    unittest.main()
