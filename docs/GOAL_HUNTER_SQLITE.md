# Goal Hunter: SQLite in GitHub (19 Nov 2026)

The **Goal Hunter / Last Minute Goal** pipeline no longer needs Supabase
credentials or quota preflight. The primary and secondary five-minute
workflows now read and write a SQLite database kept inside this repository.

- Code branch: `main`
- State branch: `state/goal-hunter`
- Database file: `data/goal_hunter.sqlite3` **on the state branch**
- Main workflow: `.github/workflows/netrattler_lmg_free.yml`
- Independent backup: `.github/workflows/netrattler_lmg_backup.yml`
- Storage implementation: `netrattler_lmg_store.py`
- Offline tests: `test_netrattler_lmg_store.py`, `test_netrattler_lmg_shadow.py`

## How this avoids ephemeral GitHub Actions storage

The workflows fetch the `state/goal-hunter` branch into an isolated Git
worktree, run SQLite integrity/schema initialization, read original alerts and
snapshots, then commit/push the database to that state branch after **every
durable state change**. The workflows share a single concurrency group.

The bot commits a unique reservation to GitHub **before** the Telegram
`sendPhoto` request. If persistence fails, the send does not happen.
Successful delivery immediately writes the Telegram message ID; settlement
edits that original message and persists the verified result.

A delivery crash between reservation and recording the Telegram response
leaves a `reserved` row. That row intentionally blocks re-send until
reconciled, because blind retries could duplicate the Telegram tip.

Snapshots are bounded to 4,500 rows and a rolling 45 days. Historical
verified alerts are retained; Git version history itself is not unlimited.

## Privacy and cost

This repository is **public**. SQLite records contain match information,
performance and Telegram *message IDs* (not a Telegram token or chat ID).
Anyone can see state branch history. No credentials or chat IDs should ever
be written to this database. SQLite is free, but frequent binary commits
consume GitHub repository storage and Actions runtime. Monitor repository
size and trim/rotate old history deliberately, not silently.

## Verification

1. The `verify` job runs the offline SQLite and Goal Hunter tests on pushes
   and manual executions.
2. The `scan` job mounts the state branch, runs
   `python netrattler_lmg_store.py init`, and then launches live scanning.
3. Look for `LMG_SQLITE_INITIALIZED` and `LMG_SQLITE_STATUS` in the scan
   job logs. A new commit on `state/goal-hunter` confirms successful writeback.
4. Check `alerts` statuses and snapshot counts. Do not treat a passing
   syntax check as a confirmed live Telegram tip.

The existing Supabase tables and two old settled rows are *not* automatically
imported. This migration changes Goal Hunter's production storage only,
not the broader NETRATTLER/BTTS pipelines that still use their own backends.
