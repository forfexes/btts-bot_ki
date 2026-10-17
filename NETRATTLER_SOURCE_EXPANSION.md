# NETRATTLER / BETCLONE — source expansion candidates

This is an investigation backlog, **not** a list of integrated or verified feeds. Verify provider rights, endpoint availability, rate limits, actual league/market coverage, timestamps and independent bookmaker identity before production use. Never infer an odds feed from an advertised bookmaker count.

| Priority | Candidate | Intended role | Acceptance test |
| --- | --- | --- | --- |
| P0 | FDB4 / footballcsv / football-catalogs | Historical matches and H2H | Verify repository/license, team normalization, dates, deduplication and actual fixture count |
| P0 | FootyStats | H2H, team form, BTTS, half-time, corners | Confirm API entitlement and per-market field coverage with real samples |
| P0 | Existing SofaScore collector / datafc | H2H, player and lineup data | Compare existing implementation, license and freshness before adding duplicate ingestion |
| P0 | Odds-API.io / oddsapiio | Multi-book odds discovery | Confirm authenticated API, quota, exact markets and bookmaker identity; never treat 265+ claim as usable coverage |
| P1 | The Odds API / oddsapiR | Existing API extension | Audit current key rotation, quota, player and half-time market availability before changing collectors |
| P1 | Sportradar / WSF Odds | Player props | Obtain authorized access and validate event/player identity, shots, fouls, tackles, cards, goalscorer |
| P1 | FotMob / FBref / SoccerStats | Match and player enrichment | Check availability and usage terms; no bookmaker-price inference |
| P1 | 7msport / Fox Sports / ESPN | Market/score cross-check | Prove precise market/selection/period and timestamp; do not promote editorial tips as bookmaker odds |
| P2 | oddsharvester / OddsPortal | Historical odds research | Confirm legal access, maintenance, exact bookmaker/source attribution and reproducibility |
| P2 | sportsdata-mcp / Bettor / pyTSPA-toolbox | Tool/model evaluation | Verify repository, actual implemented adapters, licensing, tests, data provenance |
| P2 | FootyMetrics / Action Network / Goal.com | Player prop discovery | Verify real accessible odds and player IDs; distinguish analysis from odds feed |
| P2 | Formatic / VAKYR / DuoDesk / Balltics / eScored | External model benchmarking | Verify public archived picks, timestamps, settlement and no hindsight leakage |

## Production gate

1. Verify a real endpoint and legal/authorized access, not just a product description.
2. Collect bounded samples with fixture ID, home/away, kickoff UTC, bookmaker, market period, line, selection, decimal odds, captured UTC and prematch/live state.
3. Normalize and deduplicate mirrors; reject unknown player/market codes, synthetic events and stale prices.
4. Test complete markets, suspended selections, clock/date boundaries, source failures, rate limits and independent corroboration where required.
5. Shadow-write and compare to existing odds_history; enable tip use only after tests and real GitHub Actions run evidence.

Existing 1xBet/Altenar/Smarkets/Bwin/Pinnacle/Matchbook collectors must be audited before another overlapping integration is added. No candidate in this document is newly enabled for Telegram tips.
