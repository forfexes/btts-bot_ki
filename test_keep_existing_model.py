import sys
import types

# Schlanke CI ohne ML-Pakete: fehlende Module stubben (nur _keep_existing_model wird getestet).
for _name, _attrs in {
    "xgboost": [],
    "sklearn": [],
    "sklearn.model_selection": ["TimeSeriesSplit", "StratifiedKFold"],
    "sklearn.calibration": ["CalibratedClassifierCV"],
    "sklearn.metrics": ["brier_score_loss", "roc_auc_score"],
}.items():
    try:
        __import__(_name)
        continue
    except ImportError:
        sys.modules.pop(_name, None)
        _m = types.ModuleType(_name)
        for _a in _attrs:
            setattr(_m, _a, object)
        sys.modules[_name] = _m

import train_model as tm


def test_no_skill_does_not_overwrite_skilled():
    assert tm._keep_existing_model({"model_name": "x", "no_skill": True}, existing={"no_skill": False})


def test_skilled_new_model_saved():
    assert not tm._keep_existing_model({"model_name": "x", "no_skill": False}, existing={"no_skill": False})


def test_no_skill_saved_when_nothing_better_exists():
    assert not tm._keep_existing_model({"model_name": "x", "no_skill": True}, existing={"no_skill": True})
