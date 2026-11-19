#!/usr/bin/env python3
"""Goal Hunter durable SQLite state, versioned in the SAME GitHub repository.

No Supabase, hosted database or external state service. GitHub Actions checks out
the dedicated state/goal-hunter branch into a separate worktree. A reservation
is pushed BEFORE Telegram is called; no untracked or duplicate messages.
Writes that cannot be pushed fail closed (the runner disk is ephemeral).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

STATE_BRANCH = "state/goal-hunter"
RELATIVE_PATH = "data/goal_hunter.sqlite3"
KEEP_DAYS = 45
MAX_SHADOW_ROWS = 4500


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def db_path() -> Path:
    return Path(os.getenv("LMG_SQLITE_PATH", RELATIVE_PATH)).resolve()


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not path.is_file():
        raise RuntimeError("goal_hunter_sqlite_not_initialized")
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init() -> Path:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size == 0:
        raise RuntimeError("goal_hunter_sqlite_invalid_empty_file")
    conn = sqlite3.connect(str(path), timeout=15)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_key TEXT PRIMARY KEY,
            fixture_id INTEGER NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            minute INTEGER NOT NULL,
            score TEXT NOT NULL,
            selection TEXT NOT NULL DEFAULT 'Over 0.5 rest of match',
            observed_odds REAL,
            status TEXT NOT NULL DEFAULT 'reserved',
            telegram_message_id INTEGER,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            message_kind TEXT NOT NULL DEFAULT 'photo',
            final_score TEXT,
            settled_at TEXT,
            next_goal_side TEXT,
            next_goal_result TEXT,
            signal_tier TEXT,
            source TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS alerts_pending_idx
            ON alerts(status, sent_at);
        CREATE TABLE IF NOT EXISTS shadow_snapshots (
            provider TEXT NOT NULL,
            fixture_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            final_home_goals INTEGER,
            final_away_goals INTEGER,
            final_verified_at TEXT,
            PRIMARY KEY(provider, fixture_id, slot)
        );
        CREATE INDEX IF NOT EXISTS snapshots_pending_idx
            ON shadow_snapshots(final_verified_at, collected_at);
        """)
        conn.commit()
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError("goal_hunter_sqlite_integrity_check_failed")
    finally:
        conn.close()
    persist("init SQLite state")
    return path


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(worktree), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    if result.returncode:
        # Never include command output containing remote credential information.
        raise RuntimeError("goal_hunter_git_state_sync_failed:" + args[0])
    return result


def persist(reason: str) -> bool:
    """Push every durable transition. Fail closed before any Telegram send."""
    if os.getenv("LMG_SQLITE_SYNC", "").lower() != "true":
        return False  # explicitly local/offline test mode
    worktree = Path(os.environ["LMG_STATE_WORKTREE"]).resolve()
    path = db_path()
    if path != worktree / RELATIVE_PATH:
        raise RuntimeError("goal_hunter_sqlite_unexpected_path")
    if not (worktree / ".git").exists():
        raise RuntimeError("goal_hunter_git_worktree_missing")
    _git(worktree, "add", "--", RELATIVE_PATH)
    changed = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--quiet",
                             "--", RELATIVE_PATH], timeout=20)
    if changed.returncode == 0:
        return False
    if changed.returncode != 1:
        raise RuntimeError("goal_hunter_git_diff_failed")
    _git(worktree, "-c", "user.name=NETRATTLER State Bot",
         "-c", "user.email=state-bot@users.noreply.github.com",
         "commit", "-m", "state(goal-hunter): " + reason[:70])
    _git(worktree, "push", "origin", "HEAD:refs/heads/" + STATE_BRANCH)
    return True


def reserve_alert(fixture: dict, metrics: dict | None = None) -> str | None:
    key = str(fixture["fixture_id"])
    conn = _connect()
    try:
        cursor = conn.execute("""
          INSERT OR IGNORE INTO alerts
          (alert_key, fixture_id, home, away, minute, score, selection,
           status, created_at, message_kind, next_goal_side, signal_tier, source)
          VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', ?, 'photo', ?, ?, ?)
        """, (key, int(fixture["fixture_id"]), fixture["home"], fixture["away"],
              int(fixture["minute"]), f'{fixture["hg"]}:{fixture["ag"]}',
              "Over 0.5 rest of match", utcnow(),
              (metrics or {}).get("next_goal_side"), (metrics or {}).get("tier"),
              fixture.get("source") or "espn"))
        conn.commit()
        inserted = cursor.rowcount == 1
    finally:
        conn.close()
    if inserted:
        persist("reserve fixture " + key)
        return key
    return None


def mark_sent(key: str, message_id: int) -> None:
    conn = _connect()
    try:
        cursor = conn.execute("""
            UPDATE alerts SET status='sent', telegram_message_id=?, sent_at=?
            WHERE alert_key=? AND status='reserved' AND telegram_message_id IS NULL
        """, (int(message_id), utcnow(), str(key)))
        conn.commit()
        if cursor.rowcount != 1:
            raise RuntimeError("goal_hunter_sent_state_not_reserved")
    finally:
        conn.close()
    persist("Telegram sent fixture " + str(key))


