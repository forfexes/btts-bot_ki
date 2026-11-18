#!/usr/bin/env python3
"""Licensed-specialist source adapter and fail-closed, read-only coverage audit.

Only FootyStats exposes a documented test API here. It is HISTORICAL ONLY.
Never pass this adapter's rows to live scoring, bookmaker odds or settlement.
Other vendors are registered for capability discovery, not scraped or faked.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import requests

FOOTYSTATS_ENDPOINT = "https://api.football-data-api.com/league-matches"
EXAMPLE_SEASON = 1625  # Official free sample: Premier League 2018/19
MAX_PAGES = 2
PER_PAGE = 100

SOURCES = {
    "footystats": {
        "use": "historical_match_stats_and_backtesting",
        "live": False,
        "api": "official_with_key",
        "env": "FOOTYSTATS_API_KEY",
        "status": "licensed_key_required",
        "reference": "https://footystats.org/api/documentations/faq",
    },
    "sofascore": {
        "use": "reference_only",
        "live": False,
        "api": "no_public_api",
        "status": "not_automated",
        "reference": "https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability",
    },
    "overlyzer": {
        "use": "live_pressure_research",
        "live": False,
        "api": "no_verified_public_feed",
        "status": "not_automated",
        "reference": "https://www.overlyzer.com/en/live",
    },
    "statisticsports": {
        "use": "live_and_historical_research",
        "live": False,
        "api": "commercial_inquiry_required",
        "status": "not_automated",
        "reference": "https://statisticsports.com/en/data-api",
    },
    "besoccer": {
        "use": "lower_league_coverage_research",
        "live": False,
        "api": "paid_contract_required",
        "status": "not_automated",
        "reference": "https://api.besoccer.com/en/budgets",
    },
}

def _count(value: Any) -> int | None:
    """A negative or missing provider sentinel is not observed zero."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        s = str(value).strip()
        if not re.fullmatch(r"\d+(?:\.0+)?", s):
            return None
        n = int(float(s))
        return n if n <= 999 else None
    except (ValueError, TypeError, OverflowError):
        return None

def _identifier(value: Any) -> int | None:
    """Provider IDs are unbounded relative to counts like corners/shots."""
    if value is None or isinstance(value, bool):
        return None
    string = str(value).strip()
    if not re.fullmatch(r"[1-9]\d{0,17}", string):
        return None
    return int(string)

def normalize_footystats_match(item: Any, season_id: int) -> dict[str, Any] | None:
    if not isinstance(item, dict) or str(item.get("status", "")).lower() != "complete":
        return None
    event_id = _identifier(item.get("id"))
    home_id = _identifier(item.get("homeID"))
    away_id = _identifier(item.get("awayID"))
    hg, ag = _count(item.get("homeGoalCount")), _count(item.get("awayGoalCount"))
    if (not event_id or not home_id or not away_id or home_id == away_id
            or hg is None or ag is None):
        return None
    return {
        "source": "footystats",
        "data_kind": "historical_completed_match",
        "live_eligible": False,
        "odds_eligible": False,
        "event_id": str(event_id),
        "season_id": season_id,
        "home_id": str(home_id),
        "away_id": str(away_id),
        "home_goals": hg, "away_goals": ag,
        "home_shots": _count(item.get("team_a_shots")),
        "away_shots": _count(item.get("team_b_shots")),
        "home_sot": _count(item.get("team_a_shotsOnTarget")),
        "away_sot": _count(item.get("team_b_shotsOnTarget")),
        "home_corners": _count(item.get("team_a_corners")),
        "away_corners": _count(item.get("team_b_corners")),
        "kickoff_unix": _count_timestamp(item.get("date_unix")),
    }

def _count_timestamp(value: Any) -> int | None:
    try:
        n = int(value)
        return n if 946684800 <= n <= 4102444800 else None
    except (ValueError, TypeError, OverflowError):
        return None

