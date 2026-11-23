"""Offline-only source-selection QA. No network, database or Telegram."""
import unittest
from netrattler_lmg_source_policy import (
    DECISIONS, decision, may_provide_live_tip_data, may_provide_shadow_discovery,
)


class GoalHunterSourcePolicyTests(unittest.TestCase):
    def test_all_nine_supplied_service_categories_classified(self):
        named={"sofascore","flashscore","fotmob","onefootball","espn",
               "sporteden","iscore_sports","scoreholio","keepthescore"}
        self.assertTrue(named <= set(DECISIONS))

    def test_unlicensed_consumer_sources_cannot_enter_live_tips(self):
        for source in ("sofascore","flashscore","onefootball","sporteden"):
            with self.subTest(source=source):
                self.assertFalse(may_provide_live_tip_data(source))
                self.assertFalse(may_provide_shadow_discovery(source))

    def test_operator_scoreboards_cannot_enter_live_discovery(self):
        for source in ("iscore_sports","scoreholio","keepthescore"):
            with self.subTest(source=source):
                self.assertFalse(may_provide_live_tip_data(source))
                self.assertFalse(may_provide_shadow_discovery(source))

    def test_existing_adapters_and_sportscore_shadow_only(self):
        for source in ("espn","fotmob"):
            self.assertTrue(may_provide_live_tip_data(source))
        self.assertTrue(may_provide_shadow_discovery("sportscore"))
        self.assertFalse(may_provide_live_tip_data("sportscore"))

    def test_unknown_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"unreviewed_source"):
            decision("unverified_new_scores_api")


if __name__=="__main__":
    unittest.main()
