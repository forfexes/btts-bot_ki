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
    ]
    for path in critical:
        py_compile.compile(path, doraise=True)

    import test_netrattler_source_health as source_health
    import test_netrattler_builder_guard as builder_guard

    source_health.main()
    builder_guard.main()
    print("OK: NETRATTLER consolidated hardtest passed")


if __name__ == "__main__":
    main()
