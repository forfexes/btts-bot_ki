#!/usr/bin/env python3
"""NETRATTLER player-history backfill.

Runs the existing verified player-stat collectors over a bounded historical
window.  It deliberately disables odds harvesting and Telegram: this job is
for model/history data only and must never manufacture or imply bookmaker odds.

Examples:
  python netrattler_player_history.py --days 365
  python netrattler_player_history.py --days 30 --resume-file .player_history.json
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# History collection is stats-only.  Odds are collected by the dedicated
# real-odds pipeline and REAL_ODDS_ONLY remains authoritative.
os.environ.setdefault("USE_ODDSHARVESTER_STYLE", "false")
os.environ.setdefault("TELEGRAM_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")
os.environ.setdefault("TELEGRAM_GROUP_STATS", "")

import scrape_player_stats as scraper


def _load_resume(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("completed_dates", [])}
    except Exception:
        return set()


def _save_resume(path: Path, completed: set[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_dates": sorted(completed),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def iter_dates(days: int, end_date: str | None = None):
    end = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_date
        else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    )
    start = end - timedelta(days=max(1, days) - 1)
    current = start
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--end-date", default=None)
    ap.add_argument("--resume-file", default=".player_history.json")
    ap.add_argument("--max-dates", type=int, default=0,
                    help="Optional chunk size; 0 processes the whole requested window")
    args = ap.parse_args()

    resume = Path(args.resume_file)
    completed = _load_resume(resume)
    attempted = saved_total = 0

    for day in iter_dates(args.days, args.end_date):
        if day in completed:
            continue
        if args.max_dates and attempted >= args.max_dates:
            break
        attempted += 1
        print(f"\n=== PLAYER HISTORY {day} ===")
        try:
            saved = int(scraper.scrape_player_stats(day) or 0)
        except Exception as exc:
            print(f"FAILED {day}: {exc}")
            continue
        saved_total += saved
        # A successful zero-row day is still complete; rerunning it forever
        # would only waste source quotas.
        completed.add(day)
        _save_resume(resume, completed)

    print(
        f"PLAYER HISTORY DONE attempted={attempted} "
        f"completed={len(completed)} saved={saved_total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