def fetch_footystats_history(
    *,
    api_key: str,
    season_id: int,
    limit_pages: int = MAX_PAGES,
    get: Callable[..., Any] = requests.get,
) -> list[dict[str, Any]]:
    """Fetch at most 2 pages. Production key required for non-demo seasons.

    Caller owns any storage or analysis; this function does neither.
    """
    if not api_key or api_key != api_key.strip() or not api_key.strip():
        raise ValueError("FootyStats API key missing")
    if not isinstance(season_id, int) or season_id <= 0:
        raise ValueError("invalid season ID")
    if api_key == "example" and season_id != EXAMPLE_SEASON:
        raise ValueError("demo key is restricted to the documented sample season")
    pages = min(MAX_PAGES, max(1, int(limit_pages)))
    all_rows: dict[str, dict[str, Any]] = {}
    for page in range(1, pages + 1):
        try:
            response = get(
                FOOTYSTATS_ENDPOINT,
                params={"key": api_key, "season_id": season_id,
                        "page": page, "max_per_page": PER_PAGE},
                timeout=12,
                headers={"Accept": "application/json", "User-Agent": "NETRATTLER-specialized-audit/1.0"},
            )
            if response.status_code == 429:
                raise RuntimeError("FootyStats rate_limited")
            if response.status_code in (401, 403):
                raise RuntimeError("FootyStats access_denied")
            if not response.ok:
                raise RuntimeError(f"FootyStats http_{int(response.status_code)}")
            payload = response.json()
        except requests.RequestException:
            # Do not print requests' URL: it contains the provider credential.
            raise RuntimeError("FootyStats connection_error") from None
        except ValueError:
            raise RuntimeError("FootyStats invalid_json") from None
        if not isinstance(payload, dict) or payload.get("success") not in (True, 1):
            raise RuntimeError("FootyStats api_response_unavailable")
        batch = payload.get("data")
        if not isinstance(batch, list):
            raise RuntimeError("FootyStats schema_mismatch")
        for raw in batch:
            row = normalize_footystats_match(raw, season_id)
            if row is None:
                continue
            old = all_rows.get(row["event_id"])
            if old is not None and old != row:
                raise RuntimeError("FootyStats inconsistent_duplicate_match")
            all_rows[row["event_id"]] = row
        if len(batch) < PER_PAGE:
            break
    return list(all_rows.values())

def coverage_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """No inferred event crosswalk between providers; compare IDs only if verified."""
    valid = [r for r in rows if r.get("source") == "footystats"
             and r.get("data_kind") == "historical_completed_match"
             and r.get("live_eligible") is False]
    return {
        "completed_matches": len(valid),
        "with_shots_both": sum(r.get("home_shots") is not None and r.get("away_shots") is not None for r in valid),
        "with_sot_both": sum(r.get("home_sot") is not None and r.get("away_sot") is not None for r in valid),
        "with_corners_both": sum(r.get("home_corners") is not None and r.get("away_corners") is not None for r in valid),
        "unmatched_to_other_providers": len(valid),
        "no_unverified_team_matching": True,
    }

def audit(*, demo: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow_read_only",
        "telegram_messages": 0,
        "supabase_writes": 0,
        "live_signals_enabled": False,
        "source_catalog": {k: dict(v) for k, v in SOURCES.items()},
    }
    token = os.getenv("FOOTYSTATS_API_KEY", "").strip()
    # Demo is explicit and never spends a paid key.
    if demo:
        key, season_id = "example", EXAMPLE_SEASON
    elif token:
        key, season_id = token, int(os.getenv("FOOTYSTATS_SEASON_ID", str(EXAMPLE_SEASON)))
    else:
        result["footystats_probe"] = {"status": "skipped_missing_key"}
        return result
    try:
        rows = fetch_footystats_history(api_key=key, season_id=season_id)
        result["footystats_probe"] = {
            "status": "sample_ok" if demo and rows else "historical_ok" if rows else "no_completed_matches",
            "season_id": season_id,
            **coverage_report(rows),
        }
    except (ValueError, RuntimeError, requests.RequestException) as error:
        # Only internal sanitized messages (never URL, token, or raw payload).
        result["footystats_probe"] = {"status": "failed", "reason": str(error)[:120]}
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Try only FootyStats' public sample key")
    parser.add_argument("--out", default="", help="Optional JSON audit report path")
    args = parser.parse_args()
    report = audit(demo=args.demo)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
