name: NETRATTLER Settlement Final V25 MULTISOURCE

on:
  workflow_dispatch:
  schedule:
    - cron: "20 13 * * *"
    - cron: "20 23 * * *"

jobs:
  settlement:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests python-dateutil
      - name: Compile settlement
        run: python -m py_compile netrattler_settlement_v16_final.py
      - name: Run Settlement V25 MULTISOURCE
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
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
          TELEGRAM_GROUP_HZ_LIVE: ${{ secrets.TELEGRAM_GROUP_HZ_LIVE }}
          TELEGRAM_GROUP_LATE_GOALS: ${{ secrets.TELEGRAM_GROUP_LATE_GOALS }}
          ALLSPORTS_API_KEY: ${{ secrets.ALLSPORTS_API_KEY }}
          FOOTBALL_DATA_API_KEYS: ${{ secrets.FOOTBALL_DATA_API_KEYS }}
          FOOTBALL_DATA_API_KEY: ${{ secrets.FOOTBALL_DATA_API_KEY }}
          FOOTBALLDATA_IO_API_KEY: ${{ secrets.FOOTBALLDATA_IO_API_KEY }}
          SETTLEMENT_DAYS: "14"
          SETTLEMENT_LIMIT: "3000"
          RESULT_USE_SOFASCORE: "false"
          RESULT_USE_ESPN: "true"
          RESULT_USE_OPENLIGADB: "true"
          RESULT_HTTP_TIMEOUT: "4"
          ESPN_DISABLE_AFTER_FORBIDDEN: "true"
          RESULT_USE_FOTMOB: "true"
          RESULT_USE_SOFASCORE_DETAIL: "true"
          SETTLEMENT_ALLOW_SEPARATE_RESULT_UPDATE: "false"
          RESULT_ENRICH_MAX_DETAILS: "120"
          RESULT_ENRICH_TIMEOUT: "7"
        run: python netrattler_settlement_v16_final.py
