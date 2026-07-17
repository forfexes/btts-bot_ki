#!/usr/bin/env python3
"""Reusable source fallback router with last-good cache and health audit."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from netrattler_learning_engine import SupabaseRest, stable_hash

CACHE_DIR = Path(os.getenv("NETRATTLER_SOURCE_CACHE_DIR", ".netrattler_cache"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{safe}.json"


def _write(path: Path, payload: Any) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, default=str)
        os.replace(tmp, path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def load_last_good(name: str, max_age_hours: float) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(_path(name).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(str(payload.get("saved_at")).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - saved).total_seconds() / 3600.0
        if age > max_age_hours:
            return []
        rows = [dict(row) for row in payload.get("rows") or [] if isinstance(row, Mapping)]
        for row in rows:
            row["cache_fallback"] = True
            row["cache_age_hours"] = round(age, 2)
        return rows
    except Exception:
        return []


def save_last_good(name: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if rows:
        _write(_path(name), {"saved_at": _utc(), "rows": [dict(row) for row in rows]})


@dataclass
class SourceResult:
    source: str
    status: str
    rows: List[Dict[str, Any]]
    latency_ms: int
    error: str = ""
    cached: bool = False


def run_source(
    source: str,
    fetch: Callable[[], Sequence[Mapping[str, Any]]],
    normalize: Optional[Callable[[Mapping[str, Any]], Optional[Dict[str, Any]]]] = None,
    max_cache_age_hours: float = 24.0,
    db: Optional[SupabaseRest] = None,
) -> SourceResult:
    started = time.monotonic()
    error = ""
    rows: List[Dict[str, Any]] = []
    try:
        raw = fetch() or []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            row = normalize(item) if normalize else dict(item)
            if row:
                rows.append(row)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    cached = False
    if rows:
        save_last_good(source, rows)
        status = "active"
    else:
        rows = load_last_good(source, max_cache_age_hours)
        cached = bool(rows)
        status = "cached" if cached else ("blocked" if error else "empty")
    latency = int((time.monotonic() - started) * 1000)
    db = db or SupabaseRest()
    if db.enabled:
        db.upsert("netrattler_source_tests", [{
            "test_id": stable_hash(source, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H"))[:40],
            "source_id": stable_hash(source)[:32], "status": status,
            "trust_score": 0.75 if status == "active" else 0.58 if status == "cached" else 0.20,
            "latency_ms": latency,
            "details": {"rows": len(rows), "error": error[:500], "cached": cached},
            "tested_at": _utc(),
        }], "test_id")
    return SourceResult(source, status, rows, latency, error, cached)


def first_available(
    jobs: Sequence[Tuple[str, Callable[[], Sequence[Mapping[str, Any]]]]],
    minimum_rows: int = 1,
    max_cache_age_hours: float = 24.0,
) -> SourceResult:
    last = SourceResult("none", "empty", [], 0)
    for name, fetch in jobs:
        result = run_source(name, fetch, max_cache_age_hours=max_cache_age_hours)
        print(f"SOURCE ROUTER {name}: {result.status} rows={len(result.rows)} latency={result.latency_ms}ms")
        last = result
        if len(result.rows) >= minimum_rows:
            return result
    return last
