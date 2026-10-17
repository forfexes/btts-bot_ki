# BetClone coverage — checked 2026-10-16 (UTC)

**Status: catalogue audit complete; production integration of remaining BetClone platform families incomplete.**

Source: GitHub Actions [Platform Probe run 38886119671](https://github.com/forfexes/btts-bot_ki/actions/runs/38886119671), tested from a GitHub runner with single unauthenticated HTTP requests and no access-control bypasses.

## Catalogue coverage

| BetClone group | Listed primary brands | Productive BetClone-derived feed |
| --- | ---: | --- |
| 1xBet | 28 | Existing LineFeed produces 1xbet_platform rows; confirmed used in live production tips |
| Altenar | 107 | Adapter shipped (1x2 only, `vegas.hu` brand); 21 real rows in `odds_history`, corroboration-ready, not yet fired in a live tip |
| BETBY | 98 | Investigated — no reachable public odds API found (homepage crawl) |
| BetConstruct | 13 | Investigated — no reachable public odds API found (homepage crawl) |
| Delasport | 36 | Investigated — inconclusive (browser error), not promoted |
| Digitain | 35 | Investigated — inconclusive (HTTP error), not promoted |
| FIRST | 12 | Investigated — no reachable public odds API found (homepage crawl) |
| iGate | 32 | Investigated — access denied |
| InPlayNet | 10 | Investigated — no event/odds endpoint found; catalogue/config calls only |
| SoftSwiss | 18 | Investigated — no reachable public odds API found (homepage crawl) |
| **Total** | **389** | **2 families productive (1xBet, Altenar); 7 investigated with no productive feed found** |

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

## Altenar field schema and keyless adapter — 2026-10-16 UTC

A follow-up, narrower schema sniffer (`netrattler_altenar_schema_probe.py`)
captured bounded, truncated real sample objects (not just shape counts)
from the same public Vegas.hu/biahosted.com response. This confirmed a
standard flat Altenar widget payload: `sports[]`/`categories[]`/`champs[]`/
`events[]`/`competitors[]`/`markets[]`/`odds[]` arrays cross-referenced by
id. Concretely:

- `events[]`: `id`, `sportId`, `champId`, `status`, `startDate` (real ISO
  kickoff), `marketIds[]`, `competitorIds[]` (home, away in order), `name`
  (localized `"Home vs. Away"` string, used only as a fallback).
- `markets[]`: `id`, `headerName` (`"1X2"` observed; no Over/Under or BTTS
  header seen yet), `oddIds[]`.
- `odds[]`: `id`, `competitorId`, `price`, `typeId` (1/2/3 = home/draw/away
  **selection** role — a different namespace from the market's own
  `typeId`), `oddStatus` (0 = active).
- `sports[].iconName == "soccer"` is the locale-proof way to find the
  football sport id (team/league/selection text is in the operator's own
  language, e.g. Hungarian "Döntetlen" for Draw on vegas.hu).

A second probe (`netrattler_altenar_keyless_probe.py`) confirmed the
public `GET hu-sb2frontend-altenar2.biahosted.com/api/widget/GetTopEvents`
endpoint is reachable with a **plain keyless HTTP GET** (HTTP 200, no
login, no bypass) using the same public query parameters the page's own
browser sends (`integration=vegas.hu` is the operator's public widget
brand id, not a credential) — no Playwright session needed per scrape.

**Implemented, conservative by construction:**

- `netrattler_keyless_odds._altenar_rows()` / `collect_altenar_platform()`:
  parses **only** a complete 1X2 market (all three selections present and
  active); there is no Over/Under, BTTS, half-time, corners or player-prop
  mapping yet because no such market header has been observed in this
  response. Non-football sports, non-scheduled event status and suspended
  (`oddStatus != 0`) prices are excluded.
- Registered as source `altenar_platform` in `netrattler_odds_harvester.py`
  (`COLLECTORS` / `collect_live_all`), so it is harvested into
  `odds_history` on the normal schedule.
- Gated through the **exact same** never-auto-promote shadow treatment as
  `1xbet_platform` in `netrattler_odds_cache_guard.py`
  (`X1_SHADOW_SOURCES`): an Altenar 1X2 quote is only usable as a real-odds
  fallback when all three selections independently corroborate an already
  validated `LIVE_HISTORY_SOURCES` price for the exact same fixture/date/
  selection within the 0.85–1.18 ratio window. 11 regression tests cover
  the parser (`test_netrattler_keyless_odds.py`) plus the generalized gate
  (`test_netrattler_odds_cache_guard.py`).

**Not yet done:** end-to-end confirmation that a corroborated Altenar
quote has actually reached a production fallback fill (the same
diagnostic used to confirm 1xBet in production,
`netrattler_card_diag` probe `cache_guard_1xbet_used`, now also fires for
`altenar_platform` — but no Altenar row has corroborated yet as of this
write-up, since it depends on both sources covering the same live
fixture). Only one Altenar brand (`vegas.hu`) is wired; other Altenar
operators were not probed for their own `integration` id and may use a
different regional host. No Over/Under, BTTS, corners, cards or player
markets are mapped for Altenar.

## InPlayNet — 2026-10-16 UTC

A matching bounded schema sniffer
(`netrattler_inplaynet_schema_probe.py`) visited the two curated public
homepages (Rolletto, company id 50; Cosmobet, company id 217) and
inspected every allowlisted `sportservice.inplaynet.tech` JSON response
(14 and 21 respectively). **None matched an event/market/price shape.**
All observed endpoints are catalogue/config calls: `getmarketcategories`,
`GetItemTranslationsByCompany`, `GetItemVisibilityInfoByCompany`,
`getdisablegamesbycompany`, `getdisableheaderclassifiers`,
`getprematchheadermarkets`, `getspecialoddsregions`, `gethiddenmarket`,
`getordinalnumbers`, `GetItemSortInfoByCompany`. These configure which
markets/sports a given company id shows, not the odds themselves.

**Conclusion: the public homepage load does not expose a fixtures/odds
endpoint for InPlayNet.** This is a technical observation, not a bypass
attempt and not proof odds are categorically unreachable (a specific
match page, reached only after clicking into a live event, might trigger
a further endpoint this bounded homepage+one-sports-link crawl never
reaches). **InPlayNet is not promoted to any adapter.** Revisiting this
would require navigating into an actual listed match (not just the sports
landing page), still without bypassing any access control.

## Altenar production corroboration — verified 2026-10-16 UTC (follow-up)

Cross-checked all 6 Altenar-covered `2026-10-16` fixtures
(Burnley–Wolves, Eintracht Frankfurt–1.FC Köln, Holstein Kiel–Hertha
Berlin, Le Mans–Toulouse, Frosinone–Sassuolo, Deportivo A Coruña–Levante;
MTK Budapest–Vasas is uncovered by any `LIVE_HISTORY_SOURCES`) against
independently-stored `pinnacle`/`kambi`/`bwin` 1x2 prices for the same
date. **All 6 have matching independent references, and every selection
is well inside the 0.85–1.18 corroboration ratio** (e.g. Burnley home:
altenar 3.11 vs kambi 3.08 / pinnacle 3.15 / bwin 2.93). The adapter and
corroboration gate are confirmed data-correct and would fire if used.

However, `netrattler_card_diag` shows **zero** `cache_guard_1xbet_used`
hits for `altenar_platform` across every production run in the last 3+
hours — every hit so far is the same single fixture
("Atletico de Rafaela vs Quilmes", via `1xbet_platform`). The
`builder_pool` diagnostic explains why: each run narrows a pool of
~585–588 candidate matches down to only **11** that clear the tip-quality
gates (probability ≥67%, odds 1.70–3.00, confidence ≥3) *before* the
odds-fallback/corroboration step is ever consulted for a given match.
None of the 6 Altenar-covered fixtures has yet landed in that small
11-match shortlist in any observed run. **This is normal selection
variance from the statistical model, not a defect in the Altenar
adapter, the corroboration gate, or the quality filters** — the filters
were correctly left untouched. Altenar remains ready to serve as a real
fallback the moment one of its covered fixtures clears the quality gate
on its own merits.

## Final status report (handoff step 10) — 2026-10-16 UTC

**Checked platform families:** 1xBet (pre-existing), Altenar (this
session, full investigation), InPlayNet (this session, full
investigation), plus a 389-entry catalogue-level reachability sweep
covering BETBY/BetConstruct/Delasport/Digitain/FIRST/iGate/SoftSwiss
(prior session) that found zero confirmed odds feeds from homepage/
domain probing alone.

**Productive sources (real odds confirmed flowing into `odds_history`
and usable by the shadow-corroboration gate):**
- `1xbet_platform` — confirmed used in live production tips (direct
  `cache_guard_1xbet_used` hits, e.g. "Atletico de Rafaela vs Quilmes").
- `altenar_platform` — adapter built, tested, shipped, producing real
  1x2 odds (21 rows / 7 matches at last harvest) that are data-correct
  and corroboration-ready, but **not yet observed firing in a live tip**
  (see above — a candidate-selection timing matter, not a bug).

**Markets integrated:** 1x2 (full-time result) only, for both sources.
No Over/Under, BTTS, half-time, corners, cards, or player markets are
mapped for either platform.

**Usable quotes as of this write-up:** Altenar — 7 matches × 3 selections
= 21 rows for `2026-10-16` (6 with independent corroboration available).
1xBet — ongoing, pre-existing volume (unchanged this session).

**Actual Telegram/production usage:** 1xBet — yes, confirmed. Altenar —
not yet; mechanically ready, awaiting a covered fixture to clear the
unmodified quality filters.

**Remaining technical blockers:**
- InPlayNet (Rolletto/Cosmobet): no event/odds endpoint found on the
  public homepage/sports-landing crawl; not promoted to an adapter;
  revisiting would require navigating into a real listed match page.
- BETBY, BetConstruct, Delasport, Digitain, FIRST, iGate, SoftSwiss: not
  yet individually investigated beyond the original catalogue-level
  homepage sweep (prior session) — next step per the handoff's own work
  order (point 7), not started this session.
- Only one Altenar operator brand (`vegas.hu`) is wired; other Altenar
  skins were not probed for their own `integration` id/host.
- GitHub Actions log retrieval remains blocked in this environment for
  all workflows (proxy denies `results-receiver.actions.githubusercontent.com`);
  all production verification in this session was done via bounded
  `netrattler_card_diag` writes and direct Supabase queries instead.

## Remaining BetClone families (BETBY, BetConstruct, Delasport, Digitain, FIRST, iGate, SoftSwiss) — 2026-10-16 UTC

Per the work order's point 7, all seven remaining families were probed with
the same rendered-browser methodology that found Altenar's and InPlayNet's
real platform hosts (`netrattler_betclone_browser_probe.py`, now 16 curated
public operator homepages, incl. two first-time additions: Delasport via
`grandwin.bet`, Digitain via `slottica.com`). Run:
[38935999444](https://github.com/forfexes/btts-bot_ki/actions/runs/38935999444),
results read back via `netrattler_card_diag` (probe `betclone_browser_probe`,
since GitHub Actions log retrieval is blocked in this environment).

**Result: no shared, odds-shaped hosted JSON host was observed for any of
the 7 families** (14 clean results + 2 inconclusive):

| Family | Brands checked | Finding |
| --- | --- | --- |
| BETBY | tonybet, gamdom, vave | Only `sentry.softlabs.com` (error tracking) and ad/CDN hosts; no sportsbook API host |
| BetConstruct | vbet (blocked), olybet, fastbet | Only cookie-consent and ad-delivery (`objectic.io`) hosts; vbet denied access outright |
| FIRST | bk8 | No external JSON hosts at all on the public homepage |
| SoftSwiss | metaspins (blocked), wild.io | No external JSON hosts observed |
| iGate | spinlynx | Access denied |
| Delasport | grandwin | Browser error both in CI and locally (proxy/navigation failure) — **inconclusive**, not re-attempted via any bypass |
| Digitain | slottica | HTTP error — **inconclusive**, not re-attempted via any bypass |

(Altenar's `vegas.hu` and InPlayNet's both brands are included in the same
run only as a regression check — they correctly still show their
already-known `biahosted.com`/`inplaynet.tech` hosted hosts.)

**Conclusion: none of these 7 families expose a reachable public odds API
from a homepage+one-sports-link crawl**, matching and extending the
original catalogue-level sweep. This is a genuine technical limit of this
observation method (a logged-in session or a specific live-match page
might behave differently), not a claim that these operators have no odds
anywhere, and **none of the 7 are promoted to any adapter**. Revisiting
any of them would require the same kind of deeper, still-bypass-free
investigation that found Altenar's and InPlayNet's actual platform hosts —
navigating into a real listed match, not just the sports landing page.

## Altenar: other brands checked, still only vegas.hu is usable — 2026-10-16 UTC

Closed the flagged gap ("other Altenar operators were not probed for their
own integration id/host"): extended the schema sniffer to all 6 remaining
BetClone-catalogued Altenar brands
([run 38946777512](https://github.com/forfexes/btts-bot_ki/actions/runs/38946777512)).
Result: rabona, campobet, nomini and betrepublic were access-denied at the
homepage itself; sportaza likewise; betinia rendered but never loaded any
`biahosted.com` JSON on this bounded homepage+one-sports-link crawl.
**`vegas.hu` remains the only Altenar brand with a confirmed, working
keyless widget.** No bypass was attempted for the denied/blocked brands.

## Honest outcome (2026-10-17)

What BetClone actually delivered:
- **Altenar**: ~10,000 match-level quotes per run (1X2, Over/Under 2.5, BTTS) as a *shadow* source
  (only used when an independent source corroborates it). First live use confirmed (BTTS yes quote).
- **1xBet family**: match-level quotes as shadow source. Player markets exist but the numeric bet-group
  ids are NOT mapped (the old `_1X_PLAYER_GROUPS` ids were unverified guesses; 1xBet currently yields 0 player props).
- The other seven families expose no public feed usable without evasion.

What it did NOT deliver: player-prop quotes. All live player quotes (shots, shots on target, scorer, assists,
cards, few fouls) come from Kambi, which pre-dates the BetClone work.

Open item with the highest upside: map 1xBet player groups (fouls, fouls won, tackles) from evidence.
`x1_player_snapshots` collects (G, T, line, odds, player) per match; once the matches are over, compare
against `player_game_log` (fouls_committed / fouls_won / tackles) to PROVE which group is which. No guessing.


## Verified 2026-10-17: shadow-feed balance and player-code evidence

- **Playwright** remains installed in production and was exercised in
  [tip run 39023333694](https://github.com/forfexes/btts-bot_ki/actions/runs/39023333694);
  the four-page/45-second budget was reached. Rendering does not imply
  that another BetClone bookmaker provides a validated price feed.
- **Altenar vegas.hu:** Direct database audit for 2026-10-17 found 10,386
  quote rows across 1,850 fixture IDs (5,550 1x2, 2,454 BTTS, 2,382
  O/U 2.5). These are one real operator feed, not 1,850 bookmaker brands.
- **1xBet/22bet:** Direct database audit for 2026-10-17 found 19,228 quote
  rows across 1,180 fixture IDs. A subset of 307 rows from synthetic
  `Home vs Away` or `Home (Special bets)` pseudo-events was identified;
  commit `31e0accf` now suppresses these *before* ingestion. Existing
  historical rows remain historical data and are not retrospectively deleted.
- **Balanced cache:** The independent per-platform paging and strict
  full-market corroboration gate are tested by
  [shadow coverage CI 39028406560](https://github.com/forfexes/btts-bot_ki/actions/runs/39028406560).
  It fetched 17,617 real stored rows: 7,231 1xBet and 10,386 Altenar.
  This is a cache retrieval check, *not* 17,617 released betting tips.
  Unknown/coded markets remain shadow-only.
- **Player market evidence:** Today's successful
  [probe 39028758422](https://github.com/forfexes/btts-bot_ki/actions/runs/39028758422)
  inserted the first 800 `x1_player_snapshots` records: 77 distinct
  players, 2 games, and 14 observed opaque group IDs. Player identity is
  read from the publicly observed `PL.N` and `PL.I` structure; codes
  `G`/`T` retain their source meaning and are **not** labelled as
  shots, fouls, tackles or scorer without independent proof.
  Daily bounded collection is in `netrattler_1x_props_probe.yml`.
- **Unfinished:** BETBY, BetConstruct, Delasport, Digitain, FIRST, iGate,
  InPlayNet and SoftSwiss still have no separately verified production odds
  adapter. Altenar and 1xBet do not cover every skin in their respective
  catalogues. Player outcomes must be checked against independent historical
  stats before market names or Telegram tips can be released.

### Regression incident and resolution (2026-10-17)

The intermediate build `2eb16069` changed the source filter to separate
per-provider queries and briefly broke tests that expected a combined filter
([Public Sources CI 39028237441](https://github.com/forfexes/btts-bot_ki/actions/runs/39028237441),
[Core CI 39028237545](https://github.com/forfexes/btts-bot_ki/actions/runs/39028237545)).
The tests and reader were reconciled in later commits; both
[Public Sources CI 39028406558](https://github.com/forfexes/btts-bot_ki/actions/runs/39028406558)
and [Core CI 39028406595](https://github.com/forfexes/btts-bot_ki/actions/runs/39028406595)
passed. The two earlier Telegram alerts are obsolete historical failures.
