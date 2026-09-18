#!/usr/bin/env python3
"""NETRATTLER V36 runtime policy.

Small, dependency-light module consumed by the tip bot and builder engine.
The learning workflow writes ``netrattler_active_policy.json``.  Runtime code
uses it without requiring a live Supabase request on every pick.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time

import requests
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from netrattler_autolearn_v36 import predict_probability as _v36_automl_predict
except Exception:
    _v36_automl_predict = lambda data: None

_POLICY_PATH = Path(os.getenv("NETRATTLER_POLICY_FILE", "netrattler_active_policy.json"))
_CACHE: Dict[str, Any] = {}
_MTIME = -1.0
_LOCK = threading.Lock()
_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
_REMOTE_REFRESH_SECONDS = int(os.getenv("NETRATTLER_POLICY_REFRESH_SECONDS", "300"))
_REMOTE_CHECKED_AT = 0.0

_DEFAULT_POLICY: Dict[str, Any] = {
    "version": "V36-default",
    "calibration": {},
    "weights": {
        "source": {}, "market": {}, "league": {}, "player": {},
        "builder": {}, "odds_bucket": {}, "legs": {},
    },
    "risk": {
        "mode": "normal",
        "single_max_units": 1.0,
        "builder_max_units": 0.4,
        "lottery_max_units": 0.05,
        "max_builder_legs": 9,
        "max_daily_singles": 20,
        "max_daily_builders": 8,
        "kelly_fraction": 0.25,
        "drawdown_pct": 0.0,
    },
    "thresholds": {
        "min_edge": 0.03,
        "min_probability": 0.55,
        "min_source_weight": 0.70,
        "min_market_weight": 0.70,
    },
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _merge_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(_DEFAULT_POLICY))
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _fetch_remote_policy() -> Optional[Dict[str, Any]]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Accept": "application/json",
    }
    base = f"{_SUPABASE_URL}/rest/v1/netrattler_policy_snapshots"
    queries = [
        {"select": "policy,version,created_at", "is_active": "eq.true", "order": "created_at.desc", "limit": "1"},
        {"select": "policy,version,created_at", "order": "created_at.desc", "limit": "1"},
    ]
    for params in queries:
        try:
            response = requests.get(base, headers=headers, params=params, timeout=12)
            if not response.ok:
                continue
            rows = response.json()
            if not rows:
                continue
            payload = rows[0].get("policy")
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return None


def _read_local_policy() -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _load() -> Dict[str, Any]:
    global _CACHE, _MTIME, _REMOTE_CHECKED_AT
    now = time.time()
    try:
        mtime = _POLICY_PATH.stat().st_mtime
    except OSError:
        mtime = -1.0

    with _LOCK:
        local_changed = mtime != _MTIME
        remote_due = now - _REMOTE_CHECKED_AT >= _REMOTE_REFRESH_SECONDS
        if _CACHE and not local_changed and not remote_due:
            return _CACHE

        payload: Optional[Dict[str, Any]] = None
        if remote_due:
            _REMOTE_CHECKED_AT = now
            payload = _fetch_remote_policy()
            if payload:
                try:
                    _POLICY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    mtime = _POLICY_PATH.stat().st_mtime
                except OSError:
                    pass
        if payload is None:
            payload = _read_local_policy()
        if payload is None:
            payload = _DEFAULT_POLICY
        _CACHE = _merge_policy(payload)
        _MTIME = mtime
        return _CACHE


def get_policy() -> Dict[str, Any]:
    return _load()


def _weight(dimension: str, key: Any, default: float = 1.0) -> float:
    policy = _load()
    values = (policy.get("weights") or {}).get(dimension) or {}
    item = values.get(_norm(key))
    if isinstance(item, dict):
        item = item.get("weight", default)
    try:
        return _clamp(float(item), 0.45, 1.45)
    except (TypeError, ValueError):
        return default


def source_weight(source: Any) -> float:
    return _weight("source", source)


def market_weight(market: Any) -> float:
    return _weight("market", market)


def league_weight(league: Any) -> float:
    return _weight("league", league)


def player_weight(player: Any) -> float:
    return _weight("player", player)


def builder_weight(builder_type: Any) -> float:
    return _weight("builder", builder_type)


def odds_bucket(odds: float) -> str:
    if odds < 1.50:
        return "<1.50"
    if odds < 1.80:
        return "1.50-1.79"
    if odds < 2.20:
        return "1.80-2.19"
    if odds < 3.00:
        return "2.20-2.99"
    if odds < 5.00:
        return "3.00-4.99"
    return "5.00+"


def calibration_probability(raw_probability: float, market: Any = "", league: Any = "") -> float:
    p = raw_probability / 100.0 if raw_probability > 1 else raw_probability
    p = _clamp(float(p), 0.01, 0.99)
    policy = _load()
    calibration = policy.get("calibration") or {}
    bin_key = f"{int(p * 20) / 20:.2f}"
    candidates = [
        f"market|{_norm(market)}|{bin_key}",
        f"league|{_norm(league)}|{bin_key}",
        f"global|all|{bin_key}",
    ]
    estimates = []
    for key in candidates:
        item = calibration.get(key)
        if isinstance(item, dict):
            try:
                n = int(item.get("samples", 0))
                q = float(item.get("calibrated", p))
                if n > 0:
                    estimates.append((q, min(1.0, n / 100.0)))
            except (TypeError, ValueError):
                pass
    if not estimates:
        return p
    weighted = sum(q * w for q, w in estimates) / max(1e-9, sum(w for _, w in estimates))
    confidence = min(0.75, sum(w for _, w in estimates) / 2.0)
    return _clamp((1.0 - confidence) * p + confidence * weighted, 0.01, 0.99)


def adjust_probability(
    raw_probability: float,
    *,
    market: Any = "",
    league: Any = "",
    source: Any = "",
    player: Any = "",
    builder_type: Any = "",
    odds: float = 0.0,
    line: float = 0.0,
    book_consensus: float = 0.0,
    consensus_sources: int = 0,
    line_dispersion: float = 0.0,
    legs: int = 1,
) -> float:
    raw = raw_probability / 100.0 if raw_probability > 1 else raw_probability
    raw = _clamp(float(raw), 0.01, 0.99)
    p = calibration_probability(raw, market=market, league=league)
    multiplier = math.prod([
        source_weight(source),
        market_weight(market),
        league_weight(league),
        player_weight(player) if player else 1.0,
        builder_weight(builder_type) if builder_type else 1.0,
    ])
    # Move log-odds rather than multiplying probability directly.
    logit = math.log(p / (1.0 - p)) + math.log(_clamp(multiplier, 0.35, 2.0))
    weighted = _clamp(1.0 / (1.0 + math.exp(-logit)), 0.01, 0.99)

    # V36 champion AutoML is an additional conservative calibration layer.
    # It uses settled picks only and returns None until enough chronology-safe
    # samples exist. Small samples therefore cannot override the V35 policy.
    auto = _v36_automl_predict({
        "raw_probability": raw, "probability": raw, "odds": odds,
        "market": market, "league": league, "source": source,
        "player": player, "builder_type": builder_type, "line": line,
        "book_consensus": book_consensus, "consensus_sources": consensus_sources,
        "line_dispersion": line_dispersion, "legs": legs,
    })
    if auto is None:
        return weighted
    # Do not let a new model move a pick more than 12 percentage points.
    auto = _clamp(float(auto), max(0.01, weighted - 0.12), min(0.99, weighted + 0.12))
    confidence = 0.45
    return _clamp((1.0 - confidence) * weighted + confidence * auto, 0.01, 0.99)

def adjusted_edge(
    probability: float,
    odds: float,
    *,
    market: Any = "",
    league: Any = "",
    source: Any = "",
    player: Any = "",
) -> float:
    if odds <= 1:
        return -1.0
    p = adjust_probability(
        probability, market=market, league=league, source=source, player=player, odds=odds
    )
    return p - (1.0 / odds)


def risk_state() -> Dict[str, Any]:
    return dict((_load().get("risk") or _DEFAULT_POLICY["risk"]))


def max_builder_legs() -> int:
    try:
        return max(3, min(9, int(risk_state().get("max_builder_legs", 9))))
    except (TypeError, ValueError):
        return 9


def max_daily_singles() -> int:
    try:
        return max(1, int(risk_state().get("max_daily_singles", 20)))
    except (TypeError, ValueError):
        return 20


def max_daily_builders() -> int:
    try:
        return max(1, int(risk_state().get("max_daily_builders", 8)))
    except (TypeError, ValueError):
        return 8


def minimum_edge(default: float = 0.03) -> float:
    try:
        return max(default, float((_load().get("thresholds") or {}).get("min_edge", default)))
    except (TypeError, ValueError):
        return default


def allow_pick(
    probability: float,
    odds: float,
    *,
    market: Any = "",
    league: Any = "",
    source: Any = "",
    player: Any = "",
    min_edge: Optional[float] = None,
    already_adjusted: bool = False,
) -> bool:
    if odds <= 1:
        return False
    policy = _load()
    thresholds = policy.get("thresholds") or {}
    p = probability / 100.0 if probability > 1 else probability
    p = _clamp(float(p), 0.01, 0.99)
    if not already_adjusted:
        p = adjust_probability(p, market=market, league=league, source=source, player=player, odds=odds)
    required_edge = max(float(min_edge or 0), minimum_edge())
    required_prob = float(thresholds.get("min_probability", 0.55))
    if source_weight(source) < float(thresholds.get("min_source_weight", 0.70)):
        return False
    if market_weight(market) < float(thresholds.get("min_market_weight", 0.70)):
        return False
    return p >= required_prob and p - (1.0 / odds) >= required_edge


def _kelly(probability: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    p = probability / 100.0 if probability > 1 else probability
    b = odds - 1.0
    return max(0.0, (b * p - (1.0 - p)) / b)


def stake_for_single(
    probability: float,
    odds: float,
    *,
    market: Any = "",
    league: Any = "",
    source: Any = "",
    player: Any = "",
    already_adjusted: bool = False,
) -> float:
    risk = risk_state()
    p = probability / 100.0 if probability > 1 else probability
    p = _clamp(float(p), 0.01, 0.99)
    if not already_adjusted:
        p = adjust_probability(p, market=market, league=league, source=source, player=player, odds=odds)
    kelly_fraction = float(risk.get("kelly_fraction", 0.25))
    cap = float(risk.get("single_max_units", 1.0))
    edge = p - (1.0 / max(odds, 1.0001))
    if edge <= 0:
        return 0.0
    units = _kelly(p, odds) * 100.0 * kelly_fraction
    trust = _clamp(source_weight(source) * market_weight(market) * league_weight(league), 0.5, 1.35)
    return round(_clamp(units * trust, 0.05, cap), 2)


def stake_for_builder(
    total_odds: float,
    legs: int,
    *,
    average_edge: float = 0.0,
    builder_type: Any = "",
    correlation_penalty: float = 0.0,
) -> float:
    risk = risk_state()
    if legs > max_builder_legs() or total_odds <= 1:
        return 0.0
    if total_odds >= 50:
        cap = float(risk.get("lottery_max_units", 0.05))
    else:
        cap = float(risk.get("builder_max_units", 0.40))
    base = 0.42 / max(1.0, math.sqrt(legs))
    odds_penalty = 1.0 / max(1.0, math.log(max(total_odds, math.e)))
    edge_boost = _clamp(1.0 + average_edge * 4.0, 0.7, 1.35)
    corr = _clamp(1.0 - correlation_penalty, 0.35, 1.0)
    trust = builder_weight(builder_type)
    return round(_clamp(base * odds_penalty * edge_boost * corr * trust, 0.02, cap), 2)


def policy_age_seconds() -> Optional[float]:
    try:
        return max(0.0, time.time() - _POLICY_PATH.stat().st_mtime)
    except OSError:
        return None
