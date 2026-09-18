#!/usr/bin/env python3
"""NETRATTLER V37 model registry helpers.

The existing serialized model tables stay untouched. This registry stores model
metadata, feature signatures and training fingerprints so runtime can reject an
incompatible model and training jobs can skip unchanged datasets.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def feature_hash(features: Sequence[str]) -> str:
    payload = json.dumps([str(x) for x in features], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def training_fingerprint(*, rows: int, columns: Iterable[str], max_date: Any = "", extra: Any = "") -> str:
    payload = {
        "rows": int(rows), "columns": sorted(map(str, columns)),
        "max_date": str(max_date or ""), "extra": extra,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:40]


def _headers(prefer: str = "resolution=merge-duplicates,return=minimal") -> Dict[str, str]:
    return {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Prefer": prefer}


def get_model(model_name: str) -> Optional[Dict[str, Any]]:
    if not URL or not KEY or requests is None:
        return None
    try:
        r = requests.get(
            f"{URL}/rest/v1/netrattler_model_registry", headers=_headers("return=representation"),
            params={"model_name": f"eq.{model_name}", "select": "*", "limit": "1"}, timeout=10,
        )
        rows = r.json() if r.ok else []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def register_model(meta: Mapping[str, Any], *, storage_table: str = "ml_models", status: str = "active") -> bool:
    if not URL or not KEY or requests is None or not meta.get("model_name"):
        return False
    features = list(meta.get("feature_cols") or [])
    row = {
        "model_name": str(meta.get("model_name")),
        "model_family": str(meta.get("model_family") or "match"),
        "storage_table": storage_table,
        "status": status,
        "feature_hash": feature_hash(features),
        "feature_count": len(features),
        "feature_cols": features,
        "training_samples": int(meta.get("training_samples") or 0),
        "brier_score": meta.get("brier_score"),
        "roc_auc": meta.get("roc_auc"),
        "training_fingerprint": meta.get("training_fingerprint"),
        "trained_at": meta.get("trained_at") or _utc(),
        "metadata": dict(meta),
        "updated_at": _utc(),
    }
    try:
        r = requests.post(
            f"{URL}/rest/v1/netrattler_model_registry", headers=_headers(),
            params={"on_conflict": "model_name"}, json=row, timeout=10,
        )
        return bool(r.ok)
    except Exception:
        return False


def features_compatible(model_name: str, features: Sequence[str]) -> bool:
    row = get_model(model_name)
    if not row:
        return True  # Registry is additive; legacy installs keep working.
    expected = str(row.get("feature_hash") or "")
    return not expected or expected == feature_hash(features)


def should_retrain(state_key: str, fingerprint: str, samples: int, *, min_new_samples: int = 50, max_age_days: int = 14) -> Tuple[bool, str]:
    if str(os.getenv("NETRATTLER_FORCE_RETRAIN", "false")).lower() in {"1", "true", "yes", "on"}:
        return True, "forced"
    row = get_model(f"__state__:{state_key}")
    if not row:
        return True, "no-training-state"
    old_fp = str(row.get("training_fingerprint") or "")
    old_samples = int(row.get("training_samples") or 0)
    if old_fp == fingerprint:
        return False, "training-data-unchanged"
    if samples - old_samples >= max(1, min_new_samples):
        return True, f"new-samples={samples-old_samples}"
    trained = str(row.get("trained_at") or row.get("updated_at") or "")
    try:
        dt = datetime.fromisoformat(trained.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).days
        if age >= max_age_days:
            return True, f"age={age}d"
    except Exception:
        pass
    return False, f"only-{max(0, samples-old_samples)}-new-samples"


def save_training_state(state_key: str, fingerprint: str, samples: int, *, metadata: Optional[Mapping[str, Any]] = None) -> bool:
    return register_model({
        "model_name": f"__state__:{state_key}", "model_family": "training_state",
        "feature_cols": [], "training_samples": int(samples),
        "training_fingerprint": fingerprint, "trained_at": _utc(),
        **({"state": dict(metadata)} if metadata else {}),
    }, storage_table="registry", status="state")


__all__ = ["feature_hash", "training_fingerprint", "get_model", "register_model", "features_compatible", "should_retrain", "save_training_state"]
