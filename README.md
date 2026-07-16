# NETRATTLER V34 — All Sources + ML + Bookmaker Odds

## Replace/add these files
- `scrape_player_stats.py`
- `train_model.py`
- `netrattler_odds_harvester.py`
- `netrattler_all_source_harvester.py`
- `import_football_data_sources_v14.py`
- `netrattler_source_hub.py`
- `netrattler_builder_engine.py`
- `btts_bot.py`
- `requirements_all_source.txt`
- `requirements_train.txt`
- workflows in `.github/workflows/`

## Data routing
- Match/results sources -> `match_results`, `football_historical_matches`, data lake
- Player/event sources -> `player_match_stats`, data lake
- Identity sources -> canonical Reep/OpenFootball mapping
- Bookmaker sources -> `odds_history`, fallback data lake, local snapshot
- ML reads match results, historical matches, player stats and odds history, then fuses duplicate matches instead of discarding richer rows
- Bot/Builder reads the live odds pipeline first and `odds_history` as runtime fallback

## Source fallback order
Every adapter catches its own error and continues. No free source is allowed to stop the run.

### Results/history
OpenFootball JSON + Football.TXT repos, martj42, ESPN, TheSportsDB, OpenLigaDB, Football-Data.co.uk, Supabase results.

### Player data
StatsBomb open data, FotMob direct, Soccerdata adapters (FBref, Sofascore, Understat, ESPN, Football-Data, WhoScored where available), SofaScore direct, FBref Playwright, salimt datasets.

### Identity
Reep plus OpenFootball players/clubs.

### Odds/bookmakers
Football-Data historical bookmaker columns; Pinnacle guest; The Odds API when a key exists; OddsHarvester/OddsPortal all-bookmaker pass; explicit Bet365 pass; direct public Bet365 Playwright best effort; official Betfair API when credentials exist.

Direct Bet365 scraping is inherently fragile and may be blocked. The stable Bet365 fallbacks are Football-Data historical B365 columns and OddsPortal/OddsHarvester bookmaker filtering. No anti-bot bypass or login circumvention is implemented.

## Run order
1. Historical All Sources Import V34 (first run/manual, then weekly)
2. Player Stats + Results Scraper V34
3. Odds Harvester V34
4. All Source Harvester V34
5. ML Train V34 All Sources
6. AI Tipp Bot
