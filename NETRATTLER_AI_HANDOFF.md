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
