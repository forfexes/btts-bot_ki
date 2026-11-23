"""Release provenance QA: original screenshot != clean approved Telegram asset."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from netrattler_original_release_inventory import ROOT, REFERENCES, audit


class RealOwnerOriginalReleaseQA(unittest.TestCase):
    def test_all_16_source_categories_have_truthful_status(self):
        statuses=audit()
        self.assertEqual(len(statuses),16)
        self.assertEqual(set(statuses), {
            "builder", "goal", "corner", "btts", "over", "btts_halftime",
            "over_halftime", "match_result", "combo", "player_props",
            "fouls_cards", "var", "last_minute_goal", "late_goals",
            "live_halftime", "cross_mix",
        })
        for family in ("btts","builder","combo","goal","corner"):
            self.assertTrue(statuses[family]["reference_present"])
            self.assertNotEqual(statuses[family]["state"],"approved")
        self.assertTrue(statuses["last_minute_goal"]["reference_present"])
        self.assertTrue(statuses["last_minute_goal"]["clean_candidate_present"])
        self.assertEqual(statuses["last_minute_goal"]["state"],
                         "clean_candidate_not_approved")
        for family in ("var","over","player_props","fouls_cards","cross_mix"):
            self.assertTrue(statuses[family]["technical_svg_only"])
            self.assertFalse(statuses[family]["approved_for_telegram"])
        self.assertFalse(any(x["approved_for_telegram"] for x in statuses.values()))
        # All 16 requested categories have offline reference-derived QA
        # capability, but not a single one has verified Telegram release.
        self.assertEqual(sum(x["qa_draft_buildable"] for x in statuses.values()),16)
        self.assertTrue(all(x["qa_draft_is_not_approved_original"]
                            for x in statuses.values()))
        self.assertEqual(sum(x["approved_for_telegram"] for x in statuses.values()),0)
        for category in ("builder","goal","corner","btts","combo"):
            self.assertEqual(statuses[category]["qa_preview_generator"],
                             "netrattler_five_owner_reference_qa.py")
        self.assertEqual(statuses["last_minute_goal"]["qa_preview_generator"],
                         "last_minute_owner_20261122/last_minute_dynamic_card.py")


    def test_a_self_signed_json_can_never_release_a_master(self):
        # Simulated protected release only. No actual app secrets or Telegram.
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            src=REFERENCES["last_minute_goal"]
            new_source=work/src.relative_to(ROOT)
            new_source.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,new_source)
            approved=work/"assets/approved_original_masters/last_minute_goal.png"
            approved.parent.mkdir(parents=True,exist_ok=True)
            Image.new("RGBA",(691,753),(9,21,36,255)).save(approved)
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            metadata={
                "original_source_sha256":digest(new_source),
                "approved_png_sha256":digest(approved),
                "human_visual_approved":True,
                "telegram_android_qa_approved":True,
            }
            approved.with_suffix(".json").write_text(json.dumps(metadata))
            key="NETRATTLER_APPROVED_MASTER_LAST_MINUTE_GOAL"
            with patch.dict(os.environ,{},clear=True):
                self.assertFalse(audit(work)["last_minute_goal"]["approved_for_telegram"])
            with patch.dict(os.environ,{key:"0"*64}):
                self.assertFalse(audit(work)["last_minute_goal"]["approved_for_telegram"])
            with patch.dict(os.environ,{key:digest(approved)}):
                self.assertTrue(audit(work)["last_minute_goal"]["approved_for_telegram"])
                approved.write_text("<svg>not genuine PNG</svg>")
                self.assertFalse(audit(work)["last_minute_goal"]["approved_for_telegram"])


if __name__=="__main__":
    unittest.main(verbosity=2)
