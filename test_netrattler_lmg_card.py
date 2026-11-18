"""Offline regression tests for photo-card and settlement safety."""
import unittest
from unittest.mock import patch,Mock
import netrattler_lmg_card as card
import netrattler_lmg_settle as settle

class GoalHunterCards(unittest.TestCase):
    def setUp(self):
        self.fx={"home":"Tampines Rovers FC","away":"Ratchaburi FC",
                 "hg":1,"ag":2,"minute":68,"league":"ASEAN Club Championship",
                 "home_logo_id":None,"away_logo_id":None}
        self.metrics={"tier":"STANDARD","teams":{"home":{"shots":10,"sot":4,"corners":3,"xg":1.62},
                                                   "away":{"shots":5,"sot":2,"corners":2,"xg":0.87}}}
    def test_open_and_final_render(self):
        with patch.object(card,"crest",return_value=None):
            opening=card.make_card(self.fx,self.metrics)
            final=card.make_card(self.fx,final_score="2:2",won=True)
            lost=card.make_card(self.fx,final_score="1:2",won=False)
        self.assertTrue(opening.startswith(b"\xff\xd8"))
        self.assertTrue(final.startswith(b"\xff\xd8"))
        self.assertTrue(lost.startswith(b"\xff\xd8"))
        self.assertNotEqual(opening,final)
        self.assertNotEqual(final,lost)
    def test_missing_xg_and_espn_fallback_render(self):
        import io
        from PIL import Image
        no_xg={"tier":"STANDARD","teams":{"home":{"shots":10,"sot":4,"corners":3},
                                                 "away":{"shots":5,"sot":2,"corners":2}}}
        totals={"tier":"STANDARD","shots":15,"sot":6,"corners":5}
        with patch.object(card,"crest",return_value=None):
            a=card.make_card(self.fx,no_xg)
            b=card.make_card(self.fx,totals)
        self.assertEqual(Image.open(io.BytesIO(a)).size,(1080,1350))
        self.assertEqual(Image.open(io.BytesIO(b)).size,(1080,1350))
        self.assertNotEqual(a,b)

    def test_visual_layout_and_telegram_photo_limits(self):
        import io
        from PIL import Image,ImageStat
        with patch.object(card,"crest",return_value=None):
            for label,options in (("open",{"metrics":self.metrics}),
                                  ("won",{"final_score":"3:2","won":True}),
                                  ("lost",{"final_score":"1:2","won":False})):
                raw=card.make_card(self.fx,**options)
                img=Image.open(io.BytesIO(raw))
                self.assertEqual(img.size,(1080,1350),label)
                self.assertEqual(img.format,"JPEG",label)
                self.assertLess(len(raw),10_000_000,label)
                # Detect blank/broken image, missing headline, and invisible footer.
                self.assertGreater(ImageStat.Stat(img.crop((0,0,1080,300))).stddev[0],12,label)
                self.assertGreater(ImageStat.Stat(img.crop((0,1200,1080,1350))).stddev[0],5,label)
                self.assertGreater(ImageStat.Stat(img.crop((50,600,1030,1150))).stddev[0],15,label)

    def test_finished_only_and_identity_guard(self):
        feed={"leagues":[{"name":"ASEAN","matches":[{
            "id":1000014437,"home":{"name":"Tampines Rovers FC","score":2},
            "away":{"name":"Ratchaburi FC","score":2},
            "status":{"finished":True,"cancelled":False,"scoreStr":"2 - 2"}}]}]}
        final=settle.finished_match(feed,1000014437)
        self.assertEqual(final["score"],(2,2))
        feed["leagues"][0]["matches"][0]["status"]["finished"]=False
        self.assertIsNone(settle.finished_match(feed,1000014437))
    def test_no_extra_telegram_message_on_settlement(self):
        row={"home":"Tampines Rovers FC","away":"Ratchaburi FC","minute":68,
             "score":"1:2","telegram_message_id":971,"message_kind":"photo"}
        final={"score":(2,2),"league":"ASEAN","home":{"id":1},"away":{"id":2}}
        reply=Mock()
        reply.json.return_value={"ok":True}
        with patch.dict("os.environ",{"TELEGRAM_TOKEN":"test","TELEGRAM_GROUP_LATE_GOALS":"-1"}),\
             patch("netrattler_lmg_card.make_card",return_value=b"JPEG"),\
             patch("requests.post",return_value=reply) as post:
            settle.edit_original(row,final,True)
        self.assertIn("editMessageMedia",post.call_args.args[0])
        self.assertNotIn("sendMessage",post.call_args.args[0])
        self.assertNotIn("sendPhoto",post.call_args.args[0])

if __name__=="__main__":
    unittest.main()
