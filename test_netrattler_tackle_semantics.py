import netrattler_ml_player as ml


def test_received_tackles_never_uses_committed_classifier():
    assert not ml._LINE_MODELS.get('tackles_received')
    assert ml.model_for('tackles_received',.5) is None
    assert ml.model_for('tackles_committed',.5)=='player_tackles_over05_model'


def test_received_tackles_requires_its_own_observations():
    committed={'tackles':{'avg':2.5,'games':10}}
    assert ml.empirical_player_prop_probability(committed,'tackles_received',.5) is None
    assert ml.empirical_player_prop_probability(committed,'tackles_committed',.5) is not None
    actual={**committed,'tackles_received':{'avg':.5,'games':10}}
    p=ml.empirical_player_prop_probability(actual,'tackles_received',.5)
    assert p is not None
    assert p==ml.empirical_player_prop_probability({'tackles_received':actual['tackles_received']},'tackles_received',.5)


def test_fouls_committed_and_won_are_distinct():
    assert ml.model_for('fouls',.5)!=ml.model_for('fouls_won',.5)
    assert ml.empirical_player_prop_probability({'fouls_committed':{'avg':2,'games':10}},'fouls_won',.5) is None
