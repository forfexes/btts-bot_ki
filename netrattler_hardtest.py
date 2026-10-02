#!/usr/bin/env python3
"""Consolidated offline NETRATTLER safety hardtest. No network calls."""
from __future__ import annotations

import py_compile
import unittest


def main():
    critical = [
        "netrattler_source_health.py",
        "netrattler_builder_guard.py",
        "netrattler_prop_sources.py",
        "netrattler_runtime_patch.py",
        "netrattler_builder_engine.py",
        "netrattler_builder_styles.py",
        "netrattler_builder_concepts_v2.py",
        "netrattler_result_enrichment.py",
        "netrattler_fotmob_results.py",
        "netrattler_settlement_runner.py",
        "test_netrattler_source_health.py",
        "test_netrattler_builder_guard.py",
        "test_netrattler_builder_styles.py",
        "test_netrattler_builder_concepts_v2.py",
        "test_netrattler_runtime_patch.py",
        "test_netrattler_result_enrichment.py",
        "test_netrattler_fotmob_results.py",
        "test_netrattler_settlement_runner.py",
        "test_netrattler_settlement_v21.py",
    ]
    for path in critical:
        py_compile.compile(path, doraise=True)

    # Order matters: source/runtime safety first, then REAL_ODDS/semantic guard,
    # then screenshot concepts and settlement/result parsers. All are offline.
    import test_netrattler_source_health as source_health
    import test_netrattler_builder_guard as builder_guard
    import test_netrattler_builder_styles as builder_styles
    import test_netrattler_runtime_patch as runtime_patch
    import test_netrattler_builder_concepts_v2 as builder_concepts
    import test_netrattler_oddspapi_keys as oddspapi_keys
    import test_netrattler_result_enrichment as result_enrichment
    import test_netrattler_fotmob_results as fotmob_results
    import test_netrattler_settlement_runner as settlement_runner
    import test_netrattler_settlement_v21 as settlement_v21

    source_health.main()
    builder_guard.main()
    builder_styles.main()
    oddspapi_keys.main()
    runtime_patch.main()
    builder_concepts.main()
    result_enrichment.main()
    fotmob_results.main()
    settlement_runner.main()

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(settlement_v21.SettlementV21Tests)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise SystemExit("NETRATTLER settlement V/X regression failed")

    print("OK: NETRATTLER consolidated hardtest passed (source health + REAL_ODDS guard + Builder concepts + routing + in-tip V/X settlement + result parsers)")


if __name__ == "__main__":
    main()
