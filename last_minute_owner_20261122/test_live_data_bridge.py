"""Offline no-fabrication check of the actual FotMob/ESPN fixture adapter."""
from __future__ import annotations
from io import BytesIO
from PIL import Image,ImageDraw
import unittest
from .live_data_bridge import make_live,make_settled

FIXTURE={'league':'QA LEAGUE','home':'EXAMPLE HOME','away':'EXAMPLE AWAY',
 'home_logo_id':17,'away_logo_id':22,'minute':75,'hg':1,'ag':1}
METRICS={'teams':{'home':{'shots':8,'sot':3,'xg':0.67,'corners':3},
                  'away':{'shots':11,'sot':4,'xg':1.09,'corners':6}},
         'next_goal_side':'away'}

def authentic_qa_image(team_id):
    assert team_id in (17,22)
    im=Image.new('RGBA',(96,96),(0,0,0,0))
    ImageDraw.Draw(im).ellipse((5,5,91,91),fill=(18,107,158))
    b=BytesIO();im.save(b,'PNG');return b.getvalue()

class BridgeQA(unittest.TestCase):
    def test_observed_stats_without_estimated_probabilities(self):
        image=make_live(FIXTURE,METRICS,crest_provider=authentic_qa_image,
                        preview_only=True)
        with Image.open(BytesIO(image)) as im: self.assertEqual(im.size,(1024,1078))
    def test_confirmation_does_not_fabricate_xg_history_or_winrates(self):
        self.assertNotIn('xg_previous_verified',METRICS)
        self.assertNotIn('over_probability',METRICS)
        make_live(FIXTURE,{**METRICS,'over_probability':99.8,'next_probability':91.2},
                  crest_provider=authentic_qa_image,preview_only=True)
    def test_identity_and_missing_crest_are_blocked(self):
        with self.assertRaisesRegex(ValueError,'crest IDs'):
            make_live({**FIXTURE,'home_logo_id':None},METRICS,
                      crest_provider=authentic_qa_image)
        with self.assertRaises(ValueError):
            make_live(FIXTURE,{**METRICS,'next_goal_side':'unknown'},
                      crest_provider=authentic_qa_image)
    def test_final_result_must_be_verified_and_cannot_go_backwards(self):
        with self.assertRaisesRegex(ValueError,'Confirmed win/loss'):
            make_settled(FIXTURE,final_score='2:1',won=None,
                         crest_provider=authentic_qa_image)
        with self.assertRaisesRegex(ValueError,'Final score below'):
            make_settled(FIXTURE,final_score='0:2',won=True,
                         crest_provider=authentic_qa_image)
        image=make_settled(FIXTURE,final_score='2:1',won=True,
                           crest_provider=authentic_qa_image,preview_only=True)
        with Image.open(BytesIO(image)) as im:self.assertEqual(im.size,(1024,1078))

if __name__=='__main__':unittest.main(verbosity=2)