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
    # Different fake colours stand in for two DIFFERENT observed logos.
    ImageDraw.Draw(im).ellipse((5,5,91,91),
        fill=(18,107,158) if team_id==17 else (181,40,65))
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
    def test_duplicate_home_away_crest_identifiers_blocked(self):
        # The same provider logo id cannot represent the two opposing clubs.
        for override in (
            {'away_logo_id':17},
            {'home_logo_url':'17','away_logo_url':'17'},
        ):
            fixture={**FIXTURE,**override}
            with self.subTest(override=override), self.assertRaisesRegex(
                    ValueError,'cannot share a verified crest'):
                make_live(fixture,METRICS,crest_provider=authentic_qa_image)
            with self.subTest(settled=override), self.assertRaisesRegex(
                    ValueError,'cannot share a verified crest'):
                make_settled(fixture,final_score='2:1',won=True,
                             crest_provider=authentic_qa_image)

    def test_distinct_provider_ids_cannot_return_identical_images(self):
        # An upstream source may resolve IDs 17 and 22 to the same
        # wrongly cached club crest. No visual sticker fix is allowed.
        def same_badge(team_id):
            return authentic_qa_image(17)
        with self.assertRaisesRegex(ValueError,'identical team crest artwork'):
            make_live(FIXTURE,METRICS,crest_provider=same_badge)
        with self.assertRaisesRegex(ValueError,'identical team crest artwork'):
            make_settled(FIXTURE,final_score='2:1',won=True,
                         crest_provider=same_badge)
        # Normal verified identities still work.
        rendered=make_live(FIXTURE,METRICS,
                           crest_provider=authentic_qa_image,preview_only=True)
        self.assertTrue(rendered.startswith(b'\x89PNG'))

    def test_final_goal_growth_must_match_bet_settlement(self):
        # An unchanged 1:1 match is never an Over 0.5 remaining-time win.
        with self.assertRaisesRegex(ValueError,'verdict contradicts'):
            make_settled(FIXTURE,final_score='1:1',won=True,
                         crest_provider=authentic_qa_image,preview_only=True)
        # A later goal is never a loss even when manually mislabeled.
        with self.assertRaisesRegex(ValueError,'verdict contradicts'):
            make_settled(FIXTURE,final_score='1:2',won=False,
                         crest_provider=authentic_qa_image,preview_only=True)
        # Exactly the same verified final score correctly settles as lost.
        raw=make_settled(FIXTURE,final_score='1:1',won=False,
                         crest_provider=authentic_qa_image,preview_only=True)
        with Image.open(BytesIO(raw)) as im:
            self.assertEqual(im.size,(1024,1078))
        for invalid in ('1:NaN','-1:2','1.1:2','1:31','1:2:3'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                make_settled(FIXTURE,final_score=invalid,won=True,
                             crest_provider=authentic_qa_image)
    def test_next_goal_grade_needs_observed_order_and_no_blanket_void(self):
        # Only home scored once: the home next-goal call can be proven.
        valid=make_settled(FIXTURE,final_score='2:1',won=True,
                           next_goal_side='home',next_goal_result='won',
                           crest_provider=authentic_qa_image,preview_only=True)
        self.assertTrue(valid.startswith(b'\x89PNG'))
        # Final scores cannot establish who scored FIRST if both sides did.
        with self.assertRaisesRegex(ValueError,'evidence not final score'):
            make_settled(FIXTURE,final_score='2:2',won=True,
                         next_goal_side='away',next_goal_result='won',
                         crest_provider=authentic_qa_image)
        # Zero new goals do not justify a generic sportsbook VOID.
        with self.assertRaisesRegex(ValueError,'no blanket void'):
            make_settled(FIXTURE,final_score='1:1',won=False,
                         next_goal_side='home',next_goal_result='void',
                         crest_provider=authentic_qa_image)
        # An outright contradiction cannot be reported as a WIN.
        with self.assertRaisesRegex(ValueError,'contradicts confirmed'):
            make_settled(FIXTURE,final_score='1:2',won=True,
                         next_goal_side='home',next_goal_result='won',
                         crest_provider=authentic_qa_image)
        for final,won in (('1:1',False),('2:2',True)):
            self.assertTrue(make_settled(
                FIXTURE,final_score=final,won=won,next_goal_side='home',
                next_goal_result='unverified',crest_provider=authentic_qa_image,
                preview_only=True).startswith(b'\x89PNG'))

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