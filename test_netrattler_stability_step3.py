#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import io
import os
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, "/mnt/data")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_combo_uses_dedicated_model_gate(bot):
    # Components can sit below the 58% single-market gates.  The dedicated combo
    # model + observed combined price decides, with a light 48% plausibility floor.
    assert bot._ntr_combo_candidate_ok(2.50, 55, 52, 51) is True
    assert bot._ntr_combo_candidate_ok(2.50, 55, 47, 60) is False
    assert bot._ntr_combo_candidate_ok(0, 70, 60, 60) is False


def test_special_lookup_uses_ht_models(bot):
    assert bot._ntr_special_lookup_eligible(50, 50, {"btts_ht_pct": 40}) is True
    assert bot._ntr_special_lookup_eligible(50, 50, {"over15_ht_pct": 43}) is True
    assert bot._ntr_special_lookup_eligible(50, 50, {"btts_over25_combo_pct": 53}) is True
    assert bot._ntr_special_lookup_eligible(40, 40, {}) is False


def test_kambi_special_parser(src):
    offer = {
        "betOffers": [
            {
                "criterion": {"label": "Both Teams To Score - 1st Half"},
                "outcomes": [{"label": "Yes", "odds": 2300}],
            },
            {
                "criterion": {"label": "Total Goals - First Half"},
                "outcomes": [{"label": "Over", "type": "O", "line": 1500, "odds": 1950}],
            },
            {
                "criterion": {"label": "Both Teams To Score & Total Goals"},
                "outcomes": [{"label": "Yes & Over", "line": 2500, "odds": 2800}],
            },
        ]
    }
    out = src._extract_kambi_team_specials(offer)
    assert out["btts_yes_ht"] == 2.3, out
    assert out["over_15_ht"] == 1.95, out
    assert out["btts_over25_combo"] == 2.8, out


def test_combo_cap_uses_existing_workflow_env(bot):
    old_total = os.environ.pop("NETRATTLER_MULTI_COMBO_MAX_TOTAL_ODDS", None)
    old_existing = os.environ.get("NETRATTLER_MULTI_COMBO_MAX_ODDS")
    os.environ["NETRATTLER_MULTI_COMBO_MAX_ODDS"] = "10"
    try:
        rows = [
            {"match":"A vs B","market":"btts","tip":"YES","probability":70,"odds":2.0,"confidence":3,"_no_real_odds":False},
            {"match":"C vs D","market":"over25","tip":"YES","probability":70,"odds":2.0,"confidence":3,"_no_real_odds":False},
            {"match":"E vs F","market":"corners","tip":"Over 8.5 Ecken","selection":"Over 8.5 Ecken","line":8.5,"probability":70,"odds":3.0,"confidence":3,"_no_real_odds":False},
        ]
        assert bot.generate_multi_combo_bets(rows, 3) is None  # total 12 > cap 10
    finally:
        if old_total is not None:
            os.environ["NETRATTLER_MULTI_COMBO_MAX_TOTAL_ODDS"] = old_total
        else:
            os.environ.pop("NETRATTLER_MULTI_COMBO_MAX_TOTAL_ODDS", None)
        if old_existing is not None:
            os.environ["NETRATTLER_MULTI_COMBO_MAX_ODDS"] = old_existing
        else:
            os.environ.pop("NETRATTLER_MULTI_COMBO_MAX_ODDS", None)


def test_player_ml_single_row_fallback(ml):
    ml._MODEL_CACHE.clear()
    ml._LOADED = False
    ml._LAST_LOAD_ERROR = ""
    wanted = ml._ALL_PLAYER_MODELS[:2]
    blob = base64.b64encode(pickle.dumps({"model": "dummy"})).decode("ascii")
    calls = []

    class Resp:
        ok = True
        status_code = 200
        text = ""
        def __init__(self, rows): self._rows = rows
        def json(self): return self._rows

    def get(url, headers=None, params=None, timeout=None):
        calls.append((dict(params or {}), timeout))
        filt = params.get("model_name", "")
        if filt.startswith("in."):
            return Resp([])  # simulate batch path returning no model rows
        assert filt.startswith("eq.")
        name = filt[3:]
        return Resp([{"model_name": name, "model_data": blob}])

    ml.requests.get = get
    count = ml.load_player_models("https://x.supabase.co", "k", timeout=10, model_names=wanted, batch_size=2)
    assert count == 2, ml.player_model_load_status()
    assert any(c[0].get("model_name", "").startswith("eq.") for c in calls)
    assert ml.player_model_load_status()["error"] == ""


def test_corner_routing_and_source_text(bot):
    text = Path(ROOT / "btts_bot.py").read_text(encoding="utf-8")
    assert 'group_corners = TELEGRAM_GROUPS.get("corners")' in text
    assert 'ENABLE_TEAM_LEGS_IN_PROP_BUILDER", "false"' in text
    msg = bot.format_corners_message({
        "match":"A vs B", "league":"Test", "time":"20:00", "tip":"Over 8.5 Ecken",
        "line":8.5, "probability":60, "odds":2.1, "fair_odds":1.67,
        "confidence":3, "valueRating":"VALUE", "units":1, "expected_corners":10.2,
        "_source":"kambi_ub",
    })
    assert "Over 8.5 Ecken" in msg
    assert "kambi ub" in msg.lower()


def main():
    bot = load("step3_bot", "btts_bot.py")
    src = load("step3_sources", "netrattler_prop_sources.py")
    ml = load("step3_ml", "netrattler_ml_player.py")
    test_combo_uses_dedicated_model_gate(bot)
    test_special_lookup_uses_ht_models(bot)
    test_kambi_special_parser(src)
    test_combo_cap_uses_existing_workflow_env(bot)
    test_player_ml_single_row_fallback(ml)
    test_corner_routing_and_source_text(bot)
    print("OK: NETRATTLER STABILITY STEP3 tests passed")


if __name__ == "__main__":
    main()