def pending() -> list[dict]:
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute("""
          SELECT * FROM alerts WHERE status='sent' AND telegram_message_id IS NOT NULL
          ORDER BY sent_at ASC LIMIT 80
        """).fetchall()]
    finally:
        conn.close()


def mark_settled(row: dict, score: tuple[int, int], won: bool) -> None:
    conn = _connect()
    try:
        cursor = conn.execute("""
          UPDATE alerts SET status=?, final_score=?, settled_at=?, next_goal_result=?
          WHERE alert_key=? AND status='sent'
        """, ("won" if won else "lost", f"{score[0]}:{score[1]}",
              utcnow(), row.get("next_goal_result"), row["alert_key"]))
        conn.commit()
        if cursor.rowcount != 1:
            raise RuntimeError("goal_hunter_settlement_state_changed")
    finally:
        conn.close()
    persist("settle fixture " + row["alert_key"])


def write_snapshots(rows: list[dict], *, enabled: bool = False,
                    now: dt.datetime | None = None) -> dict:
    if not enabled:
        return {"status": "disabled", "attempted": 0}
    if not rows:
        return {"status": "empty", "attempted": 0}
    if len(rows) > 16:
        raise ValueError("shadow_batch_exceeds_maximum")
    by_key: dict[tuple, dict] = {}
    for row in rows:
        key = (row["provider"], int(row["fixture_id"]), int(row["slot"]))
        if key in by_key and by_key[key] != row:
            raise ValueError("conflicting_same_batch_snapshot")
        by_key[key] = row
    cutoff = ((now or dt.datetime.now(dt.timezone.utc)) -
              dt.timedelta(days=KEEP_DAYS)).astimezone(dt.timezone.utc).isoformat()
    conn = _connect()
    try:
        deleted = conn.execute("DELETE FROM shadow_snapshots WHERE collected_at < ?",
                               (cutoff,)).rowcount
        count = conn.execute("SELECT COUNT(*) FROM shadow_snapshots").fetchone()[0]
        new_rows = [(key, row) for key, row in by_key.items()
                    if conn.execute("""SELECT 1 FROM shadow_snapshots
                        WHERE provider=? AND fixture_id=? AND slot=?""", key).fetchone() is None]
        if count + len(new_rows) > MAX_SHADOW_ROWS:
            conn.commit()
            result = {"status": "capacity_limit", "attempted": len(by_key), "rows": count}
            changed = deleted > 0
        else:
            for (provider, fixture_id, slot), row in new_rows:
                conn.execute("""
                  INSERT INTO shadow_snapshots
                  (provider,fixture_id,slot,collected_at,payload_json)
                  VALUES (?,?,?,?,?)
                """, (provider, fixture_id, slot, row["collected_at"],
                      json.dumps(row, ensure_ascii=False, separators=(",", ":"))))
            conn.commit()
            result = {"status": "saved", "attempted": len(by_key),
                      "existing": count, "inserted": len(new_rows)}
            changed = deleted > 0 or bool(new_rows)
    finally:
        conn.close()
    if changed:
        persist("capture verified live snapshots")
    return result


def pending_snapshots(now: dt.datetime | None = None) -> list[dict]:
    cutoff = ((now or dt.datetime.now(dt.timezone.utc)) -
              dt.timedelta(days=4)).astimezone(dt.timezone.utc).isoformat()
    conn = _connect()
    try:
        rows = conn.execute("""
          SELECT payload_json FROM shadow_snapshots
          WHERE final_verified_at IS NULL AND collected_at >= ?
          ORDER BY collected_at ASC LIMIT 120
        """, (cutoff,)).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]
    finally:
        conn.close()


def settle_snapshot(provider: str, fixture_id: int, final: tuple[int, int],
                    when: dt.datetime | None = None) -> int:
    conn = _connect()
    try:
        cursor = conn.execute("""
          UPDATE shadow_snapshots
          SET final_home_goals=?, final_away_goals=?, final_verified_at=?
          WHERE provider=? AND fixture_id=? AND final_verified_at IS NULL
        """, (final[0], final[1],
              (when or dt.datetime.now(dt.timezone.utc)).isoformat(),
              provider, fixture_id))
        conn.commit()
        changed = cursor.rowcount
    finally:
        conn.close()
    if changed:
        persist("settle live snapshots")
    return changed


def status() -> dict:
    conn = _connect()
    try:
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM alerts GROUP BY status")}
        return {"alerts": counts,
                "snapshots": conn.execute("SELECT COUNT(*) FROM shadow_snapshots").fetchone()[0],
                "storage": str(db_path()), "backend": "sqlite_git"}
    finally:
        conn.close()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "init":
        print("LMG_SQLITE_INITIALIZED", str(init()), flush=True)
    elif command == "status":
        print("LMG_SQLITE_STATUS", json.dumps(status()), flush=True)
    else:
        raise SystemExit("usage: netrattler_lmg_store.py [init|status]")
