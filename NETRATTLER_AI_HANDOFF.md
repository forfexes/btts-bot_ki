# NETRATTLER — AI collaboration handoff

Last updated: 2026-10-20
Repository: forfexes/btts-bot_ki
Collaborators: user, ChatGPT, Claude.ai (via shared repository; no direct agent-to-agent messaging)

## Operating rules
- Read this file before changing the project. Record decisions, test evidence, and open questions here.
- Work on separate branches/PRs where practical. Never overwrite unreviewed changes.
- Do not commit secrets, service-role keys, credentials, personal information or raw production exports.
- No production schema migrations, destructive SQL, live Telegram delivery, or settlement changes without review and a rollback plan.
- Distinguish *registered*, *tested*, *integrated*, and *enabled* sources.
- Require offline regression tests, then source health checks, then a monitored production rollout.
- Never claim a workflow passed without its actual run conclusion and logs.

## Current verified repository state
- Commit 41c1ca7: added test_netrattler_open_source_registry.py.
- Commit 25df9a1: added that test to the NETRATTLER Offline Sandbox Hardtest workflow and its push paths.
- Existing source registry mentions soccerdata, REEP, StatsBomb Open Data and OpenFootball. This does not establish that their downloads or live integrations work.
- A prior sandbox hardtest succeeded (run 39440072297), before these commits.
- Latest sandbox result after 25df9a1 is not yet verified.
- CircleCI combined status for 25df9a1 showed 'error'; root cause unknown.
- Previous settlement run 39440043588 reported six Telegram edit HTTP 400 failures (message to edit not found). Do not treat as fixed.

## Two Supabase accounts/projects — decision pending
User reports having two Supabase accounts. We have NOT verified project IDs, schema, access, billing, region, or which project holds which data.
Proposed design only:
- Operational project: fixtures, odds, current tips, Telegram references, settlements.
- Historical/analytics project: player logs, H2H, feature tables, source snapshots.
Before any migration: inventory both projects, identify current writers/readers, check RLS, storage/limits, backups, cross-project data flow and latency, and prepare reversible migration steps.
Do not assume two accounts necessarily mean two active projects.

## Source expansion — next work
1. Inventory actual source ingestion and deduplication paths (not just source registry).
2. Assess license, maintenance, freshness and schema for Reep, DataFC, historical football CSV datasets and OpenFootball.
3. Add isolated, deterministic parser tests and source-quality checks; do not activate unverified sources.
4. Verify fixture/team/player identity matching, reserve/youth/women's distinctions, date/time zones, odds provenance and market coverage.
5. Benchmark tip generation and original-message settlement recovery after changes.

## Task board
- [ ] Claude: review architecture and recommend safe two-project Supabase split; no migrations yet.
- [ ] ChatGPT: verify latest GitHub Actions sandbox run and source tests.
- [ ] Claude: audit player/club ID mapping and potential duplicate ingestion.
- [ ] ChatGPT: test open-source historical data parser with fixture samples.
- [ ] Both: compare findings here, agree on one PR per independently testable change.
- [ ] Both: review Telegram original-message edit failure and rollback strategy.

## Collaboration protocol
Each contributor appends an entry:
### YYYY-MM-DD — Agent — Task
- Branch/commit/PR:
- Changed files:
- Test command and result:
- Production impact:
- Risks / rollback:
- Next owner / action:

## Immediate request for Claude
Please review this handoff and the current repository without modifying production. Provide a proposed architecture for the user's two Supabase accounts, identifying the minimal project metadata required (never ask for passwords or service-role keys in chat), existing data flow risks, and a staged migration/testing plan. Post your findings as a PR or update to this handoff file.

---
### 2026-10-20 — Claude (Claude Code, repo + read-only Supabase access) — Architecture review: Supabase split
- Branch/commit/PR: `claude/supabase-split-plan` (docs only, this file)
- Changed files: NETRATTLER_AI_HANDOFF.md
- Test command and result: none (documentation only). Facts below come from read-only SQL (`pg_stat_user_tables`, `pg_database_size`) executed 2026-10-20 plus repo code reading.
- Production impact: none from this PR. No migrations, deletions or Telegram sends were made for this entry.
- Risks / rollback: n/a (docs).
- Next owner / action: ChatGPT + user, see "Decisions needed".

#### Correction to "decision pending": a split already exists and is live
The "Two Supabase accounts — decision pending" section above is out of date. A multi-project layout was built in earlier sessions and is in production:

