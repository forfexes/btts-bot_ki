"""Offline tests for verified optional next-goal tip and separate settlement."""
import unittest
from unittest.mock import Mock, patch

import netrattler_lmg_next_goal as next_goal
import netrattler_lmg_free as common
import netrattler_lmg_settle as settle
import netrattler_lmg_card as card


class NextGoalTests(unittest.TestCase):
    def setUp(self):
        self.metrics={"tier":"PREMIUM","shots":26,"sot":11,"corners":8,
                      "teams":{"home":{"shots":17,"sot":8,"xg":1.75,"corners":5},
                               "away":{"shots":9,"sot":3,"xg":0.60,"corners":3}}}
        self.fx={"fixture_id":1000014437,"home":"Tampines Rovers FC",
                 "away":"Ratchaburi FC","hg":1,"ag":2,"minute":68,
                 "league":"ASEAN","home_logo_id":None,"away_logo_id":None}

    def test_home_away_and_no_fabricated_percent(self):
        self.assertEqual(next_goal.select_next_goal(self.metrics),"home")
        swapped={"teams":{"home":self.metrics["teams"]["away"],
                          "away":self.metrics["teams"]["home"]}}
        self.assertEqual(next_goal.select_next_goal(swapped),"away")
        tied={"teams":{"home":{"shots":9,"sot":4,"xg":1.1},
                       "away":{"shots":10,"sot":4,"xg":1.2}}}
        self.assertIsNone(next_goal.select_next_goal(tied))
        discordant={"teams":{"home":{"shots":17,"sot":8,"xg":0.6},
                             "away":{"shots":9,"sot":3,"xg":1.75}}}
        self.assertIsNone(next_goal.select_next_goal(discordant))
        no_xg={"teams":{"home":{"shots":18,"sot":8},
                        "away":{"shots":6,"sot":2}}}
        self.assertEqual(next_goal.select_next_goal(no_xg),"home")
        no_xg["teams"]["home"]["shots"]=14
        self.assertIsNone(next_goal.select_next_goal(no_xg))
        self.assertIsNone(next_goal.select_next_goal({"teams":{}}))
        self.assertIsNone(next_goal.select_next_goal({"teams":{"home":{"shots":8,"sot":9},
                             "away":{"shots":9,"sot":3}}}))

    def test_next_team_settled_only_when_scoring_side_provable(self):
        grade=next_goal.evaluate_next_goal
        self.assertEqual(grade("home",(1,2),(3,2)),"won")
        self.assertEqual(grade("away",(1,2),(3,2)),"lost")
        self.assertEqual(grade("away",(1,2),(1,4)),"won")
        self.assertEqual(grade("home",(1,2),(1,2)),"void")
        self.assertEqual(grade("home",(1,2),(3,4)),"unverified")
        self.assertEqual(grade("home",(1,2),(0,4)),"unverified")
        self.assertIsNone(grade(None,(1,2),(3,2)))

    def test_existing_card_information_preserved(self):
        self.metrics["next_goal_side"]="home"
        with patch.object(card,"crest",return_value=None):
            old=card.make_card(self.fx,{k:v for k,v in self.metrics.items()
                                       if k!="next_goal_side"})
            open_image=card.make_card(self.fx,self.metrics)
            done=card.make_card(self.fx,final_score="3:2",won=True,
                                next_goal_side="home",next_goal_result="won")
            wrong=card.make_card(self.fx,final_score="3:2",won=True,
                                 next_goal_side="away",next_goal_result="lost")
        for data in (old,open_image,done,wrong):
            self.assertTrue(data.startswith(b"\\xff\\xd8"))
        self.assertNotEqual(open_image,old)
        self.assertNotEqual(done,wrong)

    def test_sending_one_image_with_new_caption_and_db_side(self):
        self.metrics["next_goal_side"]="home"
        response=Mock()
        response.status_code=201
        response.json.return_value=[{"alert_key":"1000014437"}]
        with patch.dict("os.environ",{"SUPABASE_URL":"https://example.supabase.co",
                                     "SUPABASE_KEY":"testsecret"}),\
             patch("requests.post",return_value=response) as post:
            key=common.reserve_alert(self.fx,self.metrics)
        self.assertEqual(key,"1000014437")
        self.assertEqual(post.call_args.kwargs["json"]["next_goal_side"],"home")

        reply=Mock()
        reply.json.return_value={"ok":True,"result":{"message_id":912}}
        with patch.dict("os.environ",{"TELEGRAM_TOKEN":"test",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}),\
             patch("netrattler_lmg_card.make_card",return_value=b"JPEG"),\
             patch("requests.post",return_value=reply) as post:
            self.assertEqual(common.send_alert(self.fx,self.metrics),912)
        self.assertTrue(post.call_args.args[0].endswith("/sendPhoto"))
        caption=post.call_args.kwargs["data"]["caption"]
        self.assertIn("Nächstes Tor (Zusatz)",caption)
        self.assertIn(self.fx["home"],caption)
        self.assertIn("Over 0.5",caption)
        self.assertIn("@prophunter",caption)
        self.assertNotIn("%",caption)

    def test_original_photo_edited_and_results_persisted_separately(self):
        row={**self.fx,"score":"1:2","telegram_message_id":912,
             "message_kind":"photo","next_goal_side":"home",
             "next_goal_result":"won"}
        final={"score":(3,2),"home":{"id":12},"away":{"id":14},"league":"ASEAN"}
        reply=Mock()
        reply.json.return_value={"ok":True}
        with patch.dict("os.environ",{"TELEGRAM_TOKEN":"test",
                                     "TELEGRAM_GROUP_LATE_GOALS":"-1"}),\
             patch("netrattler_lmg_card.make_card",return_value=b"JPEG") as render,\
             patch("requests.post",return_value=reply) as post:
            settle.edit_original(row,final,True)
        self.assertTrue(post.call_args.args[0].endswith("/editMessageMedia"))
        self.assertEqual(render.call_args.kwargs["next_goal_side"],"home")
        self.assertEqual(render.call_args.kwargs["next_goal_result"],"won")
        self.assertIn("RICHTIG",post.call_args.kwargs["data"]["media"])

        response=Mock()
        with patch.dict("os.environ",{"SUPABASE_URL":"https://example.supabase.co",
                                     "SUPABASE_KEY":"testsecret"}),\
             patch("requests.patch",return_value=response) as patcher:
            row["alert_key"]="1000014437"
            settle.mark_settled(row,(3,2),True)
        body=patcher.call_args.kwargs["json"]
        self.assertEqual(body["next_goal_result"],"won")
        self.assertEqual(body["status"],"won")


if __name__=="__main__":
    unittest.main()
