name: NETRATTLER AI Tipp Bot V20

on:
  workflow_dispatch:
  schedule:
    - cron: "0 7 * * *"
    - cron: "0 11 * * *"
    - cron: "0 17 * * *"
    - cron: "0 21 * * *"

concurrency:
  group: netrattler-main-bot
  cancel-in-progress: false

jobs:
  run-bot:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Compile NETRATTLER
        run: |
          python -m py_compile btts_bot.py netrattler_builder_engine.py

      - name: Run NETRATTLER
        env:
          GEMINI_API_KEYS: ${{ secrets.GEMINI_API_KEYS }}
          GROQ_API_KEYS: ${{ secrets.GROQ_API_KEYS }}
          OPENROUTER_API_KEYS: ${{ secrets.OPENROUTER_API_KEYS }}
          ODDS_API_KEYS: ${{ secrets.ODDS_API_KEYS }}
          FOOTBALL_DATA_API_KEYS: ${{ secrets.FOOTBALL_DATA_API_KEYS }}
          API_FOOTBALL_KEYS: ${{ secrets.API_FOOTBALL_KEYS }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TELEGRAM_GROUP_BTTS: ${{ secrets.TELEGRAM_GROUP_BTTS }}
          TELEGRAM_GROUP_OVER25: ${{ secrets.TELEGRAM_GROUP_OVER25 }}
          TELEGRAM_GROUP_COMBO: ${{ secrets.TELEGRAM_GROUP_COMBO }}
          TELEGRAM_GROUP_COMBOS: ${{ secrets.TELEGRAM_GROUP_COMBOS }}
          TELEGRAM_GROUP_BTTS_HT: ${{ secrets.TELEGRAM_GROUP_BTTS_HT }}
          TELEGRAM_GROUP_OVER15_HT: ${{ secrets.TELEGRAM_GROUP_OVER15_HT }}
          TELEGRAM_GROUP_STATS: ${{ secrets.TELEGRAM_GROUP_STATS }}
          TELEGRAM_GROUP_BUILDER: ${{ secrets.TELEGRAM_GROUP_BUILDER }}
          TELEGRAM_GROUP_PROPS: ${{ secrets.TELEGRAM_GROUP_PROPS }}
          TELEGRAM_GROUP_CORNERS: ${{ secrets.TELEGRAM_GROUP_CORNERS }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          RUN_MODE: "tips"
          ENABLE_SETTLEMENT: "false"
          ENABLE_ADVANCED_PROPS: "true"
          ENABLE_TIP_PERFORMANCE_FOOTER: "true"
          SEND_EMPTY_PERFORMANCE_CARDS: "false"
          SHOW_ML_LEARNING_FOOTER: "false"
          ENABLE_LEGACY_BUILDERS: "false"
          NETRATTLER_MAX_BUILDERS_PER_RUN: "14"
          NETRATTLER_BUILDER_MIN_ODDS: "1.75"
          NETRATTLER_BUILDER_MAX_ODDS: "80"
          MAX_LEAGUES_PER_RUN: "0"
          PARALLEL_WORKERS: "10"
          AI_SLEEP_SECONDS: "0.1"
          GROQ_SLEEP_SECONDS: "0.5"
        run: python btts_bot.py
