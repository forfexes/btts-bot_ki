# NETRATTLER specialized football sources — 2026-11-18

## Status and contractual limits

The data access status is checked against official provider documentation.

| Provider | Data relevant to NETRATTLER | Integration status |
| --- | --- | --- |
| FootyStats | Historical leagues/matches, shots, SOT, corners, cards, BTTS, O/U, backtesting | Official API adapter built; example key (season 1625) tested; **not a live-data API**; production needs a licensed key and selected season |
| SofaScore | Live stats and momentum research | **No public data API** under its stated data agreements; existing unofficial scraper is **not** used by this adapter |
| Overlyzer | Live pressure and offensive trend research | No verified public programmatic feed; subscription UI is not an API license |
| StatisticSports | Live in-play and historical data | Commercial API offered via inquiry; no authorized credentials configured here |
| BeSoccer | Lower-league schedules, live and team data | Official API exists, but official pricing states no free accounts |

## Implementation

- `netrattler_specialized_sources.py`: documented FootyStats API fetch for completed historical matches, safe shape normalization, source audit.
- `netrattler_specialized_merge_backtest.py`: exact provider-ID merge for completed fixtures; quarantine conflicts and contradictory duplicate records, retain missing values as missing; never join by similar club names. Live-only chronological replay rejects future information and requires real original model decisions.
- `test_netrattler_specialized_merge_backtest.py`: offline checks for mismatched home/away IDs, kickoff times, double-counted games, contradictory statistics and statistical-leakage safeguards.
- `netrattler_source_hub.py`: disabled registrations for these 5 research/vendor entries; not routed to production.
- `test_netrattler_specialized_sources.py`: offline tests for IDs, bad data, missing stats, restricted demo key, no secrets in exceptions, no live/odds contamination.
- `.github/workflows/netrattler_specialized_sources.yml`: manual and push-triggered read-only official-sample probe; JSON report stored as 3-day Actions artifact.
- No new Supabase tables/writes, Telegram messages, predictions, synthetic odds or provider account charges.

## Run it

```bash
python -m unittest -v test_netrattler_specialized_sources.py test_netrattler_open_source_registry.py
python netrattler_specialized_sources.py --demo --out specialized-source-report.json
```

The demo is **Premier League 2018–19 only** (FootyStats season 1625), so passing this does not establish coverage for other leagues or live performance.

To audit a licensed season locally, set `FOOTYSTATS_API_KEY` and `FOOTYSTATS_SEASON_ID` as environment variables, then run `python netrattler_specialized_sources.py`. Keep credentials out of GitHub source. Production routing stays disabled until the licensed scope, lineup/team cross-provider identities and chronology-safe historical backtest are validated.

## Validation result, 18 November 2026

GitHub Actions specialist audit **33/33 tests passed** on the final source-merge build. Official FootyStats public 2018/19 sample: **200 unique historical matches**, no duplicates, no conflicting groups; full shots, shots-on-target and corners coverage 200/200.

**Important:** There are **zero verified in-play snapshots and no paired baseline-vs-extra-source predictions** in this audit. The replay result is `not_backtestable_no_live_snapshots`, so **no Goal Hunter uplift or improved win rate is established**. The historical figures must not flow into live tips. Repeated matches are combined only when a verified provider-ID/team-ID/kickoff crosswalk exists; cross-source matches verified by this sample: **0**.

## Gates for adding a provider to production

1. Verify the provider's right to supply machine-readable data, coverage of the actual competition and freshness.
2. Resolve stable match/team ID crosswalks with no fuzzy name-only settlement.
3. Validate timestamps and distinguish historical final stats from in-play cumulative stats.
4. Replay chronological out-of-sample backtests (L10/L15) against the existing model with a verified coverage advantage.
5. Enable provider-specific production routing only after all checks pass. Original Telegram design, REAL_ODDS_ONLY and live signal rules remain unchanged.

Official references: https://footystats.org/api/documentations/faq ; https://footystats.org/api/documentations/match-schedule-and-stats ; https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability ; https://www.overlyzer.com/en/live ; https://statisticsports.com/en/data-api ; https://api.besoccer.com/en/budgets
