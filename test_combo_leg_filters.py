import os
import netrattler_builder_guard as g


class Bot:
    def __init__(self):
        self.seen = None
    def generate_multi_combo_bets(self, tips, num_tips=3):
        self.seen = list(tips)
        return {"tips": list(tips)}
    def log(self, *_a):
        pass


def tip(match, market, odds, prob=0.7, **k):
    t = {"match": match, "market": market, "odds": odds, "probability": prob, "selection": market + match}
    t.update(k); return t


def run(tips, n=3):
    g._player_prop_combo_candidates = lambda bot: []
    bot = Bot()
    g._install_multi_combo_guard(bot)
    return bot, bot.generate_multi_combo_bets(tips, num_tips=n)


def test_blocked_groups_and_fantasy_odds_excluded():
    tips = [tip("A vs B", "over25", 1.7), tip("C vs D", "btts", 1.8), tip("E vs F", "corners", 1.9),
            tip("G vs H", "over15_ht", 2.9), tip("I vs J", "btts_ht", 2.5), tip("K vs L", "1x2", 116.0)]
    bot, res = run(tips)
    markets = {t["market"] for t in bot.seen}
    assert markets == {"over25", "btts", "corners"}
    assert res is not None


def test_too_few_clean_legs_returns_none():
    tips = [tip("A vs B", "over25", 1.7), tip("G vs H", "over15_ht", 2.9), tip("K vs L", "1x2", 116.0)]
    bot, res = run(tips)
    assert res is None


def test_sane_1x2_kept():
    tips = [tip("A vs B", "over25", 1.7), tip("C vs D", "1x2", 2.1), tip("E vs F", "btts", 1.8)]
    bot, res = run(tips)
    assert res is not None and {t["market"] for t in bot.seen} == {"over25", "1x2", "btts"}


def test_combo_leg_pool_rows_accepted():
    # Form der Zeilen aus _NTR_COMBO_LEG_POOL (Prozent-Wkt, oddsYes, _combo_leg_only)
    rows = [{"match": m, "market": mk, "tip": "YES", "selection": "YES", "probability": 62.0,
             "oddsYes": 1.75, "odds": 1.75, "_no_real_odds": False, "_combo_leg_only": True}
            for m, mk in (("A vs B", "over25"), ("C vs D", "btts"), ("E vs F", "over25"))]
    bot, res = run(rows)
    assert res is not None and len(bot.seen) == 3


def test_downstream_exclusions_cannot_crowd_out_four_valid_matches():
    class ProductionLike(Bot):
        def _multi_combo_allowed_markets(self):return {'btts','over25','corners','1x2'}
        def generate_multi_combo_bets(self,tips,num_tips=3):
            self.seen=list(tips)
            valid=[r for r in tips if r['market'] in self._multi_combo_allowed_markets()]
            return {'tips':valid} if len(valid)>=num_tips else None
    bot=ProductionLike()
    g._player_prop_combo_candidates=lambda bot:[]
    g._install_multi_combo_guard(bot)
    rows=[tip('A vs B','scorer',3,.9,player='Striker')]+[
        tip(f'Home{i} vs Away{i}',market,1.8,.7)
        for i,market in enumerate(['btts','over25','corners','1x2'])]
    result=bot.generate_multi_combo_bets(rows,4)
    assert result and len(result['tips'])==4
    assert all(r['market']!='scorer' for r in bot.seen)
