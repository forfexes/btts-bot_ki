#!/usr/bin/env python3
"""Consolidated offline NETRATTLER safety hardtest. No network calls."""
from __future__ import annotations

import py_compile


def main():
    critical = [
        "netrattler_source_health.py",
        "netrattler_builder_guard.py",
        "netrattler_prop_sources.py",
        "netrattler_builder_engine.py",
        "netrattler_builder_styles.py",
        "test_netrattler_source_health.py",
        "test_netrattler_builder_guard.py",
        "test_netrattler_builder_styles.py",
    ]
    for path in critical:
        py_compile.compile(path, doraise=True)

    # Order matters: source/runtime safety first, then REAL_ODDS/semantic guard,
    # finally the screenshot-derived Builder concepts installed over the engine.
    import test_netrattler_source_health as source_health
    import test_netrattler_builder_guard as builder_guard
    import test_netrattler_builder_styles as builder_styles

    source_health.main()
    builder_guard.main()
    builder_styles.main()
    print("OK: NETRATTLER consolidated hardtest passed (source health + REAL_ODDS guard + Builder concepts)")


if __name__ == "__main__":
    main()
