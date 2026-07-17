#!/usr/bin/env python3
"""Learn empirical football builder-leg pair factors from settled legs.

Only builders with leg-level outcomes are used. Overall builder losses are not
misinterpreted as every leg losing.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from netrattler_learning_engine import SupabaseRest, norm, to_float

OUT_FILE = Path(os.getenv("NETRATTLER_BUILDER_CORRELATION_FILE", "netrattler_builder_correlations.json"))
MIN_SAMPLES = int(os.getenv("NETRATTLER_BUILDER_PAIR_MIN_SAMPLES", "20"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(payload: Any) -> None:
    fd, tmp = tempfile.mkstemp(prefix=OUT_FILE.name, suffix=".tmp", dir=str(OUT_FILE.parent or Path(".")))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, OUT_FILE)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def load_payload() -> Dict[str, Any]:
    try:
        payload = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("pairs"):
            return payload
    except Exception:
        payload = {}
    db = SupabaseRest()
    if db.enabled:
        try:
            rows = db.get("netrattler_builder_pair_models", order="n.desc", limit_total=10000)
            pairs = {str(row.get("pair_key")): dict(row) for row in rows if row.get("pair_key")}
            if pairs:
                payload = {"version": 1, "updated_at": _utc(), "pairs": pairs, "source": "supabase"}
                try:
                    _write(payload)
                except Exception:
                    pass
                return payload
        except Exception:
            pass
    return payload if isinstance(payload, dict) else {}


def market_group(value: Any) -> str:
    text = norm(value)
    rules = (
        (("shots on target", "sot"), "sot"), (("shot",), "shots"),
        (("tackles received",), "tackles_received"), (("tackle",), "tackles_committed"),
        (("fouls won",), "fouls_won"), (("foul",), "fouls_committed"),
        (("card", "booked"), "cards"), (("pass",), "passes"),
        (("assist",), "assists"), (("score", "goal"), "goals"),
        (("corner",), "corners"), (("btts", "both teams"), "btts"),
        (("over 2 5",), "over25"), (("btts ht",), "btts_ht"),
    )
    for needles, label in rules:
        if any(needle in text for needle in needles):
            return label
    return text.replace(" ", "_")[:48] or "unknown"


def _status(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    text = norm(value)
    if text in {"win", "won", "hit", "green", "success", "1", "true"}:
        return 1
    if text in {"loss", "lost", "miss", "red", "failed", "0", "false"}:
        return 0
    return None


def _direction(leg: Mapping[str, Any]) -> str:
    explicit = norm(leg.get("direction") or leg.get("side"))
    if explicit:
        return explicit
    return "under" if "under" in norm(leg.get("market")) else "over"


def _match(leg: Mapping[str, Any]) -> str:
    return norm(leg.get("match") or leg.get("game") or leg.get("event_id"))


def _leg_key(leg: Mapping[str, Any]) -> str:
    return f"{market_group(leg.get('category') or leg.get('market'))}:{_direction(leg)}"


def pair_key(a: str, b: str, relation: str = "same_match") -> str:
    x, y = sorted((a, b))
    return f"{relation}|{x}|{y}"


def _payload(event: Mapping[str, Any]) -> Dict[str, Any]:
    value = event.get("payload") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return dict(value) if isinstance(value, Mapping) else {}


def _legs(event: Mapping[str, Any]) -> List[Dict[str, Any]]:
    payload = _payload(event)
    candidates = payload.get("legs_payload") or payload.get("legs") or payload.get("builder_legs") or payload.get("leg_results") or []
    if not isinstance(candidates, list):
        return []
    output = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        outcome = _status(item.get("status") if item.get("status") is not None else item.get("outcome") if item.get("outcome") is not None else item.get("result"))
        if outcome is None:
            continue
        nested = item.get("leg") if isinstance(item.get("leg"), Mapping) else {}
        row = dict(nested)
        row.update({k: v for k, v in item.items() if k != "leg"})
        row["_outcome"] = outcome
        output.append(row)
    return output


def learn(db: Optional[SupabaseRest] = None) -> Dict[str, Any]:
    db = db or SupabaseRest()
    events = db.get("netrattler_learning_events", order="tip_date.asc", limit_total=100000) if db.enabled else []
    counts: Dict[str, Dict[str, float]] = defaultdict(lambda: {"n": 0, "a": 0, "b": 0, "joint": 0})
    builders_used = 0
    for event in events:
        legs = _legs(event)
        if len(legs) < 2:
            continue
        builders_used += 1
        for a, b in itertools.combinations(legs, 2):
            relation = "same_match" if _match(a) and _match(a) == _match(b) else "cross_match"
            ka, kb = _leg_key(a), _leg_key(b)
            key = pair_key(ka, kb, relation)
            bucket = counts[key]
            bucket["n"] += 1
            bucket["a"] += int(a["_outcome"])
            bucket["b"] += int(b["_outcome"])
            bucket["joint"] += int(a["_outcome"] and b["_outcome"])
    pairs: Dict[str, Dict[str, Any]] = {}
    rows: List[Dict[str, Any]] = []
    for key, c in counts.items():
        n = int(c["n"])
        if n < MIN_SAMPLES:
            continue
        pa = (c["a"] + 3.0) / (n + 6.0)
        pb = (c["b"] + 3.0) / (n + 6.0)
        pj = (c["joint"] + 2.0) / (n + 4.0)
        raw_factor = pj / max(0.01, pa * pb)
        shrink = n / (n + 60.0)
        factor = 1.0 + (raw_factor - 1.0) * shrink
        factor = max(0.75, min(1.20, factor))
        relation, leg_a, leg_b = key.split("|", 2)
        info = {
            "relation": relation, "leg_a": leg_a, "leg_b": leg_b,
            "n": n, "p_a": round(pa, 6), "p_b": round(pb, 6),
            "p_joint": round(pj, 6), "factor": round(factor, 6),
            "updated_at": _utc(),
        }
        pairs[key] = info
        rows.append({"pair_key": key, **info})
    payload = {"version": 1, "updated_at": _utc(), "events": len(events), "builders_used": builders_used, "pairs": pairs}
    _write(payload)
    if db.enabled and rows:
        db.upsert("netrattler_builder_pair_models", rows, "pair_key")
    print(f"V36 Builder learning: events={len(events)} builders_with_leg_results={builders_used} pair_models={len(pairs)}")
    return payload


def pair_factor(a_market: Any, a_direction: Any, b_market: Any, b_direction: Any, relation: str) -> Tuple[float, int]:
    payload = load_payload()
    pairs = payload.get("pairs") or {}
    a = f"{market_group(a_market)}:{norm(a_direction) or 'over'}"
    b = f"{market_group(b_market)}:{norm(b_direction) or 'over'}"
    info = pairs.get(pair_key(a, b, relation)) or {}
    return float(info.get("factor", 1.0)), int(info.get("n", 0))


def joint_probability(legs: Sequence[Any]) -> Tuple[float, float, int]:
    independent = math.prod(max(0.01, min(0.99, float(getattr(leg, "probability", 0.0) or 0.0))) for leg in legs)
    factors: List[float] = []
    samples: List[int] = []
    for a, b in itertools.combinations(legs, 2):
        relation = "same_match" if norm(getattr(a, "match", "")) and norm(getattr(a, "match", "")) == norm(getattr(b, "match", "")) else "cross_match"
        factor, n = pair_factor(
            getattr(a, "category", None) or getattr(a, "market", ""),
            "under" if "under" in norm(getattr(a, "market", "")) else "over",
            getattr(b, "category", None) or getattr(b, "market", ""),
            "under" if "under" in norm(getattr(b, "market", "")) else "over",
            relation,
        )
        factors.append(factor)
        samples.append(n)
    if not factors:
        return independent, 1.0, 0
    geometric = math.prod(factors) ** (1.0 / len(factors))
    minimum_n = min(samples) if samples else 0
    confidence = min(0.65, minimum_n / 100.0)
    conservative_factor = 1.0 + (geometric - 1.0) * confidence
    adjusted = max(0.001, min(0.97, independent * conservative_factor))
    return adjusted, conservative_factor, minimum_n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    learn()


if __name__ == "__main__":
    main()
