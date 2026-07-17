#!/usr/bin/env python3
"""Cross-book consensus for football props without inventing lines or odds."""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from netrattler_learning_engine import norm, to_float


def _line(row: Mapping[str, Any]) -> float:
    return to_float(row.get("line") if row.get("line") is not None else row.get("point"), 0.0)


def _direction(row: Mapping[str, Any]) -> str:
    explicit = norm(row.get("direction") or row.get("side"))
    return explicit or ("under" if "under" in norm(row.get("market")) else "over")


def _key(row: Mapping[str, Any]) -> Tuple[str, str, str, str, float]:
    return (
        norm(row.get("match") or row.get("game") or row.get("event_id")),
        norm(row.get("player") or row.get("player_name") or row.get("selection")),
        norm(row.get("category") or row.get("market") or row.get("market_key")),
        _direction(row),
        round(_line(row), 2),
    )


def enrich(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    output = [dict(row) for row in rows if isinstance(row, Mapping)]
    groups: Dict[Tuple[str, str, str, str, float], List[Dict[str, Any]]] = defaultdict(list)
    for row in output:
        odds = to_float(row.get("odds") or row.get("odds_decimal"), 0.0)
        if odds > 1 and not bool(row.get("estimated") or row.get("estimated_odds")):
            groups[_key(row)].append(row)
    for members in groups.values():
        odds = [to_float(row.get("odds") or row.get("odds_decimal"), 0.0) for row in members]
        odds = [value for value in odds if value > 1]
        implied = [1.0 / value for value in odds]
        sources = {norm(row.get("bookmaker") or row.get("source")) for row in members if norm(row.get("bookmaker") or row.get("source"))}
        if not implied:
            continue
        consensus = statistics.median(implied)
        best_odds = max(odds)
        median_odds = statistics.median(odds)
        dispersion = statistics.pstdev(odds) if len(odds) >= 2 else 0.0
        for row in members:
            row["book_consensus"] = round(consensus, 6)
            row["consensus_sources"] = len(sources)
            row["best_odds"] = round(best_odds, 4)
            row["median_odds"] = round(median_odds, 4)
            row["odds_dispersion"] = round(dispersion, 6)
            row["real_observed_line"] = True
            raw_p = to_float(row.get("model_prob") if row.get("model_prob") is not None else row.get("probability"), 0.0)
            if raw_p > 1:
                raw_p /= 100.0
            if raw_p > 0 and len(sources) >= 2:
                # Consensus is vigged; use only a conservative minority weight.
                confidence = min(0.30, 0.08 * len(sources))
                blended = (1.0 - confidence) * raw_p + confidence * consensus
                row["model_prob"] = max(0.01, min(0.99, blended))
                row["probability"] = row["model_prob"]
    return output