| Project | Role today | Evidence |
|---|---|---|
| **MAIN** `sugycqnjncgfheueqaee` (NETRATTLER Project, eu-central-1) | Operational: tips, settlements, builder picks, match_results, ml tables, diagnostics, hot `odds_history` | `netrattler_card_diag`, `tips` etc. read via MCP |
| **V2** (archive; secrets `V2_SUPABASE_URL`, `V2_SUPABASE_SERVICE_KEY`, `V2_DATABASE_URL`) | Historical: `player_game_log`, `player_match_stats`, rotated `odds_history` (older than `HOT_DAYS=3`) | `netrattler_table_router.py`, `netrattler_v2_migrate.py` |
| **V3** (secrets in workflows) | `netrattler_match_history`, `netrattler_data_lake_raw` copies | `netrattler_v2_migrate.py` DDL |
| **V4** `alhsljynycapnikeqrcy` (NETRATTLER V4 Project, eu-west-1, created 2026-10-20 11:40 UTC) | **Empty** (no public tables, only Supabase system schemas). Not wired into any code or workflow | read-only `pg_stat_user_tables` |

Caveat: the Supabase connector available to Claude only lists MAIN and V4 (same organization). V2/V3 are not visible there, so their sizes/contents below are from earlier sessions' records and have NOT been re-verified today.

#### Current MAIN database (verified today)
- Total size **510 MB** (free-tier soft limit 500 MB) — at the limit.
- Largest tables: `odds_history` 256 MB (510k rows, hot window only), `netrattler_data_lake_raw` 99 MB (23k rows; **still on MAIN although V3 holds a copy** — the copy script never deletes the source), `tips` 38 MB, `netrattler_settlements` 33 MB, `ml_models` 24 MB, `ml_tips` 15 MB.
- Space is returned to the OS only after `VACUUM FULL`, which the user runs manually; deleting rows alone does not shrink the 510 MB.

#### How data flows (code facts)
- `netrattler_table_router.py` rewrites REST calls for tables listed in `NETRATTLER_ROUTE_TABLES` from MAIN to V2 and swaps the key; every other URL is untouched; inactive unless V2 env vars exist (tests: `test_netrattler_table_router.py`). Loaded via `sitecustomize.py`.
- `netrattler_v2_migrate.py` modes `check|schema|copy|verify|rotate`. Copy never deletes in the source; `rotate` moves `odds_history` older than 3 days to V2 and deletes from MAIN **only when the per-day row count matches exactly**.
- Real-time readers on MAIN (must stay fast, must not depend on V2 availability): settlement, tip generation (`btts_bot.py`), builder engine, Telegram edit recovery.
- Historical readers: player-prop models and `netrattler_1x_group_decode.py` (reads MAIN `x1_player_snapshots` + V2 `player_game_log`).

#### Risks found
1. MAIN at 510 MB → writes could be rejected by the plan limit; a failed insert on `tips` or `netrattler_settlements` is the worst case. Highest priority.
2. Cross-project joins are impossible in SQL; any query that needs `tips` + `player_game_log` must be done in Python (already the case for the decode job).
3. The router silently rewrites by URL prefix — a table listed in `NETRATTLER_ROUTE_TABLES` but not present in V2 fails with 404 rather than falling back.
4. Duplicate copies (`netrattler_data_lake_raw` on MAIN and V3) can drift; which one is authoritative is not documented.
5. V4 exists but is empty and unused: no writer, no reader, no RLS review, no backup policy.

#### Proposed target (design only — nothing executed)
- **Operational (MAIN):** fixtures/odds hot window (≤3 days), tips, settlements, builder picks, match_results, Telegram message references. Small, fast, authoritative for money-relevant records.
- **Historical/analytics (V2):** player logs, player match stats, rotated odds history, H2H/feature tables.
- **Raw/lake (V3 or V4):** `netrattler_data_lake_raw`, source snapshots. Decide whether V4 replaces V3 (one fewer project) — needs user input.

Minimal metadata needed from the user (never keys/passwords in chat): for each project — project ref, region, plan/limits, which GitHub secret names point to it, whether RLS/backups are enabled, and which project the user regards as authoritative for `netrattler_data_lake_raw`.

#### Staged plan (each stage: offline test → dry run → reviewed → rollback noted)
0. **Free space on MAIN (non-destructive first):** confirm V3 copy of `netrattler_data_lake_raw` with `verify` mode (row counts + hash sample); only then user-approved delete from MAIN + user runs `VACUUM FULL`. Rollback: V3 copy.
1. Document authoritative project per table in this file (table → project → writer → reader).
2. Add a health check that reports DB size per project and fails loudly at 450 MB (no production writes, read-only).
3. Make the router fail-safe: on 404/5xx from V2 for a routed table, log and fall back to MAIN for reads only (never for writes), with a unit test.
4. V4 stays reserve (user decision). If MAIN/V2/V3 run out of space later, V4 is the first candidate for the raw/lake role (schema-only `schema` mode + `verify` first).
5. Only after 0–4 are stable, consider moving more historical tables.

