"""Read-only specialist history merge and chronological Goal Hunter replay gates.

Never merge providers by fuzzy club names. Never use completed-match shots to
construct an in-play prediction. An explicit provider-ID crosswalk is mandatory.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

STATS = ("home_goals", "away_goals", "home_shots", "away_shots",
         "home_sot", "away_sot", "home_corners", "away_corners")
MIN_LIVE_BACKTEST_MATCHES = 100


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing_timestamp")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_timestamp") from None
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("timezone_required")
    return d


def _score(value: Any) -> tuple[int, int]:
    if (not isinstance(value, (list, tuple)) or len(value) != 2 or
            any(type(x) is not int or not 0 <= x <= 99 for x in value)):
        raise ValueError("invalid_score")
    return tuple(value)


def merge_historical_sources(rows: list[dict], crosswalk: dict | None = None) -> dict:
    """Combine exact historical rows; quarantine conflicts, keep unknown IDs distinct.

    crosswalk keys are '<provider>:<provider_event_id>'; values are mapping
    {'canonical_id', 'home_id', 'away_id', 'kickoff_unix'}.
    The mapping must be externally verified; never derive it from names.
    """
    mapping = crosswalk or {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    duplicate_count = 0
    for row in rows:
        if (not isinstance(row, dict) or
                row.get("data_kind") != "historical_completed_match" or
                row.get("live_eligible") is not False or
                row.get("odds_eligible") is not False):
            raise ValueError("non_historical_row_rejected")
        source, event = row.get("source"), str(row.get("event_id") or "")
        if not isinstance(source, str) or not source or not event:
            raise ValueError("missing_provider_identity")
        source_event = f"{source}:{event}"
        verified = mapping.get(source_event)
        if verified is not None:
            if (not isinstance(verified, dict) or
                    not verified.get("canonical_id") or
                    str(row.get("home_id")) != str(verified.get("home_id")) or
                    str(row.get("away_id")) != str(verified.get("away_id")) or
                    row.get("kickoff_unix") is None or
                    int(row["kickoff_unix"]) != int(verified.get("kickoff_unix") or -1)):
                raise ValueError("unverified_cross_provider_identity")
            group_key = "canonical:" + str(verified["canonical_id"])
        else:
            group_key = "provider:" + source_event
        grouped[group_key].append(dict(row))
    merged: list[dict] = []
    quarantined: list[dict] = []
    for key, items in sorted(grouped.items()):
        # Same provider fixture cannot silently have two distinct versions.
        seen_by_source: dict[str, dict] = {}
        conflicts: set[str] = set()
        for item in items:
            provider_key = str(item["source"]) + ":" + str(item["event_id"])
            old = seen_by_source.get(provider_key)
            if old is None:
                seen_by_source[provider_key] = item
            elif old != item:
                conflicts.add("inconsistent_duplicate_provider_row")
            else:
                duplicate_count += 1
        observed: dict[str, Any] = {}
        for item in seen_by_source.values():
            for field in STATS:
                value = item.get(field)
                if value is None:
                    continue
                if type(value) is not int or not 0 <= value <= 999:
                    conflicts.add("invalid_" + field)
                elif field in observed and observed[field] != value:
                    conflicts.add("conflicting_" + field)
                else:
                    observed[field] = value
        if conflicts:
            quarantined.append({"identity": key, "reasons": sorted(conflicts)})
            continue
        merged.append({
            "identity": key, "data_kind": "historical_completed_match",
            "live_eligible": False, "odds_eligible": False,
            "sources": sorted({x["source"] for x in items}),
            **{f: observed.get(f) for f in STATS},
        })
    return {
        "rows": merged, "quarantined": quarantined,
        "duplicates_removed": duplicate_count,
        "unique_matches": len(merged),
        "cannot_infer_cross_provider_ids": True,
        "live_signals_enabled": False,
    }


def replay_late_goal_predictions(rows: list[dict], min_samples: int = MIN_LIVE_BACKTEST_MATCHES) -> dict:
    """Compare locked baseline/candidate on distinct, verifiable LIVE snapshots.

    Entries must contain predictions actually computed before the event and a
    subsequent verified end score. Historical full-time statistics can NEVER
    be substituted for an in-play snapshot. No odds or telegram sends here.
    """
    if min_samples < 30:
        raise ValueError("minimum_sample_size_too_small")
    observed = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict) or r.get("data_kind") != "verified_live_prediction":
            raise ValueError("historical_data_is_not_live_backtest")
        if (r.get("identity_verified") is not True or
                r.get("source_timestamp_verified") is not True or
                r.get("model_locked") is not True):
            raise ValueError("unverified_snapshot_or_model")
        identity = str(r.get("canonical_fixture_id") or "")
        if not identity or identity in seen:
            raise ValueError("duplicate_or_missing_fixture")
        seen.add(identity)
        minute = r.get("minute")
        if type(minute) is not int or not 65 <= minute <= 85:
            raise ValueError("out_of_late_goal_window")
        tip_at = _timestamp(r.get("tip_at"))
        stats_at = _timestamp(r.get("stats_at"))
        final_at = _timestamp(r.get("final_at"))
        locked_at = _timestamp(r.get("locked_at"))
        if not locked_at <= stats_at <= tip_at < final_at:
            raise ValueError("lookahead_or_stale_order")
        if (tip_at - stats_at).total_seconds() > 600:
            raise ValueError("stale_inplay_statistics")
        initial = _score(r.get("score_at_tip"))
        final = _score(r.get("final_score"))
        if any(final[i] < initial[i] for i in (0, 1)):
            raise ValueError("inconsistent_score_history")
        baseline, candidate = r.get("baseline_send"), r.get("extra_sources_send")
        if type(baseline) is not bool or type(candidate) is not bool:
            raise ValueError("missing_locked_predictions")
        observed.append((sum(final) > sum(initial), baseline, candidate))
    if not observed:
        return {"status": "not_backtestable_no_live_snapshots",
                "verified_matches": 0, "live_uplift_confirmed": False}

    def summary(position: int) -> dict:
        tipped = [hit for hit, *predictions in observed if predictions[position]]
        return {
            "sent": len(tipped), "won": sum(tipped),
            "hit_rate": round(sum(tipped) / len(tipped), 4) if tipped else None,
        }

    return {
        "status": "insufficient_for_uplift" if len(observed) < min_samples
                  else "requires_independent_statistical_review",
        "verified_matches": len(observed),
        "baseline": summary(0), "extra_sources": summary(1),
        "live_uplift_confirmed": False,
        "same_set_of_verified_matches": True,
        "no_leaked_fulltime_stats": True,
    }
