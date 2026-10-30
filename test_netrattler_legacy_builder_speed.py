"""Execute the actual legacy branch without importing the bot or using network."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


class LegacyBuilderSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('btts_bot.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'run_pinnacle_props_bot')
        cls.branch = next(n for n in fn.body if isinstance(n, ast.If)
                          and 'ENABLE_LEGACY_PINNACLE_BUILDER' in ast.unparse(n.test))
        cls.code = compile(ast.Module(body=[cls.branch], type_ignores=[]), '<legacy>', 'exec')

    def execute(self, enabled):
        quote = Mock(return_value={})
        legs = [dict(selection='A', player_prop='A shots', _cat='shots', prob=60, odds=1.8),
                dict(selection='B', player_prop='B sot', _cat='sot', prob=60, odds=1.8)]
        pool = [dict(player='A', odds=1.8)]
        ctx = dict(env=lambda name, default='': enabled, valid=legs,
                   builders=[], _wc_matches=set(), log=Mock(),
                   get_pinnacle_match_odds=quote, _calc_combo_odds=lambda legs: 3.24,
                   _NTR_BUILDER_PROP_POOL=pool)
        for row in legs:
            row['match'] = 'Home vs Away'
        exec(self.code, ctx)
        self.assertEqual(pool, [dict(player='A', odds=1.8)])
        return ctx, quote

    def test_disabled_does_not_fetch_unused_quotes_or_build(self):
        for setting in ('false', '0', ''):
            with self.subTest(setting=setting):
                ctx, quote = self.execute(setting)
                quote.assert_not_called()
                self.assertEqual(ctx['builders'], [])

    def test_explicit_legacy_opt_in_still_builds(self):
        for setting in ('true', '1', 'yes', 'on'):
            with self.subTest(setting=setting):
                ctx, quote = self.execute(setting)
                quote.assert_called_once_with('Home', 'Away')
                self.assertEqual(len(ctx['builders']), 1)
                self.assertEqual(len(ctx['builders'][0]['legs']), 2)


if __name__ == '__main__':
    unittest.main()
