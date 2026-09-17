NETRATTLER FINAL FIX44 / Settlement V25 MULTISOURCE

Replace/add exactly these runtime files:
- netrattler_settlement_v16_final.py (replace)
- netrattler_result_enrichment.py (new)
- .github/workflows/netrattler_settlement_v16_final.yml (replace)

Optional read-only verification:
- NETRATTLER_FIX44_VERIFY.sql

New targeted settlement sources:
- FotMob daily matches + matchDetails: FT score, corners, shots, SOT, xG, player stats when exposed
- SofaScore scheduled events + event statistics + lineups: FT/HT score, corners, shots, SOT, xG, player stats

Existing result sources remain active (Supabase match_results/history, TheSportsDB, AllSports, Football-Data.org, OpenLigaDB, SourceHub; ESPN guarded by circuit breaker).

Important behavior:
- Exact date + home + away identity required. No loose fuzzy result matching.
- Detail calls are only made for requested fixtures and capped per run.
- Missing data remains PENDING, never VOID.
- combo_multi is separated from combo and routes to TELEGRAM_GROUP_COMBOS.
- Over 1.5 HT falls back to TELEGRAM_GROUP_BTTS_HT when no dedicated group is configured.
