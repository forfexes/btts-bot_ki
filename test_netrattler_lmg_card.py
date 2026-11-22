"""Offline regression tests for photo-card and settlement safety."""
import unittest
from unittest.mock import patch,Mock
from PIL import Image
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
        with patch.object(card,"crest",return_value=Image.new("RGBA", (96, 96), (120, 200, 240, 255))):
            opening=card.make_card(self.fx,self.metrics)
            final=card.make_card(self.fx,final_score="2:2",won=True)
            lost=card.make_card(self.fx,final_score="1:2",won=False)
        self.assertTrue(opening.startswith(b"\xff\xd8"))
        self.assertTrue(final.startswith(b"\xff\xd8"))
        self.assertTrue(lost.startswith(b"\xff\xd8"))
        self.assertNotEqual(opening,final)
        self.assertNotEqual(final,lost)
    def test_approved_neon_frame_header_survives_render(self):
        import io
        from PIL import Image,ImageChops,ImageStat
        with patch.object(card,"crest",return_value=Image.new("RGBA", (96, 96), (120, 200, 240, 255))):
            rendered=Image.open(io.BytesIO(card.make_card(self.fx,self.metrics))).convert("RGB")
        source=Image.open(card.TEMPLATE).convert("RGB").resize((1080,1350))
        diff=ImageChops.difference(source.crop((0,0,1080,230)),
                                   rendered.crop((0,0,1080,230)))
        self.assertLess(sum(ImageStat.Stat(diff).mean)/3,12)
        self.assertTrue(card.TEMPLATE.is_file())

    def test_missing_xg_and_espn_fallback_render(self):
        import io
        from PIL import Image
        no_xg={"tier":"STANDARD","teams":{"home":{"shots":10,"sot":4,"corners":3},
                                                 "away":{"shots":5,"sot":2,"corners":2}}}
        totals={"tier":"STANDARD","shots":15,"sot":6,"corners":5}
        with patch.object(card,"crest",return_value=Image.new("RGBA", (96, 96), (120, 200, 240, 255))):
            a=card.make_card(self.fx,no_xg)
            b=card.make_card(self.fx,totals)
        self.assertEqual(Image.open(io.BytesIO(a)).size,(1080,1350))
        self.assertEqual(Image.open(io.BytesIO(b)).size,(1080,1350))
        self.assertNotEqual(a,b)

    def test_visual_layout_and_telegram_photo_limits(self):
        import io
        from PIL import Image,ImageStat
        with patch.object(card,"crest",return_value=Image.new("RGBA", (96, 96), (120, 200, 240, 255))):
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

    def test_missing_verified_team_crest_fails_closed(self):
        with patch.object(card, "crest", return_value=None):
            with self.assertRaisesRegex(ValueError, "Verified team crest missing"):
                card.make_card(self.fx, self.metrics)

    def test_verified_espn_crest_url_and_host_rejection(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (64, 64), (32, 142, 220, 255)).save(buf, "PNG")
        reply = Mock()
        reply.content = buf.getvalue()
        reply.headers = {"Content-Type": "image/png"}
        with patch.object(card.requests, "get", return_value=reply) as get:
            crest = card.crest("https://a.espncdn.com/i/teamlogos/soccer/500/1.png")
            self.assertIsNotNone(crest)
            self.assertEqual(crest.size, (64, 64))
            self.assertEqual(get.call_count, 1)
            self.assertIsNone(card.crest("https://a.espncdn.com.evil.example/logo.png"))
            self.assertIsNone(card.crest("https://evil.example/logo.png"))
            self.assertIsNone(card.crest("https://a.espncdn.com:abc/logo.png"))
            self.assertIsNone(card.crest(None))
            self.assertEqual(get.call_count, 1)

    def test_card_prefers_verified_espn_crest_url(self):
        fixture = dict(self.fx, home_logo_url="https://a.espncdn.com/home.png",
                       away_logo_url="https://a.espncdn.com/away.png")
        with patch.object(card, "crest", return_value=Image.new("RGBA", (96, 96))) as load:
            card.make_card(fixture, self.metrics)
        self.assertEqual([call.args[0] for call in load.call_args_list],
                         [fixture["home_logo_url"], fixture["away_logo_url"]])

    def test_finished_only_and_identity_guard(self):
        feed={"leagues":[{"name":"ASEAN","matches":[{
            "id":1000014437,"home":{"name":"Tampines Rovers FC","score":2},
            "away":{"name":"Ratchaburi FC","score":2},
            "status":{"finished":True,"cancelled":False,"scoreStr":"2 - 2"}}]}]}
        final=settle.finished_match(feed,1000014437)
        self.assertEqual(final["score"],(2,2))
        feed["leagues"][0]["matches"][0]["status"]["finished"]=False
        self.assertIsNone(settle.finished_match(feed,1000014437))
    def test_clean_owner_release_blocks_legacy_jpeg_and_sqlite_reservation(self):
        from netrattler_lmg_free import send_alert, reserve_alert
        with patch.dict("os.environ",{"LMG_OWNER_CLEAN_RELEASED":"0",
                                     "TELEGRAM_TOKEN":"qa",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}), \
             patch("netrattler_lmg_card.make_card",
                   side_effect=AssertionError("Legacy JPEG must not render")), \
             patch("netrattler_lmg_store.reserve_alert",
                   side_effect=AssertionError("No abandoned reservation")) as store, \
             patch("requests.post",
                   side_effect=AssertionError("No Telegram post")) as post:
            with self.assertRaisesRegex(RuntimeError,"visual_release_required"):
                reserve_alert(self.fx,self.metrics)
            with self.assertRaisesRegex(RuntimeError,"visual_release_required"):
                send_alert(self.fx,self.metrics)
            store.assert_not_called()
            post.assert_not_called()

    def test_next_goal_claim_must_match_verified_pressure(self):
        from netrattler_lmg_free import send_alert, reserve_alert
        invalid={**self.metrics,"next_goal_side":"away"}
        with patch.dict("os.environ",{"LMG_OWNER_CLEAN_RELEASED":"1",
                                     "TELEGRAM_TOKEN":"qa",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}), \
             patch("netrattler_lmg_store.reserve_alert") as store, \
             patch("requests.post") as post:
            with self.assertRaisesRegex(ValueError,"Unverified next-goal"):
                reserve_alert(self.fx,invalid)
            with self.assertRaisesRegex(ValueError,"Unverified next-goal"):
                send_alert(self.fx,invalid)
            store.assert_not_called()
            post.assert_not_called()

    def test_clean_owner_png_is_the_only_live_release_path(self):
        from netrattler_lmg_free import send_alert
        reply=Mock()
        reply.json.return_value={"ok":True,"result":{"message_id":345}}
        with patch.dict("os.environ",{"LMG_OWNER_CLEAN_RELEASED":"1",
                                     "TELEGRAM_TOKEN":"qa",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}), \
             patch("netrattler_lmg_card.make_card",
                   side_effect=AssertionError("Old JPEG fallback")), \
             patch("netrattler_lmg_card.crest",
                   return_value=Image.new("RGBA",(100,100),(10,20,30,255))), \
             patch("last_minute_owner_20261122.live_data_bridge.make_live",
                   return_value=b"synthetic-clean-owner-png") as renderer, \
             patch("requests.post",return_value=reply) as post:
            message_id=send_alert(self.fx,self.metrics)
        self.assertEqual(message_id,345)
        self.assertEqual(renderer.call_count,1)
        self.assertEqual(post.call_count,1)
        payload=post.call_args.kwargs["files"]["photo"]
        self.assertEqual(payload[0],"last_minute_owner_original.png")
        self.assertEqual(payload[2],"image/png")
        self.assertNotIn("caption",post.call_args.kwargs["data"])

    def test_versioned_clean_png_settlement_edits_same_message(self):
        row={"home":"Tampines Rovers FC","away":"Ratchaburi FC",
             "minute":68,"score":"1:2","telegram_message_id":975,
             "message_kind":"owner_clean_png","next_goal_side":"home",
             "next_goal_result":"won",
             "home_logo_source":"12345",
             "away_logo_source":"https://a.espncdn.com/i/teamlogos/soccer/500/1.png"}
        final={"score":(2,2),"league":"ASEAN",
               "home":{"id":1},"away":{"id":2}}
        reply=Mock()
        reply.json.return_value={"ok":True}
        with patch.dict("os.environ",{"TELEGRAM_TOKEN":"qa",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}), \
             patch("last_minute_owner_20261122.live_data_bridge.make_settled",
                   return_value=b"synthetic-settled-owner-png") as render, \
             patch("requests.post",return_value=reply) as post:
            settle.edit_original(row,final,True)
        self.assertEqual(render.call_count,1)
        self.assertEqual(render.call_args.kwargs["next_goal_result"],"won")
        self.assertEqual(render.call_args.args[0]["home_logo_id"],"12345")
        self.assertEqual(
            render.call_args.args[0]["away_logo_id"],
            "https://a.espncdn.com/i/teamlogos/soccer/500/1.png")
        self.assertIn("editMessageMedia",post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["files"]["result_photo"][2],"image/png")
        self.assertEqual(post.call_args.kwargs["data"]["message_id"],975)
        self.assertNotIn("caption",post.call_args.kwargs["data"])

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
