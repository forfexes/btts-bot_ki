"""Daily image QA scans every name over time without repeating one fixed sample."""
import unittest
from asset_coverage_audit import select_batch, fallback_club, full_chain_budget


class CoverageRotation(unittest.TestCase):
    def test_fixed_priority_and_daily_progress(self):
        items = list(range(55))
        first, meta = select_batch(items, 10, rotate=True, anchor=2, ordinal=0)
        second, meta2 = select_batch(items, 10, rotate=True, anchor=2, ordinal=1)
        self.assertEqual(first[:2], [0, 1])
        self.assertEqual(second[:2], [0, 1])
        self.assertEqual(first[2:], list(range(2, 10)))
        self.assertEqual(second[2:], list(range(10, 18)))
        self.assertEqual(meta["mode"], "daily_rotation")
        self.assertEqual(meta["slices"], meta2["slices"])

    def test_all_names_eventually_scanned(self):
        items = list(range(55))
        covered = set()
        for day in range(12):
            selected, meta = select_batch(items, 10, rotate=True, anchor=2, ordinal=day)
            self.assertEqual(len(selected), len(set(selected)))
            covered.update(selected)
        self.assertEqual(covered, set(items))

    def test_small_rotating_batch_respects_cap_and_covers_roster(self):
        items = list(range(9))
        covered = set()
        for day in range(9):
            selected, _ = select_batch(items, 2, rotate=True, anchor=20, ordinal=day)
            self.assertLessEqual(len(selected), 2)
            covered.update(selected)
        self.assertEqual(covered, set(items))

    def test_full_chain_budget_all_is_bounded_by_batch(self):
        self.assertEqual(full_chain_budget("all", 100), 100)
        self.assertEqual(full_chain_budget("ALL", 0), 0)
        self.assertEqual(full_chain_budget("16", 8), 8)
        self.assertEqual(full_chain_budget("100", 100), 30)
        self.assertEqual(full_chain_budget("-1", 100), 0)

    def test_priority_mode_backwards_compatible(self):
        selected, meta = select_batch(list(range(12)), 5)
        self.assertEqual(selected, [0, 1, 2, 3, 4])
        self.assertEqual(meta["mode"], "priority")

    def test_empty_and_small_rosters(self):
        self.assertEqual(select_batch([], 10, rotate=True)[0], [])
        self.assertEqual(select_batch([1, 2, 3], 10, rotate=True)[0], [1, 2, 3])


    def test_tip_club_resolves_historical_transfer_for_probe(self):
        self.assertEqual(fallback_club({"teams": {"Old Club", "New Club"},
                                       "tip_teams": {"New Club"}}), "New Club")

    def test_conflicting_tip_clubs_are_not_guessed(self):
        self.assertIsNone(fallback_club({"teams": {"A", "B"}, "tip_teams": {"A", "B"}}))

    def test_no_tip_club_requires_unique_historical_club(self):
        self.assertEqual(fallback_club({"teams": {"Only Club"}}), "Only Club")
        self.assertIsNone(fallback_club({"teams": {"A", "B"}}))
        self.assertIsNone(fallback_club({"teams": set()}))


if __name__ == "__main__":
    unittest.main()
