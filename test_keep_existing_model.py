import train_model as tm


def test_no_skill_does_not_overwrite_skilled():
    assert tm._keep_existing_model({"model_name": "x", "no_skill": True}, existing={"no_skill": False})


def test_skilled_new_model_saved():
    assert not tm._keep_existing_model({"model_name": "x", "no_skill": False}, existing={"no_skill": False})


def test_no_skill_saved_when_nothing_better_exists():
    assert not tm._keep_existing_model({"model_name": "x", "no_skill": True}, existing={"no_skill": True})
