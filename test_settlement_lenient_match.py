"""Lenient result matching: fixes real-world naming/timezone gaps, never mixes men/women/ambiguous."""
import importlib.util, pathlib, unittest

spec = importlib.util.spec_from_file_location("sett", pathlib.Path(__file__).resolve().parent / "netrattler_settlement_v16_final.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def res(h, a, hs, aw, d, league="", src="fotmob"):
    return {"home_team": h, "away_team": a, "home_score": hs, "away_score": aw, "match_date": d, "league": league, "source": src}


def tip(match, d, league=""):
    return {"match": match, "match_date": d, "league": league}


class Lenient(unittest.TestCase):
    def test_club_prefix_suffix(self):
        r = mod.find_result(tip("Casertana FC vs SS Monopoli", "2026-10-10", "Italy - Serie C, Group C"),
                            [res("Casertana", "Monopoli", 3, 1, "2026-10-10", "Serie C")])
        self.assertEqual((r["home_score"], r["away_score"]), (3, 1))

    def test_long_official_name(self):
        r = mod.find_result(tip("Kayserispor vs Manisa", "2026-10-09"),
                            [res("Kayserispor", "Manisa Futbol Kulübü", 3, 2, "2026-10-09")])
        self.assertIsNotNone(r)

    def test_plus_one_day_timezone(self):
        r = mod.find_result(tip("Tractor vs Al-Shamal", "2026-10-11"),
                            [res("Tractor", "Al-Shamal", 0, 0, "2026-10-12")])
        self.assertIsNotNone(r)

    def test_women_tip_never_gets_men_result(self):
        r = mod.find_result(tip("Tokyo Verdy Beleza vs Sanfrecce Hiroshima Regina", "2026-10-11", "Japan - League Cup Women"),
                            [res("Tokyo Verdy", "Sanfrecce Hiroshima", 0, 2, "2026-10-11", "J.League Cup")])
        self.assertIsNone(r)

    def test_conflicting_scores_stay_unsettled(self):
        r = mod.find_result(tip("Casertana FC vs SS Monopoli", "2026-10-10"),
                            [res("Casertana", "Monopoli", 3, 1, "2026-10-10"),
                             res("Casertana", "Monopoli", 2, 1, "2026-10-10", src="espn")])
        self.assertIsNone(r)

    def test_agreeing_sources_settle(self):
        r = mod.find_result(tip("Casertana FC vs SS Monopoli", "2026-10-10"),
                            [res("Casertana", "Monopoli", 3, 1, "2026-10-10"),
                             res("Casertana FC", "SS Monopoli", 3, 1, "2026-10-10", src="espn")])
        self.assertIsNotNone(r)

    def test_wrong_opponent_not_matched(self):
        r = mod.find_result(tip("Casertana FC vs SS Monopoli", "2026-10-10"),
                            [res("Casertana", "Foggia", 3, 1, "2026-10-10")])
        self.assertIsNone(r)

    def test_two_days_off_not_matched(self):
        r = mod.find_result(tip("Casertana FC vs SS Monopoli", "2026-10-10"),
                            [res("Casertana", "Monopoli", 3, 1, "2026-10-13")])
        self.assertIsNone(r)


class HalfTime(unittest.TestCase):
    TIP = {"market": "over15_ht", "market_name": "Over 1.5 HT", "tip": "Over 1.5 Tore HT", "match": "A vs B", "date": "2026-10-10"}

    def test_ht_from_match_results_columns(self):
        self.assertEqual(mod.settle_score_market(self.TIP, {"home_score": 2, "away_score": 1, "raw": {"ht_home": 1, "ht_away": 1, "source": "thesportsdb"}})[0], "win")
        self.assertEqual(mod.settle_score_market(self.TIP, {"home_score": 2, "away_score": 1, "raw": {"ht_home": 0, "ht_away": 1, "source": "thesportsdb"}})[0], "loss")

    def test_fotmob_ht_not_trusted(self):
        r = {"home_score": 2, "away_score": 1, "result_source": "fotmob", "raw": {"ht_home": 0, "ht_away": 0, "source": "fotmob"}}
        self.assertEqual(mod.settle_score_market(self.TIP, r)[0], "pending")

    def test_missing_ht_stays_pending(self):
        self.assertEqual(mod.settle_score_market(self.TIP, {"home_score": 2, "away_score": 1, "raw": {}})[0], "pending")


if __name__ == "__main__":
    unittest.main()
