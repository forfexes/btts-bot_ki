import unittest
from netrattler_reviewed_results import EVIDENCE, collect
from netrattler_settlement_v16_final import match_parts, row_date, _strict_team_match, settle_tip

class ReviewedResults(unittest.TestCase):
    def test_settlement_and_identity(self):
        for evidence, expected in zip(EVIDENCE, ['win', 'win', 'loss', 'loss', 'win']):
            key, day, home, away, *_ = evidence
            tip = dict(tip_id=key, match=key[len('corners_'):-11].replace('_', ' '), match_date=key[-10:],
                       market_group='corners', market='Over 7.5 Corners', category='corners', line=7.5, side='over')
            rows = collect([tip], match_parts, row_date, _strict_team_match)
            self.assertEqual(len(rows), 1, key)
            self.assertEqual(rows[0]['match_date'], day)
            self.assertEqual(settle_tip(tip, rows, [])['status'], expected, key)
            for mutation in [dict(tip_id='other'), dict(match_date='2026-11-01'), dict(match='Other vs Club')]:
                self.assertEqual(collect([dict(tip, **mutation)], match_parts, row_date, _strict_team_match), [])

if __name__ == '__main__': unittest.main()
