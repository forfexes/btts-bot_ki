# NETRATTLER — Current Production Architecture

Stand: September 2026

## Production entry point

The scheduled GitHub Actions tips workflow is `.github/workflows/btts_tips.yml`.
It starts `netrattler_builder_guard.py`, which applies the player-prop safety layer and then runs `btts_bot.main()`.

Important production rules:
- REAL_ODDS_ONLY: no synthetic bookmaker quotes.
- V37 runtime-policy/data-fusion remains shadow-only while the safe rollback path is production master.
- Player-prop models are loaded from Supabase and only used when a compatible model/market is available.
- Same-game specialty markets require an observed bookmaker quote.
- Telegram failures must not mark a pick as sent or persist a builder as delivered.

## Core runtime files

- `btts_bot.py` — main football tips pipeline.
- `netrattler_builder_guard.py` — production guard for player-prop semantics, exact model lines and builder edge sanity.
- `netrattler_builder_engine.py` — player-prop builder generation.
- `netrattler_ml_player.py` — trained player-prop model loader/predictor.
- `netrattler_prop_sources.py` — Kambi/1xbet and other player-prop source adapters.
- `netrattler_runtime_policy.py` — runtime policy, currently not allowed to override the safe production candidate path.
- `netrattler_coverage_watchdog_v37.py` — coverage diagnostics.
- `netrattler_settlement_v16_final.py` — settlement and result updates.

Version suffixes in older module filenames are historical names. Do not rename them only for cosmetics because workflows/imports still reference those paths.

## Data and source flow

- Match/results: Supabase match results/history, OpenFootball, Football-Data.co.uk, martj42 and other fallbacks.
- Player stats: Supabase `player_match_stats`, StatsBomb/FotMob/SofaScore/FBref/soccerdata where available.
- Match odds: Pinnacle first, then configured real-odds fallbacks.
- Player props: Kambi is the strongest current fallback when Pinnacle player props are unavailable; 1xbet/other adapters are best effort.
- Big Balls remains integrated as a source.
- ML training writes match and player-prop models to Supabase `ml_models`.

## GitHub Actions

Active workflows live in `.github/workflows/`:
- `btts_tips.yml` — scheduled and manual tips runs.
- `netrattler_settlement_v16_final.yml` — settlement.
- `scrape_player_stats.yml` — player stats/results collection.
- `train_model.yml` — ML training.
- `netrattler_odds_harvester.yml` — odds snapshots/history.
- `netrattler_all_source_harvester.yml` — broader source collection.
- `netrattler_github_watch.yml` — source/repository watch.
- `netrattler_source_learning_v35.yml` — source learning.
- `netrattler_ai_master_v35.yml` — manual consolidated maintenance/orchestration workflow.

GitHub Actions is the production CI/runtime platform. Legacy CircleCI configuration is not part of the production path.

## Regression checks

Keep these tests when changing the runtime:
- `test_netrattler_core.py`
- `test_netrattler_regression_step1.py`
- `test_netrattler_stability_step2.py`
- `test_netrattler_stability_step3.py`
- `test_netrattler_settlement_v21.py`

For the tips pipeline, prefer the smallest possible change and do not start extra Actions runs only for experimentation.
