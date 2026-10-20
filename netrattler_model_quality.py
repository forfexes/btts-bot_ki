"""Quality gate for stored ML models.

A model is only used at runtime when it demonstrably beats the base rate:
- Brier score on its evaluation set must be below the constant-prediction Brier p*(1-p)
  by at least MIN_SKILL (relative), otherwise it adds noise to the edge calculation;
- ROC-AUC must lie in [MIN_AUC, MAX_AUC]; a very high AUC on match/prop data is a leakage signal;
- the model must not be older than MAX_AGE_DAYS;
- models marked no_skill by the trainer are rejected;
- rows without any meta are legacy and stay allowed (no evidence either way).
Rejected models fall back to the existing Elo/Poisson or empirical estimates.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

MIN_SKILL = float(os.getenv("NETRATTLER_MODEL_MIN_SKILL", "0.005"))
MIN_AUC = float(os.getenv("NETRATTLER_MODEL_MIN_AUC", "0.55"))
MAX_AUC = float(os.getenv("NETRATTLER_MODEL_MAX_AUC", "0.92"))
MAX_AGE_DAYS = int(os.getenv("NETRATTLER_MODEL_MAX_AGE_DAYS", "60"))


def parse_meta(meta: Any) -> Dict[str, Any]:
    for _ in range(3):
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                return {}
        else:
            break
    return meta if isinstance(meta, dict) else {}


def base_brier(pos_rate: float) -> float:
    p = min(max(float(pos_rate), 0.0), 1.0)
    return p * (1.0 - p)


def model_has_skill(meta: Any, now: Optional[datetime] = None) -> Tuple[bool, str]:
    m = parse_meta(meta)
    if not m:
        # Legacy rows without metrics: unknown quality -> keep previous behaviour (allowed).
        return True, "no meta (legacy)"
    if m.get("no_skill") is True:
        return False, "trainer marked no_skill"
    try:
        brier = float(m.get("brier_score"))
        pos = float(m.get("positive_rate"))
    except (TypeError, ValueError):
        return False, "no brier/positive_rate"
    if not (0.0 < pos < 1.0):
        return False, f"degenerate positive_rate {pos}"
    base = float(m.get("base_brier") or base_brier(pos))
    if brier >= base * (1.0 - MIN_SKILL):
        return False, f"brier {brier:.4f} not better than base {base:.4f}"
    try:
        auc = float(m.get("roc_auc"))
    except (TypeError, ValueError):
        auc = 0.5
    if auc < MIN_AUC:
        return False, f"auc {auc:.3f} < {MIN_AUC}"
    if auc > MAX_AUC:
        return False, f"auc {auc:.3f} > {MAX_AUC} (leakage suspected)"
    ts = str(m.get("trained_at") or "")
    if ts:
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age = ((now or datetime.now(timezone.utc)) - t).days
            if age > MAX_AGE_DAYS:
                return False, f"stale ({age} days)"
        except ValueError:
            pass
    return True, "ok"
