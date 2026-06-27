forfexes/btts-bot_ki/
├── btts_bot.py              # Haupt-Bot (~22.000 Zeilen)
├── prop_builder_v4.py       # Standalone Prop Builder (Pinnacle Specials)
├── settlement.py            # ⚠️ FALSCH — Kopie von scrape_player_stats.py!
├── scrape_player_stats.py   # Player Stats Scraper (StatsBomb/SofaScore/FBref)
├── train_model.py           # XGBoost ML-Training (wöchentlich)
├── supabase_v4.py           # Supabase Helper-Klasse
├── player_identity.py       # looks_like_player(), extract_player_from_description()
├── prop_value_engine.py     # Edge/Value Berechnungen
├── requirements.txt         # Python Dependencies
├── MASTERPLAN.md            # Dieses Dokument
└── .github/workflows/
    ├── btts_tips.yml        # Haupt-Bot (4x täglich: 06:30/12:30/18:30/21:30 UTC)
    ├── btts-settlement.yml  # Settlement (alle 3h) ⚠️ ruft falsches script auf
    ├── scrape_player_stats.yml  # Player Stats (täglich 04:10 UTC)
    ├── train_model.yml      # ML Training (montags 04:00 UTC)
    ├── cleanup.yml          # GitHub Runs cleanup (täglich 03:00 UTC)
    └── telegram_test.yml    # Telegram Test (manuell)
