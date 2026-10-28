"""NETRATTLER key audit: reports only whether each known optional API-key env
var is set (non-empty) in this GitHub Actions run, never the value itself.
Writes the result to netrattler_card_diag for readback."""
import os
import json
import requests

KEYS = [
    "GEMINI_API_KEYS", "GROQ_API_KEYS", "OPENROUTER_API_KEYS", "MISTRAL_API_KEYS",
    "COHERE_API_KEY", "HUGGINGFACE_API_KEY", "TAVILY_API_KEY",
    "ODDS_API_KEYS", "ODDS_API_NET_KEY", "FOOTBALL_DATA_API_KEYS", "API_FOOTBALL_KEYS",
    "SPORTMONKS_API_KEY", "SPORTDB_API_KEY", "ALLSPORTS_API_KEY", "FOOTYSTATS_API_KEY",
    "OPENWEATHER_API_KEY", "THESTATSAPI_KEY", "THESTATSAPI_KEYS", "API_NINJAS_KEY",
    "ODDSPAPI_KEYS", "ODDSPAPI_KEY", "FIVEDOLLAR_API_KEY", "FIELDFUNDED_API_KEY",
    "SOCKODDS_API_KEY", "BIGBALLS_API_KEY", "BBS_API_KEY",
    "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_GROUP_BTTS", "TELEGRAM_GROUP_OVER25",
    "TELEGRAM_GROUP_COMBO", "TELEGRAM_GROUP_COMBOS", "TELEGRAM_GROUP_BTTS_HT",
    "TELEGRAM_GROUP_HZ_LIVE", "TELEGRAM_GROUP_CORNERS", "TELEGRAM_GROUP_LATE_GOALS",
    "TELEGRAM_GROUP_STATS", "TELEGRAM_GROUP_PLAYER_PROPS", "TELEGRAM_GROUP_BUILDER",
    "TELEGRAM_GROUP_OVER15_HT",
    "ODDSAPIIO_KEY", "RAPIDAPI_KEY", "SPORTAPI_AI_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_GROUP_ALERTS", "V4_DATABASE_URL",
    "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_PLAYERS_URL", "SUPABASE_PLAYERS_SERVICE_KEY",
    "V2_SUPABASE_URL", "V2_SUPABASE_SERVICE_KEY", "V2_DATABASE_URL", "V3_DATABASE_URL",
]

present = {}
missing = []
for k in KEYS:
    v = os.environ.get(k, "")
    ok = bool(v and v.strip())
    present[k] = ok
    if not ok:
        missing.append(k)

out = {"probe": "key_audit", "present_count": sum(present.values()), "total": len(KEYS), "missing": missing}

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
if SUPABASE_URL and SUPABASE_KEY:
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/netrattler_card_diag",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={"info": out},
            timeout=15,
        )
    except Exception as e:
        print("report failed:", e)

print(json.dumps(out, indent=2))
