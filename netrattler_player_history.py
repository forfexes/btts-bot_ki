#!/usr/bin/env python3
"""NETRATTLER 365-day player match history backfill.

Historical dates use only date-native match collectors (FotMob + SofaScore).
Static/season sources belong to the normal daily enrichment job and are not
re-fetched hundreds of times. Odds are never collected here.
"""
from __future__ import annotations
import argparse, json, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["USE_ODDSHARVESTER_STYLE"] = "false"
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["TELEGRAM_GROUP_STATS"] = ""

import scrape_player_stats as scraper


def _load(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("completed_dates", []))
    except Exception:
        return set()


def _save(path: Path, completed: set[str]) -> None:
    path.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_dates": sorted(completed),
    }, indent=2), encoding="utf-8")


def dates(days: int, end_date: str | None):
    end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else (
        datetime.now(timezone.utc) - timedelta(days=1)).date()
    start = end - timedelta(days=max(1, days) - 1)
    for i in range((end - start).days + 1):
        yield (start + timedelta(days=i)).isoformat()


def collect_date(day: str) -> int:
    """Collect actual per-match player rows for one historical date."""
    jobs = []
    if scraper.USE_FOTMOB:
        jobs.append(("fotmob", lambda: scraper.scrape_fotmob_date(day)))
    if scraper.USE_SOFASCORE:
        jobs.append(("sofascore", lambda: scraper.scrape_sofascore_date(day)))

    rows = []
    with ThreadPoolExecutor(max_workers=max(1, min(2, len(jobs)))) as pool:
        futs = {pool.submit(fn): name for name, fn in jobs}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                got = fut.result() or []
                rows.extend(got)
                print(f"  {name}: {len(got)} rows")
            except Exception as exc:
                print(f"  {name}: FAILED {str(exc)[:160]}")

    clean = scraper._dedupe_rows(rows, "source,event_id,player_id,stat_name")
    saved = scraper._sb_post(
        "player_match_stats", clean,
        conflict="source,event_id,player_id,stat_name",
    )
    print(f"  raw={len(rows)} unique={len(clean)} saved={saved}")
    return int(saved or 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--end-date")
    ap.add_argument("--resume-file", default=".player_history.json")
    ap.add_argument("--max-dates", type=int, default=7,
                    help="Dates per invocation; rerun to resume. Default 7 keeps CI bounded.")
    args = ap.parse_args()

    resume = Path(args.resume_file)
    completed = _load(resume)
    attempted = saved_total = 0

    for day in dates(args.days, args.end_date):
        if day in completed:
            continue
        if args.max_dates and attempted >= args.max_dates:
            break
        attempted += 1
        print(f"\n=== PLAYER HISTORY {day} ===")
        try:
            saved_total += collect_date(day)
        except Exception as exc:
            print(f"FAILED {day}: {exc}")
            continue
        completed.add(day)
        _save(resume, completed)

    print(f"PLAYER HISTORY DONE attempted={attempted} completed={len(completed)} saved={saved_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
