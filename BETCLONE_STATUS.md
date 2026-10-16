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

## Playwright verification (2026-10-16)

Live GitHub browser audit [run 38897332586](https://github.com/forfexes/btts-bot_ki/actions/runs/38897332586):
Chromium launched successfully; **10 operator homepages in 6 families** were
rendered without bypassing access controls. All four browser-audit unit tests
passed. Public sportsbook links were followed on Betinia, Gamdom, Rolletto,
and Wild.io. **Zero additional verified structured odds feeds** emerged.

| BetClone group | Browser-tested sites | Outcome |
| --- | --- | --- |
| Altenar | Betinia | Rendered, sports link; no verified prices |
| BETBY | Tonybet, Gamdom | JSON responses, no verified prices |
| BetConstruct | VBET, Olybet, Fastbet | VBET denied; others rendered without verified odds |
| FIRST | BK8 | Rendered without verified odds |
| InPlayNet | Rolletto | Sports link, no verified first-party prices |
| SoftSwiss | Metaspins, Wild.io | Metaspins denied; Wild.io rendered, no verified odds |

Browsers are **operational**, as independently demonstrated by
[Playwright CI 38895482826](https://github.com/forfexes/btts-bot_ki/actions/runs/38895482826).
The actual tips workflow installs Chromium and sets
`NETRATTLER_PLAYWRIGHT_ENABLED=true`, but caps browser usage to 4 pages / 45s.
A browser-rendered homepage is not a data feed, and browser availability does
not mean every BetClone operator has become an odds provider.

## Confirmed sources, distinct from the BetClone directory audit

On 2026-10-16 UTC the `odds_history` table contained 11,671 `1xbet_platform` price records, 7,566 `kambi`, 5,532 `pinnacle`, 5,149 `matchbook`, and 3,706 `bwin`. These **are records, not distinct bookmakers**, and the latter four are not necessarily listed in the ten BetClone groups. 1xBet market type codes remain shadow-only until accurately mapped.

## Playwright Chromium verification — 2026-10-16 UTC

- Production browser dependency and Chrome Headless Shell installation passed in
  [Playwright Browser CI run 38895482826](https://github.com/forfexes/btts-bot_ki/actions/runs/38895482826).
  Real Chromium launch plus DOM inspection passed. This confirms runtime
  availability, **not** an extra football bookmaker feed.
- The production tip bot [run 38895482998](https://github.com/forfexes/btts-bot_ki/actions/runs/38895482998)
  logged `Playwright: available` and consumed its strict four-page/45-second
  browser budget. Its subsequent analysis had no new validated BetClone family
  integrated via Playwright.
- The browser-specific BetClone probe
  [run 38897332586](https://github.com/forfexes/btts-bot_ki/actions/runs/38897332586)
  visited ten curated operator homepages from six catalogue groups:
  eight rendered without a independently validated sports-odds feed, two
  returned access-denied, **zero** price candidates and **zero** confirmed
  production integrations. Four rendered sites did offer a public sports
  page link, which is **not** evidence of extractable market prices.
- The production Playwright guard now reports only host-level and success/empty
  counts when its browser budget is exhausted. URL parameters, HTML, cookies,
  and browser response bodies are not stored in these diagnostics.
- Expanding browser checks cannot justify relabelling a general HTML page as
  usable pre-match football odds; explicit event, market, selection, odds,
  timestamp and source mappings still need independent validation.

## Remaining work / acceptance criteria

1. For every other platform family, find a legitimately available **structured** public feed or confirm that only authenticated/partner feeds are available. Do not declare an HTML page an integrated feed.
2. Validate event ID, teams, start time, prematch status, full market name, selection, decimal odds, and source timestamp with multiple live samples.
3. Map independent football market families (1X2, BTTS, O/U, halftime, corners/cards, scorer/player props). Unknown group and numeric codes stay shadow and cannot produce Telegram tips.
4. Test multiple bookmaker domains *only when those are actually distinct sources*, deduplicate mirrors, capture source-level diagnostics, and test Supabase insert/end-to-end candidate generation.
5. Report per-platform usable market coverage and API restrictions. Complete means verified prices *and* safe, tested NETRATTLER integration, not an HTTP 200 or a green audit.

**Do not mark BetClone fully finished without these criteria.**

## Extended browser audit — 2026-10-16 UTC

- [Follow-up run 38907432247](https://github.com/forfexes/btts-bot_ki/actions/runs/38907432247):
  14 curated public homepages covering **7** catalogue platform families,
  with 5/5 offline checks passing.
- 12 pages rendered, while VBET and Spinlynx returned access denied.
  Newly visited Vegas.hu, Cosmobet and Vave rendered; none yielded a
  verified structured odds price. **Zero new production feeds**.
- Rolletto and Cosmobet each returned more than 100 JSON network responses.
  Some responses were hosted on other origins. Their hostnames, when
  collected in subsequent runs, remain **investigative metadata**, not
  authorization to access undocumented/partner APIs and not tip-ready prices.
- Redirecting to an operator's publicly rendered canonical hostname is now
  considered when examining same-origin responses; it does not turn a
  third-party response or an HTML document into a validated sportsbook feed.

## Strictly conditional 1xBet quote corroboration — 2026-10-16 UTC

The current NETRATTLER code optionally admits **only** the 1xBet-platform
`1x2` and `totals_2_5` rows when every outcome in the same market is
corroborated by a *different validated bookmaker feed* for the **exact same
home team, away team, fixture date, market and selection**. Each 1xBet
quote must independently be within the 0.85–1.18 ratio window, and the
`imported_at` timestamp must be fresh. A 1xBet quote with no reference or
only a partially matched market is still shadow and cannot enter live tips.
All other numeric-code 1xBet markets remain blocked.

- Git commit: `6869e0e654a6b2824f2c671c8bb04566a8098271`
- An independent read-only SQL cross-check of the 2026-10-16 Supabase snapshot
  identified 38 fully comparable 1X2 match-markets and 33 fully comparable
  Over/Under 2.5 match-markets using these numerical criteria.
- These counts are comparable stored market groups, **not 71 bets sent, and not
  a claim that all cloned brands are integrated**.
- Altenar public browser diagnostics observed 46 price-and-label-key
  structures with event/market context, but no separately validated,
  selection-mapped quote. **Altenar is not promoted to a live source.**

## BTTS conditional corroboration — 2026-10-16 UTC

Following same-fixture read-only agreement against labelled independent
bookmakers, the `btts` market is included in the strict conditional 1xBet
gate. Both YES and NO selections must exist, agree with independently mapped
prices and be fresh. The user-visible `btts_yes` price is eligible only when
all those conditions hold. Incomplete matches, BTTS half-time, cards, corners,
player markets and unknown numeric codes remain excluded. A complete pair is
NOT proof that every 1xBet brand is live or that a Telegram tip was sent.

## Altenar public hosted quote candidates — 2026-10-16 UTC

In the successful, headless [BetClone Playwright Audit #38920290197](https://github.com/forfexes/btts-bot_ki/actions/runs/38920290197),
Vegas.hu triggered an observed public `biahosted.com` JSON response.
The bounded depth-aware browser inspector identified **69 price-like records**
with public market/event context and plausible decimal `name`/`price`
fields. All **38 parser/browser regression tests** passed. The page is
marked `candidate_prices_require_independent_market_validation`.

**This is not a validated Altenar bookmaker feed.** These 69 are
*observations from several public JSON responses*, not 69 confirmed distinct
football fixtures, and do not yet establish home/away, kickoff time,
football market-period, selection mapping, price timestamp or bookmaker
identity. They must remain excluded from the production quote allowlist
until those fields are independently mapped and tested.

The updated inspector recognises both `event(s)` and `marketGroup(s)`
wrappers, explores bounded deep JSON, and records candidates without
capturing full request URLs, cookies, credentials or response payloads.
