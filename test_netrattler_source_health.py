#!/usr/bin/env python3
"""Offline hard tests for NETRATTLER source-health guard."""
from __future__ import annotations

import time
from netrattler_source_health import classify_exception, run_source


def test_ok_and_empty():
    value, health = run_source("ok", lambda: [1, 2, 3], timeout=0.5)
    assert value == [1, 2, 3]
    assert health.status == "ok" and health.rows == 3
    value, health = run_source("empty", lambda: [], timeout=0.5)
    assert value == []
    assert health.status == "empty" and health.rows == 0


def test_error_classification():
    assert classify_exception(RuntimeError("HTTP 403 Forbidden")) == "blocked"
    assert classify_exception(RuntimeError("HTTP 429 Too Many Requests")) == "rate_limited"
    assert classify_exception(TimeoutError("timed out")) == "timeout"
    assert classify_exception(ValueError("bad parser")) == "error"


def test_budget_is_non_blocking():
    started = time.monotonic()
    value, health = run_source("slow", lambda: time.sleep(0.5), timeout=0.05)
    elapsed = time.monotonic() - started
    assert value is None
    assert health.status == "budget_exceeded"
    assert elapsed < 0.25, elapsed


def test_real_data_is_not_mutated():
    payload = [{"odds": 2.10, "source": "pinnacle", "line": 2.5}]
    value, health = run_source("pinnacle", lambda: payload, timeout=0.5)
    assert value is payload
    assert value[0]["odds"] == 2.10
    assert health.rows == 1


def main():
    test_ok_and_empty()
    test_error_classification()
    test_budget_is_non_blocking()
    test_real_data_is_not_mutated()
    print("OK: NETRATTLER source-health hard tests passed")


if __name__ == "__main__":
    main()
