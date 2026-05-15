name: BTTS Settlement
on:
  schedule:
    - cron: '0 15 * * *'
    - cron: '45 23 * * *'
    - cron: '30 5 * * *'
  workflow_dispatch:
jobs:
  run-settlement:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests python-dotenv
      - name: Run Settlement
        env:
          RUN_MODE: "settlement"
          GEMINI_API_KEYS: ${{ secrets.GEMINI_API_KEYS }}
          GROQ_API_KEYS: ${{ secrets.GROQ_API_KEYS }}
          ODDS_API_KEYS: ${{ secrets.ODDS_API_KEYS }}
          FOOTBALL_DATA_API_KEYS: ${{ secrets.FOOTBALL_DATA_API_KEYS }}
          API_FOOTBALL_KEYS: ${{ secrets.API_FOOTBALL_KEYS }}
          ALLSPORTS_API_KEY: ${{ secrets.ALLSPORTS_API_KEY }}
          OPENWEATHER_API_KEY: ${{ secrets.OPENWEATHER_API_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TELEGRAM_GROUP_STATS: ${{ secrets.TELEGRAM_GROUP_STATS }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python btts_bot.py
      - if: always()
        run: echo "Done"
