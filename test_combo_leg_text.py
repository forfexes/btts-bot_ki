import unittest
import btts_bot as b

class T(unittest.TestCase):
    def test_raw_provider_text_cleaned(self):
        t = ("Razvan Marin shots (Settled using Opta data) | Player's shots (Settled using Opta data) "
             "| Player Occurrence Line Over 0.5")
        out = b._clean_combo_leg_text(t)
        self.assertEqual(out, "Razvan Marin — Schüsse Über 0.5")
        self.assertNotIn("Opta", out)

    def test_sot_and_plain_untouched(self):
        t = "X Y shots on target (Settled using Opta data) | Player Occurrence Line Over 1.5"
        self.assertEqual(b._clean_combo_leg_text(t), "X Y — Schüsse aufs Tor Über 1.5")
        self.assertEqual(b._clean_combo_leg_text("Over 2.5"), "Over 2.5")
        self.assertEqual(b._clean_combo_leg_text("Over 7.5 Ecken"), "Over 7.5 Ecken")

if __name__ == "__main__":
    unittest.main()
