import unittest
from unittest.mock import patch
from netrattler_hf_reference import fixtures, collect, benchmark

class References(unittest.TestCase):
    def row(self, **extra):
        return dict(dict(kickoff_utc='2026-10-20T17:00:00Z',home_team='Home',away_team='Away',home_goals='0',away_goals='1',p_home='.2',p_draw='.3',p_away='.5'), **extra)
    def test_no_fake_zero_conflicts_or_future(self):
        self.assertEqual(fixtures([self.row(home_goals='')]), [])
        self.assertEqual(fixtures([self.row(),self.row(home_goals='2')]), [])
        self.assertEqual(fixtures([self.row(kickoff_utc='2099-01-01T00:00:00Z')]), [])
        self.assertEqual(len(fixtures([self.row(),self.row()])), 1)
    def test_exact_fixture_and_no_price(self):
        parts=lambda t:(t['home'],t['away'],'')
        date=lambda t:t['day']
        tip=dict(home='Home',away='Away',day='2026-10-20')
        with patch('netrattler_hf_reference.read_rows',return_value=[self.row()]):
            rows=collect([tip],parts,date,lambda a,b:a==b,lambda _:None)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['home_score'],0)
            self.assertNotIn('odds',rows[0])
            self.assertEqual(collect([dict(tip,away='Other')],parts,date,lambda a,b:a==b,lambda _:None),[])
            self.assertEqual(collect([dict(tip,day='2026-10-19')],parts,date,lambda a,b:a==b,lambda _:None),[])
    def test_market_rows_count_once(self):
        report=benchmark('footinsights',[self.row(),self.row()])
        self.assertEqual(report['scored_fixtures'],1)
        self.assertAlmostEqual(report['brier_1x2'],.38)
        self.assertEqual(benchmark('footinsights',[self.row(p_home='nan')])['scored_fixtures'],0)

if __name__=='__main__':unittest.main()
