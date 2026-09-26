#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def test_settlement_routes():
    fake = types.ModuleType("netrattler_settlement_v16_final")
    fake.TG_DEFAULT = "AI"
    fake.GROUPS = {"1x2": "LATE", "scorer": "LATE", "btts_ht": "HT", "over15_ht": "OTHER"}
    fake.send_roi_report = lambda _history: "old-global-report"
    fake.main = lambda: None
    old = sys.modules.get("netrattler_settlement_v16_final")
    sys.modules["netrattler_settlement_v16_final"] = fake
    try:
        path = Path(__file__).resolve().parent / "netrattler_settlement_runner.py"
        spec = importlib.util.spec_from_file_location("_settlement_runner_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        module.install_routing()
        assert fake.GROUPS["1x2"] == "AI"
        assert fake.GROUPS["scorer"] == "LATE"
        assert fake.GROUPS["over15_ht"] == "HT"
        assert fake.send_roi_report([]) is None
    finally:
        if old is None:
            sys.modules.pop("netrattler_settlement_v16_final", None)
        else:
            sys.modules["netrattler_settlement_v16_final"] = old


def main():
    test_settlement_routes()
    print("OK: 1X2 -> AI, HT shared group, no mixed global ROI report")


if __name__ == "__main__":
    main()
