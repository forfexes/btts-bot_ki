# NETRATTLER V30

Football analytics / Telegram tip bot with modular source, identity, builder, settlement and ML layers.

## V30 Source Stack

Integrated as guarded adapters with timeout, cache, health checks and fallback behavior:

- probberechts/soccerdata
- statsbomb/open-data
- davidrocha9/fotmob-scraper concepts
- withqwerty/reep identity mapping concepts
- OddsHarvester as optional CLV/OddsPortal fallback
- Simatwa/livescore-api as optional guarded settlement fallback
- openfootball/football.json
- openfootball/worldcup.json
- openfootball/south-america
- openfootball/europe
- openfootball/champions-league
- openfootball/internationals
- openfootball/players
- openfootball/clubs
- salimt/football-datasets
- eddwebster/football_analytics feature catalog

Every source may fail without stopping the main bot.

## Important modules

- `btts_bot.py` — main Telegram bot
- `scrape_player_stats.py` — result + player-stat scraper
- `netrattler_builder_engine.py` — pure builder engine
- `netrattler_identity_hub.py` — team/player alias matching
- `netrattler_source_hub.py` — GitHub/OpenFootball/source adapters
- `netrattler_feature_hub.py` — football_analytics-inspired feature recipes
- `netrattler_settlement_v16_final.py` — settlement with SourceHub fallbacks

## Tests

```bash
python -m py_compile btts_bot.py netrattler_builder_engine.py netrattler_settlement_v16_final.py netrattler_source_hub.py netrattler_identity_hub.py netrattler_feature_hub.py scrape_player_stats.py
python test_netrattler_core.py
python test_source_hub_v30.py
```
