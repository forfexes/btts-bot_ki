"""Offline non-network hardtests for original-only Last Minute Goal artwork."""
import io
import unittest
from pathlib import Path
from PIL import Image,ImageDraw

from build_master import SOURCE,TARGET,REGIONS,make_plate
from last_minute_dynamic_card import render_card


def crest():
    im=Image.new('RGBA',(80,80),(0,0,0,0))
    ImageDraw.Draw(im).ellipse((5,5,75,75),fill=(38,95,156,255))
    buf=io.BytesIO();im.save(buf,'PNG')
    return buf.getvalue()

DATA={
    'league':'OFFLINE QA ONLY','home':'TEAM ALPHA','away':'TEAM BETA',
    'minute':72,'hg':1,'ag':2,
    'stats':{'shots':[9,13],'sot':[4,5],'possession':[42,58],
             'corners':[3,7],'attacks':[25,37]},
    'xg_prev_home':0.35,'xg_home':0.72,'xg_prev_away':0.79,'xg_away':1.22,
    'over_probability':70.1,'next_probability':60.8,
    'next_goal_team':'TEAM BETA','status':'offen',
}

class LastMinuteOriginalQa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stats=make_plate()

    def test_original_art_kept_and_plate_cleaned_once(self):
        self.assertGreater(self.stats['unchanged_pct'],70)
        self.assertLess(self.stats['unchanged_pct'],95)
        with Image.open(SOURCE) as source, Image.open(TARGET) as plate:
            self.assertEqual(source.size,plate.size)
            self.assertNotEqual(source.getpixel((252,173)),plate.getpixel((252,173)))
            self.assertEqual(source.getpixel((257,53)),plate.getpixel((257,53)))
            self.assertEqual(source.getpixel((204,501)),plate.getpixel((204,501)))

    def test_all_dynamic_fields_render_into_clean_original_style(self):
        raw=render_card(DATA,home_crest=crest(),away_crest=crest(),preview_only=True)
        with Image.open(io.BytesIO(raw)) as pic:
            pic.load()
            self.assertEqual(pic.size,(1024,1078))
        self.assertGreater(len(raw),200_000)

    def test_missing_or_unverified_logo_never_falls_back(self):
        with self.assertRaisesRegex(ValueError,'crest'):
            render_card(DATA,home_crest=None,away_crest=crest())
        with self.assertRaisesRegex(ValueError,'crest'):
            render_card(DATA,home_crest=b'synthetic image',away_crest=crest())

    def test_missing_data_are_not_fabricated(self):
        clean={k:v for k,v in DATA.items() if k not in (
            'over_probability','next_probability','next_goal_team','stats')}
        render_card(clean,home_crest=crest(),away_crest=crest(),preview_only=True)
        bad={**DATA,'over_probability':105}
        with self.assertRaisesRegex(ValueError,'over_probability'):
            render_card(bad,home_crest=crest(),away_crest=crest())

    def test_team_identity_and_result_consistency(self):
        for bad in ({'home':'TEAM BETA'},
                    {'next_goal_team':'OTHER TEAM'},
                    {'minute':-1},{'hg':None},
                    {'status':'assumed_win'},
                    {'stats':{'shots':[5,-1]}},
                    {'next_goal_team':None,'next_probability':72}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                render_card({**DATA,**bad},home_crest=crest(),away_crest=crest())

    def test_never_draw_sample_filled_reference_directly(self):
        with self.assertRaisesRegex(ValueError,'sample-filled'):
            render_card(DATA,home_crest=crest(),away_crest=crest(),plate=SOURCE)
        with self.assertRaisesRegex(RuntimeError,'No cleaned'):
            render_card(DATA,home_crest=crest(),away_crest=crest(),plate=Path('missing_plate.png'))

if __name__=='__main__':unittest.main(verbosity=2)