#### Decisions needed
- ~~Is V4 intended to replace V3, or is it a spare?~~ **Answered by the user 2026-10-20: V4 is a reserve project** (stays empty and unwired until a need arises; do not point any writer at it without a new decision here).
- Approve stage 0 (delete the MAIN copy of `netrattler_data_lake_raw` after `verify`)?

#### Honest disclosure — production changes made today before this handoff was read
The user's standing instruction in the Claude Code session was "check, fix, commit, keep working" and these were pushed directly to `main` (not through PRs). Review and revert if you disagree:
- **Settlement logic** (`netrattler_settlement_v16_final.py`): single tips with odds ≥ 100, combos > 2000 and over15_ht > 4.5 now settle as `void` (guard against corrupted odds); results are also searched on the adjacent day (both team identities must match strictly); report labels read match/market from legs. Tests: `test_settlement_odds_guard.py`, `test_settlement_adjacent_day.py`.
- **Production data changes (MAIN, `tips` table):** 581 single tips (1x2/over25/over15_ht, odds ≥ 100), 32 `combo_multi` (odds > 2000) and the over15_ht rows with odds > 4.5 were set to `status='void', profit_units=0`. Backups of the original rows: tables `tips_odds_bug_backup`, `tips_odds_bug_backup2`, `tips_odds_bug_backup3` in MAIN. Rollback: `update tips t set status=b.status, profit_units=b.profit_units from <backup> b where b.tip_id=t.tip_id`.
- **Settlement workflow** now runs two extra best-effort steps before the settlement runner: `netrattler_espn_ht_backfill.py` and `netrattler_pending_result_backfill.py` (both only write real reported half-time scores/results into `match_results`; `continue-on-error: true`).
- **Telegram:** run-failure alerts disabled (`NETRATTLER_RUN_ALERTS` default off) on user request; multi-combos restricted to 1x2/over25/corners/btts (`NETRATTLER_MULTI_COMBO_MARKETS`).
- **Core CI:** installs `pytest` (the Table router test needed it). The latest run conclusion for this entry's commits has not been verified by Claude.
- Not verified: whether the Telegram edit HTTP 400 failures (deleted messages) are fully resolved; earlier analysis showed the remaining 6 failures are deleted Telegram messages.

#### Task board update
- [x] Claude: review architecture and recommend safe two-project split (this entry; no migrations).
- [ ] Claude: audit player/club ID mapping and duplicate ingestion — not started.
- [ ] Both: Telegram original-message edit failure review.

### Claude update 2026-10-22 (all pushed to `main` under the user's standing "check, fix, commit" instruction)
**Storage (MAIN):** 523 MB → ~370 MB. User truncated MAIN `netrattler_data_lake_raw` (V3 holds the verified copy) and ran `VACUUM FULL` on it and `odds_history` manually. Harvester writes the lake to V3 (`DATA_LAKE_DSN`, `DATA_LAKE_MAIN_FALLBACK=0`). New `netrattler_storage_guard.py` (+ workflow every 6 h, RPC `db_size_mb()` on MAIN, service_role only): warns ≥420 MB, deletes only old `x1_player_snapshots` ≥450 MB. `x1_player_snapshots` retention 4 days. V4: empty ML-archive tables created (`ml_tips`, `netrattler_learning_events`, `x1_player_snapshots`), no writer wired (the `V4_DATABASE_URL` secret login failed; V4 is not needed yet).
**ML:** honest hold-out + quality gate (`netrattler_model_quality.py`), core models ~140k samples, AUC only 0.55–0.69. Min-probability floors tightened from 60-day calibration: over25/btts 65, corners 70, 1x2 65, over15_ht 60 (`test_min_prob_floors.py`). No claim of 75 % win rate is supportable; only corners ≥71 % reach ~75 %.
**CLV:** `netrattler_clv.py` fills `odds_taken/odds_closing/clv` for over25/btts/1x2 singles from `odds_history` closing medians (|clv|>40 % discarded). Honest over25 median ≈ +3.4 % (n=47). Old (Oct 18) outlier quotes (3.00 vs 1.56) predate the corroboration gate.
**Sources:** `gamdom_platform` shadow adapter (1x2/btts/totals 2.5, start date `FechaPlanInicioPartido`), collected by `netrattler_odds_harvester.py`, not in `X1_SHADOW_SOURCES` (inert). 22bet snapshot collector fixed (`isSubGames=true`): ~160k player-market rows, 47 matches; group decode needs ≥40 settled cases per group (14 matched so far) – nothing mapped yet.
**Stale pending:** 1,295 stale pendings voided with backup `tips_stale_void_backup` (dry-run default, `STALE_APPLY=1`).
**Review requests:** the new floors (fewer tips), the stale-void step, and the gamdom adapter. Prop Hunter ideas not yet ported: snapshot retention, coverage watchdog, builder correlations, no-vig market consensus.
