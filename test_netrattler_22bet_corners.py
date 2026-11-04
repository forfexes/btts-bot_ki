import json
from pathlib import Path
import unittest
from netrattler_keyless_odds import _x1_corner_rows

class Corners(unittest.TestCase):
    def test_live_response_totals_and_isolation(self):
        sub=json.loads(Path('tests/fixtures/22bet_full_match_corners.json').read_text())
        parent=dict(I=767313717,O1='Alverca',O2='Casa Pia',L='Portugal. Primeira Liga',S=1794074400)
        rows=_x1_corner_rows(parent,sub,'https://22bet.com')
        self.assertGreater(len(rows),0)
        over=next(x for x in rows if x['market']=='corners_9_5' and x['selection']=='over_9_5')
        self.assertEqual(float(over['odds']),1.85)
        self.assertTrue(all(x['market'].startswith('corners_') for x in rows))
        self.assertTrue(all(float(x['market'].split('_',1)[1].replace('_','.'))>=6.5 for x in rows))
        for change in ({'PN':'1st half'},{'TG':'Goals'},{'O2':'Other Club'}):
            self.assertEqual(_x1_corner_rows(parent,dict(sub,**change),'https://22bet.com'),[])
        self.assertEqual(_x1_corner_rows(parent,dict(sub,GE=[x for x in sub['GE'] if x['G'] in (5,6)]),'https://22bet.com'),[])

if __name__=='__main__':unittest.main()
