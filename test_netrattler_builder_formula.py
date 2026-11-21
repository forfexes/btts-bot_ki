"""Builder formula integration for goals/shots/fouls/tackles and model-only picks."""
from types import SimpleNamespace as N
import math
from netrattler_builder_engine import builder_formula


def leg(game, p, odds=None):
    return N(match=game,probability=p,odds=odds)

def test_builder_same_match_requires_joint_evidence():
    b=N(legs=[leg("FC Test vs AC Test",0.75,1.9),
              leg("FC Test vs AC Test",0.70,2.1)])
    model=builder_formula(b)
    assert model["scope"]=="shared_game_correlated"
    assert model["fair_model_odds"] is None
    assert model["indicative_leg_product"]==3.99

def test_builder_conditional_model_has_fair_odds_not_fake_ticket():
    b=N(legs=[leg("FC Test vs AC Test",0.75,1.9),
              leg("FC Test vs AC Test",0.70,2.1)])
    model=builder_formula(b,conditional_probabilities=[0.8])
    assert math.isclose(model["joint_probability"],0.6)
    assert math.isclose(model["fair_model_odds"],5/3)
    assert model["ev_percent_using_real_ticket_only"] is None

def test_builder_model_only_unpriced_uses_real_observed_probs():
    b=N(legs=[leg("FC Test vs AC Test",0.70),
              leg("AC A vs FC B",0.50)])
    model=builder_formula(b)
    assert model["indicative_leg_product"] is None
    assert math.isclose(model["joint_probability"],0.35)
    assert math.isclose(model["fair_model_odds"],1/0.35)
