name: Asia BTTS Tipps 🌏

on:
  schedule:
    - cron: '0 2 * * *'   # 02:00 UTC = 04:00 CH Sommer / 03:00 CH Winter
  workflow_dispatch:

jobs:
  run-bot-asia:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests python-dotenv

      - name: Run Asia Bot 🌏
        env:
          GEMINI_API_KEYS: ${{ secrets.GEMINI_API_KEYS }}
          GROQ_API_KEYS: ${{ secrets.GROQ_API_KEYS }}
          ODDS_API_KEYS: ${{ secrets.ODDS_API_KEYS }}
          FOOTBALL_DATA_API_KEYS: ${{ secrets.FOOTBALL_DATA_API_KEYS }}
          API_FOOTBALL_KEYS: ${{ secrets.API_FOOTBALL_KEYS }}
          SPORTMONKS_API_KEY: ${{ secrets.SPORTMONKS_API_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TELEGRAM_GROUP_BTTS: ${{ secrets.TELEGRAM_GROUP_BTTS }}
          TELEGRAM_GROUP_OVER25: ${{ secrets.TELEGRAM_GROUP_OVER25 }}
          TELEGRAM_GROUP_COMBO: ${{ secrets.TELEGRAM_GROUP_COMBO }}
          TELEGRAM_GROUP_BTTS_HT: ${{ secrets.TELEGRAM_GROUP_BTTS_HT }}
          TELEGRAM_GROUP_STATS: ${{ secrets.TELEGRAM_GROUP_STATS }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          AI_SLEEP_SECONDS: "1.5"
          LEAGUE_ROTATION_ENABLED: "true"
          # 🌏 Asien + Australien + Ozeanien + Naher Osten
          ACTIVE_LEAGUES: "J1 League Japan,K League 1,China Super League,A-League,Saudi Pro League,Iceland Premier League,Iceland 1. Deild"
        run: python btts_asia.py

      - name: Log Summary
        if: always()
        run: |
          echo "✅ Asia Bot Complete"
          echo "Schedule: 02:00 UTC = 04:00 Schweizer Zeit"
          echo "Ligen: Japan, Korea, China, A-League, Saudi, Iceland"
