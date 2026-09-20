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


def test_telegram_429(bot):
    os.environ["NETRATTLER_TELEGRAM_CHAT_INTERVAL_SEC"] = "0"
    os.environ["NETRATTLER_TELEGRAM_429_RETRIES"] = "2"
    bot.TELEGRAM_TOKEN = "T"
    bot.TELEGRAM_CHAT_ID = "1"
    bot._ntr_enhance_message_with_stats = lambda text, chat: text
    bot._ntr_strip_duplicate_group_footer = lambda text: text
    sleeps = []

    class R429:
        ok = False
        status_code = 429
        text = 'Too Many Requests: retry after 1'
        def json(self):
            return {"ok": False, "parameters": {"retry_after": 1}}

    class R200:
        ok = True
        status_code = 200
        text = "ok"
        def json(self):
            return {"result": {"message_id": 77, "chat": {"id": 1}}}

    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs.get("json"))
        return R429() if len(calls) == 1 else R200()
    bot.requests.post = post

    import time
    real_sleep = time.sleep
    time.sleep = lambda s: sleeps.append(s)
    try:
        mid = bot.send_telegram("hello", "1")
    finally:
        time.sleep = real_sleep
    assert mid == 77
    assert len(calls) == 2
    assert any(s >= 2 for s in sleeps), sleeps


def test_multi_combo_sanity(bot):
    bad = [
        {"match":"A vs B","market":"corners","tip":"Over 8.5 Ecken","selection":"Over 8.5 Ecken","line":8.5,"probability":61,"odds":255.0,"confidence":3,"_no_real_odds":False},
        {"match":"C vs D","market":"btts","tip":"YES","probability":62,"odds":1.9,"confidence":3,"_no_real_odds":False},
        {"match":"E vs F","market":"over25","tip":"YES","probability":63,"odds":1.95,"confidence":3,"_no_real_odds":False},
    ]
    assert bot.generate_multi_combo_bets(bad, 3) is None

    good = [
        {"match":"A vs B","market":"corners","tip":"Over 8.5 Ecken","selection":"Over 8.5 Ecken","line":8.5,"probability":61,"odds":2.55,"confidence":3,"_no_real_odds":False},
        {"match":"C vs D","market":"btts","tip":"YES","probability":62,"odds":1.9,"confidence":3,"_no_real_odds":False},
        {"match":"E vs F","market":"over25","tip":"YES","probability":63,"odds":1.95,"confidence":3,"_no_real_odds":False},
    ]
    combo = bot.generate_multi_combo_bets(good, 3)
    assert combo is not None
    assert combo["total_odds"] < 20
    msg = bot.format_combo_telegram_message(combo)
    assert "Over 8.5 Ecken @ 2.55" in msg


def test_player_model_batch_loader(ml):
    ml._MODEL_CACHE.clear()
    ml._LOADED = False
    ml._LAST_LOAD_ERROR = ""
    wanted = ml._ALL_PLAYER_MODELS[:4]
    blob = base64.b64encode(pickle.dumps({"model": "dummy"})).decode("ascii")
    calls = []

    class Resp:
        ok = True
        status_code = 200
        text = ""
        def __init__(self, rows): self._rows = rows
        def json(self): return self._rows

    def get(url, headers=None, params=None, timeout=None):
        calls.append((params, timeout))
        raw = params["model_name"]
        names = raw[len("in.("):-1].split(",")
        return Resp([{"model_name": n, "model_data": blob} for n in names])

    ml.requests.get = get
    count = ml.load_player_models("https://x.supabase.co", "k", timeout=20, model_names=wanted, batch_size=2)
    assert count == 4
    assert len(calls) == 2
    assert all(c[1] >= 10 for c in calls)
    assert ml.player_model_load_status()["error"] == ""


def test_builder_sanity_and_send_commit(builder):
    # absurd team-market price is rejected at normalization
    bad = {
        "player":"Over 2.5", "team":"A", "match":"A vs B", "league":"T",
        "market":"Over 2.5", "category":"match_goals", "line":2.5,
        "odds":145.0, "source":"kambi", "probability":0.6,
    }
    assert builder.normalize_prop(bad) is None

    # Standard match builders are capped even with individually sane quotes.
    leg1 = builder.PropLeg("BTTS","A","A vs B","T","BTTS","btts",0.5,6.0,0.7,"pinnacle")
    leg2 = builder.PropLeg("Over","A","A vs B","T","Over","match_goals",2.5,10.0,0.7,"kambi")
    assert builder._make_builder("MATCH BUILDER","SAFE",[leg1,leg2],"2026-09-20") is not None  # 60 <= 75
    leg3 = builder.PropLeg("Over","A","A vs B","T","Over","match_goals",2.5,10.0,0.7,"kambi")
    leg4 = builder.PropLeg("Result","A","A vs B","T","1","result",0.5,8.0,0.7,"pinnacle")
    assert builder._make_builder("MATCH BUILDER","VALUE",[leg1,leg3,leg4],"2026-09-20") is None

    pick = builder.BuilderPick("id1","TEST","SAFE",[leg1,leg2],60.0,0.1,False,"2026-09-20")
    builder.deduplicate_props = lambda raw: []
    builder.build_builder_picks = lambda *a, **k: [pick]
    posts = []

    class GetResp:
        ok=True
        def json(self): return []
    class PostResp:
        status_code=201
    builder.requests.get = lambda *a, **k: GetResp()
    builder.requests.post = lambda *a, **k: posts.append(1) or PostResp()

    sent, _ = builder.run_builder_engine([], lambda msg: None, supabase_url="https://x", supabase_key="k")
    assert sent == 0 and posts == []
    sent, _ = builder.run_builder_engine([], lambda msg: 123, supabase_url="https://x", supabase_key="k")
    assert sent == 1 and len(posts) == 1


def test_static_contracts():
    text = (ROOT / "btts_bot.py").read_text(encoding="utf-8")
    assert 'btts_over25_combo_model", "btts_over25_combo_pct' in text
    assert 'get("over15_ht_pct")' in text
    assert 'get("btts_ht_pct")' in text
    assert 'if msg_id is None:' in text
    assert 'if _combo_mid is None:' in text


def main():
    bot = load("step2_bot", "btts_bot.py")
    builder = load("step2_builder", "netrattler_builder_engine.py")
    ml = load("netrattler_ml_player", "netrattler_ml_player.py")
    test_telegram_429(bot)
    test_multi_combo_sanity(bot)
    test_player_model_batch_loader(ml)
    test_builder_sanity_and_send_commit(builder)
    test_static_contracts()
    print("OK: NETRATTLER STABILITY STEP2 tests passed")


if __name__ == "__main__":
    main()
