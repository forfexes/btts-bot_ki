"""User owner-original artwork may not be screenshot-repainted by default.

QA previews deliberately opt in with NETRATTLER_BLOCK_OVERPAINTED_MASTERS=0.
Real Telegram publication and historical image edits must fail closed if the
release flag is unset, mistyped, or set to 1. This test is network-free.
"""
import os
import unittest
from unittest.mock import patch

import netrattler_btts_owner_original as btts
import netrattler_combo_owner_original as combo
import netrattler_original_template_renderer as original
import netrattler_stats_match_cards as cards


def disallowed_calls():
    return (
        (btts.render, (None,"HOME","AWAY",None,None,2.0), {}),
        (combo.render_original_combo, ([],), {
            "combined_odds":2.2,"probability":0.7,"ev":0.1,
            "confidence":80,"stake":1.0,
            "combined_odds_observed":True,
            "combined_quote_id":"TEST-NOT-A-BOOKMAKER",
            "bookmaker":"QA","crest_provider":None,
        }),
        (original.render_builder, (None,), {}),
        (original.render_goal, (None,None), {}),
        (cards.render_card, ([],None), {}),
    )


class NoScreenshotOverpaint(unittest.TestCase):
    def test_unset_config_blocks_every_legacy_direct_entrypoint(self):
        # Even a direct Python call must not bypass the Telegram adapter.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NETRATTLER_BLOCK_OVERPAINTED_MASTERS",None)
            for func,args,kwargs in disallowed_calls():
                with self.subTest(function=func.__qualname__), self.assertRaises(ValueError):
                    func(*args,**kwargs)
            notices=[]
            self.assertEqual(cards.update_cards_with_results(
                None,[],log=notices.append),0)
            # Edits stay deferred until the exact stadium master exists; once it is
            # deployed the call proceeds (and returns 0 here: no token/results).
            from netrattler_stadium_portrait import master_ready
            deferred = any("deferred" in x for x in notices)
            self.assertEqual(deferred, not master_ready())

    def test_mistyped_or_explicit_lock_remains_fail_closed(self):
        for flag in ("1","true","YES","", "off"):
            with patch.dict(os.environ,{"NETRATTLER_BLOCK_OVERPAINTED_MASTERS":flag}):
                for func,args,kwargs in disallowed_calls():
                    with self.subTest(flag=flag,func=func.__qualname__):
                        with self.assertRaises(ValueError):
                            func(*args,**kwargs)


if __name__=="__main__":
    unittest.main(verbosity=2)
