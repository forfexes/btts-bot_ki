#!/usr/bin/env python3
"""NETRATTLER 365-day player match history backfill.

Historical dates use only date-native match collectors (FotMob + SofaScore).
Static/season sources belong to the normal daily enrichment job and are not
re-fetched hundreds of times. Odds are never collected here.
"""
from __future__ import annotations
import argparse, json, os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["USE_ODDSHARVESTER_STYLE"] = "false"
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["TELEGRAM_GROUP_STATS"] = ""

import scrape_player_stats as scraper

JOB_KEY = "player_history_365d"
PROGRESS_TABLE = "netrattler_backfill_progress"


def _progress_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or scraper.SUPABASE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _load_remote() -> set[str]:
    """Load completed dates from Supabase so fresh CI runners resume correctly."""
    if not scraper.SUPABASE_URL or not scraper.SUPABASE_KEY:
        return set()
    endpoint = f"{scraper.SUPABASE_URL.rstrip('/')}/rest/v1/{PROGRESS_TABLE}"
    try:
        r = requests.get(endpoint, headers=_progress_headers(), params={
            "select": "backfill_date",
            "job_key": f"eq.{JOB_KEY}",
            "status": "eq.completed",
            "order": "backfill_date.asc",
        }, timeout=30)
        if not r.ok:
            print(f"  ⚠️  Progress load {r.status_code}: {r.text[:200]}")
            return set()
        return {str(row["backfill_date"]) for row in r.json() if row.get("backfill_date")}
    except Exception as exc:
        print(f"  ⚠️  Progress load failed: {str(exc)[:160]}")
        return set()


def _save_remote(day: str, rows_saved: int, status: str = "completed") -> bool:
    """Persist one date checkpoint in Supabase. Service-role workflow access bypasses RLS."""
    if not scraper.SUPABASE_URL or not scraper.SUPABASE_KEY:
        return False
    endpoint = f"{scraper.SUPABASE_URL.rstrip('/')}/rest/v1/{PROGRESS_TABLE}"
    headers = _progress_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    try:
        r = requests.post(endpoint, headers=headers,
            params={"on_conflict": "job_key,backfill_date"}, json=[{
                "job_key": JOB_KEY,
                "backfill_date": day,
                "status": status,
                "rows_saved": int(rows_saved or 0),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }], timeout=30)
        if not r.ok:
            print(f"  ⚠️  Progress save {r.status_code}: {r.text[:200]}")
        return r.ok
    except Exception as exc:
        print(f"  ⚠️  Progress save failed: {str(exc)[:160]}")
        return False


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
    ap.add_argument("--max-dates", type=int, default=365,
                    help="Maximum missing dates per invocation.")
    ap.add_argument("--date-workers", type=int, default=4,
                    help="Historical dates processed concurrently; default 4.")
    args = ap.parse_args()

    resume = Path(args.resume_file)
    completed = _load_remote() | _load(resume)
    print(f"Persistent progress: {len(completed)} completed dates")
    pending = [day for day in dates(args.days, args.end_date) if day not in completed]
    if args.max_dates:
        pending = pending[:args.max_dates]
    attempted = len(pending)
    saved_total = 0
    workers = max(1, min(int(args.date_workers or 1), 8, len(pending) or 1))
    print(f"Pending dates: {attempted}; date workers: {workers}")

    def run_day(day: str):
        print(f"\n=== PLAYER HISTORY {day} ===")
        try:
            return day, collect_date(day), None
        except Exception as exc:
            return day, 0, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run_day, day): day for day in pending}
        for fut in as_completed(futs):
            day, saved, error = fut.result()
            if error:
                print(f"FAILED {day}: {error}")
                continue
            saved_total += saved
            if not _save_remote(day, saved):
                print(f"FAILED {day}: checkpoint was not persisted; date will be retried safely")
                continue
            completed.add(day)
            _save(resume, completed)
            print(f"CHECKPOINT {day}: saved={saved} completed={len(completed)}")

    print(f"PLAYER HISTORY DONE attempted={attempted} completed={len(completed)} saved={saved_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
