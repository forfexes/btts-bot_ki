import importlib.util, pathlib, sys

_spec = importlib.util.spec_from_file_location("bot_odds_band", pathlib.Path(__file__).with_name("btts_bot.py"))
bot = importlib.util.module_from_spec(_spec); sys.modules["bot_odds_band"] = bot; _spec.loader.exec_module(bot)


def test_odds_band_loosened_below_190_but_loss_zone_stays_blocked():
    ok = bot.odds_band_policy_ok
    assert ok("over25", 61.0, 1.893) and ok("over25", 60.0, 1.73) and ok("over25", 59.0, 1.87)
    assert not ok("over25", 57.0, 1.80)            # unter Mindest-Prob
    assert not ok("over25", 59.0, 2.13)            # Verlustzone 1.90-2.19
    assert not ok("over25", 70.0, 1.95)
    assert ok("over25", 60.0, 2.30) and ok("btts", 50.0, 1.5)
