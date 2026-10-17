import tempfile
import unittest
from pathlib import Path
from netrattler_open_h2h import parse_results, h2h


class OpenH2HTests(unittest.TestCase):
    def test_parse_and_aggregate_both_venues(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'results.csv'
            p.write_text('Team 1,FT,Team 2,Date\nArsenal,2-1,Chelsea,2020-01-01\nChelsea,3-3,Arsenal,2020-02-01\nArsenal,0-2,Liverpool,2020-03-01\nArsenal,postponed,Chelsea,2020-04-01\n', encoding='utf-8')
            games = parse_results(p)
            self.assertEqual(len(games), 3)
            self.assertEqual(h2h(games, 'Arsenal', 'Chelsea'), {
                'games': 2, 'a_wins': 1, 'b_wins': 0, 'draws': 1, 'btts': 2, 'over25': 2})

    def test_invalid_teams_rejected(self):
        with self.assertRaises(ValueError):
            h2h([], 'Arsenal', 'arsenal')


if __name__ == '__main__':
    unittest.main()
