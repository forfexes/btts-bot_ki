#!/usr/bin/env python3
"""NETRATTLER source-health/runtime telemetry.

Dependency-free helper for bounded source calls and compact diagnostics.
It does not synthesize odds and does not alter REAL_ODDS_ONLY semantics.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class SourceHealth:
    source: str
    status: str
    rows: int
    elapsed_ms: int
    detail: str = ""


def classify_exception(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return "rate_limited"
    if "403" in text or "forbidden" in text:
        return "blocked"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "error"


def row_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    try:
        return len(value)
    except (TypeError, AttributeError):
        return 1


def run_source(
    source: str,
    func: Callable[..., Any],
    *args: Any,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> tuple[Any, SourceHealth]:
    """Run one source with a hard wall-clock budget and classify its result."""
    budget = float(timeout or os.getenv("NETRATTLER_SOURCE_TIMEOUT", "8"))
    started = time.monotonic()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args, **kwargs)
    try:
        value = future.result(timeout=max(0.05, budget))
        rows = row_count(value)
        status = "ok" if rows else "empty"
        health = SourceHealth(source, status, rows, int((time.monotonic() - started) * 1000))
        return value, health
    except concurrent.futures.TimeoutError:
        future.cancel()
        health = SourceHealth(source, "budget_exceeded", 0, int((time.monotonic() - started) * 1000), f"budget={budget:g}s")
        return None, health
    except BaseException as exc:
        health = SourceHealth(source, classify_exception(exc), 0, int((time.monotonic() - started) * 1000), str(exc)[:240])
        return None, health
    finally:
        # wait=False is essential: a timed-out source must not stall the caller.
        executor.shutdown(wait=False, cancel_futures=True)


def format_health(health: SourceHealth) -> str:
    detail = f" detail={health.detail}" if health.detail else ""
    return f"SOURCE_HEALTH source={health.source} status={health.status} rows={health.rows} ms={health.elapsed_ms}{detail}"


def health_dict(health: SourceHealth) -> Dict[str, Any]:
    return asdict(health)


def dump_health(path: str, records: list[SourceHealth]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([health_dict(x) for x in records], handle, ensure_ascii=False, indent=2)
