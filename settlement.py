name: NETRATTLER Settlement V4 DATECACHE

on:
  schedule:
    - cron: "20 */3 * * *"
  workflow_dispatch:

jobs:
  settlement:
    runs-on: ubuntu-latest
    timeout-minutes: 3

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
          pip install requests python-dotenv

      - name: Run Settlement V4
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TELEGRAM_GROUP_STATS: ${{ secrets.TELEGRAM_GROUP_STATS }}
          FOOTBALL_DATA_API_KEYS: ${{ secrets.FOOTBALL_DATA_API_KEYS }}
          FOOTBALL_DATA_API_KEY: ${{ secrets.FOOTBALL_DATA_API_KEY }}
          SETTLEMENT_DAYS_BACK: "2"
          SETTLEMENT_LIMIT: "250"
          SETTLEMENT_MAX_DATES: "3"
          SETTLEMENT_TIMEOUT_SECONDS: "60"
          SETTLEMENT_SEND_SUMMARY: "true"
        run: |
          echo "⚽ NETRATTLER Settlement V4 DATECACHE startet..."
          python settlement.py
