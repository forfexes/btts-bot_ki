# NETRATTLER MASTERPLAN — CURRENT

## Production path

`GitHub Actions -> .github/workflows/btts_tips.yml -> netrattler_builder_guard.py -> btts_bot.main()`

The guard is part of the current production path. It prevents malformed player-prop lines, unsupported specialty markets and incompatible player models from entering the Builder.

## Core files

- `btts_bot.py` — main tips pipeline and market generation.
- `netrattler_builder_guard.py` — player-prop/Builder safety entry point.
- `netrattler_builder_engine.py` — Builder selection, formatting, persistence.
- `netrattler_ml_player.py` — player-prop ML loading/prediction.
- `netrattler_prop_sources.py` — real player-prop sources/fallbacks.
- `netrattler_runtime_policy.py` — policy layer; shadow-only for production filtering while safe rollback is active.
- `netrattler_coverage_watchdog_v37.py` — market coverage diagnostics.
- `netrattler_settlement_v16_final.py` — result settlement and same-post updates.
- `scrape_player_stats.py` — player stats/results collection.
- `train_model.py` — match + player-prop model training.
- `netrattler_odds_harvester.py` — odds history/snapshots.
- `netrattler_all_source_harvester.py` — broad source harvesting.

## Production invariants

1. REAL_ODDS_ONLY — never invent/synthesize a bookmaker quote.
2. A valid Builder leg needs a real observed quote.
3. Do not use a single-player model for `Either Player`, header/other scorer specialties or unsupported first-half player props.
4. Modelled Builder edge is model probability minus bookmaker implied probability in percentage points.
5. Failed Telegram delivery must not be marked as sent or persisted as delivered.
6. Do not let V37 runtime policy/max-edge wipe otherwise valid market-specific candidates.
7. Corner picks/legs must retain the exact selection and line.
8. Same-game BTTS+O2.5 requires an observed combined quote; do not multiply separate same-game prices.

## Workflows

- `btts_tips.yml` — production tips schedule + manual tips run.
- `netrattler_settlement_v16_final.yml` — settlement.
- `scrape_player_stats.yml` — stats/results.
- `train_model.yml` — model training.
- `netrattler_odds_harvester.yml` — odds harvester.
- `netrattler_all_source_harvester.yml` — all-source harvester.
- `netrattler_github_watch.yml` — repository/source watch.
- `netrattler_source_learning_v35.yml` — source learning.
- `netrattler_ai_master_v35.yml` — manual consolidated maintenance workflow.

Historical version suffixes in filenames can remain if imports/workflows use them. Do not rename files just to make the number look current.

## Change policy

- Prefer small, local fixes over large patches.
- Run deterministic/local regression checks before production changes where possible.
- Avoid extra GitHub Actions runs unless the normal scheduled run can validate the change.
- Keep working fallbacks and Big Balls integration unless there is evidence they are harmful.
