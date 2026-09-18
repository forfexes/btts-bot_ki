#!/usr/bin/env python3
"""NETRATTLER V37 coverage watchdog and market discovery.

Lightweight runtime diagnostics for the production bot. It does not scrape and
never blocks a tip run. It records which expected market groups have candidates,
which were emptied by validation/real-odds filters, source coverage of player
props, and previously unseen market/category labels.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
OUT = Path(os.getenv("NETRATTLER_COVERAGE_REPORT", "netrattler_coverage_watchdog.json"))

EXPECTED_MARKETS = (
    "btts", "over25", "combo", "btts_ht", "over15_ht", "1x2",
    "corners", "scorer", "props", "builder", "combo_multi",
)
KNOWN_PROP_CATEGORIES = {
    "shots", "sot", "shots_on_target", "sot_outside_box", "shots_outside_box",
    "fouls", "fouls_committed", "fouls_won", "fouled", "tackles",
    "tackles_committed", "tackles_received", "cards", "yellow_cards", "booked",
    "goals", "score", "first_scorer", "last_scorer", "assist", "assists",
    "score_assist", "goal_or_assist", "passes", "offsides", "interceptions",
    "clearances", "saves", "goalkeeper_saves", "team_corners", "corners",
    "match_corners", "team_cards", "match_cards", "btts", "btts_ht",
    "over_goals", "half_goals_1st", "half_goals_2nd", "double_chance", "result",
    "match_goals", "match_sot", "team_shots",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().replace("_", " ").split())


def _hash(*parts: Any) -> str:
    return hashlib.sha256("||".join(map(str, parts)).encode("utf-8")).hexdigest()[:48]


def _atomic_write(payload: Mapping[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=OUT.name, suffix=".tmp", dir=str(OUT.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, OUT)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _post(table: str, rows: Sequence[Mapping[str, Any]], conflict: str = "") -> bool:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY or requests is None:
        return False
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    params = {"on_conflict": conflict} if conflict else {}
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params,
            json=[dict(row) for row in rows], timeout=10,
        )
        return bool(response.ok)
    except Exception:
        return False


def _counts(tips_by_market: Optional[Mapping[str, Sequence[Mapping[str, Any]]]]) -> Dict[str, int]:
    tips_by_market = tips_by_market or {}
    return {key: len(tips_by_market.get(key, []) or []) for key in EXPECTED_MARKETS}


def _source_counts(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows or []:
        source = _norm(row.get("bookmaker") or row.get("source") or "unknown") or "unknown"
        counter[source] += 1
    return dict(counter.most_common())


def discover_unknown_markets(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        category = _norm(row.get("category") or row.get("market_key") or row.get("market"))
        if not category:
            continue
        key = category.replace(" ", "_")
        if key in KNOWN_PROP_CATEGORIES or category in {_norm(x) for x in KNOWN_PROP_CATEGORIES}:
            continue
        source = _norm(row.get("bookmaker") or row.get("source") or "unknown") or "unknown"
        ident = f"{source}|{category}"
        item = found.setdefault(ident, {
            "source": source,
            "market_key": category,
            "samples": 0,
            "example": {},
        })
        item["samples"] += 1
        if not item["example"]:
            item["example"] = {
                "market": row.get("market"), "category": row.get("category"),
                "line": row.get("line"), "player": row.get("player") or row.get("player_name"),
                "match": row.get("match") or row.get("game"),
            }
    return found


def build_report(
    *,
    before_filter: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
    after_filter: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
    prop_rows: Iterable[Mapping[str, Any]] = (),
    rejection_stats: Optional[Mapping[str, Mapping[str, Any]]] = None,
    extra_counts: Optional[Mapping[str, int]] = None,
    run_id: str = "",
) -> Dict[str, Any]:
    before = _counts(before_filter)
    after = _counts(after_filter)
    # Markets generated outside tips_by_market (corners/scorer/builder/combos)
    # can report their real sent/candidate counts without faking list entries.
    for key, value in (extra_counts or {}).items():
        if key in EXPECTED_MARKETS:
            count = max(0, int(value or 0))
            before[key] = max(before.get(key, 0), count)
            after[key] = max(after.get(key, 0), count)
    props = [dict(row) for row in (prop_rows or []) if isinstance(row, Mapping)]
    unknown = discover_unknown_markets(props)
    problems: Dict[str, str] = {}
    for market in EXPECTED_MARKETS:
        if before.get(market, 0) <= 0:
            problems[market] = "no_candidates"
        elif after.get(market, 0) <= 0:
            stat = (rejection_stats or {}).get(market) or {}
            if int(stat.get("no_quote", 0) or 0) > 0:
                problems[market] = "real_odds_missing_or_stale"
            elif int(stat.get("below_min", 0) or 0) > 0:
                problems[market] = "edge_or_probability_filter"
            else:
                problems[market] = "filtered_out"
    return {
        "version": "V37",
        "run_id": run_id or _hash(_utc())[:24],
        "generated_at": _utc(),
        "before_filter": before,
        "after_filter": after,
        "problems": problems,
        "prop_rows": len(props),
        "prop_sources": _source_counts(props),
        "unknown_markets": list(unknown.values()),
        "rejection_stats": {k: dict(v) for k, v in (rejection_stats or {}).items()},
    }


def persist_report(report: Mapping[str, Any]) -> None:
    _atomic_write(report)
    row = {
        "run_id": str(report.get("run_id") or _hash(report.get("generated_at")))[:48],
        "generated_at": report.get("generated_at") or _utc(),
        "before_filter": report.get("before_filter") or {},
        "after_filter": report.get("after_filter") or {},
        "problems": report.get("problems") or {},
        "prop_sources": report.get("prop_sources") or {},
        "prop_rows": int(report.get("prop_rows") or 0),
        "payload": dict(report),
    }
    _post("netrattler_coverage_watchdog", [row], "run_id")
    discoveries = []
    now = _utc()
    for item in report.get("unknown_markets") or []:
        if not isinstance(item, Mapping):
            continue
        source = str(item.get("source") or "unknown")
        market_key = str(item.get("market_key") or "unknown")
        discoveries.append({
            "discovery_id": _hash(source, market_key),
            "source": source,
            "market_key": market_key,
            "samples": int(item.get("samples") or 0),
            "example": item.get("example") or {},
            "last_seen": now,
            "status": "unmapped",
        })
    if discoveries:
        _post("netrattler_market_discovery", discoveries, "discovery_id")


def run_watchdog(**kwargs: Any) -> Dict[str, Any]:
    report = build_report(**kwargs)
    persist_report(report)
    return report


__all__ = ["EXPECTED_MARKETS", "KNOWN_PROP_CATEGORIES", "build_report", "persist_report", "run_watchdog", "discover_unknown_markets"]
