import ast
from pathlib import Path
import unittest
from netrattler_player_form import recent_form

class PlayerForm(unittest.TestCase):
    def test_observed_zero_and_short_history(self):
        self.assertIsNone(recent_form({'avg':2,'games':40}))
        self.assertIsNone(recent_form({'series':[1,1,None,1,1]}))
        self.assertEqual(recent_form({'series':[0]*10})['avg'],0)
        self.assertEqual(recent_form({'series':[1]*10+[0]*5})['l15_games'],15)
    def test_scorer_form_changes_selection(self):
        # Execute the actual scorer function with controlled history and real-price provenance.
        tree=ast.parse(Path('btts_bot.py').read_text())
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='analyze_scorer_tips')
        namespace = {'normalize_team_name': lambda s: str(s).lower(),
                     'get_supabase_player_avg_stats': lambda n: self.history,
                     'os': __import__('os'), 'requests': None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<scorer>', 'exec'), namespace)
        fixture = dict(home='Home', away='Away', home_id=1, away_id=2)
        scorers = [dict(name='Test Player', team_id=1, goals_per_game=1, goals_total=30)]
        quotes = [dict(player='Test Player', market='anytime goalscorer', odds=2.0,
                       home='Home', away='Away', source='pinnacle')]
        self.history = {'goals': {'series': [0]*10, 'avg': 1, 'games': 30}}
        self.assertEqual(namespace['analyze_scorer_tips'](fixture, 'League', scorers, quotes), [])
        self.history = {'goals': {'series': [1]*10, 'avg': .1, 'games': 30}}
        tips = namespace['analyze_scorer_tips'](fixture, 'League', scorers, quotes)
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0]['goals_per_game'], 1)
        self.assertEqual(tips[0]['form_games'], 10)
        self.history = {'goals': {'avg': 2, 'games': 40}}
        self.assertEqual(namespace['analyze_scorer_tips'](fixture, 'League', scorers, quotes), [])

    def test_builder_needs_measured_form(self):
        from netrattler_builder_engine import PropLeg, LEG_HISTORY, norm, weak_leg
        leg=PropLeg('Test Player', 'Home', 'Home vs Away', 'League', 'Shots 1+', 'shots', 1, 1.8, .7, 'pinnacle')
        key=(norm(leg.player),leg.category)
        try:
            LEG_HISTORY.pop(key,None)
            self.assertTrue(weak_leg(leg))
            LEG_HISTORY[key]=[1]*10
            self.assertFalse(weak_leg(leg))
            LEG_HISTORY[key]=[0]*10
            self.assertTrue(weak_leg(leg))
        finally: LEG_HISTORY.pop(key,None)

if __name__=='__main__':unittest.main()
