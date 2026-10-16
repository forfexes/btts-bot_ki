# BetClone coverage — checked 2026-10-16 (UTC)

**Status: catalogue audit complete; production integration of remaining BetClone platform families incomplete.**

Source: GitHub Actions [Platform Probe run 38886119671](https://github.com/forfexes/btts-bot_ki/actions/runs/38886119671), tested from a GitHub runner with single unauthenticated HTTP requests and no access-control bypasses.

## Catalogue coverage

| BetClone group | Listed primary brands | Productive BetClone-derived feed |
| --- | ---: | --- |
| 1xBet | 28 | Existing LineFeed produces 1xbet_platform rows; numeric market codes not cleared for tips |
| Altenar | 107 | Not verified |
| BETBY | 98 | Not verified |
| BetConstruct | 13 | Not verified |
| Delasport | 36 | Not verified |
| Digitain | 35 | Not verified |
| FIRST | 12 | Not verified |
| iGate | 32 | Not verified |
| InPlayNet | 10 | Not verified |
| SoftSwiss | 18 | Not verified |
| **Total** | **389** | **1 family partially integrated** |

The catalogue also exposes 151 historical appendix names, separately marked as unverified; they are NOT counted among the 389 primary rows.

- 10/10 catalogue pages read successfully.
- 53 curated homepage URLs tested; **46** directly matched the listed 389 entries, leaving 343 without a curated site.
- 338/343 unverified candidate domains were attempted. The other five lacked a safe one-domain guess.
- Curated homepages: 21 blocked, 12 HTTP errors, 18 HTML without verified odds, 2 network errors.
- Unverified domain guesses: 197 blocked, 21 HTTP errors, 90 HTML without verified odds, 30 network errors.
- **Zero confirmed usable odds feeds from any of the 391 homepage/candidate-domain attempts**. This does not mean the operator has no odds. Frontends can use separate APIs.
- Candidates for human/technical follow-up, **not verified feeds**: BETBY/Inkybet, FIRST/Hugobets, FIRST/Locowin, FIRST/Simsinos, InPlayNet/CasinOK, SoftSwiss/Dailyspins.
- Explicit authenticated/business-partner APIs require authorized credentials; no proxy/captcha/geo-block evasion permitted.

## Confirmed sources, distinct from the BetClone directory audit

On 2026-10-16 UTC the `odds_history` table contained 11,671 `1xbet_platform` price records, 7,566 `kambi`, 5,532 `pinnacle`, 5,149 `matchbook`, and 3,706 `bwin`. These **are records, not distinct bookmakers**, and the latter four are not necessarily listed in the ten BetClone groups. 1xBet market type codes remain shadow-only until accurately mapped.

## Remaining work / acceptance criteria

1. For every other platform family, find a legitimately available **structured** public feed or confirm that only authenticated/partner feeds are available. Do not declare an HTML page an integrated feed.
2. Validate event ID, teams, start time, prematch status, full market name, selection, decimal odds, and source timestamp with multiple live samples.
3. Map independent football market families (1X2, BTTS, O/U, halftime, corners/cards, scorer/player props). Unknown group and numeric codes stay shadow and cannot produce Telegram tips.
4. Test multiple bookmaker domains *only when those are actually distinct sources*, deduplicate mirrors, capture source-level diagnostics, and test Supabase insert/end-to-end candidate generation.
5. Report per-platform usable market coverage and API restrictions. Complete means verified prices *and* safe, tested NETRATTLER integration, not an HTTP 200 or a green audit.

**Do not mark BetClone fully finished without these criteria.**
