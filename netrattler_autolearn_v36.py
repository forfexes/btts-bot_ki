#!/usr/bin/env python3
"""NETRATTLER V36 settled-pick AutoML.

Football adaptation of the useful PROP HUNTER V12 pattern:
- trains only on settled historical picks;
- chronological out-of-fold evaluation;
- Platt calibration fitted only on out-of-fold predictions;
- promotion by Brier score and log loss against both implied-odds baseline
  and the current champion;
- pure-Python JSON inference at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from netrattler_learning_engine import SupabaseRest, clamp, norm, to_float

MODEL_FILE = Path(os.getenv("NETRATTLER_AUTOML_MODEL_FILE", "netrattler_autolearn_registry.json"))
REPORT_FILE = Path(os.getenv("NETRATTLER_AUTOML_REPORT_FILE", "netrattler_autolearn_report.json"))
MIN_GLOBAL = int(os.getenv("NETRATTLER_AUTOML_MIN_GLOBAL", "80"))
MIN_GROUP = int(os.getenv("NETRATTLER_AUTOML_MIN_GROUP", "60"))
N_HASH = 32
NUMERIC_FEATURES = (
    "raw_probability", "implied_probability", "log_odds", "edge",
    "line", "legs", "source_trust", "book_consensus",
    "consensus_sources", "line_dispersion", "closing_move",
)
DIM = len(NUMERIC_FEATURES) + N_HASH


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _safe_json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _clip(value: float, lo: float = 1e-5, hi: float = 1 - 1e-5) -> float:
    return max(lo, min(hi, float(value)))


def _hash_index(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % N_HASH


def _payload(event: Mapping[str, Any]) -> Dict[str, Any]:
    value = event.get("payload") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return dict(value) if isinstance(value, Mapping) else {}


def _first(event: Mapping[str, Any], payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for container in (event, payload):
        for key in keys:
            value = container.get(key)
            if value not in (None, ""):
                return value
    return default


def _market_group(value: Any) -> str:
    text = norm(value)
    rules = (
        (("shots on target", "sot"), "sot"),
        (("shot", "shots"), "shots"),
        (("tackles received",), "tackles_received"),
        (("tackles committed", "tackles"), "tackles_committed"),
        (("fouls won",), "fouls_won"),
        (("foul",), "fouls_committed"),
        (("card", "booked"), "cards"),
        (("passes",), "passes"),
        (("assist",), "assists"),
        (("goalscorer", "to score", "goal"), "goals"),
        (("corner",), "corners"),
        (("both teams to score", "btts"), "btts"),
        (("over 2 5", "over25"), "over25"),
        (("btts ht",), "btts_ht"),
        (("over 1 5 ht", "over15 ht"), "over15_ht"),
    )
    for needles, label in rules:
        if any(needle in text for needle in needles):
            return label
    return (text.replace(" ", "_")[:48] or "unknown")


def _canonical_event(event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    outcome = event.get("outcome")
    try:
        y = int(outcome)
    except (TypeError, ValueError):
        return None
    if y not in (0, 1):
        return None
    payload = _payload(event)
    odds = to_float(_first(event, payload, "odds", "bet365_quote", "oddsYes"), 0.0)
    raw_p = to_float(_first(event, payload, "probability", "calibrated_probability", "prob"), 0.0)
    if raw_p > 1:
        raw_p /= 100.0
    if odds <= 1 or raw_p <= 0:
        return None
    market = str(_first(event, payload, "market", "market_name", "category", default="unknown"))
    league = str(_first(event, payload, "league", default="unknown"))
    source = str(_first(event, payload, "source", "edge_source", "bookie", default="unknown"))
    player = str(_first(event, payload, "player", "player_name", default=""))
    builder_type = str(_first(event, payload, "builder_type", "builder_style", default="single"))
    legs = max(1, int(to_float(_first(event, payload, "legs", "builder_total_legs", "leg_count", default=1), 1)))
    date_value = str(_first(event, payload, "tip_date", "date", "settled_at", default=""))
    implied = _clip(1.0 / odds)
    return {
        "y": y,
        "date": date_value,
        "market": market,
        "market_group": _market_group(market),
        "league": norm(league) or "unknown",
        "source": norm(source) or "unknown",
        "player": norm(player),
        "builder_type": norm(builder_type) or "single",
        "direction": norm(_first(event, payload, "direction", "side", default="over")) or "over",
        "odds_bucket": str(event.get("odds_bucket") or "unknown"),
        "raw_probability": _clip(raw_p),
        "implied_probability": implied,
        "log_odds": math.log(odds),
        "edge": raw_p - implied,
        "line": to_float(_first(event, payload, "line", "point"), 0.0),
        "legs": float(legs),
        "source_trust": to_float(_first(event, payload, "source_trust", default=1.0), 1.0),
        "book_consensus": to_float(_first(event, payload, "book_consensus", "consensus_prob"), 0.0),
        "consensus_sources": to_float(_first(event, payload, "consensus_sources"), 0.0),
        "line_dispersion": to_float(_first(event, payload, "line_dispersion"), 0.0),
        "closing_move": to_float(_first(event, payload, "line_move", "closing_move"), 0.0),
    }


def load_training_rows(db: Optional[SupabaseRest] = None, limit: int = 100000) -> List[Dict[str, Any]]:
    db = db or SupabaseRest()
    raw = db.get("netrattler_learning_events", order="tip_date.asc", limit_total=limit) if db.enabled else []
    rows = [row for row in (_canonical_event(item) for item in raw) if row]
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = "|".join(str(row.get(k, "")) for k in (
            "date", "market_group", "league", "player", "source", "odds_bucket", "raw_probability", "y"
        ))
        dedup[key] = row
    return sorted(dedup.values(), key=lambda row: row.get("date") or "")


def _vector(row: Mapping[str, Any]) -> List[float]:
    vec = [float(row.get(name, 0.0) or 0.0) for name in NUMERIC_FEATURES] + [0.0] * N_HASH
    tokens = (
        f"market={row.get('market_group')}", f"league={row.get('league')}",
        f"source={row.get('source')}", f"player={row.get('player')}",
        f"builder={row.get('builder_type')}", f"direction={row.get('direction')}",
        f"odds={row.get('odds_bucket')}",
    )
    for token in tokens:
        vec[len(NUMERIC_FEATURES) + _hash_index(token)] += 1.0
    return vec


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, value))))


def _metrics(y: Sequence[int], probabilities: Sequence[float]) -> Dict[str, float]:
    if not y:
        return {"brier": 1.0, "logloss": 9.0, "calibration_error": 1.0}
    probs = [_clip(value) for value in probabilities]
    brier = sum((p - target) ** 2 for p, target in zip(probs, y)) / len(y)
    logloss = -sum(target * math.log(p) + (1 - target) * math.log(1 - p) for p, target in zip(probs, y)) / len(y)
    bins: Dict[int, List[Tuple[float, int]]] = {}
    for p, target in zip(probs, y):
        bins.setdefault(min(9, int(p * 10)), []).append((p, target))
    ece = sum(
        len(values) / len(y) * abs(
            sum(p for p, _ in values) / len(values) - sum(target for _, target in values) / len(values)
        ) for values in bins.values()
    )
    return {"brier": round(brier, 6), "logloss": round(logloss, 6), "calibration_error": round(ece, 6)}


def _serialise(pipe: Any, calibrator: Any, metrics: Mapping[str, Any], n: int) -> Dict[str, Any]:
    scaler = pipe.named_steps["scale"]
    model = pipe.named_steps["model"]
    cal_model = calibrator.named_steps["model"]
    return {
        "n_samples": n, "dimension": DIM, "numeric_features": list(NUMERIC_FEATURES), "hash_bins": N_HASH,
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0]),
        "calibration_coef": float(cal_model.coef_[0][0]),
        "calibration_intercept": float(cal_model.intercept_[0]),
        "metrics": dict(metrics), "trained_at": _utc(),
    }


def _fit_candidate(rows: List[Dict[str, Any]], folds: int = 5) -> Optional[Dict[str, Any]]:
    if len(rows) < 40 or len({row["y"] for row in rows}) < 2:
        return None
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:
        print(f"V36 AutoML skipped: sklearn unavailable: {exc}")
        return None
    X = np.asarray([_vector(row) for row in rows], dtype=float)
    y = np.asarray([row["y"] for row in rows], dtype=int)
    n = len(rows)
    test_size = max(10, n // (folds + 2))
    first = max(30, n - folds * test_size)
    starts = list(range(first, n, test_size))
    oof_y: List[int] = []
    oof_raw: List[float] = []
    oof_indices: List[int] = []
    for start in starts:
        end = min(n, start + test_size)
        if end <= start or len(set(y[:start])) < 2:
            continue
        pipe = Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=1500, C=0.30, class_weight="balanced")),
        ])
        pipe.fit(X[:start], y[:start])
        pred = pipe.predict_proba(X[start:end])[:, 1]
        oof_y.extend(y[start:end].tolist())
        oof_raw.extend(pred.tolist())
        oof_indices.extend(range(start, end))
    if len(oof_y) < 20 or len(set(oof_y)) < 2:
        return None
    logits = np.asarray([[math.log(_clip(p) / (1 - _clip(p)))] for p in oof_raw], dtype=float)
    calibrator = Pipeline([("model", LogisticRegression(max_iter=800, C=0.5))])
    calibrator.fit(logits, np.asarray(oof_y))
    calibrated = calibrator.predict_proba(logits)[:, 1].tolist()
    candidate_metrics = _metrics(oof_y, calibrated)
    baseline_implied = [rows[index]["implied_probability"] for index in oof_indices]
    baseline_raw = [rows[index]["raw_probability"] for index in oof_indices]
    implied_metrics = _metrics(oof_y, baseline_implied)
    raw_metrics = _metrics(oof_y, baseline_raw)
    candidate_metrics.update({
        "baseline_brier": implied_metrics["brier"],
        "baseline_logloss": implied_metrics["logloss"],
        "raw_brier": raw_metrics["brier"],
        "raw_logloss": raw_metrics["logloss"],
        "oof_samples": len(oof_y),
    })
    final_pipe = Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1500, C=0.30, class_weight="balanced")),
    ])
    final_pipe.fit(X, y)
    return _serialise(final_pipe, calibrator, candidate_metrics, n)


def _groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {"global": rows}
    for row in rows:
        market = row["market_group"]
        league = row["league"]
        groups.setdefault(f"market:{market}", []).append(row)
        groups.setdefault(f"league:{league}", []).append(row)
        groups.setdefault(f"market_league:{market}:{league}", []).append(row)
    return groups


def _promote(candidate: Mapping[str, Any], champion: Optional[Mapping[str, Any]]) -> Tuple[bool, str]:
    metrics = candidate.get("metrics") or {}
    brier = float(metrics.get("brier", 99))
    logloss = float(metrics.get("logloss", 99))
    baseline_brier = float(metrics.get("baseline_brier", 99))
    baseline_logloss = float(metrics.get("baseline_logloss", 99))
    beats_market = brier <= baseline_brier - 0.001 and logloss <= baseline_logloss + 0.002
    if not beats_market:
        return False, "does-not-beat-implied-baseline"
    if not champion:
        return True, "first-champion"
    old_metrics = champion.get("metrics") or {}
    old_brier = float(old_metrics.get("brier", 99))
    old_logloss = float(old_metrics.get("logloss", 99))
    improves_brier = brier <= old_brier - 0.0005 and logloss <= old_logloss + 0.003
    improves_logloss = logloss <= old_logloss - 0.001 and brier <= old_brier + 0.001
    return (improves_brier or improves_logloss), (
        f"candidate brier={brier:.5f}/{old_brier:.5f} logloss={logloss:.5f}/{old_logloss:.5f}"
    )


def train_and_promote(db: Optional[SupabaseRest] = None) -> Dict[str, Any]:
    db = db or SupabaseRest()
    rows = load_training_rows(db)
    old_payload = _safe_json_load(MODEL_FILE, {}) or {}
    fingerprint = hashlib.sha256(json.dumps([
        (row.get("date"), row.get("market_group"), row.get("league"), row.get("odds_bucket"), row.get("raw_probability"), row.get("y"))
        for row in rows
    ], separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    if isinstance(old_payload, Mapping) and old_payload.get("training_fingerprint") == fingerprint:
        report = {"rows": len(rows), "trained_at": _utc(), "status": "unchanged", "groups": {}}
        _atomic_json_write(REPORT_FILE, report)
        print(f"V36 AutoML: unchanged settled history rows={len(rows)}; training skipped")
        return report
    champions = dict(old_payload.get("models") or {}) if isinstance(old_payload, Mapping) else {}
    report: Dict[str, Any] = {"rows": len(rows), "trained_at": _utc(), "groups": {}}
    for key, group_rows in _groups(rows).items():
        minimum = MIN_GLOBAL if key == "global" else MIN_GROUP
        if len(group_rows) < minimum:
            report["groups"][key] = {"status": "insufficient", "n": len(group_rows)}
            continue
        candidate = _fit_candidate(group_rows)
        if not candidate:
            report["groups"][key] = {"status": "not_trainable", "n": len(group_rows)}
            continue
        promoted, reason = _promote(candidate, champions.get(key))
        status = "promoted" if promoted else "rejected"
        if promoted:
            champions[key] = candidate
        report["groups"][key] = {"status": status, "n": len(group_rows), "reason": reason, **candidate["metrics"]}
        if db.enabled and promoted:
            metrics = candidate["metrics"]
            db.upsert("netrattler_autolearn_models", [{
                "model_key": key,
                "status": "champion",
                "n_samples": candidate.get("n_samples"),
                "brier_score": metrics.get("brier"),
                "log_loss": metrics.get("logloss"),
                "baseline_brier": metrics.get("baseline_brier"),
                "baseline_log_loss": metrics.get("baseline_logloss"),
                "model": candidate,
                "updated_at": _utc(),
            }], "model_key")
    payload = {"version": 3, "updated_at": _utc(), "training_rows": len(rows), "training_fingerprint": fingerprint, "models": champions, "last_report": report}
    _atomic_json_write(MODEL_FILE, payload)
    _atomic_json_write(REPORT_FILE, report)
    print(f"V36 AutoML: rows={len(rows)} champions={len(champions)}")
    for key, info in report["groups"].items():
        if info.get("status") in {"promoted", "rejected"}:
            print(f"  {key}: {info['status']} n={info['n']} brier={info.get('brier')} logloss={info.get('logloss')}")
    return report


def _predict_model(model: Mapping[str, Any], vector: Sequence[float]) -> Optional[float]:
    try:
        mean, scale, coef = model["mean"], model["scale"], model["coef"]
        if not (len(vector) == len(mean) == len(scale) == len(coef)):
            return None
        value = float(model["intercept"])
        for x, m, s, c in zip(vector, mean, scale, coef):
            denom = float(s) if abs(float(s)) > 1e-12 else 1.0
            value += ((float(x) - float(m)) / denom) * float(c)
        raw = _sigmoid(value)
        logit = math.log(_clip(raw) / (1 - _clip(raw)))
        return _clip(_sigmoid(float(model.get("calibration_intercept", 0)) + float(model.get("calibration_coef", 1)) * logit), 0.02, 0.98)
    except Exception:
        return None


def _runtime_row(data: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    raw_p = to_float(data.get("raw_probability") if data.get("raw_probability") is not None else data.get("probability"), 0.0)
    if raw_p > 1:
        raw_p /= 100.0
    raw_p = _clip(raw_p or 0.5)
    odds = to_float(data.get("odds"), 0.0)
    implied = _clip(1.0 / odds) if odds > 1 else raw_p
    market = str(data.get("market") or data.get("category") or "unknown")
    return {
        "market": market,
        "market_group": _market_group(market),
        "league": norm(data.get("league")) or "unknown",
        "source": norm(data.get("source")) or "unknown",
        "player": norm(data.get("player")),
        "builder_type": norm(data.get("builder_type")) or "single",
        "direction": norm(data.get("direction")) or "over",
        "odds_bucket": str(data.get("odds_bucket") or "unknown"),
        "raw_probability": raw_p,
        "implied_probability": implied,
        "log_odds": math.log(odds) if odds > 1 else math.log(max(1.01, 1.0 / raw_p)),
        "edge": raw_p - implied,
        "line": to_float(data.get("line"), 0.0),
        "legs": to_float(data.get("legs"), 1.0),
        "source_trust": to_float(data.get("source_trust"), 1.0),
        "book_consensus": to_float(data.get("book_consensus"), 0.0),
        "consensus_sources": to_float(data.get("consensus_sources"), 0.0),
        "line_dispersion": to_float(data.get("line_dispersion"), 0.0),
        "closing_move": to_float(data.get("closing_move"), 0.0),
    }


def _load_runtime_registry() -> Dict[str, Any]:
    registry = _safe_json_load(MODEL_FILE, {}) or {}
    if isinstance(registry, Mapping) and registry.get("models"):
        return dict(registry)
    db = SupabaseRest()
    if not db.enabled:
        return dict(registry) if isinstance(registry, Mapping) else {}
    try:
        rows = db.get(
            "netrattler_autolearn_models",
            filters={"status": "eq.champion"},
            order="updated_at.desc",
            limit_total=5000,
        )
        models = {str(row.get("model_key")): row.get("model") for row in rows if isinstance(row.get("model"), Mapping)}
        if models:
            payload = {"version": 3, "updated_at": _utc(), "models": models, "source": "supabase"}
            try:
                _atomic_json_write(MODEL_FILE, payload)
            except Exception:
                pass
            return payload
    except Exception:
        pass
    return dict(registry) if isinstance(registry, Mapping) else {}


def predict_probability(data: Mapping[str, Any]) -> Optional[float]:
    registry = _load_runtime_registry()
    models = registry.get("models") or {} if isinstance(registry, Mapping) else {}
    row = _runtime_row(data)
    if not row or not models:
        return None
    keys = [
        f"market_league:{row['market_group']}:{row['league']}",
        f"market:{row['market_group']}",
        f"league:{row['league']}",
        "global",
    ]
    predictions: List[Tuple[float, float]] = []
    for rank, key in enumerate(keys):
        model = models.get(key)
        if not isinstance(model, Mapping):
            continue
        prediction = _predict_model(model, _vector(row))
        if prediction is not None:
            predictions.append((prediction, 4.0 - rank))
    if not predictions:
        return None
    return sum(p * w for p, w in predictions) / sum(w for _, w in predictions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        train_and_promote()
    else:
        print(json.dumps(_safe_json_load(MODEL_FILE, {}), indent=2)[:5000])


if __name__ == "__main__":
    main()
