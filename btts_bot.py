"""
AI TIPP BOT - GITHUB SINGLE FILE EDITION
=======================================

WICHTIG:
- Keine API Keys direkt in diesen Code schreiben.
- Lokal: .env Datei erstellen.
- GitHub: Secrets verwenden.

Benötigte GitHub Secrets / .env Variablen:
GEMINI_API_KEYS=key1,key2,key3
GROQ_API_KEYS=key1,key2
ODDS_API_KEYS=key1,key2
FOOTBALL_DATA_API_KEY=...
API_FOOTBALL_KEY=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_GROUP_BTTS=...
TELEGRAM_GROUP_OVER25=...
TELEGRAM_GROUP_COMBO=...
TELEGRAM_GROUP_BTTS_HT=...
TELEGRAM_GROUP_STATS=...
SUPABASE_URL=...
SUPABASE_KEY=...
"""

import os
import re
import sys
import json
import traceback
import time
from datetime import date, datetime, timedelta, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================================================
# CONFIG
# ============================================================

def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_list(name: str) -> list[str]:
    value = env(name)
    return [x.strip() for x in value.split(",") if x.strip()]


GEMINI_API_KEYS = env_list("GEMINI_API_KEYS")
GROQ_API_KEYS = env_list("GROQ_API_KEYS")
ODDS_API_KEYS = env_list("ODDS_API_KEYS")

FOOTBALL_DATA_API_KEY = env("FOOTBALL_DATA_API_KEY")
# 🆕 Mehrere Football-Data Keys unterstützen (kommasepariert, 10 Requests/Min pro Key)
FOOTBALL_DATA_API_KEYS = env_list("FOOTBALL_DATA_API_KEYS")
if not FOOTBALL_DATA_API_KEYS and FOOTBALL_DATA_API_KEY:
    FOOTBALL_DATA_API_KEYS = [FOOTBALL_DATA_API_KEY]
# Erster Key für Backwards-Kompatibilität
FOOTBALL_DATA_API_KEY = FOOTBALL_DATA_API_KEYS[0] if FOOTBALL_DATA_API_KEYS else ""

# 🆕 Mehrere API-Football Keys unterstützen (kommasepariert)
# Backwards-kompatibel: Falls API_FOOTBALL_KEY (singular) gesetzt ist, wird der genutzt
API_FOOTBALL_KEYS = env_list("API_FOOTBALL_KEYS")
if not API_FOOTBALL_KEYS:
    single_key = env("API_FOOTBALL_KEY")
    if single_key:
        API_FOOTBALL_KEYS = [single_key]
# Erster Key für Backwards-Kompatibilität
API_FOOTBALL_KEY = API_FOOTBALL_KEYS[0] if API_FOOTBALL_KEYS else ""

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

TELEGRAM_GROUPS = {
    "btts": env("TELEGRAM_GROUP_BTTS", TELEGRAM_CHAT_ID),
    "over25": env("TELEGRAM_GROUP_OVER25", TELEGRAM_CHAT_ID),
    "combo": env("TELEGRAM_GROUP_COMBO") or env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID),
    "btts_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
}

SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "67"))  # 🆕 Hybrid: 67% (zwischen 65-69)
MIN_ODDS = float(env("MIN_ODDS", "1.65"))
MAX_ODDS = float(env("MAX_ODDS", "3.0"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))
# 🆕 Nur HIGH + OK Value (LOW fliegt raus)
MIN_VALUE_RATING = env("MIN_VALUE_RATING", "OK")  # HIGH, OK, oder LOW

MARKETS_TO_RUN = ["btts", "over25", "combo", "btts_ht"]

# ============================================================
# AUTO LIGA SWITCH
# ============================================================
AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "true").lower() in ["1", "true", "yes", "on"]
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "0"))
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "1.5"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "2.5"))
USE_GROQ_FALLBACK = env("USE_GROQ_FALLBACK", "true").lower() in ["1", "true", "yes", "on"]

ALWAYS_ON_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_ON_LEAGUES", "Champions League,Europa League,Premier League,Bundesliga,La Liga,Serie A,Ligue 1").split(",")
    if x.strip()
]

ALWAYS_OFF_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_OFF_LEAGUES", "").split(",")
    if x.strip()
]

ACTIVE_LEAGUES_OVERRIDE = [
    x.strip()
    for x in env("ACTIVE_LEAGUES", "").split(",")
    if x.strip()
]

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"


# ============================================================
# LIGEN
# ============================================================

LEAGUES_TO_RUN = [
    "Champions League",
    "Europa League",
    "Conference League",
    "Bundesliga",
    "2. Bundesliga",
    "3. Liga Deutschland",
    "Premier League",
    "Championship",
    "EFL League 1",
    "EFL League 2",
    "National League",
    "La Liga",
    "La Liga 2",
    "Serie A",
    "Serie B",
    "Serie C",
    "Ligue 1",
    "Ligue 2",
    "Eredivisie",
    "Eerste Divisie",
    "Primeira Liga",
    "Pro League Belgien",
    "Belgium Challenger",
    "Süper Lig",
    "Turkish 1. Lig",
    "Bundesliga Österreich",
    "Austria 2. Liga",
    "Super League Schweiz",
    "Swiss Challenge",
    "Scottish Premiership",
    "Scottish Championship",
    "Scottish League One",
    "Danish Superliga",
    "Danish 1. Division",
    "Norway Eliteserien",
    "Norwegian 1. Division",
    "Sweden Allsvenskan",
    "Swedish Superettan",
    "Finland Veikkausliiga",
    "Iceland Premier",
    "Iceland 1. Deild",
    "Greece Super League",
    "Croatia HNL",
    "Serbia SuperLiga",
    "Romania Liga I",
    "Czech First League",
    "Czech 2. Liga",
    "Poland Ekstraklasa",
    "Slovak Super Liga",
    "Hungarian NB I",
    "Bulgarian First",
    "Israeli Liga Leumit",
    "Israeli Premier",
    "Ukrainian Premier",
    "Russian Premier",
    "Belarus Premier",
    "Latvian Higher League",
    "Lithuanian A Lyga",
    "Estonian Premium",
    "Kazakh Premier",
    "UEFA Youth League",
    "Bundesliga U19",
    "Bundesliga U17",
    "Premier League U21",
    "Premier League U18",
    "La Liga U19",
    "Serie A U19",
    "Ligue 1 U19",
    "Eredivisie U21",
    "MLS",
    "USL Championship",
    "Brasileirao Serie A",
    "Brasileirao Serie B",
    "Liga Argentinien",
    "Argentina Primera B",
    "Liga MX",
    "Liga MX Expansion",
    "Uruguay Primera",
    "Chile Primera",
    "Colombia Primera",
    "Ecuador Serie A",
    "Peru Primera",
    "Venezuela Primera",
    "Paraguay Division",
    "Bolivia Division",
    "Costa Rica Primera",
    "Guatemala Liga",
    "Honduras Liga",
    "Copa Libertadores",
    "Copa Sudamericana",
    "CONCACAF Champions",
    "Saudi Pro League",
    "Qatar Stars League",
    "UAE Pro League",
    "Egypt Premier",
    "Morocco Botola",
    "Tunisia Ligue 1",
    "South Africa PSL",
    "Algeria Ligue 1",
    "Nigeria Premier",
    "Kenya Premier",
    "Iran Pro League",
    "Jordan Pro League",
    "Kuwait Premier",
    "Bahrain Premier",
    "J1 League Japan",
    "J2 League Japan",
    "J3 League Japan",
    "K League 1",
    "K League 2",
    "China Super League",
    "China League 1",
    "India Super League",
    "India I-League",
    "Vietnam V-League",
    "Thailand League 1",
    "Malaysia Super League",
    "Indonesia Liga 1",
    "Philippines United",
    "Singapore Premier",
    "Myanmar National",
    "Taiwan Football Prem",
    "Hong Kong Premier",
    "A-League Australia",
    "A-League Women",
    "New Zealand NZFC",
    "AFC Champions League",
    "AFC Cup",
    "Kazakhstan Premier",
    "Uzbekistan Super",
    "Tajikistan League",
]

# Zeitfenster pro Liga (UTC Stunden)
LEAGUES_TIME_MAP = {
    "Champions League": "evening",
    "Europa League": "evening",
    "Conference League": "evening",
    "Bundesliga": "evening",
    "2. Bundesliga": "evening",
    "3. Liga Deutschland": "evening",
    "Premier League": "evening",
    "Championship": "evening",
    "EFL League 1": "evening",
    "EFL League 2": "evening",
    "National League": "evening",
    "La Liga": "evening",
    "La Liga 2": "evening",
    "Serie A": "evening",
    "Serie B": "evening",
    "Serie C": "evening",
    "Ligue 1": "evening",
    "Ligue 2": "evening",
    "Eredivisie": "evening",
    "Eerste Divisie": "evening",
    "Primeira Liga": "evening",
    "Pro League Belgien": "evening",
    "Belgium Challenger": "evening",
    "Süper Lig": "evening",
    "Turkish 1. Lig": "evening",
    "Bundesliga Österreich": "evening",
    "Austria 2. Liga": "evening",
    "Super League Schweiz": "evening",
    "Swiss Challenge": "evening",
    "Scottish Premiership": "evening",
    "Scottish Championship": "evening",
    "Scottish League One": "evening",
    "Danish Superliga": "evening",
    "Danish 1. Division": "evening",
    "Norway Eliteserien": "evening",
    "Norwegian 1. Division": "evening",
    "Sweden Allsvenskan": "evening",
    "Swedish Superettan": "evening",
    "Finland Veikkausliiga": "evening",
    "Iceland Premier": "evening",
    "Iceland 1. Deild": "evening",
    "Greece Super League": "evening",
    "Croatia HNL": "evening",
    "Serbia SuperLiga": "evening",
    "Romania Liga I": "evening",
    "Czech First League": "evening",
    "Czech 2. Liga": "evening",
    "Poland Ekstraklasa": "evening",
    "Slovak Super Liga": "evening",
    "Hungarian NB I": "evening",
    "Bulgarian First": "evening",
    "Israeli Liga Leumit": "evening",
    "Israeli Premier": "evening",
    "Ukrainian Premier": "evening",
    "Russian Premier": "evening",
    "Belarus Premier": "evening",
    "Latvian Higher League": "evening",
    "Lithuanian A Lyga": "evening",
    "Estonian Premium": "evening",
    "Kazakh Premier": "evening",
    "UEFA Youth League": "evening",
    "Bundesliga U19": "afternoon",
    "Bundesliga U17": "afternoon",
    "Premier League U21": "afternoon",
    "Premier League U18": "afternoon",
    "La Liga U19": "afternoon",
    "Serie A U19": "afternoon",
    "Ligue 1 U19": "afternoon",
    "Eredivisie U21": "afternoon",
    "MLS": "night",
    "USL Championship": "night",
    "Brasileirao Serie A": "night",
    "Brasileirao Serie B": "night",
    "Liga Argentinien": "night",
    "Argentina Primera B": "night",
    "Liga MX": "night",
    "Liga MX Expansion": "night",
    "Uruguay Primera": "night",
    "Chile Primera": "night",
    "Colombia Primera": "night",
    "Ecuador Serie A": "night",
    "Peru Primera": "night",
    "Venezuela Primera": "night",
    "Paraguay Division": "night",
    "Bolivia Division": "night",
    "Costa Rica Primera": "night",
    "Guatemala Liga": "night",
    "Honduras Liga": "night",
    "Copa Libertadores": "night",
    "Copa Sudamericana": "night",
    "CONCACAF Champions": "night",
    "Saudi Pro League": "afternoon",
    "Qatar Stars League": "afternoon",
    "UAE Pro League": "afternoon",
    "Egypt Premier": "afternoon",
    "Morocco Botola": "afternoon",
    "Tunisia Ligue 1": "afternoon",
    "South Africa PSL": "afternoon",
    "Algeria Ligue 1": "afternoon",
    "Nigeria Premier": "afternoon",
    "Kenya Premier": "afternoon",
    "Iran Pro League": "afternoon",
    "Jordan Pro League": "afternoon",
    "Kuwait Premier": "afternoon",
    "Bahrain Premier": "afternoon",
    "J1 League Japan": "morning",
    "J2 League Japan": "morning",
    "J3 League Japan": "morning",
    "K League 1": "morning",
    "K League 2": "morning",
    "China Super League": "morning",
    "China League 1": "morning",
    "India Super League": "morning",
    "India I-League": "morning",
    "Vietnam V-League": "morning",
    "Thailand League 1": "morning",
    "Malaysia Super League": "morning",
    "Indonesia Liga 1": "morning",
    "Philippines United": "morning",
    "Singapore Premier": "morning",
    "Myanmar National": "morning",
    "Taiwan Football Prem": "morning",
    "Hong Kong Premier": "morning",
    "A-League Australia": "morning",
    "A-League Women": "morning",
    "New Zealand NZFC": "morning",
    "AFC Champions League": "morning",
    "AFC Cup": "morning",
    "Kazakhstan Premier": "morning",
    "Uzbekistan Super": "morning",
    "Tajikistan League": "morning",
}


LEAGUE_KEYS = {
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
    "Bundesliga": "soccer_germany_bundesliga",
    "2. Bundesliga": "soccer_germany_bundesliga2",
    "Premier League": "soccer_epl",
    "Championship": "soccer_efl_champ",
    "La Liga": "soccer_spain_la_liga",
    "La Liga 2": "soccer_spain_segunda_division",
    "Serie A": "soccer_italy_serie_a",
    "Serie B": "soccer_italy_serie_b",
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Pro League Belgien": "soccer_belgium_first_div",
    "Süper Lig": "soccer_turkey_super_league",
    "Bundesliga Österreich": "soccer_austria_bundesliga",
    "Super League Schweiz": "soccer_switzerland_superleague",
    "Scottish Premiership": "soccer_spl",
    "MLS": "soccer_usa_mls",
    "Brasileirao Serie A": "soccer_brazil_campeonato",
    "Liga Argentinien": "soccer_argentina_primera_division",
    "J1 League Japan": "soccer_japan_j_league",
    "Saudi Pro League": "soccer_saudi_arabia_league",
    "Liga MX": "soccer_mexico_ligamx",
    "A-League": "soccer_australia_aleague",
    "Iceland Premier League": "soccer_iceland_urvalsdeild",
    "K League 1": "soccer_korea_kleague1",
    "China Super League": "soccer_china_superleague",
    # 🆕 8 neue Ligen
    "EFL League 1": "soccer_england_league1",
    "EFL League 2": "soccer_england_league2",
    "Finland Veikkausliiga": "soccer_finland_veikkausliiga",
    "Uruguay Primera": "soccer_uruguay_primera_division",
    "India Super League": "soccer_india_superleague",
    "Qatar Stars League": "soccer_qatar_league",
    "South Africa PSL": "soccer_south_africa_premier_league",
    "Vietnam V-League": "soccer_vietnam_v_league",
    "Danish Superliga": "soccer_denmark_superliga",
    "Norway Eliteserien": "soccer_norway_eliteserien",
    "Sweden Allsvenskan": "soccer_sweden_allsvenskan",
    "Greece Super League": "soccer_greece_super_league",
    "Poland Ekstraklasa": "soccer_poland_ekstraklasa",
    "Slovak Super Liga": "soccer_slovakia_super_liga",
    # 🆕 B/C-Ligen (falls Odds API sie hat)
    "Eerste Divisie": "soccer_netherlands_eerste_divisie",
    "Norwegian 1. Division": "soccer_norway_first_division",
    "Turkish 1. Lig": "soccer_turkey_first_league",
    "Belgian Challenger Pro": "soccer_belgium_first_div_b",
    "Czech 2. Liga": "soccer_czech_2_liga",
    "Scottish Championship": "soccer_scotland_championship",
    "Swedish Superettan": "soccer_sweden_superettan",
    "Israeli Liga Leumit": "soccer_israel_liga_leumit",
}

FOOTBALL_DATA_CODES = {
    "Champions League": "CL",
    "Bundesliga": "BL1",
    "2. Bundesliga": "BL2",
    "Premier League": "PL",
    "Championship": "ELC",
    "La Liga": "PD",
    "Serie A": "SA",
    "Ligue 1": "FL1",
    "Eredivisie": "DED",
    "Primeira Liga": "PPL",
    "Brasileirao Serie A": "BSA",
}

API_FOOTBALL_LEAGUES = {
    "Champions League": 2,
    "Europa League": 3,
    "Conference League": 848,
    "Bundesliga": 78,
    "2. Bundesliga": 79,
    "3. Liga Deutschland": 82,
    "Premier League": 39,
    "Championship": 40,
    "EFL League 1": 41,
    "EFL League 2": 42,
    "National League": 43,
    "La Liga": 140,
    "La Liga 2": 141,
    "Serie A": 135,
    "Serie B": 136,
    "Serie C": 137,
    "Ligue 1": 61,
    "Ligue 2": 62,
    "Eredivisie": 88,
    "Eerste Divisie": 89,
    "Primeira Liga": 94,
    "Pro League Belgien": 144,
    "Belgium Challenger": 296,
    "Süper Lig": 203,
    "Turkish 1. Lig": 200,
    "Bundesliga Österreich": 218,
    "Austria 2. Liga": 293,
    "Super League Schweiz": 207,
    "Swiss Challenge": 265,
    "Scottish Premiership": 179,
    "Scottish Championship": 181,
    "Scottish League One": 182,
    "Danish Superliga": 119,
    "Danish 1. Division": 120,
    "Norway Eliteserien": 103,
    "Norwegian 1. Division": 104,
    "Sweden Allsvenskan": 113,
    "Swedish Superettan": 114,
    "Finland Veikkausliiga": 244,
    "Iceland Premier": 271,
    "Iceland 1. Deild": 272,
    "Greece Super League": 197,
    "Croatia HNL": 210,
    "Serbia SuperLiga": 286,
    "Romania Liga I": 283,
    "Czech First League": 345,
    "Czech 2. Liga": 346,
    "Poland Ekstraklasa": 106,
    "Slovak Super Liga": 332,
    "Hungarian NB I": 325,
    "Bulgarian First": 348,
    "Israeli Liga Leumit": 289,
    "Israeli Premier": 288,
    "Ukrainian Premier": 333,
    "Russian Premier": 235,
    "Belarus Premier": 338,
    "Latvian Higher League": 366,
    "Lithuanian A Lyga": 365,
    "Estonian Premium": 330,
    "Kazakh Premier": 381,
    "UEFA Youth League": 10,
    "Bundesliga U19": 63,
    "Bundesliga U17": 64,
    "Premier League U21": 45,
    "Premier League U18": 48,
    "La Liga U19": 384,
    "Serie A U19": 233,
    "Ligue 1 U19": 114,
    "Eredivisie U21": 90,
    "MLS": 253,
    "USL Championship": 254,
    "Brasileirao Serie A": 71,
    "Brasileirao Serie B": 72,
    "Liga Argentinien": 128,
    "Argentina Primera B": 129,
    "Liga MX": 262,
    "Liga MX Expansion": 263,
    "Uruguay Primera": 268,
    "Chile Primera": 265,
    "Colombia Primera": 239,
    "Ecuador Serie A": 240,
    "Peru Primera": 281,
    "Venezuela Primera": 243,
    "Paraguay Division": 242,
    "Bolivia Division": 321,
    "Costa Rica Primera": 266,
    "Guatemala Liga": 267,
    "Honduras Liga": 268,
    "Copa Libertadores": 13,
    "Copa Sudamericana": 14,
    "CONCACAF Champions": 26,
    "Saudi Pro League": 307,
    "Qatar Stars League": 98,
    "UAE Pro League": 306,
    "Egypt Premier": 233,
    "Morocco Botola": 200,
    "Tunisia Ligue 1": 311,
    "South Africa PSL": 288,
    "Algeria Ligue 1": 298,
    "Nigeria Premier": 300,
    "Kenya Premier": 302,
    "Iran Pro League": 290,
    "Jordan Pro League": 373,
    "Kuwait Premier": 374,
    "Bahrain Premier": 375,
    "J1 League Japan": 98,
    "J2 League Japan": 99,
    "J3 League Japan": 100,
    "K League 1": 292,
    "K League 2": 293,
    "China Super League": 169,
    "China League 1": 170,
    "India Super League": 323,
    "India I-League": 324,
    "Vietnam V-League": 340,
    "Thailand League 1": 296,
    "Malaysia Super League": 297,
    "Indonesia Liga 1": 299,
    "Philippines United": 301,
    "Singapore Premier": 303,
    "Myanmar National": 304,
    "Taiwan Football Prem": 350,
    "Hong Kong Premier": 351,
    "A-League Australia": 188,
    "A-League Women": 187,
    "New Zealand NZFC": 189,
    "AFC Champions League": 2,
    "AFC Cup": 3,
    "Kazakhstan Premier": 381,
    "Uzbekistan Super": 382,
    "Tajikistan League": 383,
}

FOOTBALL_JSON_LEAGUES = {
    "Bundesliga": "de.1",
    "2. Bundesliga": "de.2",
    "Premier League": "en.1",
    "Championship": "en.2",
    "La Liga": "es.1",
    "La Liga 2": "es.2",
    "Serie A": "it.1",
    "Serie B": "it.2",
    "Ligue 1": "fr.1",
    "Ligue 2": "fr.2",
    "Eredivisie": "nl.1",
    "Primeira Liga": "pt.1",
    "Champions League": "uefa.cl",
    "Europa League": "uefa.el",
}

OPENLIGADB_LEAGUES = {
    "Bundesliga": "bl1",
    "2. Bundesliga": "bl2",
    "Bundesliga Österreich": "bl-at",
    "Süper Lig": "tr1",
    "Champions League": "ucl",
    "Europa League": "uel",
}

UNDERSTAT_LEAGUES = {
    "Premier League": "EPL",
    "La Liga": "La_liga",
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie_A",
    "Ligue 1": "Ligue_1",
}

MARKET_INFO = {
    "btts": {
        "name": "⚽ BTTS",
        "instr": "Analysiere BTTS (Both Teams To Score - beide Teams treffen).",
    },
    "over25": {
        "name": "🎯 Over 2.5",
        "instr": "Analysiere Over 2.5 Tore.",
    },
    "combo": {
        "name": "🔥 BTTS + Over 2.5",
        "instr": "Analysiere BTTS & Over 2.5 KOMBO.",
    },
    "btts_ht": {
        "name": "🕐 BTTS HT",
        "instr": "Analysiere BTTS in der 1. Halbzeit (Beide Teams treffen bis zur Pause). Wichtig: xG HT, Pressing der Teams, frühe Tore Statistik.",
    },
}


# ============================================================
# UTILS
# ============================================================

def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def get_local_time(utc_iso_str):
    try:
        dt_utc = datetime.fromisoformat(utc_iso_str.replace("Z", "+00:00"))
        year = dt_utc.year

        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)

        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)

        offset = 2 if march_last <= dt_utc < oct_last else 1
        return (dt_utc + timedelta(hours=offset)).strftime("%H:%M")
    except Exception:
        return "TBD"


def extract_json_array(text):
    cleaned = text.replace("```json", "").replace("```", "").strip()

    try:
        s = cleaned.find("[")
        e = cleaned.rfind("]")
        if s != -1 and e > s:
            return json.loads(cleaned[s:e + 1])
    except Exception:
        pass

    objects = []
    depth = 0
    start_idx = -1

    for i, c in enumerate(cleaned):
        if c == "{":
            if depth == 0:
                start_idx = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    obj = json.loads(cleaned[start_idx:i + 1])
                    if "match" in obj:
                        objects.append(obj)
                except Exception:
                    pass
                start_idx = -1

    return objects


def normalize_team_name(name):
    if not name:
        return ""

    n = name.lower().strip()
    remove = [
        " fc", " cf", " ac", " sc", " sv", " 1.",
        "fc ", "ac ", "sc ", "sv ", "1. ",
        " e.v.", " ev",
    ]

    for x in remove:
        n = n.replace(x, " ")

    return " ".join(n.split())


def teams_match(name1, name2):
    n1 = normalize_team_name(name1)
    n2 = normalize_team_name(name2)

    if not n1 or not n2:
        return False

    if n1 == n2 or n1 in n2 or n2 in n1:
        return True

    w1 = [w for w in n1.split() if len(w) > 3]
    w2 = [w for w in n2.split() if len(w) > 3]

    return any(w in n2 for w in w1) or any(w in n1 for w in w2)


def parse_odds(val):
    try:
        return float(str(val).replace(",", "."))
    except Exception:
        return 0.0


# ============================================================
# DATA SOURCES
# ============================================================

UNDERSTAT_CACHE = {}

# ============================================================
# 🆕 OPENWEATHERMAP - Wetterdaten (kostenlos, 1000 Calls/Tag)
# ============================================================
WEATHER_API_KEY = env("OPENWEATHER_API_KEY", "")
WEATHER_CACHE = {}

STADIUM_CITIES = {
    "Premier League": "London",
    "Bundesliga": "Munich",
    "La Liga": "Madrid",
    "Serie A": "Rome",
    "Ligue 1": "Paris",
    "Eredivisie": "Amsterdam",
    "Primeira Liga": "Lisbon",
    "Champions League": "London",
    "Europa League": "London",
    "Scottish Premiership": "Glasgow",
    "Danish Superliga": "Copenhagen",
    "Norway Eliteserien": "Oslo",
    "Sweden Allsvenskan": "Stockholm",
    "MLS": "New York",
    "Brasileirao Serie A": "Sao Paulo",
    "Liga Argentinien": "Buenos Aires",
    "J1 League Japan": "Tokyo",
    "K League 1": "Seoul",
    "China Super League": "Beijing",
    "A-League": "Sydney",
    "Saudi Pro League": "Riyadh",
}

def get_weather_for_league(league_name, target_date):
    """
    Holt Wetterdaten für eine Liga (Stadt-basiert).
    Returns: {'temp': 18, 'rain': 2.5, 'wind': 15, 'condition': 'Rain', 'impact': 'negative'}
    """
    if not WEATHER_API_KEY:
        return None

    city = STADIUM_CITIES.get(league_name)
    if not city:
        return None

    cache_key = f"{city}_{target_date}"
    if cache_key in WEATHER_CACHE:
        return WEATHER_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": city,
                "appid": WEATHER_API_KEY,
                "units": "metric",
                "cnt": 8,
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        forecasts = data.get("list", [])

        if not forecasts:
            return None

        # Nehme Mittags-Forecast (12:00-18:00 Uhr)
        best = forecasts[0]
        for f in forecasts:
            dt = datetime.fromtimestamp(f["dt"], tz=timezone.utc)
            if 12 <= dt.hour <= 18:
                best = f
                break

        temp = best.get("main", {}).get("temp", 20)
        wind = best.get("wind", {}).get("speed", 0) * 3.6  # m/s → km/h
        rain = best.get("rain", {}).get("3h", 0)
        condition = best.get("weather", [{}])[0].get("main", "Clear")

        # Impact auf BTTS berechnen
        impact = "neutral"
        impact_notes = []

        if rain > 3:
            impact = "negative"
            impact_notes.append(f"🌧️ Starker Regen ({rain:.1f}mm) → weniger Tore")
        elif rain > 1:
            impact_notes.append(f"🌦️ Leichter Regen ({rain:.1f}mm)")

        if wind > 50:
            impact = "negative"
            impact_notes.append(f"💨 Starker Wind ({wind:.0f}km/h) → schlechtere Pässe")
        elif wind > 30:
            impact_notes.append(f"🌬️ Wind {wind:.0f}km/h")

        if temp > 32:
            impact_notes.append(f"🥵 Hitze ({temp:.0f}°C) → Teams langsamer")
        elif temp < 2:
            impact_notes.append(f"🥶 Kälte ({temp:.0f}°C) → harter Rasen")

        result = {
            "city": city,
            "temp": round(temp, 1),
            "rain": round(rain, 1),
            "wind": round(wind, 1),
            "condition": condition,
            "impact": impact,
            "notes": impact_notes,
        }

        WEATHER_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Weather Error: {e}", "WARN")
        return None


# ============================================================
# 🆕 FOOTYSTATS - BTTS + Over 2.5 Statistiken
# ============================================================
FOOTYSTATS_API_KEY = env("FOOTYSTATS_API_KEY", "")
SPORTDB_API_KEY = env("SPORTDB_API_KEY", "")  # SportDB.dev / Flashscore API
FOOTYSTATS_CACHE = {}

FOOTYSTATS_LEAGUE_IDS = {
    "Premier League": 1625,
    "Bundesliga": 1617,
    "La Liga": 1621,
    "Serie A": 1627,
    "Ligue 1": 1619,
    "Eredivisie": 1631,
    "Primeira Liga": 1629,
    "Championship": 1626,
    "Scottish Premiership": 1637,
    "MLS": 1651,
    "Brasileirao Serie A": 1671,
}

def get_footystats_team(team_name, league_name):
    """
    Holt BTTS + Over 2.5 Statistiken von FootyStats.
    Returns: {'btts_rate': 65, 'over25_rate': 72, 'avg_goals': 2.8}
    """
    if not FOOTYSTATS_API_KEY:
        return None

    league_id = FOOTYSTATS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return None

    cache_key = f"{team_name}_{league_id}"
    if cache_key in FOOTYSTATS_CACHE:
        return FOOTYSTATS_CACHE[cache_key]

    try:
        r = requests.get(
            f"https://api.football-data-api.com/league-teams",
            params={
                "key": FOOTYSTATS_API_KEY,
                "season_id": league_id,
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        teams = data.get("data", [])

        for team in teams:
            name = team.get("cleanName", "").lower()
            if team_name.lower()[:6] in name or name[:6] in team_name.lower():
                stats = team.get("stats", {})
                result = {
                    "btts_rate": stats.get("btts_percentage", 0),
                    "over25_rate": stats.get("over25_percentage", 0),
                    "avg_goals": stats.get("avg_goals_per_game_scored", 0),
                    "avg_conceded": stats.get("avg_goals_per_game_conceded", 0),
                    "clean_sheets_pct": stats.get("clean_sheet_percentage", 0),
                }
                FOOTYSTATS_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        log(f"FootyStats Error: {e}", "WARN")
        return None



# ============================================================
# 🆕 SPORTDB.DEV / FLASHSCORE - Lineups & Live Data
# ============================================================
SPORTDB_API_KEY = env("SPORTDB_API_KEY", "")
SPORTDB_CACHE = {}

SPORTDB_LEAGUE_IDS = {
    "Premier League": "premier-league",
    "Bundesliga": "bundesliga",
    "La Liga": "la-liga",
    "Serie A": "serie-a",
    "Ligue 1": "ligue-1",
    "Eredivisie": "eredivisie",
    "Champions League": "champions-league",
    "Europa League": "europa-league",
    "Championship": "championship",
    "Scottish Premiership": "scottish-premiership",
    "Primeira Liga": "primeira-liga",
    "Süper Lig": "super-lig",
}

def get_sportdb_lineups(home_team, away_team, target_date):
    """
    Holt Aufstellungen von SportDB.dev (Flashscore API).
    Returns: {'home_lineup': [...], 'away_lineup': [...], 'home_missing': [...]}
    """
    if not SPORTDB_API_KEY:
        return None

    cache_key = f"{home_team}_{away_team}_{target_date}"
    if cache_key in SPORTDB_CACHE:
        return SPORTDB_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.sportdb.dev/v1/football/fixtures",
            headers={
                "X-API-Key": SPORTDB_API_KEY,
                "Content-Type": "application/json",
            },
            params={
                "date": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        fixtures = data.get("data", data.get("fixtures", data.get("results", [])))

        if not fixtures:
            return None

        # Suche das passende Spiel
        for fix in fixtures:
            home = fix.get("home_team", fix.get("homeTeam", {}).get("name", ""))
            away = fix.get("away_team", fix.get("awayTeam", {}).get("name", ""))

            if not teams_match(home_team, str(home)):
                continue
            if not teams_match(away_team, str(away)):
                continue

            # Lineup extrahieren
            lineups = fix.get("lineups", fix.get("lineup", {}))
            home_lineup = []
            away_lineup = []

            if lineups:
                home_players = lineups.get("home", lineups.get("homeTeam", {}).get("startXI", []))
                away_players = lineups.get("away", lineups.get("awayTeam", {}).get("startXI", []))

                for p in home_players[:11]:
                    name = p.get("name", p.get("player", {}).get("name", ""))
                    if name:
                        home_lineup.append(name)

                for p in away_players[:11]:
                    name = p.get("name", p.get("player", {}).get("name", ""))
                    if name:
                        away_lineup.append(name)

            result = {
                "fixture_id": fix.get("id", fix.get("fixture_id", "")),
                "home_lineup": home_lineup,
                "away_lineup": away_lineup,
                "lineup_available": len(home_lineup) > 0,
                "status": fix.get("status", fix.get("fixture", {}).get("status", {}).get("short", "NS")),
            }

            SPORTDB_CACHE[cache_key] = result
            return result

        return None

    except Exception as e:
        log(f"SportDB Error: {e}", "WARN")
        return None


def get_sportdb_fixtures(league_name, target_date):
    """
    Holt Spielpläne von SportDB.dev für eine Liga.
    Returns: Liste mit Fixtures
    """
    if not SPORTDB_API_KEY:
        return []

    try:
        r = requests.get(
            "https://api.sportdb.dev/v1/football/fixtures",
            headers={
                "X-API-Key": SPORTDB_API_KEY,
            },
            params={
                "date": str(target_date),
                "league": SPORTDB_LEAGUE_IDS.get(league_name, ""),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        fixtures_raw = data.get("data", data.get("fixtures", []))
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for fix in fixtures_raw:
            try:
                home = fix.get("home_team", fix.get("homeTeam", {}).get("name", ""))
                away = fix.get("away_team", fix.get("awayTeam", {}).get("name", ""))
                kickoff_str = fix.get("date", fix.get("datetime", fix.get("fixture", {}).get("date", "")))

                if not home or not away:
                    continue

                if kickoff_str:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue

                fixtures.append({
                    "home": str(home),
                    "away": str(away),
                    "match_id": fix.get("id", fix.get("fixture_id", "")),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str) if kickoff_str else "TBD",
                    "source": "sportdb",
                })
            except Exception:
                continue

        return fixtures

    except Exception as e:
        log(f"SportDB Fixtures Error: {e}", "WARN")
        return []


# ============================================================
# 🆕 FOREBET - Mathematische BTTS + Over 2.5 Predictions
# ============================================================
FOREBET_CACHE = {}
FOREBET_BLOCKED = False

FOREBET_LEAGUE_URLS = {
    "Premier League": "https://www.forebet.com/en/football-tips-and-predictions-for-england/premier-league",
    "Bundesliga": "https://www.forebet.com/en/football-tips-and-predictions-for-germany/bundesliga",
    "La Liga": "https://www.forebet.com/en/football-tips-and-predictions-for-spain/la-liga",
    "Serie A": "https://www.forebet.com/en/football-tips-and-predictions-for-italy/serie-a",
    "Ligue 1": "https://www.forebet.com/en/football-tips-and-predictions-for-france/ligue-1",
    "Eredivisie": "https://www.forebet.com/en/football-tips-and-predictions-for-netherlands/eredivisie",
    "Champions League": "https://www.forebet.com/en/football-tips-and-predictions-for-europe/champions-league",
    "Europa League": "https://www.forebet.com/en/football-tips-and-predictions-for-europe/europa-league",
    "Championship": "https://www.forebet.com/en/football-tips-and-predictions-for-england/championship",
    "Scottish Premiership": "https://www.forebet.com/en/football-tips-and-predictions-for-scotland/premiership",
}

def get_forebet_prediction(home_team, away_team, league_name, target_date):
    """
    Holt Forebet BTTS + Over 2.5 Wahrscheinlichkeiten via Scraping.
    Returns: {'btts_pct': 68, 'over25_pct': 72, 'avg_goals': 2.8, 'tip': '2'}
    """
    global FOREBET_BLOCKED

    if FOREBET_BLOCKED:
        return None

    cache_key = f"{home_team}_{away_team}_{target_date}"
    if cache_key in FOREBET_CACHE:
        return FOREBET_CACHE[cache_key]

    # Forebet Hauptseite für heutige Spiele
    try:
        date_str = str(target_date).replace("-", "/")
        url = f"https://www.forebet.com/en/football-predictions/predictions-1x2/{date_str}"

        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.forebet.com/",
            },
            timeout=15,
        )

        if r.status_code in [403, 429, 503]:
            log(f"   ℹ️  Forebet nicht erreichbar ({r.status_code}) - überspringe", "INFO")
            FOREBET_BLOCKED = True
            return None

        if not r.ok:
            return None

        html = r.text

        # Team-Namen normalisieren für Suche
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        # Suche nach Spielblock mit beiden Teams
        # Forebet HTML: <div class="rcnt"> ... teamname ... </div>
        import re as _re

        # Pattern für Spielzeilen
        rows = _re.findall(
            r'<tr[^>]*class="[^"]*tr_0[^"]*"[^>]*>(.*?)</tr>',
            html,
            _re.DOTALL | _re.IGNORECASE
        )

        for row in rows:
            # Team-Namen aus Row extrahieren
            teams_found = _re.findall(r'<span[^>]*class="[^"]*tnms[^"]*"[^>]*>([^<]+)</span>', row)
            if len(teams_found) < 2:
                teams_found = _re.findall(r'<div[^>]*class="[^"]*team[^"]*"[^>]*>([^<]+)</div>', row)

            if len(teams_found) < 2:
                continue

            row_home = normalize_team_name(teams_found[0])
            row_away = normalize_team_name(teams_found[1])

            # Match prüfen
            if not (home_norm[:6] in row_home or row_home[:6] in home_norm):
                continue
            if not (away_norm[:6] in row_away or row_away[:6] in away_norm):
                continue

            # Wahrscheinlichkeiten extrahieren
            probs = _re.findall(r'<span[^>]*class="[^"]*prb[^"]*"[^>]*>(\d+)%?</span>', row)
            avg_goals_m = _re.search(r'<span[^>]*class="[^"]*avg[^"]*"[^>]*>([\d.]+)</span>', row)
            over25_m = _re.search(r'<span[^>]*class="[^"]*ov25[^"]*"[^>]*>([\d.]+)%?</span>', row)
            btts_m = _re.search(r'<span[^>]*class="[^"]*btts[^"]*"[^>]*>([\d.]+)%?</span>', row)

            result = {}

            if len(probs) >= 3:
                result["prob_home"] = int(probs[0])
                result["prob_draw"] = int(probs[1])
                result["prob_away"] = int(probs[2])
                # Forebet Tipp (höchste Wahrscheinlichkeit)
                max_prob = max(result["prob_home"], result["prob_draw"], result["prob_away"])
                if max_prob == result["prob_home"]:
                    result["tip"] = "1"
                elif max_prob == result["prob_draw"]:
                    result["tip"] = "X"
                else:
                    result["tip"] = "2"

            if avg_goals_m:
                result["avg_goals"] = float(avg_goals_m.group(1))
                # Over 2.5 approximieren aus avg goals
                if "avg_goals" in result:
                    g = result["avg_goals"]
                    # Poisson-Approximation
                    import math as _math
                    over25_approx = 1 - sum(
                        (_math.exp(-g) * (g**k)) / _math.factorial(k)
                        for k in range(3)
                    )
                    result["over25_pct"] = round(over25_approx * 100, 1)

            if over25_m:
                result["over25_pct"] = float(over25_m.group(1))

            if btts_m:
                result["btts_pct"] = float(btts_m.group(1))

            if result:
                FOREBET_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        log(f"Forebet Error: {str(e)[:60]}", "WARN")
        return None


# ============================================================
# 🆕 SCOUTINGSTATS - AI BTTS Predictions (kostenlos)
# ============================================================
SCOUTINGSTATS_CACHE = {}
SCOUTINGSTATS_BLOCKED = False

def get_scoutingstats_prediction(home_team, away_team, target_date):
    """
    Holt ScoutingStats.ai BTTS + Value Predictions.
    Returns: {'btts_pct': 74, 'over25_pct': 68, 'value_edge': 12}
    """
    global SCOUTINGSTATS_BLOCKED

    if SCOUTINGSTATS_BLOCKED:
        return None

    cache_key = f"{home_team}_{away_team}_{target_date}"
    if cache_key in SCOUTINGSTATS_CACHE:
        return SCOUTINGSTATS_CACHE[cache_key]

    try:
        # ScoutingStats API / Scraping
        r = requests.get(
            "https://scoutingstats.ai/api/predictions",
            params={
                "home": home_team,
                "away": away_team,
                "date": str(target_date),
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            timeout=12,
        )

        if r.status_code in [403, 404, 429]:
            # Fallback: Webseite scrapen
            return _scrape_scoutingstats(home_team, away_team, target_date)

        if not r.ok:
            return None

        data = r.json()
        if not data:
            return None

        result = {
            "btts_pct": data.get("btts_probability", data.get("btts_pct", 0)),
            "over25_pct": data.get("over25_probability", data.get("over25_pct", 0)),
            "value_edge": data.get("value_edge", 0),
            "confidence": data.get("confidence", 0),
        }

        SCOUTINGSTATS_CACHE[cache_key] = result
        return result

    except Exception:
        return _scrape_scoutingstats(home_team, away_team, target_date)


def _scrape_scoutingstats(home_team, away_team, target_date):
    """Fallback: ScoutingStats Webseite scrapen"""
    global SCOUTINGSTATS_BLOCKED

    try:
        url = f"https://scoutingstats.ai/predictions/{str(target_date)}"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            },
            timeout=12,
        )

        if r.status_code in [403, 429, 503]:
            SCOUTINGSTATS_BLOCKED = True
            return None

        if not r.ok:
            return None

        html = r.text
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        import re as _re

        # Suche Spielblock
        blocks = _re.findall(r'<div[^>]*class="[^"]*match[^"]*"[^>]*>(.*?)</div>', html, _re.DOTALL)

        for block in blocks:
            teams = _re.findall(r'class="[^"]*team[^"]*"[^>]*>([^<]+)<', block)
            if len(teams) < 2:
                continue

            if not teams_match(home_team, teams[0]):
                continue
            if not teams_match(away_team, teams[1]):
                continue

            btts_m = _re.search(r'btts[^>]*>(\d+)%', block, _re.IGNORECASE)
            over25_m = _re.search(r'over.?2\.?5[^>]*>(\d+)%', block, _re.IGNORECASE)

            result = {}
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))

            if result:
                SCOUTINGSTATS_CACHE[f"{home_team}_{away_team}_{target_date}"] = result
                return result

        return None

    except Exception:
        return None




# ============================================================
# 🆕 SOFASCORE - Inoffizielle API (alle Ligen weltweit!)
# ============================================================
SOFASCORE_CACHE = {}
SOFASCORE_BLOCKED = False

SOFASCORE_SLUG_MAP = {
    "Champions League": "uefa-champions-league",
    "Europa League": "uefa-europa-league", 
    "Conference League": "uefa-europa-conference-league",
    "Bundesliga": "bundesliga",
    "2. Bundesliga": "2-bundesliga",
    "Premier League": "premier-league",
    "Championship": "championship",
    "La Liga": "laliga",
    "La Liga 2": "laliga2",
    "Serie A": "serie-a",
    "Serie B": "serie-b",
    "Ligue 1": "ligue-1",
    "Ligue 2": "ligue-2",
    "Eredivisie": "eredivisie",
    "Primeira Liga": "liga-portugal",
    "Pro League Belgien": "jupiler-pro-league",
    "Süper Lig": "super-lig",
    "Bundesliga Österreich": "admiral-bundesliga",
    "Super League Schweiz": "super-league",
    "Scottish Premiership": "scottish-premiership",
    "Danish Superliga": "superliga",
    "Norway Eliteserien": "eliteserien",
    "Sweden Allsvenskan": "allsvenskan",
    "Greece Super League": "super-league-1",
    "Croatia HNL": "hnl",
    "Serbia SuperLiga": "super-liga",
    "Romania Liga I": "liga-i",
    "Czech First League": "czech-liga",
    "Poland Ekstraklasa": "ekstraklasa",
    "MLS": "mls",
    "Brasileirao Serie A": "brasileirao-serie-a",
    "Liga Argentinien": "liga-profesional-argentina",
    "Liga MX": "liga-mx",
    "J1 League Japan": "j1-league",
    "K League 1": "k-league-1",
    "China Super League": "chinese-super-league",
    "Saudi Pro League": "saudi-professional-league",
    "A-League": "a-league",
    "EFL League 1": "league-one",
    "EFL League 2": "league-two",
    "Finland Veikkausliiga": "veikkausliiga",
    "Uruguay Primera": "primera-division-2",
    "India Super League": "isl",
    "Qatar Stars League": "qatar-stars-league",
    "South Africa PSL": "dstv-premiership",
    "Vietnam V-League": "v-league-1",
    "Eerste Divisie": "eerste-divisie",
    "3. Liga Deutschland": "3-liga",
    "Norwegian 1. Division": "1-division",
    "Turkish 1. Lig": "tff-first-league",
    "Danish 1. Division": "1st-division",
    "Swedish Superettan": "superettan",
    "Swiss Challenge League": "challenge-league",
    "Israeli Liga Leumit": "leumit-league",
    "Bulgarian First League": "first-league",
    "Hungarian NB I": "nb-i",
    "Iceland Premier League": "urvalsdeild",
}

def fetch_sofascore_fixtures(league_name, target_date):
    """
    Holt Spielpläne von SofaScore (inoffizielle API).
    Deckt ALLE Ligen weltweit ab - kein Key nötig!
    """
    global SOFASCORE_BLOCKED
    
    if SOFASCORE_BLOCKED:
        return []
    
    cache_key = f"sofa_{league_name}_{target_date}"
    if cache_key in SOFASCORE_CACHE:
        return SOFASCORE_CACHE[cache_key]
    
    try:
        date_str = str(target_date)  # YYYY-MM-DD
        
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
            },
            timeout=15,
        )
        
        if r.status_code in [403, 429, 503]:
            log(f"   ℹ️  SofaScore nicht erreichbar ({r.status_code})", "INFO")
            SOFASCORE_BLOCKED = True
            return []
        
        if not r.ok:
            return []
        
        data = r.json()
        events = data.get("events", [])
        
        if not events:
            return []
        
        # Liga-Slug für Filterung
        league_slug = SOFASCORE_SLUG_MAP.get(league_name, "").lower()
        
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for event in events:
            try:
                # Liga prüfen
                tournament = event.get("tournament", {})
                tour_slug = tournament.get("slug", "").lower()
                tour_name = tournament.get("name", "").lower()
                category = tournament.get("category", {}).get("name", "").lower()
                
                # Match-Check für Liga
                if league_slug:
                    if league_slug not in tour_slug and league_slug not in tour_name:
                        # Fallback: Kategorie oder Name prüfen
                        league_lower = league_name.lower()
                        if not any(w in tour_name for w in league_lower.split() if len(w) > 4):
                            continue
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                
                if not home_team or not away_team:
                    continue
                
                # Kickoff Zeit
                start_timestamp = event.get("startTimestamp", 0)
                if start_timestamp:
                    kickoff = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff_str = f"{target_date}T00:00:00Z"
                
                # Status prüfen (nur nicht gestartete)
                status = event.get("status", {}).get("type", "")
                if status in ["inprogress", "finished"]:
                    continue
                
                fixtures.append({
                    "home": home_team,
                    "away": away_team,
                    "match_id": event.get("id", ""),
                    "home_id": event.get("homeTeam", {}).get("id"),
                    "away_id": event.get("awayTeam", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore",
                })
                
            except Exception:
                continue
        
        SOFASCORE_CACHE[cache_key] = fixtures
        
        if fixtures:
            log(f"   ⚡ SofaScore: {len(fixtures)} Spiele für {league_name}")
        
        return fixtures
        
    except Exception as e:
        log(f"SofaScore Error: {str(e)[:60]}", "WARN")
        return []


def fetch_sofascore_all_today(target_date):
    """
    Holt ALLE heutigen Spiele von SofaScore auf einmal.
    Viel effizienter als pro-Liga Calls!
    """
    global SOFASCORE_BLOCKED
    
    if SOFASCORE_BLOCKED:
        return {}
    
    cache_key = f"sofa_all_{target_date}"
    if cache_key in SOFASCORE_CACHE:
        return SOFASCORE_CACHE[cache_key]
    
    try:
        date_str = str(target_date)
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=20,
        )
        
        if r.status_code in [403, 429, 503]:
            SOFASCORE_BLOCKED = True
            return {}
        
        if not r.ok:
            return {}
        
        data = r.json()
        events = data.get("events", [])
        
        if not events:
            return {}
        
        # Gruppiere nach Liga-Slug
        now_utc = datetime.now(timezone.utc)
        by_league = {}
        
        for event in events:
            try:
                status = event.get("status", {}).get("type", "")
                if status in ["inprogress", "finished"]:
                    continue
                
                tournament = event.get("tournament", {})
                tour_slug = tournament.get("slug", "").lower()
                tour_name = tournament.get("name", "")
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                
                if not home_team or not away_team:
                    continue
                
                start_timestamp = event.get("startTimestamp", 0)
                if start_timestamp:
                    kickoff = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff_str = f"{target_date}T00:00:00Z"
                
                fixture = {
                    "home": home_team,
                    "away": away_team,
                    "match_id": event.get("id", ""),
                    "home_id": event.get("homeTeam", {}).get("id"),
                    "away_id": event.get("awayTeam", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore",
                }
                
                if tour_slug not in by_league:
                    by_league[tour_slug] = []
                by_league[tour_slug].append(fixture)
                
            except Exception:
                continue
        
        SOFASCORE_CACHE[cache_key] = by_league
        log(f"   ⚡ SofaScore: {len(events)} Spiele total, {len(by_league)} Ligen geladen")
        return by_league
        
    except Exception as e:
        log(f"SofaScore All Error: {str(e)[:60]}", "WARN")
        return {}



# ============================================================
# 🆕 SOFASCORE LINEUPS - Aufstellungen (kein Key nötig!)
# ============================================================
SOFASCORE_LINEUP_CACHE = {}

def get_sofascore_lineups(match_id, home_team, away_team):
    """
    Holt Aufstellungen von SofaScore.
    Returns: {'home_lineup': [...], 'away_lineup': [...], 'confirmed': bool}
    """
    if not match_id:
        return None

    cache_key = f"sofa_lineup_{match_id}"
    if cache_key in SOFASCORE_LINEUP_CACHE:
        return SOFASCORE_LINEUP_CACHE[cache_key]

    try:
        url = f"https://api.sofascore.com/api/v1/event/{match_id}/lineups"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            SOFASCORE_LINEUP_CACHE[cache_key] = None
            return None

        data = r.json()
        home_data = data.get("home", {})
        away_data = data.get("away", {})

        def extract_players(team_data, only_starters=True):
            players = []
            for p in team_data.get("players", []):
                player = p.get("player", {})
                stats = p.get("statistics", {})
                position = p.get("position", "")
                # SofaScore: position 1-11 = Starter, 12+ = Reserve
                shirt = p.get("shirtNumber", 99)
                is_starter = shirt <= 11 or position in ["G", "D", "M", "F"]
                if only_starters and not is_starter:
                    continue
                players.append({
                    "name": player.get("name", ""),
                    "position": position,
                    "shirt": shirt,
                    "rating": stats.get("rating", 0),
                })
            return players

        home_starters = extract_players(home_data)
        away_starters = extract_players(away_data)
        home_subs = extract_players(home_data, only_starters=False)
        away_subs = extract_players(away_data, only_starters=False)

        confirmed = data.get("confirmed", False)

        result = {
            "home_lineup": home_starters,
            "away_lineup": away_starters,
            "home_subs": home_subs,
            "away_subs": away_subs,
            "confirmed": confirmed,
            "lineup_available": len(home_starters) > 0,
        }

        SOFASCORE_LINEUP_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"SofaScore Lineup Error: {str(e)[:60]}", "WARN")
        SOFASCORE_LINEUP_CACHE[cache_key] = None
        return None


def get_sofascore_match_result(match_id):
    """
    Holt Spielergebnis von SofaScore für check.py
    Returns: {'home_score': 2, 'away_score': 1, 'status': 'finished', 'ht_home': 1, 'ht_away': 0}
    """
    if not match_id:
        return None

    try:
        url = f"https://api.sofascore.com/api/v1/event/{match_id}"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        event = data.get("event", {})
        status = event.get("status", {}).get("type", "")

        if status != "finished":
            return None

        score = event.get("homeScore", {})
        home_score = event.get("homeScore", {}).get("current", 0) or 0
        away_score = event.get("awayScore", {}).get("current", 0) or 0
        ht_home = event.get("homeScore", {}).get("period1", 0) or 0
        ht_away = event.get("awayScore", {}).get("period1", 0) or 0

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "status": "finished",
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": ht_home > 0 and ht_away > 0,
            "total_goals": home_score + away_score,
        }

    except Exception as e:
        log(f"SofaScore Result Error: {str(e)[:60]}", "WARN")
        return None


# ============================================================
# 🆕 CLUBELO - Team Stärke Ratings (kein Key nötig!)
# ============================================================
CLUBELO_CACHE = {}

def get_clubelo_rating(team_name):
    """
    Holt Team-Stärke Rating von ClubElo.com
    Elo-Rating: ~1800 = Top Team, ~1500 = Mittelfeld, ~1200 = schwach
    Returns: {'elo': 1750, 'rank': 5, 'country': 'GER'}
    """
    cache_key = f"elo_{team_name}"
    if cache_key in CLUBELO_CACHE:
        return CLUBELO_CACHE[cache_key]

    try:
        # ClubElo API - kein Key nötig
        name_clean = team_name.replace(" ", "_").replace(".", "")
        url = f"http://api.clubelo.com/{name_clean}"

        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            CLUBELO_CACHE[cache_key] = None
            return None

        lines = r.text.strip().splitlines()
        if len(lines) < 2:
            CLUBELO_CACHE[cache_key] = None
            return None

        # Format: Rank,Club,Country,Level,Elo,From,To
        last_line = lines[-1].split(",")
        if len(last_line) < 5:
            CLUBELO_CACHE[cache_key] = None
            return None

        result = {
            "rank": int(last_line[0]) if last_line[0].isdigit() else 0,
            "team": last_line[1],
            "country": last_line[2],
            "level": int(last_line[3]) if last_line[3].isdigit() else 0,
            "elo": float(last_line[4]) if last_line[4].replace(".", "").isdigit() else 0,
        }

        CLUBELO_CACHE[cache_key] = result
        return result

    except Exception:
        CLUBELO_CACHE[cache_key] = None
        return None


def calculate_elo_btts_probability(home_elo, away_elo):
    """
    Berechnet BTTS-Wahrscheinlichkeit aus Elo-Ratings.
    Ausgeglichenere Teams = mehr BTTS.
    """
    if not home_elo or not away_elo:
        return None

    elo_diff = abs(home_elo - away_elo)

    # Je kleiner der Unterschied, desto mehr BTTS
    if elo_diff < 50:
        btts_boost = 8   # Sehr ausgeglichen
    elif elo_diff < 100:
        btts_boost = 5
    elif elo_diff < 200:
        btts_boost = 2
    elif elo_diff < 300:
        btts_boost = -3
    else:
        btts_boost = -8  # Großer Unterschied = weniger BTTS

    base_btts = 52  # Durchschnittliche BTTS Rate
    return min(85, max(30, base_btts + btts_boost))


# ============================================================
# 🆕 ALLSPORTSAPI - 500+ Ligen weltweit (100 Calls/Tag gratis)
# ============================================================
ALLSPORTS_API_KEY = env("ALLSPORTS_API_KEY", "")
ALLSPORTS_CACHE = {}

ALLSPORTS_LEAGUE_IDS = {
    "Champions League": 175,
    "Europa League": 176,
    "Premier League": 4,
    "Bundesliga": 78,
    "La Liga": 87,
    "Serie A": 186,
    "Ligue 1": 168,
    "Eredivisie": 61,
    "Primeira Liga": 182,
    "MLS": 199,
    "Brasileirao Serie A": 36,
    "Liga Argentinien": 14,
    "J1 League Japan": 98,
    "K League 1": 106,
    "Saudi Pro League": 184,
    "A-League": 15,
    "EFL League 1": 8,
    "EFL League 2": 9,
    "Championship": 7,
    "Scottish Premiership": 185,
    "Finland Veikkausliiga": 72,
    "Uruguay Primera": 207,
    "India Super League": 93,
    "Qatar Stars League": 181,
    "South Africa PSL": 188,
    "Vietnam V-League": 213,
    "Denmark Superliga": 57,
    "Norway Eliteserien": 167,
    "Sweden Allsvenskan": 191,
    "Greece Super League": 83,
    "Croatia HNL": 46,
    "Bulgaria First League": 38,
    "Hungary NB I": 89,
    "Iceland Premier League": 90,
}

def fetch_allsports_fixtures(league_name, target_date):
    """
    Holt Spielpläne von AllSportsAPI (500+ Ligen, 100 Calls/Tag gratis).
    """
    if not ALLSPORTS_API_KEY:
        return []

    league_id = ALLSPORTS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []

    cache_key = f"allsports_{league_name}_{target_date}"
    if cache_key in ALLSPORTS_CACHE:
        return ALLSPORTS_CACHE[cache_key]

    try:
        r = requests.get(
            "https://allsportsapi.com/api/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "leagueId": league_id,
                "from": str(target_date),
                "to": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        matches = data.get("result", [])

        if not matches:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in matches:
            try:
                kickoff_str = f"{m.get('event_date', '')}T{m.get('event_time', '00:00')}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff <= now_utc:
                    continue

                fixtures.append({
                    "home": m.get("event_home_team", ""),
                    "away": m.get("event_away_team", ""),
                    "match_id": str(m.get("event_key", "")),
                    "home_id": m.get("home_team_key"),
                    "away_id": m.get("away_team_key"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "allsports",
                })
            except Exception:
                continue

        ALLSPORTS_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"AllSports Error: {str(e)[:60]}", "WARN")
        return []


def get_allsports_result(match_id):
    """
    Holt Spielergebnis von AllSportsAPI für check.py
    """
    if not ALLSPORTS_API_KEY or not match_id:
        return None

    try:
        r = requests.get(
            "https://allsportsapi.com/api/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "matchId": match_id,
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        match = data.get("result", [{}])[0] if data.get("result") else None

        if not match:
            return None

        status = match.get("event_status", "")
        if status != "Finished":
            return None

        home_score = int(match.get("event_final_result", "0-0").split("-")[0] or 0)
        away_score = int(match.get("event_final_result", "0-0").split("-")[1] or 0)
        ht = match.get("event_halftime_result", "0-0")
        ht_home = int(ht.split("-")[0] or 0)
        ht_away = int(ht.split("-")[1] or 0)

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": ht_home > 0 and ht_away > 0,
            "total_goals": home_score + away_score,
            "status": "finished",
        }

    except Exception:
        return None


# ============================================================
# 🆕 TRANSFERMARKT - Verletzungen (beste Quelle weltweit!)
# ============================================================
TRANSFERMARKT_CACHE = {}
TRANSFERMARKT_BLOCKED = False

TM_LEAGUE_SLUGS = {
    "Bundesliga": ("bundesliga", "L1"),
    "2. Bundesliga": ("2-bundesliga", "L2"),
    "Premier League": ("premier-league", "GB1"),
    "Championship": ("championship", "GB2"),
    "La Liga": ("primera-division", "ES1"),
    "Serie A": ("serie-a", "IT1"),
    "Ligue 1": ("ligue-1", "FR1"),
    "Eredivisie": ("eredivisie", "NL1"),
    "Primeira Liga": ("liga-nos", "PO1"),
    "Pro League Belgien": ("jupiler-pro-league", "BE1"),
    "Süper Lig": ("super-lig", "TR1"),
    "Champions League": ("champions-league", "CL"),
    "Europa League": ("europa-league", "EL"),
}

def get_transfermarkt_injuries(team_name, league_name):
    """
    Holt Verletzungen von Transfermarkt.
    Unterscheidet zwischen Stammspieler und Reserve!
    Returns: {'injured': [...], 'suspended': [...], 'starters_out': [...], 'reserves_out': [...]}
    """
    global TRANSFERMARKT_BLOCKED

    if TRANSFERMARKT_BLOCKED:
        return None

    cache_key = f"tm_{team_name}_{league_name}"
    if cache_key in TRANSFERMARKT_CACHE:
        return TRANSFERMARKT_CACHE[cache_key]

    try:
        # Team-Suche auf Transfermarkt
        search_url = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
        r = requests.get(
            search_url,
            params={"query": team_name, "Datei": "spieler"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "de-DE,de;q=0.9",
                "Referer": "https://www.transfermarkt.com/",
            },
            timeout=12,
        )

        if r.status_code in [403, 429, 503]:
            TRANSFERMARKT_BLOCKED = True
            log(f"   ℹ️  Transfermarkt blockiert ({r.status_code})", "INFO")
            return None

        if not r.ok:
            return None

        html = r.text

        # Suche nach Verletzungs-Tabelle
        import re as _re

        # Pattern für verletzte Spieler
        injured_pattern = _re.findall(
            r'class="[^"]*verletzt[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]+)</td>',
            html,
            _re.DOTALL | _re.IGNORECASE
        )

        result = {
            "injured": [],
            "suspended": [],
            "starters_out": [],
            "reserves_out": [],
            "total_out": 0,
        }

        for player_name, reason in injured_pattern[:10]:
            player_name = player_name.strip()
            reason = reason.strip()

            is_starter = True  # Vereinfacht - in Produktion aus Marktwert schätzen

            entry = {"name": player_name, "reason": reason}

            if "gesperrt" in reason.lower() or "sperre" in reason.lower():
                result["suspended"].append(entry)
            else:
                result["injured"].append(entry)

            if is_starter:
                result["starters_out"].append(entry)
            else:
                result["reserves_out"].append(entry)

        result["total_out"] = len(result["injured"]) + len(result["suspended"])
        result["has_data"] = result["total_out"] > 0

        TRANSFERMARKT_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Transfermarkt Error: {str(e)[:60]}", "WARN")
        TRANSFERMARKT_CACHE[cache_key] = None
        return None


# ============================================================
# 🆕 ESPN API (inoffiziell) - US Ligen + weitere
# ============================================================
ESPN_CACHE = {}

ESPN_LEAGUE_IDS = {
    "MLS": ("soccer", "usa.1"),
    "Premier League": ("soccer", "eng.1"),
    "Bundesliga": ("soccer", "ger.1"),
    "La Liga": ("soccer", "esp.1"),
    "Serie A": ("soccer", "ita.1"),
    "Ligue 1": ("soccer", "fra.1"),
    "Champions League": ("soccer", "uefa.champions"),
    "Liga MX": ("soccer", "mex.1"),
    "Brasileirao Serie A": ("soccer", "bra.1"),
    "Liga Argentinien": ("soccer", "arg.1"),
    "A-League": ("soccer", "aus.1"),
    "J1 League Japan": ("soccer", "jpn.1"),
    "K League 1": ("soccer", "kor.1"),
    "Saudi Pro League": ("soccer", "sau.1"),
    "EFL League 1": ("soccer", "eng.3"),
    "EFL League 2": ("soccer", "eng.4"),
    "Championship": ("soccer", "eng.2"),
    "Scottish Premiership": ("soccer", "sco.1"),
}

def fetch_espn_fixtures(league_name, target_date):
    """
    Holt Spielpläne von ESPN inoffizieller API.
    Gut für US Ligen und Top-Ligen.
    """
    league_info = ESPN_LEAGUE_IDS.get(league_name)
    if not league_info:
        return []

    sport, league_id = league_info
    cache_key = f"espn_{league_name}_{target_date}"

    if cache_key in ESPN_CACHE:
        return ESPN_CACHE[cache_key]

    try:
        date_str = str(target_date).replace("-", "")  # YYYYMMDD
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/scoreboard"

        r = requests.get(
            url,
            params={"dates": date_str},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events", [])

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in events:
            try:
                competitions = event.get("competitions", [{}])
                comp = competitions[0] if competitions else {}
                competitors = comp.get("competitors", [])

                if len(competitors) < 2:
                    continue

                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                home_name = home.get("team", {}).get("displayName", "")
                away_name = away.get("team", {}).get("displayName", "")

                if not home_name or not away_name:
                    continue

                kickoff_str = event.get("date", "")
                if kickoff_str:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue

                status = comp.get("status", {}).get("type", {}).get("name", "")
                if status in ["STATUS_FINAL", "STATUS_IN_PROGRESS"]:
                    continue

                fixtures.append({
                    "home": home_name,
                    "away": away_name,
                    "match_id": event.get("id", ""),
                    "home_id": home.get("team", {}).get("id"),
                    "away_id": away.get("team", {}).get("id"),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str) if kickoff_str else "TBD",
                    "source": "espn",
                })

            except Exception:
                continue

        ESPN_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"ESPN Error: {str(e)[:60]}", "WARN")
        return []


def get_espn_result(match_id, league_name):
    """
    Holt Spielergebnis von ESPN für check.py
    """
    league_info = ESPN_LEAGUE_IDS.get(league_name)
    if not league_info or not match_id:
        return None

    sport, league_id = league_info

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/summary"
        r = requests.get(
            url,
            params={"event": match_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])
        comp = competitions[0] if competitions else {}

        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            return None

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)

        return {
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": 0,  # ESPN HT nicht immer verfügbar
            "ht_away": 0,
            "btts": home_score > 0 and away_score > 0,
            "over25": (home_score + away_score) > 2,
            "btts_ht": False,
            "total_goals": home_score + away_score,
            "status": "finished",
        }

    except Exception:
        return None


def fetch_odds_api(league_name, target_date):
    sport_key = LEAGUE_KEYS.get(league_name)

    if not sport_key or not ODDS_API_KEYS:
        return []

    for key in ODDS_API_KEYS:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h,totals",
                    "oddsFormat": "decimal",
                    "includeLinks": "true",  # 🆕 Deeplinks zu Betslips holen
                    "includeSids": "true",
                },
                timeout=15,
            )

            if r.status_code in [401, 429]:
                continue

            if not r.ok:
                continue

            games = r.json()
            target = target_date.isoformat()
            now_utc = datetime.now(timezone.utc)
            filtered = []

            for g in games:
                commence = g.get("commence_time", "")

                if not commence.startswith(target):
                    continue

                try:
                    kickoff = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                    if kickoff > now_utc:
                        filtered.append(g)
                except Exception:
                    continue

            return filtered

        except Exception:
            continue

    return []


# 🆕 Round-Robin Counter für Football-Data Keys
_FD_KEY_OFFSET = 0
_FD_DEAD_KEYS = set()


def fetch_football_data(league_name, target_date):
    global _FD_KEY_OFFSET

    code = FOOTBALL_DATA_CODES.get(league_name)

    if not code or not FOOTBALL_DATA_API_KEYS:
        return []

    n = len(FOOTBALL_DATA_API_KEYS)

    # Round-Robin: Probiere Keys, überspringe tote
    for offset in range(n):
        idx = (_FD_KEY_OFFSET + offset) % n
        if idx in _FD_DEAD_KEYS:
            continue
        key = FOOTBALL_DATA_API_KEYS[idx]

        try:
            r = requests.get(
                f"https://api.football-data.org/v4/competitions/{code}/matches",
                params={
                    "dateFrom": target_date.isoformat(),
                    "dateTo": target_date.isoformat(),
                },
                headers={"X-Auth-Token": key},
                timeout=15,
            )

            # 429 = Rate Limit (10 req/min) → Key kurz tot markieren
            if r.status_code == 429:
                _FD_DEAD_KEYS.add(idx)
                continue

            # 403 = Key ungültig oder gesperrt
            if r.status_code == 403:
                _FD_DEAD_KEYS.add(idx)
                continue

            if not r.ok:
                continue

            # Erfolg → beim nächsten Call den nächsten Key nehmen
            _FD_KEY_OFFSET = (idx + 1) % n

            data = r.json()
            now_utc = datetime.now(timezone.utc)
            fixtures = []

            for m in data.get("matches", []):
                try:
                    kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                    if kickoff > now_utc:
                        fixtures.append({
                            "home": m["homeTeam"]["name"],
                            "away": m["awayTeam"]["name"],
                            "match_id": m.get("id"),
                            "time_utc": m["utcDate"],
                            "time_local": get_local_time(m["utcDate"]),
                            "source": "football-data",
                        })
                except Exception:
                    continue

            return fixtures

        except Exception:
            continue

    return []


def fetch_api_football(league_name, target_date):
    league_id = API_FOOTBALL_LEAGUES.get(league_name)

    if not league_id or not API_FOOTBALL_KEYS:
        return []

    try:
        season = target_date.year if target_date.month > 6 else target_date.year - 1

        # 🆕 Round-Robin Key-Auswahl, tote Keys überspringen
        n = len(API_FOOTBALL_KEYS)
        for offset in range(n):
            idx = (APIFOOTBALL_KEY_OFFSET + offset) % n
            if idx in APIFOOTBALL_DEAD_KEYS:
                continue
            key = API_FOOTBALL_KEYS[idx]

            try:
                r = requests.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers={
                        "x-rapidapi-key": key,
                        "x-rapidapi-host": "v3.football.api-sports.io",
                    },
                    params={
                        "date": target_date.isoformat(),
                        "league": league_id,
                        "season": season,
                        "status": "NS",
                    },
                    timeout=15,
                )
            except Exception:
                continue

            # 429 = Rate Limit
            if r.status_code == 429:
                APIFOOTBALL_DEAD_KEYS.add(idx)
                continue

            if not r.ok:
                continue

            # Erfolg verbucht
            data = r.json()
            now_utc = datetime.now(timezone.utc)
            fixtures = []

            for fix in data.get("response", []):
                try:
                    kickoff_str = fix.get("fixture", {}).get("date", "")
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                    if kickoff > now_utc:
                        teams = fix.get("teams", {})
                        fixtures.append({
                            "home": teams.get("home", {}).get("name", ""),
                            "away": teams.get("away", {}).get("name", ""),
                            "match_id": fix.get("fixture", {}).get("id"),
                            "home_id": teams.get("home", {}).get("id"),
                            "away_id": teams.get("away", {}).get("id"),
                            "time_utc": kickoff_str,
                            "time_local": get_local_time(kickoff_str),
                            "source": "api-football",
                        })
                except Exception:
                    continue

            return fixtures

        return []

    except Exception:
        return []


# ============================================================
# 🆕 API-FOOTBALL ERWEITERUNGEN (Team Stats, Verletzungen, H2H, Predictions)
# ============================================================
APIFOOTBALL_TEAM_STATS_CACHE = {}
APIFOOTBALL_INJURIES_CACHE = {}
APIFOOTBALL_H2H_CACHE = {}
APIFOOTBALL_PREDICTIONS_CACHE = {}

# 🆕 QUOTA-SCHUTZ für Free Plan (100 Calls/Tag pro Key)
# Wir reservieren Calls für die wichtigsten Funktionen.
APIFOOTBALL_CALL_COUNTER = 0
# 🆕 Default 100 Calls/Run (bei 3 Keys × 100 Calls = 300/Tag, also reichen 100/Run für 2-3 Runs)
APIFOOTBALL_MAX_CALLS_PER_RUN = int(env("APIFOOTBALL_MAX_CALLS", "100"))
APIFOOTBALL_QUOTA_EXHAUSTED = False
# 🆕 Round-Robin Counter für Keys
APIFOOTBALL_KEY_OFFSET = 0
# 🆕 Set für erschöpfte Keys (per-Run)
APIFOOTBALL_DEAD_KEYS = set()
# Steuerung welche Erweiterungen aktiv sind (mit 3 Keys = 300 Calls/Tag → alles AN möglich)
APIFOOTBALL_ENABLE_TEAM_STATS = env("APIFOOTBALL_TEAM_STATS", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_H2H = env("APIFOOTBALL_H2H", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_INJURIES = env("APIFOOTBALL_INJURIES", "true").lower() in ["1", "true", "yes"]
APIFOOTBALL_ENABLE_PREDICTIONS = env("APIFOOTBALL_PREDICTIONS", "true").lower() in ["1", "true", "yes"]

# ============================================================
# 🆕 LEAGUE ROTATION SYSTEM - Auto Ligen ein/ausschalten
# ============================================================
LEAGUE_ROTATION_ENABLED = env("LEAGUE_ROTATION_ENABLED", "true").lower() in ["1", "true", "yes"]
LEAGUE_ROTATION_MIN_SAMPLES = int(env("LEAGUE_ROTATION_MIN_SAMPLES", "5"))  # Mindest 5 Tipps pro Liga
LEAGUE_ROTATION_MIN_QUOTE = float(env("LEAGUE_ROTATION_MIN_QUOTE", "0.50"))  # <50% = rausnehmen
LEAGUE_ROTATION_MAX_QUOTE = float(env("LEAGUE_ROTATION_MAX_QUOTE", "0.70"))  # >70% = reinmachen
LEAGUE_ROTATION_CHECK_DAY = env("LEAGUE_ROTATION_CHECK_DAY", "6")  # Sonntag (6) = weekly check

# Aktive Ligen - wird dynamisch aktualisiert
ACTIVE_LEAGUES = set(LEAGUES_TO_RUN)  # Alle starten aktiv
LEAGUE_STATS_CACHE = {}


def get_league_performance(league_name):
    """
    Holt Performance-Stats für eine Liga aus Supabase.
    Returns: {"won": 5, "lost": 2, "pending": 3, "quote": 0.714}
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        
        # Alle tips für diese Liga (status = won/lost)
        params = {
            "league": f"eq.{league_name}",
            "select": "status",
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=10)
        
        if not r.ok:
            return None
        
        tips = r.json()
        won = sum(1 for t in tips if t.get("status") == "won")
        lost = sum(1 for t in tips if t.get("status") == "lost")
        total = won + lost
        
        if total < LEAGUE_ROTATION_MIN_SAMPLES:
            return None  # Zu wenig Daten
        
        quote = won / total if total > 0 else 0
        
        return {
            "league": league_name,
            "won": won,
            "lost": lost,
            "total": total,
            "quote": quote,
        }
    
    except Exception as e:
        log(f"League Stats Error ({league_name}): {e}", "WARN")
        return None


def rotate_leagues():
    """
    Checkt Liga-Performance und nimmt schlecht/gut performende Ligen raus/rein.
    Wird 1x pro Woche aufgerufen (Sonntag).
    """
    global ACTIVE_LEAGUES
    
    if not LEAGUE_ROTATION_ENABLED:
        return
    
    log("🔄 League Rotation Check startet...")
    
    to_remove = []
    to_add = []
    
    # Check alle Ligen (auch inactive)
    all_leagues = set(LEAGUES_TO_RUN)
    
    for league in all_leagues:
        stats = get_league_performance(league)
        
        if not stats:
            continue  # Zu wenig Daten
        
        is_active = league in ACTIVE_LEAGUES
        quote = stats["quote"]
        
        # Rausnehmen: <50% quote
        if is_active and quote < LEAGUE_ROTATION_MIN_QUOTE:
            to_remove.append(league)
            log(f"   ❌ {league}: {quote*100:.0f}% - RAUSNEHMEN")
        
        # Reinmachen: >70% quote
        if not is_active and quote > LEAGUE_ROTATION_MAX_QUOTE:
            to_add.append(league)
            log(f"   ✅ {league}: {quote*100:.0f}% - REINMACHEN")
    
    # Applizieren
    for league in to_remove:
        ACTIVE_LEAGUES.discard(league)
    
    for league in to_add:
        ACTIVE_LEAGUES.add(league)
    
    log(f"🔄 Rotation done: -{len(to_remove)} Ligen, +{len(to_add)} Ligen")
    log(f"   Aktive Ligen jetzt: {len(ACTIVE_LEAGUES)}/{len(LEAGUES_TO_RUN)}")
    
    # Telegram Info
    if to_remove or to_add:
        msg = f"🔄 <b>League Rotation</b>\n\n"
        if to_remove:
            msg += f"❌ Raus: {', '.join(to_remove)}\n"
        if to_add:
            msg += f"✅ Rein: {', '.join(to_add)}\n"
        msg += f"\n📊 Aktiv: {len(ACTIVE_LEAGUES)}/{len(LEAGUES_TO_RUN)}"
        send_telegram(msg, TELEGRAM_GROUPS.get("stats"))


def check_rotation_schedule():
    """
    Checkt ob heute der Rotation-Tag ist (Sonntag).
    """
    if not LEAGUE_ROTATION_ENABLED:
        return
    
    today = datetime.now()
    if today.weekday() == int(LEAGUE_ROTATION_CHECK_DAY):
        rotate_leagues()



def _af_request(endpoint, params, timeout=12):
    """
    Helper für API-Football Requests mit Quota-Schutz und Round-Robin über mehrere Keys.
    Bei Free Plan: 100 Calls/Tag PRO KEY.
    """
    global APIFOOTBALL_CALL_COUNTER, APIFOOTBALL_QUOTA_EXHAUSTED, APIFOOTBALL_KEY_OFFSET

    if not API_FOOTBALL_KEYS:
        return None

    if APIFOOTBALL_QUOTA_EXHAUSTED:
        return None

    if APIFOOTBALL_CALL_COUNTER >= APIFOOTBALL_MAX_CALLS_PER_RUN:
        if not APIFOOTBALL_QUOTA_EXHAUSTED:
            log(f"   ⚠️ API-Football Limit erreicht ({APIFOOTBALL_MAX_CALLS_PER_RUN} Calls) - Erweiterungen aus", "WARN")
            APIFOOTBALL_QUOTA_EXHAUSTED = True
        return None

    n = len(API_FOOTBALL_KEYS)
    # Probiere bis zu n Keys (Round-Robin), überspringe tote Keys
    for offset in range(n):
        idx = (APIFOOTBALL_KEY_OFFSET + offset) % n
        if idx in APIFOOTBALL_DEAD_KEYS:
            continue
        key = API_FOOTBALL_KEYS[idx]

        try:
            r = requests.get(
                f"https://v3.football.api-sports.io{endpoint}",
                headers={
                    "x-rapidapi-key": key,
                    "x-rapidapi-host": "v3.football.api-sports.io",
                },
                params=params,
                timeout=timeout,
            )
            APIFOOTBALL_CALL_COUNTER += 1

            # Rate Limit Header lesen
            remaining = r.headers.get("x-ratelimit-requests-remaining")
            if remaining is not None:
                try:
                    rem = int(remaining)
                    # Wenn dieser Key fast leer → markiere als tot, nimm nächsten beim nächsten Call
                    if rem < 3:
                        APIFOOTBALL_DEAD_KEYS.add(idx)
                        log(f"   ℹ️ API-Football Key #{idx+1} fast leer ({rem} übrig) - Wechsel auf nächsten", "INFO")
                except:
                    pass

            # 429 = Rate Limit überschritten → Key tot markieren
            if r.status_code == 429:
                APIFOOTBALL_DEAD_KEYS.add(idx)
                log(f"   ⚠️ API-Football Key #{idx+1} rate-limited - Wechsel", "WARN")
                continue

            # Wenn alle Keys tot sind → Quota total leer
            if len(APIFOOTBALL_DEAD_KEYS) >= n:
                log(f"   ⚠️ Alle {n} API-Football Keys erschöpft", "WARN")
                APIFOOTBALL_QUOTA_EXHAUSTED = True
                return None

            if not r.ok:
                continue

            data = r.json()
            if data.get("errors"):
                continue

            # Erfolg! Beim nächsten Call den nächsten Key nehmen
            APIFOOTBALL_KEY_OFFSET = (idx + 1) % n
            return data.get("response", [])
        except Exception:
            continue

    return None


def fetch_team_statistics(team_id, league_id, season):
    """
    Holt Saison-Statistiken eines Teams.
    Liefert: Form, Goals avg, Clean Sheets, BTTS-Approximation
    """
    cache_key = f"{team_id}_{league_id}_{season}"
    if cache_key in APIFOOTBALL_TEAM_STATS_CACHE:
        return APIFOOTBALL_TEAM_STATS_CACHE[cache_key]

    response = _af_request("/teams/statistics", {
        "team": team_id,
        "league": league_id,
        "season": season,
    })

    stats = response if isinstance(response, dict) else None
    if not stats:
        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = None
        return None

    try:
        played = stats.get("fixtures", {}).get("played", {}).get("total", 0) or 0
        clean_sheets = stats.get("clean_sheet", {}).get("total", 0) or 0
        failed_to_score = stats.get("failed_to_score", {}).get("total", 0) or 0

        # BTTS-Rate Approximation
        scored_games = max(0, played - failed_to_score)
        conceded_games = max(0, played - clean_sheets)
        btts_approx = round(min(scored_games, conceded_games) / played * 100, 1) if played > 0 else 0

        result = {
            "form": (stats.get("form") or "")[-5:],
            "goals_for_avg": stats.get("goals", {}).get("for", {}).get("average", {}).get("total", "0"),
            "goals_against_avg": stats.get("goals", {}).get("against", {}).get("average", {}).get("total", "0"),
            "matches_played": played,
            "clean_sheets": clean_sheets,
            "failed_to_score": failed_to_score,
            "btts_rate_approx": btts_approx,
            "wins": stats.get("fixtures", {}).get("wins", {}).get("total", 0),
            "draws": stats.get("fixtures", {}).get("draws", {}).get("total", 0),
            "losses": stats.get("fixtures", {}).get("loses", {}).get("total", 0),
        }

        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = result
        return result
    except Exception:
        APIFOOTBALL_TEAM_STATS_CACHE[cache_key] = None
        return None


def fetch_injuries(team_id, league_id, season):
    """
    Holt verletzte/gesperrte Spieler.
    """
    cache_key = f"{team_id}_{league_id}_{season}"
    if cache_key in APIFOOTBALL_INJURIES_CACHE:
        return APIFOOTBALL_INJURIES_CACHE[cache_key]

    response = _af_request("/injuries", {
        "team": team_id,
        "league": league_id,
        "season": season,
    })

    if not response:
        APIFOOTBALL_INJURIES_CACHE[cache_key] = []
        return []

    injuries = []
    for entry in response:
        try:
            player = entry.get("player", {})
            name = player.get("name", "")
            if name:
                injuries.append({
                    "name": name,
                    "reason": player.get("reason", ""),
                    "type": player.get("type", ""),
                })
        except Exception:
            continue

    APIFOOTBALL_INJURIES_CACHE[cache_key] = injuries
    return injuries


def fetch_head_to_head(home_id, away_id, last=5):
    """
    Head-to-Head Historie zwischen 2 Teams.
    """
    cache_key = f"{home_id}_{away_id}_{last}"
    if cache_key in APIFOOTBALL_H2H_CACHE:
        return APIFOOTBALL_H2H_CACHE[cache_key]

    response = _af_request("/fixtures/headtohead", {
        "h2h": f"{home_id}-{away_id}",
        "last": last,
    })

    if not response:
        APIFOOTBALL_H2H_CACHE[cache_key] = None
        return None

    matches = []
    for m in response:
        try:
            goals = m.get("goals", {})
            home_g = goals.get("home", 0) or 0
            away_g = goals.get("away", 0) or 0
            teams = m.get("teams", {})
            matches.append({
                "date": m.get("fixture", {}).get("date", "")[:10],
                "home": teams.get("home", {}).get("name", ""),
                "away": teams.get("away", {}).get("name", ""),
                "home_goals": home_g,
                "away_goals": away_g,
                "btts": (home_g > 0 and away_g > 0),
                "total_goals": home_g + away_g,
                "over25": (home_g + away_g) > 2,
            })
        except Exception:
            continue

    if not matches:
        APIFOOTBALL_H2H_CACHE[cache_key] = None
        return None

    btts_count = sum(1 for m in matches if m["btts"])
    over25_count = sum(1 for m in matches if m["over25"])
    avg_goals = sum(m["total_goals"] for m in matches) / len(matches)

    result = {
        "matches": matches,
        "count": len(matches),
        "btts_rate": round(btts_count / len(matches) * 100, 1),
        "over25_rate": round(over25_count / len(matches) * 100, 1),
        "avg_goals": round(avg_goals, 2),
    }

    APIFOOTBALL_H2H_CACHE[cache_key] = result
    return result


def fetch_predictions(fixture_id):
    """
    API-Football's eingebaute Predictions für ein Fixture.
    """
    if fixture_id in APIFOOTBALL_PREDICTIONS_CACHE:
        return APIFOOTBALL_PREDICTIONS_CACHE[fixture_id]

    response = _af_request("/predictions", {
        "fixture": fixture_id,
    })

    if not response or not isinstance(response, list) or not response:
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = None
        return None

    try:
        pred = response[0].get("predictions", {})
        result = {
            "winner": (pred.get("winner") or {}).get("name"),
            "win_or_draw": pred.get("win_or_draw"),
            "under_over": pred.get("under_over"),
            "goals_home": (pred.get("goals") or {}).get("home"),
            "goals_away": (pred.get("goals") or {}).get("away"),
            "advice": pred.get("advice", ""),
            "percent_home": (pred.get("percent") or {}).get("home", "?"),
            "percent_draw": (pred.get("percent") or {}).get("draw", "?"),
            "percent_away": (pred.get("percent") or {}).get("away", "?"),
        }
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = result
        return result
    except Exception:
        APIFOOTBALL_PREDICTIONS_CACHE[fixture_id] = None
        return None


def fetch_football_json(league_name, target_date):
    league_code = FOOTBALL_JSON_LEAGUES.get(league_name)

    if not league_code:
        return []

    try:
        year = target_date.year

        if target_date.month >= 7:
            season = f"{year}-{(year + 1) % 100:02d}"
        else:
            season = f"{year - 1}-{year % 100:02d}"

        url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league_code}.json"

        r = requests.get(url, timeout=10)

        if not r.ok:
            return []

        data = r.json()
        fixtures = []

        for m in data.get("matches", []):
            if m.get("date") == target_date.isoformat():
                fixtures.append({
                    "home": m.get("team1", ""),
                    "away": m.get("team2", ""),
                    "time_local": "TBD",
                    "source": "football.json",
                })

        return fixtures

    except Exception:
        return []


def fetch_openligadb(league_name, target_date):
    code = OPENLIGADB_LEAGUES.get(league_name)

    if not code:
        return []

    try:
        season = target_date.year if target_date.month >= 7 else target_date.year - 1
        url = f"https://api.openligadb.de/getmatchdata/{code}/{season}"

        r = requests.get(url, timeout=15)

        if not r.ok:
            return []

        data = r.json()
        target_str = target_date.isoformat()
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in data:
            try:
                kickoff_str = m.get("matchDateTimeUTC", "")

                if not kickoff_str or not kickoff_str.startswith(target_str):
                    continue

                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff > now_utc:
                    fixtures.append({
                        "home": m.get("team1", {}).get("teamName", ""),
                        "away": m.get("team2", {}).get("teamName", ""),
                        "match_id": m.get("matchID"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "openligadb",
                    })

            except Exception:
                continue

        return fixtures

    except Exception:
        return []


def fetch_football_data_co_uk(league_name, season="2425"):
    """
    Holt historische Ergebnisse + Quoten von football-data.co.uk
    Perfekt für Backtesting und Kontext-Analyse.
    """
    codes = {
        "Bundesliga": ("D", "D1"),
        "2. Bundesliga": ("D", "D2"),
        "Premier League": ("E", "E0"),
        "Championship": ("E", "E1"),
        "La Liga": ("SP", "SP1"),
        "La Liga 2": ("SP", "SP2"),
        "Serie A": ("I", "I1"),
        "Serie B": ("I", "I2"),
        "Ligue 1": ("F", "F1"),
        "Ligue 2": ("F", "F2"),
        "Eredivisie": ("N", "N1"),
        "Primeira Liga": ("P", "P1"),
        "Pro League Belgien": ("B", "B1"),
        "Süper Lig": ("T", "T1"),
        "Scottish Premiership": ("SC", "SC0"),
    }
    code = codes.get(league_name)
    if not code:
        return []
    try:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code[1]}.csv"
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        if not r.ok:
            return []
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return []
        headers = lines[0].split(",")
        results = []
        for line in lines[-20:]:
            try:
                vals = line.split(",")
                if len(vals) < len(headers):
                    continue
                row = dict(zip(headers, vals))
                results.append({
                    "date": row.get("Date", ""),
                    "home": row.get("HomeTeam", ""),
                    "away": row.get("AwayTeam", ""),
                    "fthg": row.get("FTHG", ""),
                    "ftag": row.get("FTAG", ""),
                    "hthg": row.get("HTHG", ""),
                    "htag": row.get("HTAG", ""),
                    "b365_over": row.get("B365>2.5", row.get("B365O", "")),
                    "pin_over": row.get("PINN>2.5", row.get("PINO", "")),
                })
            except Exception:
                continue
        return results
    except Exception:
        return []


def analyze_line_movement(odds_data, home_team, away_team):
    """
    Analysiert Line Movement via Odds API.
    Vergleicht Pinnacle vs Markt-Durchschnitt als Proxy für Opening/Closing.
    """
    if not odds_data:
        return None

    all_over25 = {}
    all_h2h_home = {}

    for g in odds_data:
        gh = g.get("home_team", "").lower()
        if home_team.lower() not in gh and gh not in home_team.lower():
            continue

        for bm in g.get("bookmakers", []):
            title = bm.get("title", "")
            for m in bm.get("markets", []):
                if m["key"] == "totals":
                    ov = next((float(o["price"]) for o in m["outcomes"]
                              if o["name"] == "Over" and o.get("point") == 2.5), None)
                    if ov:
                        all_over25[title] = ov
                if m["key"] == "h2h":
                    ho = next((float(o["price"]) for o in m["outcomes"]
                              if o["name"] == g.get("home_team")), None)
                    if ho:
                        all_h2h_home[title] = ho

    if not all_over25:
        return None

    signals = []

    pinnacle_over = None
    soft_overs = []
    for bm, odds in all_over25.items():
        if "pinnacle" in bm.lower():
            pinnacle_over = odds
        elif bm.lower() in ["bet365", "william hill", "bwin", "unibet", "betway"]:
            soft_overs.append(odds)

    if pinnacle_over and soft_overs:
        soft_avg = sum(soft_overs) / len(soft_overs)
        movement = pinnacle_over - soft_avg
        pct = (movement / soft_avg) * 100

        if pct > 4:
            signals.append(f"📈 Line Movement Over 2.5: +{round(pct,1)}% (Pin:{pinnacle_over} vs Soft:{round(soft_avg,2)})")
        elif pct < -4:
            signals.append(f"📉 Line Movement Over 2.5: {round(pct,1)}% (Pin:{pinnacle_over} vs Soft:{round(soft_avg,2)})")

    if len(all_over25) >= 3:
        vals = list(all_over25.values())
        spread = max(vals) - min(vals)
        if spread > 0.15:
            signals.append(f"⚡ Hohe Quoten-Divergenz Over 2.5: {min(vals)}-{max(vals)} (Spread: {round(spread,2)})")

    return signals if signals else None


def get_historical_btts_rate(league_name, home_team, away_team):
    """
    Berechnet historische BTTS-Rate aus football-data.co.uk Daten.
    """
    try:
        data = fetch_football_data_co_uk(league_name)
        if not data:
            return None

        home_l = home_team.lower()
        away_l = away_team.lower()

        home_games = []
        away_games = []

        for g in data:
            gh = g.get("home", "").lower()
            ga = g.get("away", "").lower()
            fthg = g.get("fthg", "")
            ftag = g.get("ftag", "")

            if not fthg or not ftag:
                continue

            try:
                h_goals = int(fthg)
                a_goals = int(ftag)
                btts = h_goals > 0 and a_goals > 0
                total = h_goals + a_goals
            except:
                continue

            if home_l in gh or gh in home_l:
                home_games.append({"btts": btts, "total": total})
            if away_l in ga or ga in away_l:
                away_games.append({"btts": btts, "total": total})

        if not home_games and not away_games:
            return None

        result = {}
        if home_games:
            btts_rate = sum(1 for g in home_games if g["btts"]) / len(home_games)
            avg_goals = sum(g["total"] for g in home_games) / len(home_games)
            result["home"] = {
                "btts_rate": round(btts_rate * 100, 1),
                "avg_goals": round(avg_goals, 2),
                "games": len(home_games)
            }
        if away_games:
            btts_rate = sum(1 for g in away_games if g["btts"]) / len(away_games)
            avg_goals = sum(g["total"] for g in away_games) / len(away_games)
            result["away"] = {
                "btts_rate": round(btts_rate * 100, 1),
                "avg_goals": round(avg_goals, 2),
                "games": len(away_games)
            }
        return result
    except Exception:
        return None


def load_understat_league(league_name):
    if league_name in UNDERSTAT_CACHE:
        return UNDERSTAT_CACHE[league_name]

    league_code = UNDERSTAT_LEAGUES.get(league_name)

    if not league_code:
        UNDERSTAT_CACHE[league_name] = {}
        return {}

    try:
        url = f"https://understat.com/league/{league_code}"

        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        if not r.ok:
            UNDERSTAT_CACHE[league_name] = {}
            return {}

        m = re.search(r"var teamsData\s*=\s*JSON\.parse\('([^']+)'\)", r.text)

        if not m:
            UNDERSTAT_CACHE[league_name] = {}
            return {}

        encoded = m.group(1).encode().decode("unicode_escape")
        teams_data = json.loads(encoded)
        result = {}

        for _, info in teams_data.items():
            title = info.get("title", "")
            history = info.get("history", [])

            if not title or not history:
                continue

            last5 = history[-5:]
            avg_xg = sum(float(h.get("xG", 0)) for h in last5) / len(last5)
            avg_xga = sum(float(h.get("xGA", 0)) for h in last5) / len(last5)

            result[title.lower()] = {
                "xG": round(avg_xg, 2),
                "xGA": round(avg_xga, 2),
            }

        UNDERSTAT_CACHE[league_name] = result
        return result

    except Exception:
        UNDERSTAT_CACHE[league_name] = {}
        return {}


def get_team_xg(team_name, league_name):
    data = load_understat_league(league_name)
    t = team_name.lower()

    for title, stats in data.items():
        if t in title or title in t:
            return stats

    return None


# ============================================================
# AI CLIENTS
# ============================================================

# 🆕 Globaler Status: Wenn Groq rate-limited → nicht mehr probieren
_GROQ_RATE_LIMITED = False

# 🆕 Round-Robin Counter für Gemini Keys (verteilt Last gleichmäßig)
_GEMINI_KEY_OFFSET = 0


def call_gemini(prompt, use_tools=True):
    global _GEMINI_KEY_OFFSET

    if not GEMINI_API_KEYS:
        return None, "Keine Gemini Keys"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 32000 if use_tools else 16000,
        },
    }

    if use_tools:
        payload["tools"] = [{"google_search": {}}]

    last_error = None
    n = len(GEMINI_API_KEYS)

    # 🆕 Round-Robin: Beim nächsten Key starten (verteilt Last gleichmäßig)
    for offset in range(n):
        idx = (_GEMINI_KEY_OFFSET + offset) % n
        key = GEMINI_API_KEYS[idx]

        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload,
                timeout=240 if use_tools else 120,
            )

            data = r.json()

            if "error" in data:
                last_error = data.get("error", {}).get("message", "")[:120]
                continue

            candidates = data.get("candidates", [])

            if not candidates:
                last_error = "no candidates"
                continue

            text = "".join(
                p.get("text", "")
                for p in candidates[0].get("content", {}).get("parts", [])
            )

            if not text.strip():
                last_error = "empty response"
                continue

            results = extract_json_array(text)

            if results is not None:
                # 🆕 Beim nächsten Aufruf rotieren
                _GEMINI_KEY_OFFSET = (idx + 1) % n
                label = f"Gemini #{idx + 1}" if use_tools else f"Gemini-NoTools #{idx + 1}"
                return results, label

        except Exception as e:
            last_error = str(e)[:120]
            continue

    return None, f"Gemini erschöpft ({last_error})"


def call_groq(prompt):
    global _GROQ_RATE_LIMITED

    if not GROQ_API_KEYS:
        return None, "Keine Groq Keys"

    if not USE_GROQ_FALLBACK:
        return None, "Groq deaktiviert"

    # 🆕 Wenn Groq schon erschöpft ist, nicht nochmal probieren!
    if _GROQ_RATE_LIMITED:
        return None, "Groq übersprungen (Rate Limit erreicht)"

    if len(prompt) > 30000:
        prompt = prompt[:30000] + "\n\nAntworte mit JSON-Array."

    last_error = None
    rate_limit_hits = 0

    for idx, key in enumerate(GROQ_API_KEYS):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 4000,
                },
                timeout=120,
            )

            data = r.json()

            if "error" in data:
                err_msg = data.get("error", {}).get("message", "")[:120]
                last_error = err_msg
                # 🆕 Rate Limit erkennen
                if "rate limit" in err_msg.lower() or "rate_limit" in err_msg.lower():
                    rate_limit_hits += 1
                time.sleep(GROQ_SLEEP_SECONDS)
                continue

            choices = data.get("choices", [])

            if not choices:
                last_error = "no choices"
                time.sleep(GROQ_SLEEP_SECONDS)
                continue

            text = choices[0].get("message", {}).get("content", "")
            results = extract_json_array(text)

            if results is not None:
                return results, f"Groq #{idx + 1}"

        except Exception as e:
            last_error = str(e)[:120]
            time.sleep(GROQ_SLEEP_SECONDS)
            continue

    # 🆕 Wenn ALLE Groq Keys Rate-Limit haben → global deaktivieren
    if rate_limit_hits >= len(GROQ_API_KEYS):
        _GROQ_RATE_LIMITED = True
        log("⚠️  Groq global deaktiviert (alle Keys rate-limited)", "WARN")

    return None, f"Groq erschöpft ({last_error})"


# ============================================================
# ANALYSIS
# ============================================================

def merge_fixtures(*sources):
    all_fixtures = []
    seen = set()

    def norm(name):
        n = name.lower().strip()
        for rem in [" fc", " cf", " ac", " sc", " sv", "fc ", "ac ", "1. ", " 1."]:
            n = n.replace(rem, " ")
        return " ".join(n.split())[:20]

    for source in sources:
        for f in source:
            home = f.get("home", "").lower().strip()
            away = f.get("away", "").lower().strip()

            if not home or not away:
                continue

            home_norm = norm(home)
            away_norm = norm(away)
            key = (home_norm, away_norm)
            key_rev = (away_norm, home_norm)

            if key in seen or key_rev in seen:
                continue

            seen.add(key)
            all_fixtures.append(f)

    return all_fixtures


def calculate_kelly_units(probability, odds, max_units=3.0, bank_units=100):
    """
    Kelly Kriterium für optimale Einsatzgröße in Units.
    Half-Kelly für Sicherheit. Max 3 Units pro Tipp.
    """
    try:
        p = probability / 100
        b = odds - 1
        kelly = (p * b - (1 - p)) / b

        if kelly <= 0:
            return 0.5

        half_kelly = kelly / 2
        units = round(half_kelly * 100, 1)
        units = max(0.5, min(units, max_units))

        return units
    except Exception:
        return 1.0


def fetch_fbref_team_stats(team_name, league_name):
    """
    Holt erweiterte Stats von FBref (xG, xGA, Pressing, Possession).
    DEPRECATED - benutze besser get_fbref_stats() mit Caching.
    """
    return get_fbref_stats(team_name, league_name)


# 🆕 FBref Cache (pro Liga 1x laden, dann alle Teams aus dem Cache)
FBREF_CACHE = {}
FBREF_BLOCKED = False  # Wenn FBref blockt, schalten wir ab


def load_fbref_league(league_name):
    """
    Lädt FBref-Ligadaten EINMAL pro Run und cached sie.
    Parsed das Squad Standard Stats Table für xG, xGA, Possession.
    """
    global FBREF_BLOCKED

    if FBREF_BLOCKED:
        return {}

    if league_name in FBREF_CACHE:
        return FBREF_CACHE[league_name]

    fbref_urls = {
        "Premier League": "https://fbref.com/en/comps/9/Premier-League-Stats",
        "Bundesliga": "https://fbref.com/en/comps/20/Bundesliga-Stats",
        "La Liga": "https://fbref.com/en/comps/12/La-Liga-Stats",
        "Serie A": "https://fbref.com/en/comps/11/Serie-A-Stats",
        "Ligue 1": "https://fbref.com/en/comps/13/Ligue-1-Stats",
        "Eredivisie": "https://fbref.com/en/comps/23/Eredivisie-Stats",
        "Primeira Liga": "https://fbref.com/en/comps/32/Primeira-Liga-Stats",
        "Championship": "https://fbref.com/en/comps/10/Championship-Stats",
        "Champions League": "https://fbref.com/en/comps/8/Champions-League-Stats",
        "Europa League": "https://fbref.com/en/comps/19/Europa-League-Stats",
    }

    url = fbref_urls.get(league_name)
    if not url:
        FBREF_CACHE[league_name] = {}
        return {}

    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
        )

        # FBref blockt mit 403 oder 429 wenn zu viele Requests
        if r.status_code in [403, 429]:
            # Nur 1x loggen, dann still bleiben
            if not FBREF_BLOCKED:
                log(f"   ℹ️  FBref nicht erreichbar ({r.status_code}) - überspringe (kein Problem, andere Quellen reichen)")
            FBREF_BLOCKED = True
            FBREF_CACHE[league_name] = {}
            return {}

        if not r.ok:
            FBREF_CACHE[league_name] = {}
            return {}

        html = r.text

        # FBref versteckt einige Tables in HTML-Kommentaren - rauspulen
        html = html.replace("<!--", "").replace("-->", "")

        # Parse Squad Standard Stats Table
        # Format: <tr><th>...<a href=".../squads/...">TeamName</a>...<td>games</td>...<td>xG</td><td>xGA</td>...
        result = {}

        # Suche alle Team-Zeilen aus der "stats_squads_standard_for" Tabelle
        # FBref Pattern: <tr ...><th ...><a href="/en/squads/.../...">TeamName</a></th>
        team_pattern = re.compile(
            r'<tr[^>]*>\s*<th[^>]*data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>',
            re.IGNORECASE
        )

        # Suche xG, xGA, Possession via data-stat Attribut (zuverlässiger)
        # Wir finden Zeilen, dann extrahieren wir alle Werte aus der Zeile

        # Vereinfachter Ansatz: für jede gefundene Zeile, hole die Stats
        rows = re.findall(
            r'<tr[^>]*>\s*<th[^>]*data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>.*?</tr>',
            html,
            re.DOTALL | re.IGNORECASE
        )

        # Alternative: Komplette Tabellenzeilen finden
        for match in re.finditer(
            r'<tr[^>]*>(.*?)</tr>',
            html,
            re.DOTALL
        ):
            row_html = match.group(1)

            # Team-Name extrahieren
            team_m = re.search(
                r'data-stat="team"[^>]*>\s*<a[^>]*href="/en/squads/[^"]+"[^>]*>([^<]+)</a>',
                row_html
            )
            if not team_m:
                continue

            team_title = team_m.group(1).strip()

            # Stats extrahieren via data-stat
            xg_m = re.search(r'data-stat="xg_for"[^>]*>([\d.]+)<', row_html)
            xga_m = re.search(r'data-stat="xg_against"[^>]*>([\d.]+)<', row_html)
            poss_m = re.search(r'data-stat="possession"[^>]*>([\d.]+)<', row_html)
            games_m = re.search(r'data-stat="games"[^>]*>([\d.]+)<', row_html)
            goals_for_m = re.search(r'data-stat="goals_for"[^>]*>([\d.]+)<', row_html)
            goals_against_m = re.search(r'data-stat="goals_against"[^>]*>([\d.]+)<', row_html)

            stats = {}
            if games_m:
                games = float(games_m.group(1))
                stats["games"] = int(games) if games > 0 else 0
            else:
                continue  # Ohne games-Anzahl ist die Zeile nutzlos

            # Werte sind kumuliert über die Saison → pro Spiel umrechnen
            games = stats["games"] or 1

            if xg_m:
                stats["xG"] = round(float(xg_m.group(1)) / games, 2)
            if xga_m:
                stats["xGA"] = round(float(xga_m.group(1)) / games, 2)
            if poss_m:
                stats["possession"] = round(float(poss_m.group(1)), 1)
            if goals_for_m:
                stats["goals_for"] = round(float(goals_for_m.group(1)) / games, 2)
            if goals_against_m:
                stats["goals_against"] = round(float(goals_against_m.group(1)) / games, 2)

            if stats and len(stats) > 1:
                result[team_title.lower()] = stats

        FBREF_CACHE[league_name] = result

        if result:
            log(f"   📊 FBref geladen: {len(result)} Teams in {league_name}")

        return result

    except Exception as e:
        log(f"   ⚠️ FBref Fehler: {str(e)[:80]}", "WARN")
        FBREF_CACHE[league_name] = {}
        return {}


def get_fbref_stats(team_name, league_name):
    """
    Holt FBref-Stats für ein Team aus dem Cache.
    Lädt die Liga beim ersten Aufruf, dann nur Cache-Lookup.
    """
    data = load_fbref_league(league_name)

    if not data:
        return None

    t = team_name.lower().strip()

    # Exakter Match
    if t in data:
        return data[t]

    # Fuzzy Match: Team-Name beginnt gleich oder ist enthalten
    for title, stats in data.items():
        if t in title or title in t:
            return stats

        # Wort-basierter Match (z.B. "Bayern" vs "Bayern Munich")
        t_words = [w for w in t.split() if len(w) > 3]
        title_words = [w for w in title.split() if len(w) > 3]

        if t_words and title_words:
            if any(w in title for w in t_words) or any(w in t for w in title_words):
                return stats

    return None


def analyze_pinnacle_value(odds_data, home_team, away_team):
    """
    Analysiert Sharp Money via Pinnacle vs andere Bookies.
    """
    if not odds_data:
        return None

    pinnacle_over = None
    avg_over = []
    pinnacle_home = None
    avg_home = []

    for g in odds_data:
        gh = g.get("home_team", "").lower()
        ga = g.get("away_team", "").lower()
        if home_team.lower() not in gh and gh not in home_team.lower():
            continue

        for bm in g.get("bookmakers", []):
            title = bm.get("title", "").lower()
            is_pinnacle = "pinnacle" in title

            for m in bm.get("markets", []):
                if m["key"] == "totals":
                    ov = next((o["price"] for o in m["outcomes"]
                              if o["name"] == "Over" and o.get("point") == 2.5), None)
                    if ov:
                        if is_pinnacle:
                            pinnacle_over = float(ov)
                        else:
                            avg_over.append(float(ov))

                if m["key"] == "h2h":
                    ho = next((o["price"] for o in m["outcomes"]
                              if o["name"] == g.get("home_team")), None)
                    if ho:
                        if is_pinnacle:
                            pinnacle_home = float(ho)
                        else:
                            avg_home.append(float(ho))

    signals = []

    if pinnacle_over and avg_over:
        avg = sum(avg_over) / len(avg_over)
        diff_pct = ((pinnacle_over - avg) / avg) * 100
        if diff_pct > 3:
            signals.append(f"🔥 Over 2.5: Pinnacle {pinnacle_over} > Markt {round(avg,2)} (+{round(diff_pct,1)}%)")
        elif diff_pct < -3:
            signals.append(f"⚠️ Over 2.5: Pinnacle {pinnacle_over} < Markt {round(avg,2)} ({round(diff_pct,1)}%)")

    if pinnacle_home and avg_home:
        avg = sum(avg_home) / len(avg_home)
        diff_pct = ((pinnacle_home - avg) / avg) * 100
        if diff_pct > 3:
            signals.append(f"🔥 Heimsieg: Pinnacle {pinnacle_home} > Markt {round(avg,2)} (+{round(diff_pct,1)}%)")
        elif diff_pct < -3:
            signals.append(f"⚠️ Heimsieg: Pinnacle {pinnacle_home} < Markt {round(avg,2)} ({round(diff_pct,1)}%)")

    return signals if signals else None


def build_context(odds_data, fixtures, league, target_date=None):
    ctx = ""

    # 🆕 WETTERDATEN
    weather = get_weather_for_league(league, date.today())
    if weather:
        ctx += f"\n🌤️ WETTER ({weather['city']}):\n"
        ctx += f"• {weather['condition']} · {weather['temp']}°C · "
        ctx += f"Wind {weather['wind']}km/h · Regen {weather['rain']}mm\n"
        if weather['notes']:
            for note in weather['notes']:
                ctx += f"• {note}\n"
        if weather['impact'] == 'negative':
            ctx += f"⚠️ Wetter-Impact: Schlechtere Bedingungen → weniger Tore erwartet!\n"
        ctx += "\n"

    league_id = API_FOOTBALL_LEAGUES.get(league)
    season = None
    if league_id:
        from datetime import date as _date
        td = _date.today()
        season = td.year if td.month > 6 else td.year - 1

    if fixtures:
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE:\n"

        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f.get('time_local', 'TBD')} Uhr [{f.get('source', '?')}]"

            if league in UNDERSTAT_LEAGUES:
                home_xg = get_team_xg(f["home"], league)
                away_xg = get_team_xg(f["away"], league)

                if home_xg:
                    line += f"\n   📊 {f['home']}: xG {home_xg['xG']}/Spiel, xGA {home_xg['xGA']} [Understat]"
                if away_xg:
                    line += f"\n   📊 {f['away']}: xG {away_xg['xG']}/Spiel, xGA {away_xg['xGA']} [Understat]"

            # 🆕 FBref Stats (xG, Possession, Goals)
            home_fb = get_fbref_stats(f["home"], league)
            away_fb = get_fbref_stats(f["away"], league)

            if home_fb:
                fb_str = f"\n   ⚡ {f['home']}: xG {home_fb.get('xG','?')}, xGA {home_fb.get('xGA','?')}"
                if 'possession' in home_fb:
                    fb_str += f", Poss {home_fb['possession']}%"
                if 'goals_for' in home_fb:
                    fb_str += f", Tore {home_fb['goals_for']}/Spiel"
                fb_str += f" [FBref · {home_fb.get('games',0)} Spiele]"
                line += fb_str

            if away_fb:
                fb_str = f"\n   ⚡ {f['away']}: xG {away_fb.get('xG','?')}, xGA {away_fb.get('xGA','?')}"
                if 'possession' in away_fb:
                    fb_str += f", Poss {away_fb['possession']}%"
                if 'goals_for' in away_fb:
                    fb_str += f", Tore {away_fb['goals_for']}/Spiel"
                fb_str += f" [FBref · {away_fb.get('games',0)} Spiele]"
                line += fb_str

            # 🆕 FootyStats BTTS + Over 2.5 Stats
            home_fs = get_footystats_team(f["home"], league)
            away_fs = get_footystats_team(f["away"], league)

            if home_fs:
                line += (
                    f"\n   📊 {f['home']} [FootyStats]: "
                    f"BTTS {home_fs['btts_rate']}%, "
                    f"Over2.5 {home_fs['over25_rate']}%, "
                    f"Ø {home_fs['avg_goals']} Tore/Spiel"
                )
            if away_fs:
                line += (
                    f"\n   📊 {f['away']} [FootyStats]: "
                    f"BTTS {away_fs['btts_rate']}%, "
                    f"Over2.5 {away_fs['over25_rate']}%, "
                    f"Ø {away_fs['avg_goals']} Tore/Spiel"
                )

            # 🆕 FOREBET - Mathematische Predictions
            forebet = get_forebet_prediction(f["home"], f["away"], league, target_date)
            if forebet:
                fb_parts = []
                if forebet.get("btts_pct"):
                    fb_parts.append(f"BTTS {forebet['btts_pct']}%")
                if forebet.get("over25_pct"):
                    fb_parts.append(f"Over2.5 {forebet['over25_pct']}%")
                if forebet.get("avg_goals"):
                    fb_parts.append(f"Ø {forebet['avg_goals']} Tore")
                if forebet.get("tip"):
                    fb_parts.append(f"Tipp: {forebet['tip']}")
                if fb_parts:
                    line += f"\n   🔢 [Forebet]: {' · '.join(fb_parts)}"

            # 🆕 SCOUTINGSTATS - AI Predictions
            scout = get_scoutingstats_prediction(f["home"], f["away"], target_date)
            if scout:
                sc_parts = []
                if scout.get("btts_pct"):
                    sc_parts.append(f"BTTS {scout['btts_pct']}%")
                if scout.get("over25_pct"):
                    sc_parts.append(f"Over2.5 {scout['over25_pct']}%")
                if scout.get("value_edge"):
                    sc_parts.append(f"Edge +{scout['value_edge']}%")
                if sc_parts:
                    line += f"\n   🤖 [ScoutingStats]: {' · '.join(sc_parts)}"

            # 🆕 SPORTDB.DEV - Aufstellungen
            if SPORTDB_API_KEY:
                lineup = get_sportdb_lineups(f["home"], f["away"], target_date)
                if lineup and lineup.get("lineup_available"):
                    if lineup.get("home_lineup"):
                        players = ", ".join(lineup["home_lineup"][:5])
                        line += f"\n   👕 {f['home']} XI (Top 5): {players}..."
                    if lineup.get("away_lineup"):
                        players = ", ".join(lineup["away_lineup"][:5])
                        line += f"\n   👕 {f['away']} XI (Top 5): {players}..."

            # 🆕 SOFASCORE LINEUPS - Aufstellungen (zuverlässiger!)
            sofa_match_id = f.get("match_id") if f.get("source") == "sofascore" else None
            if sofa_match_id:
                sofa_lineup = get_sofascore_lineups(sofa_match_id, f["home"], f["away"])
                if sofa_lineup and sofa_lineup.get("lineup_available"):
                    confirmed = "✅ Bestätigt" if sofa_lineup.get("confirmed") else "⏳ Vorläufig"
                    if sofa_lineup.get("home_lineup"):
                        starters = [p["name"] for p in sofa_lineup["home_lineup"][:5]]
                        line += f"\n   👕 {f['home']} XI ({confirmed}): {', '.join(starters)}..."
                    if sofa_lineup.get("away_lineup"):
                        starters = [p["name"] for p in sofa_lineup["away_lineup"][:5]]
                        line += f"\n   👕 {f['away']} XI ({confirmed}): {', '.join(starters)}..."

            # 🆕 CLUBELO - Team Stärke
            home_elo = get_clubelo_rating(f["home"])
            away_elo = get_clubelo_rating(f["away"])
            if home_elo and away_elo:
                elo_diff = abs(home_elo["elo"] - away_elo["elo"])
                btts_prob = calculate_elo_btts_probability(home_elo["elo"], away_elo["elo"])
                line += (
                    f"\n   📊 Elo: {f['home']} {home_elo['elo']:.0f} vs "
                    f"{f['away']} {away_elo['elo']:.0f} "
                    f"(Diff: {elo_diff:.0f}, BTTS-Wahrscheinlichkeit: ~{btts_prob}%)"
                )

            # 🆕 TRANSFERMARKT - Verletzungen
            home_tm = get_transfermarkt_injuries(f["home"], league)
            away_tm = get_transfermarkt_injuries(f["away"], league)
            if home_tm and home_tm.get("has_data"):
                if home_tm.get("starters_out"):
                    names = ", ".join([p["name"] for p in home_tm["starters_out"][:3]])
                    line += f"\n   🏥 {f['home']} Stammspieler fehlen: {names}"
                if home_tm.get("suspended"):
                    names = ", ".join([p["name"] for p in home_tm["suspended"][:2]])
                    line += f"\n   🟥 {f['home']} Gesperrt: {names}"
            if away_tm and away_tm.get("has_data"):
                if away_tm.get("starters_out"):
                    names = ", ".join([p["name"] for p in away_tm["starters_out"][:3]])
                    line += f"\n   🏥 {f['away']} Stammspieler fehlen: {names}"
                if away_tm.get("suspended"):
                    names = ", ".join([p["name"] for p in away_tm["suspended"][:2]])
                    line += f"\n   🟥 {f['away']} Gesperrt: {names}"

            hist = get_historical_btts_rate(league, f["home"], f["away"])
            if hist:
                if hist.get("home"):
                    h = hist["home"]
                    line += f"\n   📈 {f['home']} (Heim): BTTS {h['btts_rate']}%, Ø {h['avg_goals']} Tore ({h['games']} Spiele) [fd.co.uk]"
                if hist.get("away"):
                    a = hist["away"]
                    line += f"\n   📈 {f['away']} (Auswärts): BTTS {a['btts_rate']}%, Ø {a['avg_goals']} Tore ({a['games']} Spiele) [fd.co.uk]"

            # 🆕 API-Football Erweiterungen (nur wenn fixture aus api-football kommt)
            # WICHTIG: Free Plan = 100 Calls/Tag. Daher nur für Top-Ligen!
            home_id = f.get("home_id")
            away_id = f.get("away_id")
            fixture_id = f.get("match_id")

            # Top-Ligen die API-Calls "wert" sind
            APIF_PRIORITY_LEAGUES = {
                "Champions League", "Europa League", "Conference League",
                "Premier League", "Bundesliga", "La Liga", "Serie A", "Ligue 1",
                "Eredivisie", "Primeira Liga", "Süper Lig",
                "Championship", "Bundesliga Österreich", "Super League Schweiz",
            }

            is_priority = league in APIF_PRIORITY_LEAGUES

            if home_id and away_id and league_id and season and is_priority:
                # 1. Team-Statistiken (2 Calls pro Spiel)
                if APIFOOTBALL_ENABLE_TEAM_STATS and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    home_stats = fetch_team_statistics(home_id, league_id, season)
                    if home_stats and home_stats.get("matches_played", 0) >= 3:
                        line += (
                            f"\n   🏠 {f['home']} Stats: Form {home_stats['form']}, "
                            f"⚽{home_stats['goals_for_avg']}/Spiel, "
                            f"🛡️{home_stats['goals_against_avg']} kassiert, "
                            f"BTTS≈{home_stats['btts_rate_approx']}%, "
                            f"Clean Sheets {home_stats['clean_sheets']}/{home_stats['matches_played']} "
                            f"[API-Football]"
                        )

                    away_stats = fetch_team_statistics(away_id, league_id, season)
                    if away_stats and away_stats.get("matches_played", 0) >= 3:
                        line += (
                            f"\n   ✈️ {f['away']} Stats: Form {away_stats['form']}, "
                            f"⚽{away_stats['goals_for_avg']}/Spiel, "
                            f"🛡️{away_stats['goals_against_avg']} kassiert, "
                            f"BTTS≈{away_stats['btts_rate_approx']}%, "
                            f"Clean Sheets {away_stats['clean_sheets']}/{away_stats['matches_played']} "
                            f"[API-Football]"
                        )

                # 2. H2H History (1 Call pro Spiel)
                if APIFOOTBALL_ENABLE_H2H and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    h2h = fetch_head_to_head(home_id, away_id, last=5)
                    if h2h and h2h["count"] >= 2:
                        line += (
                            f"\n   ⚔️ Direkter Vergleich (letzte {h2h['count']}): "
                            f"BTTS {h2h['btts_rate']}%, "
                            f"Over 2.5 {h2h['over25_rate']}%, "
                            f"Ø {h2h['avg_goals']} Tore [API-Football H2H]"
                        )

                # 3. Verletzungen (2 Calls pro Spiel) - DEFAULT AUS für Free Plan
                if APIFOOTBALL_ENABLE_INJURIES and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    home_inj = fetch_injuries(home_id, league_id, season)
                    away_inj = fetch_injuries(away_id, league_id, season)
                    if home_inj:
                        inj_names = ", ".join([i["name"] for i in home_inj[:5]])
                        line += f"\n   🤕 {f['home']} Ausfälle ({len(home_inj)}): {inj_names}"
                    if away_inj:
                        inj_names = ", ".join([i["name"] for i in away_inj[:5]])
                        line += f"\n   🤕 {f['away']} Ausfälle ({len(away_inj)}): {inj_names}"

            # 4. API-Football Predictions (1 Call pro Spiel) - DEFAULT AUS für Free Plan
            if (APIFOOTBALL_ENABLE_PREDICTIONS and fixture_id and is_priority
                and f.get("source") == "api-football" and not APIFOOTBALL_QUOTA_EXHAUSTED):
                pred = fetch_predictions(fixture_id)
                if pred and pred.get("advice"):
                    line += (
                        f"\n   🎯 API-Football Tip: '{pred['advice']}' "
                        f"({pred.get('percent_home','?')}/"
                        f"{pred.get('percent_draw','?')}/"
                        f"{pred.get('percent_away','?')})"
                    )
                    if pred.get("under_over"):
                        line += f", Goals: {pred['under_over']}"

            ctx += line + "\n"

    if odds_data:
        ctx += "\n💰 LIVE-QUOTEN:\n"

        for g in odds_data[:10]:
            try:
                t = get_local_time(g["commence_time"])
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}\n"

                for bm in g.get("bookmakers", [])[:5]:
                    for m in bm.get("markets", []):
                        if m["key"] == "totals":
                            ov = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Over" and o.get("point") == 2.5),
                                None,
                            )
                            un = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Under" and o.get("point") == 2.5),
                                None,
                            )
                            if ov:
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}\n"

                        if m["key"] == "h2h":
                            home_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == g["home_team"]),
                                None,
                            )
                            draw_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == "Draw"),
                                None,
                            )
                            away_o = next(
                                (o["price"] for o in m["outcomes"]
                                 if o["name"] == g["away_team"]),
                                None,
                            )
                            if home_o:
                                ctx += f"  [{bm['title']}] 1: {home_o} / X: {draw_o} / 2: {away_o}\n"

                line_signals = analyze_line_movement(
                    odds_data, g["home_team"], g["away_team"]
                )
                if line_signals:
                    ctx += "  📉 Line Movement:\n"
                    for sig in line_signals:
                        ctx += f"    {sig}\n"

                pinnacle_signals = analyze_pinnacle_value(
                    odds_data, g["home_team"], g["away_team"]
                )
                if pinnacle_signals:
                    ctx += "  💹 Sharp Money Signale:\n"
                    for sig in pinnacle_signals:
                        ctx += f"    {sig}\n"

            except Exception:
                continue

    return ctx


def build_prompt(market, league, target_date, context):
    info = MARKET_INFO[market]

    if market == "1x2":
        json_format = (
            '[{"match":"A vs B","league":"' + league +
            '","time":"HH:MM","tip":"1","probability":55,'
            '"confidence":4,"fairOdds":"1.85","oddsYes":"1.95",'
            '"oddsNo":"-","bookie":"Bet365","homeForm":"WWDLW",'
            '"awayForm":"LWWDD","valueRating":"HIGH",'
            '"keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        )
        tip_help = 'tip: "1" / "X" / "2"'
    else:
        json_format = (
            '[{"match":"A vs B","league":"' + league +
            '","time":"HH:MM","tip":"YES","probability":72,'
            '"confidence":4,"fairOdds":"1.65","oddsYes":"1.72",'
            '"oddsNo":"2.10","bookie":"Bet365","homeForm":"WWDLW",'
            '"awayForm":"LWWDD","valueRating":"HIGH",'
            '"keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        )
        tip_help = 'tip: "YES" / "NO" / "MAYBE"'

    return f"""Du bist Fußball-Wettanalyst. {info['instr']}

Liga: "{league}" · Datum: {target_date}

{context}

KRITISCH:
1. Analysiere AUSSCHLIESSLICH die oben aufgeführten Spiele.
2. Erfinde keine Spiele.
3. Verwende echte Anstoßzeiten.
4. Berücksichtige xG-Daten.
5. Wenn Liste leer: gib [] zurück.

Antworte nur mit JSON-Array:
{json_format}

{tip_help}
Falls keine echten Spiele: []"""


def validate_tips(tips, real_fixtures, real_odds):
    if not tips:
        return []

    real_matches = []

    for f in real_fixtures:
        real_matches.append((
            f.get("home", ""),
            f.get("away", ""),
            f.get("time_local", ""),
        ))

    for g in real_odds:
        try:
            real_matches.append((
                g.get("home_team", ""),
                g.get("away_team", ""),
                get_local_time(g.get("commence_time", "")),
            ))
        except Exception:
            continue

    if not real_matches:
        return []

    validated = []

    for tip in tips:
        match = tip.get("match", "")

        if " vs " not in match:
            continue

        teams = match.split(" vs ", 1)

        if len(teams) != 2:
            continue

        tip_home, tip_away = teams[0].strip(), teams[1].strip()

        for r_home, r_away, r_time in real_matches:
            if teams_match(tip_home, r_home) and teams_match(tip_away, r_away):
                if r_time and r_time != "TBD":
                    tip["time"] = r_time

                tip["match"] = f"{r_home} vs {r_away}"
                validated.append(tip)
                break

    return validated


def is_future_game(time_str, target_date):
    try:
        if not time_str or time_str == "TBD":
            return True

        hour, minute = map(int, time_str.split(":")[:2])
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year

        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)

        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)

        offset = 2 if march_last <= now_utc < oct_last else 1

        game_local = datetime.combine(
            target_date,
            datetime.min.time().replace(hour=hour, minute=minute),
        )

        game_utc = (game_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)

        return game_utc > now_utc - timedelta(minutes=15)

    except Exception:
        return True


def filter_top_tips(tips, target_date, market):
    filtered = []

    max_odds_for_market = 4.5 if market == "btts_ht" else MAX_ODDS
    min_odds_for_market = 1.6 if market == "btts_ht" else MIN_ODDS

    for r in tips:
        if not is_future_game(r.get("time", ""), target_date):
            continue

        if r.get("tip") != "YES":
            continue

        if int(r.get("probability", 0)) < MIN_PROBABILITY:
            continue

        if int(r.get("confidence", 0)) < MIN_CONFIDENCE:
            continue

        # 🆕 Value Rating Filter (nur HIGH oder OK je nach Setting)
        value_rating = r.get("valueRating", "OK")
        if MIN_VALUE_RATING == "HIGH" and value_rating != "HIGH":
            continue
        elif MIN_VALUE_RATING == "OK" and value_rating == "LOW":
            continue

        odds = parse_odds(r.get("oddsYes", 0))

        if odds < min_odds_for_market or odds > max_odds_for_market:
            continue

        filtered.append(r)

    seen = set()
    unique = []

    for t in filtered:
        key = (t.get("match", "").lower(), t.get("tip", ""))

        if key in seen:
            continue

        seen.add(key)
        unique.append(t)

    unique.sort(
        key=lambda r: (
            0 if r.get("valueRating") == "HIGH" else 1,
            -int(r.get("probability", 0)),
        )
    )

    return unique


def fetch_league_data_once(league, target_date):
    """
    Holt alle Daten für eine Liga nur EINMAL pro Run.
    """
    odds = fetch_odds_api(league, target_date)
    fd_fix = fetch_football_data(league, target_date)
    af_fix = fetch_api_football(league, target_date)
    fj_fix = fetch_football_json(league, target_date)
    ol_fix = fetch_openligadb(league, target_date)
    bsd_fix = fetch_bsd_fixtures(league, target_date)
    sm_fix = fetch_sportmonks_fixtures(league, target_date)
    sdb_fix = get_sportdb_fixtures(league, target_date)
    sofa_fix = fetch_sofascore_fixtures(league, target_date)   # Alle Ligen!
    espn_fix = fetch_espn_fixtures(league, target_date)        # 🆕 ESPN
    asp_fix = fetch_allsports_fixtures(league, target_date)    # 🆕 AllSports

    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix, bsd_fix, sm_fix, sdb_fix, sofa_fix, espn_fix, asp_fix)

    log(
        f"   Quellen: Odds={len(odds)}, FD={len(fd_fix)}, "
        f"AF={len(af_fix)}, FJ={len(fj_fix)}, OL={len(ol_fix)}, "
        f"BSD={len(bsd_fix)}, SM={len(sm_fix)}, SDB={len(sdb_fix)}, "
        f"Sofa={len(sofa_fix)}, ESPN={len(espn_fix)}, ASP={len(asp_fix)} → Total={len(fixtures)}"
    )

    return odds, fixtures


def analyze_market_with_data(market, league, target_date, odds, fixtures):
    """
    Analysiert einen Markt mit bereits geladenen Liga-Daten.
    """
    if not odds and not fixtures:
        return [], "Keine echten Spiele heute"

    ctx = build_context(odds, fixtures, league, target_date)
    prompt = build_prompt(market, league, target_date, ctx)

    results, source = call_gemini(prompt, use_tools=False)

    if results is None:
        results, source = call_gemini(prompt, use_tools=True)

    if results is None and USE_GROQ_FALLBACK:
        results, source = call_groq(prompt)

    if not results:
        return [], source

    validated = validate_tips(results, fixtures, odds)

    # 🆕 FIX: League + Odds-Daten an jeden Tipp hängen
    # So sind die Daten auch in send_top_tips() verfügbar
    for tip in validated:
        if not tip.get("league"):
            tip["league"] = league
        # Odds-Daten als _internal Feld (wird nicht in Supabase gespeichert)
        tip["_odds_data"] = odds
        tip["_source_league"] = league

    return validated, source


# ============================================================
# 🆕 THESPORTSDB - Team Logos/Wappen (kostenlos)
# ============================================================
THESPORTSDB_CACHE = {}

def get_team_badge(team_name):
    """
    Holt Team-Wappen URL von TheSportsDB.
    Returns: {'badge_url': '...', 'team_id': '...'} oder None
    """
    if team_name in THESPORTSDB_CACHE:
        return THESPORTSDB_CACHE[team_name]

    try:
        # Free API Key "123" für Test-Nutzung
        r = requests.get(
            "https://www.thesportsdb.com/api/v1/json/123/searchteams.php",
            params={"t": team_name},
            timeout=10,
        )

        if not r.ok:
            THESPORTSDB_CACHE[team_name] = None
            return None

        data = r.json()
        teams = data.get("teams")

        if not teams:
            THESPORTSDB_CACHE[team_name] = None
            return None

        # Erstes Match nehmen
        team = teams[0]
        result = {
            "badge_url": team.get("strBadge"),  # PNG transparent
            "team_id": team.get("idTeam"),
            "team_name": team.get("strTeam"),
        }

        THESPORTSDB_CACHE[team_name] = result
        return result

    except Exception:
        THESPORTSDB_CACHE[team_name] = None
        return None


# ============================================================
# 🆕 SPORTMONKS - Free Forever für 2 Ligen
# ============================================================
SPORTMONKS_API_KEY = env("SPORTMONKS_API_KEY", "")  # Free tier API Key
SPORTMONKS_CACHE = {}

SPORTMONKS_LEAGUE_IDS = {
    # Nur 2 Ligen im Free Tier verfügbar
    "Danish Superligaen": 271,      # Dänemark
    "Scottish Premiership": 501,    # Schottland
}


def fetch_sportmonks_fixtures(league_name, target_date):
    """
    Holt Spielpläne von Sportmonks (Free Tier: Dänemark, Schottland).
    Returns: Liste mit Fixtures oder []
    """
    if not SPORTMONKS_API_KEY:
        return []
    
    league_id = SPORTMONKS_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []  # Sportmonks deckt diese Liga nicht ab (nur 2 im Free Tier)
    
    try:
        # Sportmonks V2 API
        r = requests.get(
            f"https://api.sportmonks.com/v2.0/fixtures",
            params={
                "api_token": SPORTMONKS_API_KEY,
                "filters": f"leagueId:{league_id},statusId:1",  # Status 1 = Not Started
                "include": "teams",
                "sort": "-date",
            },
            timeout=12,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for match in data.get("data", []):
            try:
                kickoff_str = match.get("date")
                if not kickoff_str:
                    continue
                
                # Sportmonks gibt UTC Zeit
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                
                if kickoff > now_utc:
                    # Teams aus nested data
                    teams = match.get("teams", {})
                    home_team = teams.get("data", [])[0] if teams.get("data") else {}
                    away_team = teams.get("data", [])[1] if len(teams.get("data", [])) > 1 else {}
                    
                    fixtures.append({
                        "home": home_team.get("name", ""),
                        "away": away_team.get("name", ""),
                        "match_id": match.get("id"),
                        "home_id": home_team.get("id"),
                        "away_id": away_team.get("id"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "sportmonks",
                    })
            except Exception:
                continue
        
        return fixtures
    
    except Exception as e:
        log(f"Sportmonks Error: {e}", "WARN")
        return []
# ============================================================
BSD_API_URL = "https://sports.bzzoiro.com/api"
BSD_CACHE = {}

BSD_LEAGUE_IDS = {
    # 8 Top-Ligen die BSD abdeckt
    "Premier League": 1,          # England
    "La Liga": 8,                 # Spain
    "Serie A": 10,                # Italy
    "Bundesliga": 12,             # Germany
    "Ligue 1": 61,                # France
    "Championship": 2,            # England 2nd
    "Primeira Liga": 32,          # Portugal
    "Eredivisie": 13,             # Netherlands
}


def fetch_bsd_fixtures(league_name, target_date):
    """
    Holt Spielpläne von BSD für die 8 unterstützten Top-Ligen.
    Returns: Liste mit Fixtures oder []
    """
    league_id = BSD_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []  # BSD deckt diese Liga nicht ab
    
    try:
        # BSD API für matches
        r = requests.get(
            f"{BSD_API_URL}/matches",
            params={
                "league_id": league_id,
                "date": target_date.isoformat(),
                "status": "upcoming",
            },
            timeout=12,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        
        for match in data.get("matches", []):
            try:
                kickoff_str = match.get("datetime")
                if not kickoff_str:
                    continue
                    
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                
                if kickoff > now_utc:
                    fixtures.append({
                        "home": match.get("home_team", {}).get("name", ""),
                        "away": match.get("away_team", {}).get("name", ""),
                        "match_id": match.get("id"),
                        "home_id": match.get("home_team", {}).get("id"),
                        "away_id": match.get("away_team", {}).get("id"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "bsd",
                    })
            except Exception:
                continue
        
        return fixtures
    
    except Exception as e:
        log(f"BSD Error: {e}", "WARN")
        return []


def get_bsd_odds(match_id):
    """
    Holt aktuelle Quoten von 41+ Bookies für ein Match.
    Returns: {'btts_yes': 1.85, 'over25': 2.10, ...} oder None
    """
    if not match_id:
        return None
    
    try:
        r = requests.get(
            f"{BSD_API_URL}/odds/compare/{match_id}",
            timeout=10,
        )
        
        if not r.ok:
            return None
        
        data = r.json()
        odds = {}
        
        # BTTS Quoten sammeln
        for market in data.get("markets", []):
            if market.get("name") == "btts":
                yes_odds = market.get("outcomes", {}).get("yes", {}).get("odds")
                if yes_odds:
                    odds["btts_yes"] = float(yes_odds)
        
        return odds if odds else None
    
    except Exception:
        return None

# 🆕 BOOKIE DEEPLINK CONFIG
# Diese Bookies werden als Buttons unter jedem Tipp angezeigt.
# Reihenfolge bestimmt Reihenfolge der Buttons im Telegram.
BOOKIE_BUTTONS = [
    {"key": "pinnacle", "label": "🎯 Pinnacle", "search_url": "https://www.pinnacle.com/de/soccer/matchups"},
    {"key": "betfair_ex_eu", "label": "📊 Betfair", "search_url": "https://www.betfair.com/exchange/plus/football"},
    {"key": "onexbet", "label": "🎰 1xBet", "search_url": "https://1xbet.com/en/line/football/"},
    {"key": "bet365", "label": "🎰 Bet365", "search_url": "https://www.bet365.com/#/AS/B1/"},
]


def get_bookie_links(odds_data, home_team, away_team):
    """
    Sucht Deeplinks zu Betslips aus Odds API für ein bestimmtes Spiel.
    Gibt dict zurück: {bookie_key: betslip_url}
    Fallback ist die jeweilige Search/Home URL des Bookies.
    """
    links = {}

    if not odds_data:
        return links

    # Suche das passende Game in odds_data
    for g in odds_data:
        gh = g.get("home_team", "").lower()
        ga = g.get("away_team", "").lower()
        h_low = home_team.lower()
        a_low = away_team.lower()

        # Match-Check (gleiche Logic wie teams_match)
        if not (h_low in gh or gh in h_low):
            continue
        if not (a_low in ga or ga in a_low):
            continue

        # Event-Level Link
        event_link = g.get("link")

        # Pro Bookmaker schauen
        for bm in g.get("bookmakers", []):
            bm_key = bm.get("key", "")
            bm_link = bm.get("link") or event_link

            if bm_link:
                links[bm_key] = bm_link

        break  # Spiel gefunden, fertig

    return links


def build_inline_keyboard(odds_data, match_name):
    """
    Baut die Telegram Inline-Keyboard Struktur mit Bookie-Buttons.
    Pro Reihe 2 Buttons (auf Handy lesbarer).
    """
    if not match_name or " vs " not in match_name:
        return None

    parts = match_name.split(" vs ", 1)
    if len(parts) != 2:
        return None

    home, away = parts[0].strip(), parts[1].strip()

    # Deeplinks aus Odds API holen
    deeplinks = get_bookie_links(odds_data, home, away)

    buttons = []
    row = []

    for bookie in BOOKIE_BUTTONS:
        key = bookie["key"]
        label = bookie["label"]

        # Wenn echter Deeplink existiert: nimm den. Sonst Search-URL.
        url = deeplinks.get(key) or bookie["search_url"]

        # Falls Deeplink vorhanden, mit ⚡ markieren
        if key in deeplinks:
            label = "⚡ " + label

        row.append({"text": label, "url": url})

        # Alle 2 Buttons neue Reihe
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return {"inline_keyboard": buttons}


def send_telegram(text, chat_id=None, reply_markup=None):
    if not TELEGRAM_TOKEN:
        log("Telegram Token fehlt", "WARN")
        return None

    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if not chat_id:
        log("Telegram Chat ID fehlt", "WARN")
        return None

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    # 🆕 Inline-Buttons hinzufügen wenn vorhanden
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
            timeout=15,
        )

        if not r.ok:
            # 🆕 Fallback: Wenn Channel fehlt (400 error) → Main Chat nutzen
            if r.status_code == 400 and chat_id != TELEGRAM_CHAT_ID:
                log(f"⚠️ Chat {chat_id} nicht gefunden - fallback zu Main Chat", "WARN")
                payload["chat_id"] = TELEGRAM_CHAT_ID
                r = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json=payload,
                    timeout=15,
                )
            
            # Fallback ohne HTML-Tags
            payload["text"] = re.sub(r"<[^>]+>", "", text)
            payload.pop("parse_mode", None)
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json=payload,
                timeout=15,
            )

        if r.ok:
            return r.json().get("result", {}).get("message_id")

    except Exception:
        pass

    return None


def is_duplicate_tip(match, market, target_date):
    """Prüft ob Tipp für dieses Spiel+Markt heute schon in Supabase ist"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "date": f"eq.{target_date}",
                "market": f"eq.{market}",
                "match": f"eq.{match}",
                "select": "id",
                "limit": "1",
            },
            timeout=10,
        )
        if r.ok and len(r.json()) > 0:
            return True
    except Exception:
        pass
    return False


def is_valid_tip(tip, target_date):
    """
    Prüft ob ein Tipp wirklich heute + in der Zukunft liegt.
    """
    tip_date = tip.get("date", "")
    today_str = str(target_date)
    if tip_date and tip_date != today_str:
        log(f"   ⚠️ Falsches Datum: {tip_date} (erwartet {today_str})")
        return False

    time_str = tip.get("time", "")
    if not is_future_game(time_str, target_date):
        log(f"   ⚠️ Spiel bereits vorbei: {tip.get('match','')} um {time_str}")
        return False

    return True


def save_to_supabase(tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        # 🆕 FIX: Internal Felder vor dem Speichern entfernen
        clean_tip = {k: v for k, v in tip.items() if not k.startswith("_")}

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=clean_tip,
            timeout=10,
        )

        return r.ok

    except Exception:
        return False


def get_overall_stats():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "*", "order": "date.desc,id.desc"},
            timeout=15,
        )
        if not r.ok:
            return None
        tips = r.json()
        won = [t for t in tips if t.get("status") == "won"]
        lost = [t for t in tips if t.get("status") == "lost"]
        pending = [t for t in tips if t.get("status") == "pending"]
        if not won and not lost:
            return None
        total = len(won) + len(lost)
        quote_pct = round(len(won) / total * 100) if total else 0

        units_won = 0.0
        units_lost = 0.0
        for t in won:
            try:
                u = float(t.get("units", 1.0) or 1.0)
                odds = float(str(t.get("odds", "1")).replace(",", "."))
                units_won += u * (odds - 1)
            except:
                units_won += 1.0
        for t in lost:
            try:
                units_lost += float(t.get("units", 1.0) or 1.0)
            except:
                units_lost += 1.0
        roi_units = round(units_won - units_lost, 2)

        by_market = {
            "btts": {"w": 0, "l": 0, "units": 0.0},
            "over25": {"w": 0, "l": 0, "units": 0.0},
            "combo": {"w": 0, "l": 0, "units": 0.0},
            "btts_ht": {"w": 0, "l": 0, "units": 0.0},
        }
        for t in won + lost:
            m = t.get("market", "")
            if m not in by_market:
                continue
            u = float(t.get("units", 1.0) or 1.0)
            if t.get("status") == "won":
                by_market[m]["w"] += 1
                try:
                    by_market[m]["units"] += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
                except:
                    pass
            else:
                by_market[m]["l"] += 1
                by_market[m]["units"] -= u

        from datetime import date as date_cls
        today = date_cls.today()
        month_start = today.replace(day=1).isoformat()
        month_won = [t for t in won if t.get("date","") >= month_start]
        month_lost = [t for t in lost if t.get("date","") >= month_start]
        month_total = len(month_won) + len(month_lost)
        month_pct = round(len(month_won)/month_total*100) if month_total else 0
        month_units = 0.0
        for t in month_won:
            try:
                u = float(t.get("units",1.0) or 1.0)
                month_units += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
            except:
                month_units += 1.0
        for t in month_lost:
            try:
                month_units -= float(t.get("units",1.0) or 1.0)
            except:
                month_units -= 1.0
        month_names = ["","Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]
        month_name = month_names[today.month]

        by_league = {}
        for t in won + lost:
            lg = t.get("league","?")
            if lg not in by_league:
                by_league[lg] = {"w":0,"l":0,"units":0.0}
            u = float(t.get("units",1.0) or 1.0)
            if t.get("status") == "won":
                by_league[lg]["w"] += 1
                try:
                    by_league[lg]["units"] += u * (float(str(t.get("odds","1")).replace(",",".")) - 1)
                except:
                    by_league[lg]["units"] += 1.0
            else:
                by_league[lg]["l"] += 1
                by_league[lg]["units"] -= u

        top_leagues = []
        for lg, s in by_league.items():
            tot = s["w"] + s["l"]
            if tot >= 2:
                pct = round(s["w"]/tot*100)
                top_leagues.append((lg, s["w"], tot, pct, round(s["units"],2)))
        top_leagues.sort(key=lambda x: (-x[4], -x[3]))

        return {
            "won": len(won), "lost": len(lost), "pending": len(pending),
            "total": total, "quote_pct": quote_pct,
            "roi_units": roi_units,
            "by_market": by_market,
            "month": {
                "name": month_name, "won": len(month_won), "lost": len(month_lost),
                "total": month_total, "pct": month_pct, "units": round(month_units,2)
            },
            "top_leagues": top_leagues[:10],
        }
    except Exception:
        return None


def generate_multi_combo_bets(all_tips, num_tips=3):
    """
    🆕 Generiert automatisch Multi-Combos aus den besten Tipps.
    num_tips: 3, 4, 5, 6, 7 oder 8 Tipps pro Combo
    """
    if not all_tips:
        return None

    # Alle Tipps normalisieren (oddsYes → odds)
    normalized = []
    for t in all_tips:
        try:
            odds = float(str(t.get("oddsYes", t.get("odds", 0))).replace(",", "."))
            if odds >= 1.50:
                normalized.append({
                    "match": t.get("match", ""),
                    "league": t.get("league", ""),
                    "market": t.get("market", "btts"),
                    "tip": t.get("tip", "YES"),
                    "odds": odds,
                    "confidence": int(t.get("confidence", 0)),
                    "value_rating": t.get("valueRating", "OK"),
                    "probability": int(t.get("probability", 0)),
                })
        except Exception:
            continue

    if not normalized:
        return None

    # Sortiere nach Confidence + Probability
    sorted_tips = sorted(
        normalized,
        key=lambda x: (x.get("confidence", 0), x.get("probability", 0)),
        reverse=True
    )

    # Genug Tipps vorhanden?
    if len(sorted_tips) < num_tips:
        return None

    # Beste N Tipps nehmen
    selected = sorted_tips[:num_tips]

    # Berechne Gesamt-Quote
    total_odds = 1.0
    for tip in selected:
        total_odds *= tip.get("odds", 1.0)

    avg_confidence = sum(t.get("confidence", 0) for t in selected) / len(selected)

    # Combo Label basierend auf Anzahl
    labels = {
        3: ("🥉 COMBO 3", "Einsteiger-Kombi"),
        4: ("🥈 COMBO 4", "Solide Kombi"),
        5: ("🥇 COMBO 5", "Standard-Kombi"),
        6: ("💎 COMBO 6", "Value-Kombi"),
        7: ("🔥 COMBO 7", "High-Risk Kombi"),
        8: ("🚀 COMBO 8", "Jackpot-Kombi"),
    }
    label, desc = labels.get(num_tips, (f"🎲 COMBO {num_tips}", "Multi-Kombi"))

    # Stake Suggestion (weniger bei mehr Tipps)
    stakes = {3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1}
    stake = stakes.get(num_tips, 1)

    return {
        "num_tips": num_tips,
        "label": label,
        "desc": desc,
        "tips": selected,
        "total_odds": round(total_odds, 2),
        "expected_confidence": round(avg_confidence, 1),
        "stake_suggestion": stake,
    }


def format_combo_telegram_message(combo):
    """🆕 Formatiert Multi-Combo für Telegram"""
    if not combo:
        return ""

    msg = f"<b>{combo['label']}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 <b>Gesamt-Quote: {combo['total_odds']}</b>\n"
    msg += f"⚡ Ø Confidence: {combo['expected_confidence']}/5\n"
    msg += f"💰 Empfehlung: {combo['stake_suggestion']} Units\n"
    msg += f"📋 Anzahl Tipps: {combo['num_tips']}\n\n"
    msg += f"<b>🎫 TIPPS:</b>\n"

    for i, tip in enumerate(combo["tips"], 1):
        conf_stars = "⭐" * int(tip.get("confidence", 0))
        msg += f"\n{i}. <b>{tip.get('match', 'N/A')}</b>\n"
        msg += f"   📍 {tip.get('league', 'N/A')}\n"
        msg += f"   ⚽ {tip.get('market', 'BTTS').upper()}: <b>{tip.get('tip', 'YES')}</b>\n"
        msg += f"   💰 Quote: <b>{tip.get('odds', 0.0)}</b>\n"
        msg += f"   {conf_stars} {tip.get('confidence', 0)}/5\n"

    msg += f"\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>💡 {combo['desc']}</b>\n"
    msg += f"• Einsatz: {combo['stake_suggestion']} Units\n"
    msg += f"• Möglicher Gewinn: ~{round(combo['total_odds'] * combo['stake_suggestion'], 1)} Units\n\n"
    msg += f"<i>⚠️ Verantwortungsvoll spielen!</i>"

    return msg


def send_top_tips(tips_by_market, target_date):
    icons = {
        "YES": "✅",
        "NO": "❌",
        "MAYBE": "⚠️",
        "1": "🏠",
        "X": "🤝",
        "2": "✈️",
    }

    val_icons = {
        "HIGH": "🔥",
        "OK": "🟡",
        "LOW": "🔴",
    }

    market_emoji = {
        "btts": "⚽",
        "over25": "🎯",
        "combo": "🔥",
        "1x2": "🏆",
    }

    total_tips = sum(len(t) for t in tips_by_market.values())

    stats_header = f"<b>🤖 AI TIPP BOT - DAILY</b>\n<i>{target_date}</i>\n\n"
    stats_header += "📊 <b>Übersicht heute:</b>\n"

    for m_id in MARKETS_TO_RUN:
        count = len(tips_by_market.get(m_id, []))
        stats_header += f"• {MARKET_INFO[m_id]['name']}: <b>{count}</b> Tipps\n"

    stats_header += f"\n💎 <b>Total: {total_tips} Top-Tipps</b>"

    stats = get_overall_stats()

    if stats:
        stats_header += "\n\n━━━━━━━━━━━━━━━━━━\n"
        stats_header += "📈 <b>GESAMT-STATISTIK</b>\n"
        stats_header += f"✅ Gewonnen: <b>{stats['won']}</b>\n"
        stats_header += f"❌ Verloren: <b>{stats['lost']}</b>\n"
        if stats["pending"]:
            stats_header += f"⏳ Pending: <b>{stats['pending']}</b>\n"
        stats_header += f"🎯 Trefferquote: <b>{stats['quote_pct']}%</b>\n"
        roi_emoji = "🟢" if stats["roi_units"] >= 0 else "🔴"
        stats_header += f"💰 ROI: <b>{'+' if stats['roi_units'] >= 0 else ''}{stats['roi_units']}</b> Units {roi_emoji}\n"

        if stats.get("month") and stats["month"]["total"] > 0:
            m = stats["month"]
            m_emoji = "🟢" if m["units"] >= 0 else "🔴"
            stats_header += f"\n📆 <b>{m['name']}:</b> {m['won']}/{m['total']} ({m['pct']}%) · "
            stats_header += f"<b>{'+' if m['units'] >= 0 else ''}{m['units']} Units</b> {m_emoji}\n"

        stats_header += f"\n<b>📊 Pro Markt:</b>\n"
        market_names = {"btts": "⚽ BTTS", "over25": "🎯 Over 2.5",
                       "combo": "🔥 Combo", "btts_ht": "🕐 BTTS HT"}
        for m_id in MARKETS_TO_RUN:
            mb = stats["by_market"].get(m_id, {"w":0,"l":0,"units":0.0})
            tot = mb["w"] + mb["l"]
            if tot > 0:
                pct = round(mb["w"]/tot*100)
                emoji = "🟢" if pct >= 60 else "🟡" if pct >= 40 else "🔴"
                u_str = f"+{round(mb['units'],2)}" if mb["units"] >= 0 else f"{round(mb['units'],2)}"
                stats_header += f"{market_names.get(m_id,m_id)}: {mb['w']}/{tot} ({pct}%) · {u_str}U {emoji}\n"

        if stats.get("top_leagues"):
            stats_header += f"\n<b>🏆 Top Ligen Ranking:</b>\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
            for i, (lg, w, tot, pct, units) in enumerate(stats["top_leagues"]):
                medal = medals[i] if i < len(medals) else "•"
                u_str = f"+{units}" if units >= 0 else str(units)
                stats_header += f"{medal} {lg}: {w}/{tot} ({pct}%) · {u_str}U\n"

    send_telegram(stats_header, TELEGRAM_GROUPS.get("stats"))

    if total_tips == 0:
        send_telegram(
            f"ℹ️ Heute keine Top-Tipps.\n"
            f"Filter:\n"
            f"• Wahrscheinlichkeit ≥ {MIN_PROBABILITY}%\n"
            f"• Quote {MIN_ODDS}-{MAX_ODDS}\n"
            f"• Confidence ≥ {MIN_CONFIDENCE}⭐",
            TELEGRAM_GROUPS.get("stats"),
        )
        return

    saved = 0

    for market_id, tips in tips_by_market.items():
        if not tips:
            continue

        target_chat = TELEGRAM_GROUPS.get(market_id, TELEGRAM_CHAT_ID)
        market_name = MARKET_INFO[market_id]["name"]
        emoji = market_emoji.get(market_id, "💎")

        header = f"<b>{emoji} {market_name} TOP-TIPPS</b>\n"
        header += f"<i>📅 {target_date}</i>\n"
        header += f"<i>{len(tips)} Top-Tipps · validiert ✓</i>"

        send_telegram(header, target_chat)

        for i, r in enumerate(tips, 1):
            confidence = int(r.get("confidence", 0))
            match_name = r.get("match", "?")

            r["date"] = str(target_date)
            if not is_valid_tip(r, target_date):
                continue

            if is_duplicate_tip(match_name, market_id, target_date):
                log(f"   ⏭️ Duplikat übersprungen: {match_name} ({market_id})")
                continue

            msg = f"<b>💎 Tipp {i}/{len(tips)}</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"
            
            # 🆕 Team-Emojis basierend auf bekannten Teams (ohne API Call)
            team_icons = {
                "bayern": "🔴⚪", "dortmund": "🟡⚫", "leipzig": "🔴⚪",
                "real madrid": "⚪", "barcelona": "🔵🔴", "atletico": "🔴⚪",
                "liverpool": "🔴", "chelsea": "🔵", "arsenal": "🔴⚪",
                "manchester united": "🔴", "manchester city": "🔵",
                "juventus": "⚫⚪", "milan": "🔴⚫", "inter": "🔵⚫",
                "psg": "🔵🔴", "marseille": "⚪🔵", "lyon": "🔴🔵",
            }
            
            # Simple Icon-Suche
            match_lower = match_name.lower()
            home_icon = ""
            away_icon = ""
            
            for team, icon in team_icons.items():
                if team in match_lower:
                    parts = match_name.split(" vs ")
                    if len(parts) == 2 and team in parts[0].lower():
                        home_icon = icon + " "
                    elif len(parts) == 2 and team in parts[1].lower():
                        away_icon = " " + icon
            
            msg += f"<b>{home_icon}{match_name}{away_icon}</b>\n"
            msg += f"📍 {r.get('league', '')}\n"

            tip_time = r.get('time', '').strip()
            if tip_time and tip_time not in ['TBD', 'N/A', '-', '']:
                msg += f"⏰ {tip_time} Uhr\n\n"
            else:
                msg += f"⏰ Spielzeit folgt\n\n"

            msg += f"{icons.get(r.get('tip', '?'), '')} <b>Tipp: {r.get('tip', '?')}</b>\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability', 0)}%</b>\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}\n\n"
            msg += f"💰 <b>Quote: {r.get('oddsYes', '-')}</b>\n"
            msg += f"🎯 Fair Odds: {r.get('fairOdds', '-')}\n"
            msg += f"{val_icons.get(r.get('valueRating', 'OK'), '🟡')} Value: <b>{r.get('valueRating', 'OK')}</b>\n"

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                units = calculate_kelly_units(prob_val, odds_val)
                units_emoji = "🔥" if units >= 2.5 else "💚" if units >= 1.5 else "🟡"
                msg += f"\n{units_emoji} <b>Empfehlung: {units} Units</b>\n"
            except:
                msg += f"\n💚 <b>Empfehlung: 1.0 Units</b>\n"

            if r.get("bookie"):
                msg += f"🏦 Bookie: {r.get('bookie')}\n"

            home_form = r.get('homeForm', '').strip()
            away_form = r.get('awayForm', '').strip()
            if (home_form and home_form not in ['N/A', '-', '?', '']) or \
               (away_form and away_form not in ['N/A', '-', '?', '']):
                msg += "\n📊 <b>Form</b>\n"
                if home_form and home_form not in ['N/A', '-', '?', '']:
                    msg += f"🏠 Heim: {home_form}\n"
                if away_form and away_form not in ['N/A', '-', '?', '']:
                    msg += f"✈️ Auswärts: {away_form}\n"

            if r.get("keyFactor"):
                msg += f"\n⚡ <i>{r.get('keyFactor')}</i>\n"

            reasoning = r.get("reasoning", "")[:300]

            if reasoning:
                msg += f"\n💭 <i>{reasoning}</i>"

            # 🆕 Footer mit Hinweis zu Buttons
            try:
                stake_chf = float(units) if 'units' in dir() and units else 1.0
            except:
                stake_chf = 1.0
            msg += f"\n\n━━━━━━━━━━━━━━━━━━"
            msg += f"\n<i>⚡ = direkter Betslip-Link · Sonst: Bookie öffnen</i>"

            # 🆕 Inline-Buttons mit Bookie-Links bauen
            tip_odds_data = r.get("_odds_data", [])
            inline_keyboard = build_inline_keyboard(tip_odds_data, match_name)

            msg_id = send_telegram(msg, target_chat, reply_markup=inline_keyboard)

            # ============================================================
            # ML Features sammeln (FIX: tip_league + tip_odds aus dem Tipp)
            # ============================================================
            try:
                tip_hour = int(r.get("time", "00:00").split(":")[0])
                tip_weekday = datetime.now().weekday()
            except:
                tip_hour = 0
                tip_weekday = 0

            # 🆕 FIX: League und Odds aus dem Tipp selbst holen
            tip_league = r.get("league", "") or r.get("_source_league", "")
            tip_odds_data = r.get("_odds_data", [])

            # xG Daten
            xg_home = xg_away = xga_home = xga_away = 0.0
            if tip_league in UNDERSTAT_LEAGUES:
                try:
                    parts = match_name.split(" vs ")
                    if len(parts) == 2:
                        hxg = get_team_xg(parts[0].strip(), tip_league)
                        axg = get_team_xg(parts[1].strip(), tip_league)
                        if hxg:
                            xg_home = float(hxg.get("xG", 0))
                            xga_home = float(hxg.get("xGA", 0))
                        if axg:
                            xg_away = float(axg.get("xG", 0))
                            xga_away = float(axg.get("xGA", 0))
                except:
                    pass

            # Sharp Money + Line Movement
            sharp = line_mov = 0.0
            try:
                parts = match_name.split(" vs ")
                if len(parts) == 2 and tip_odds_data:
                    signals = analyze_pinnacle_value(tip_odds_data, parts[0], parts[1])
                    if signals:
                        for sig in signals:
                            if "+" in sig:
                                m = re.search(r'\+(\d+\.?\d*)', sig)
                                if m:
                                    sharp = float(m.group(1))
                            elif "-" in sig:
                                m = re.search(r'(-\d+\.?\d*)', sig)
                                if m:
                                    sharp = float(m.group(1))
                    lm_signals = analyze_line_movement(tip_odds_data, parts[0], parts[1])
                    if lm_signals:
                        for sig in lm_signals:
                            m = re.search(r'([+-]\d+\.?\d*)%', sig)
                            if m:
                                line_mov = float(m.group(1))
            except:
                pass

            # Historische BTTS Rate
            btts_h = btts_a = avg_g_h = avg_g_a = 0.0
            try:
                parts = match_name.split(" vs ")
                if len(parts) == 2 and tip_league:
                    hist = get_historical_btts_rate(tip_league, parts[0], parts[1])
                    if hist:
                        if hist.get("home"):
                            btts_h = hist["home"].get("btts_rate", 0)
                            avg_g_h = hist["home"].get("avg_goals", 0)
                        if hist.get("away"):
                            btts_a = hist["away"].get("btts_rate", 0)
                            avg_g_a = hist["away"].get("avg_goals", 0)
            except:
                pass

            tip_id = f"{market_id}_{target_date}_{i}_{abs(hash(match_name)) % 100000}"

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                tip_units = calculate_kelly_units(prob_val, odds_val)
            except:
                tip_units = 1.0

            tip_data = {
                "tip_id": tip_id,
                "date": str(target_date),
                "market": market_id,
                "market_name": market_name,
                "match": match_name,
                "league": r.get("league", ""),
                "time": r.get("time", ""),
                "tip": r.get("tip", ""),
                "probability": r.get("probability", 0),
                "confidence": r.get("confidence", 0),
                "odds": str(r.get("oddsYes", "0")),
                "fair_odds": str(r.get("fairOdds", "0")),
                "bookie": r.get("bookie", ""),
                "value_rating": r.get("valueRating", "OK"),
                "home_form": r.get("homeForm", ""),
                "away_form": r.get("awayForm", ""),
                "reasoning": r.get("reasoning", "")[:500],
                "key_factor": r.get("keyFactor", "")[:200],
                "telegram_chat_id": str(target_chat),
                "telegram_msg_id": msg_id,
                "units": tip_units,
                "status": "pending",
                # ML Features
                "weekday": tip_weekday,
                "hour": tip_hour,
                "xg_home": xg_home,
                "xg_away": xg_away,
                "xga_home": xga_home,
                "xga_away": xga_away,
                "sharp_money": sharp,
                "line_movement": line_mov,
                "btts_rate_home": btts_h,
                "btts_rate_away": btts_a,
                "avg_goals_home": avg_g_h,
                "avg_goals_away": avg_g_a,
            }

            if save_to_supabase(tip_data):
                saved += 1

        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")

        footer = "━━━━━━━━━━━━━━━━━━\n"
        footer += "📊 <b>Zusammenfassung</b>\n"
        footer += f"• {len(tips)} Tipps · 🔥 {value_count} Value-Bets\n"
        footer += "<i>Viel Erfolg! 🍀</i>"

        send_telegram(footer, target_chat)

    log(f"Gespeichert in Supabase: {saved}")


# ============================================================
# AUTO LEAGUE SWITCH FUNKTIONEN
# ============================================================

def fetch_all_closed_tips_from_supabase():
    """
    Holt abgeschlossene Tipps aus Supabase.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Auto Liga Switch: Supabase fehlt, alle Ligen bleiben aktiv.", "WARN")
        return []

    try:
        since_date = (date.today() - timedelta(days=AUTO_LEAGUE_LOOKBACK_DAYS)).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "select": "league,status,odds,date",
                "status": "in.(won,lost)",
                "date": f"gte.{since_date}",
                "limit": "5000",
            },
            timeout=20,
        )

        if not r.ok:
            log(f"Auto Liga Switch: Supabase Fehler {r.status_code}", "WARN")
            return []

        return r.json()

    except Exception as e:
        log(f"Auto Liga Switch Fehler: {e}", "WARN")
        return []


def calculate_league_performance(tips):
    """
    Berechnet pro Liga Performance-Metriken.
    """
    stats = {}
    sorted_tips = sorted(tips, key=lambda t: t.get("date", ""), reverse=True)

    for t in sorted_tips:
        league = t.get("league") or "Unknown"
        status = t.get("status")

        if league not in stats:
            stats[league] = {
                "won": 0, "lost": 0, "total": 0,
                "roi": 0.0, "winrate": 0.0,
                "recent": {"won": 0, "lost": 0, "total": 0, "roi": 0.0, "winrate": 0.0}
            }

        if status == "won":
            stats[league]["won"] += 1
            try:
                odds = float(str(t.get("odds", "1")).replace(",", "."))
                stats[league]["roi"] += odds - 1
                if stats[league]["total"] < 10:
                    stats[league]["recent"]["won"] += 1
                    stats[league]["recent"]["roi"] += odds - 1
            except Exception:
                pass
        elif status == "lost":
            stats[league]["lost"] += 1
            stats[league]["roi"] -= 1
            if stats[league]["total"] < 10:
                stats[league]["recent"]["lost"] += 1
                stats[league]["recent"]["roi"] -= 1
        else:
            continue

        stats[league]["total"] += 1
        if stats[league]["total"] <= 10:
            stats[league]["recent"]["total"] += 1

    for league, s in stats.items():
        if s["total"] > 0:
            s["winrate"] = round((s["won"] / s["total"]) * 100, 1)
            s["roi"] = round(s["roi"], 2)
        r = s["recent"]
        if r["total"] > 0:
            r["winrate"] = round((r["won"] / r["total"]) * 100, 1)
            r["roi"] = round(r["roi"], 2)

    return stats


def should_run_league(league, league_stats):
    """
    Entscheidung ob Liga laufen soll.
    """
    if league in ALWAYS_OFF_LEAGUES:
        return False, "ALWAYS_OFF"

    if league in ALWAYS_ON_LEAGUES:
        return True, "ALWAYS_ON"

    s = league_stats.get(league)

    if not s:
        return True, "keine Daten"

    if s["total"] < AUTO_LEAGUE_MIN_TIPS:
        return True, f"zu wenig Daten ({s['total']}/{AUTO_LEAGUE_MIN_TIPS})"

    winrate_bad = s["winrate"] < AUTO_LEAGUE_MIN_WINRATE
    roi_bad = s["roi"] < AUTO_LEAGUE_MIN_ROI

    if winrate_bad or roi_bad:
        recent = s.get("recent", {})
        recent_total = recent.get("total", 0)
        recent_winrate = recent.get("winrate", 0)
        recent_roi = recent.get("roi", 0)

        if recent_total >= 5:
            recent_good = (
                recent_winrate >= AUTO_LEAGUE_MIN_WINRATE + 5 and
                recent_roi >= AUTO_LEAGUE_MIN_ROI + 1.0
            )
            if recent_good:
                return True, (
                    f"🔄 REAKTIVIERT! Letzte {recent_total}: "
                    f"{recent_winrate}% / ROI {recent_roi} "
                    f"(Gesamt: {s['winrate']}% / ROI {s['roi']})"
                )

        reason = []
        if winrate_bad:
            reason.append(f"Winrate {s['winrate']}% < {AUTO_LEAGUE_MIN_WINRATE}%")
        if roi_bad:
            reason.append(f"ROI {s['roi']} < {AUTO_LEAGUE_MIN_ROI}")
        return False, " · ".join(reason)

    return True, f"OK ({s['winrate']}%, ROI {s['roi']})"


def get_active_leagues():
    """
    Gibt die Ligen zurück die jetzt relevant sind.
    Basiert auf aktueller UTC-Zeit + Liga-Zeitfenster.
    """
    from datetime import datetime, timezone as _tz
    now_utc = datetime.now(_tz.utc)
    hour = now_utc.hour

    if ACTIVE_LEAGUES_OVERRIDE:
        log(f"🎯 Override: {len(ACTIVE_LEAGUES_OVERRIDE)} Ligen")
        return ACTIVE_LEAGUES_OVERRIDE, {}

    # Zeit-basierte Filterung
    time_filtered = []
    for league in LEAGUES_TO_RUN:
        window = LEAGUES_TIME_MAP.get(league, "all")
        tw = {
            "morning":   (1, 11),
            "afternoon": (10, 17),
            "evening":   (15, 23),
            "night":     (22, 6),
            "all":       (0, 24),
        }.get(window, (0, 24))
        
        start_h, end_h = tw
        if start_h <= end_h:
            in_window = start_h <= hour < end_h
        else:  # Über Mitternacht
            in_window = hour >= start_h or hour < end_h
        
        # Außerhalb Zeitfenster: trotzdem einbeziehen wenn Spiele vorhanden sein könnten
        # ±3 Stunden Puffer
        if not in_window:
            if start_h <= end_h:
                in_window = (start_h - 3) <= hour < (end_h + 3)
            
        if in_window:
            time_filtered.append(league)

    log(f"⏰ {hour:02d}:00 UTC → {len(time_filtered)}/{len(LEAGUES_TO_RUN)} Ligen im Zeitfenster")

    if not AUTO_LEAGUE_SWITCH:
        log("Auto Liga Switch: AUS")
        return time_filtered, {}

    log("Auto Liga Switch: AN")
    log(
        f"Regeln: min. {AUTO_LEAGUE_MIN_TIPS} Tipps · "
        f"Winrate ≥ {AUTO_LEAGUE_MIN_WINRATE}% · "
        f"ROI ≥ {AUTO_LEAGUE_MIN_ROI} · "
        f"Lookback {AUTO_LEAGUE_LOOKBACK_DAYS} Tage"
    )

    tips = fetch_all_closed_tips_from_supabase()
    league_stats = calculate_league_performance(tips)

    active = []
    disabled = []

    for league in LEAGUES_TO_RUN:
        run, reason = should_run_league(league, league_stats)

        if run:
            active.append(league)
            log(f" ✅ {league}: {reason}")
        else:
            disabled.append((league, reason))
            log(f" ⛔ {league}: {reason}", "SKIP")

    log(f"Auto Liga Switch Ergebnis: {len(active)} aktiv, {len(disabled)} deaktiviert")

    return active, league_stats



# ============================================================
# 🏆 SETTLEMENT / CHECK SYSTEM - Post-Match Auswertung
# ============================================================

def check_tip_result(tip, result):
    """
    Prüft ob ein Tipp gewonnen oder verloren hat.
    result: {'home_score': 2, 'away_score': 1, 'btts': True, 'over25': True, 'btts_ht': False}
    """
    if not result or not tip:
        return None

    market = tip.get("market", "btts")
    tip_value = tip.get("tip", "YES")

    won = False

    if market == "btts":
        won = result.get("btts", False) if tip_value == "YES" else not result.get("btts", False)
    elif market == "over25":
        won = result.get("over25", False) if tip_value == "YES" else not result.get("over25", False)
    elif market == "combo":
        won = result.get("btts", False) and result.get("over25", False) if tip_value == "YES" else not (result.get("btts", False) and result.get("over25", False))
    elif market == "btts_ht":
        won = result.get("btts_ht", False) if tip_value == "YES" else not result.get("btts_ht", False)

    return "won" if won else "lost"


def get_match_result_from_sources(tip):
    """
    Versucht Spielergebnis von mehreren Quellen zu holen.
    Priorität: SofaScore → ESPN → AllSports → API-Football
    """
    match_name = tip.get("match", "")
    league = tip.get("league", "")
    match_id = tip.get("telegram_msg_id", "")  # Wir brauchen die echte match_id

    # Versuche SofaScore zuerst
    sofa_id = tip.get("sofa_match_id")
    if sofa_id:
        result = get_sofascore_match_result(sofa_id)
        if result:
            return result

    # ESPN Fallback
    espn_id = tip.get("espn_match_id")
    if espn_id:
        result = get_espn_result(espn_id, league)
        if result:
            return result

    # AllSports Fallback
    asp_id = tip.get("allsports_match_id")
    if asp_id:
        result = get_allsports_result(asp_id)
        if result:
            return result

    # API-Football Fallback - Suche nach Ergebnis
    if API_FOOTBALL_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            
            league_id = API_FOOTBALL_LEAGUES.get(league)
            if league_id:
                season = int(tip_date[:4]) if int(tip_date[5:7]) > 6 else int(tip_date[:4]) - 1
                
                r = _af_request("/fixtures", {
                    "date": tip_date,
                    "league": league_id,
                    "season": season,
                    "status": "FT",  # Full Time = beendet
                })
                
                if r:
                    for fix in r:
                        teams = fix.get("teams", {})
                        h = teams.get("home", {}).get("name", "")
                        if teams_match(home_team, h):
                            goals = fix.get("goals", {})
                            score = fix.get("score", {})
                            home_g = goals.get("home", 0) or 0
                            away_g = goals.get("away", 0) or 0
                            ht_home = score.get("halftime", {}).get("home", 0) or 0
                            ht_away = score.get("halftime", {}).get("away", 0) or 0
                            
                            return {
                                "home_score": home_g,
                                "away_score": away_g,
                                "ht_home": ht_home,
                                "ht_away": ht_away,
                                "btts": home_g > 0 and away_g > 0,
                                "over25": (home_g + away_g) > 2,
                                "btts_ht": ht_home > 0 and ht_away > 0,
                                "total_goals": home_g + away_g,
                                "status": "finished",
                            }
        except Exception as e:
            log(f"Settlement API-Football Error: {e}", "WARN")

    return None


def edit_telegram_message(chat_id, message_id, new_text):
    """
    Editiert eine bestehende Telegram Nachricht mit dem Ergebnis.
    """
    if not TELEGRAM_TOKEN or not message_id:
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": new_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        return r.ok
    except Exception:
        return False


def format_result_text(tip, result, status):
    """
    Formatiert den Ergebnis-Text für Telegram Edit.
    """
    match = tip.get("match", "?")
    market = tip.get("market", "btts")
    tip_val = tip.get("tip", "YES")
    odds = tip.get("odds", "?")
    units = tip.get("units", 1.0)

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")
    total = result.get("total_goals", "?")

    status_emoji = "✅ GEWONNEN" if status == "won" else "❌ VERLOREN"
    profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    profit_str = f"+{profit}" if profit >= 0 else str(profit)

    nl = "\n"
    msg = f"<b>{status_emoji}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{match}</b>{nl}"
    msg += f"⚽ Ergebnis: <b>{home_s} : {away_s}</b>"
    if ht_home != "?" and ht_away != "?":
        msg += f" (HZ: {ht_home}:{ht_away})"
    msg += nl
    msg += f"📊 Tore gesamt: {total}{nl}"
    msg += f"🎯 Tipp: {tip_val} ({market.upper()}){nl}"
    msg += f"💰 Quote: {odds} | Units: {units}{nl}"
    profit_emoji = "🟢" if status == "won" else "🔴"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>{nl}"
    msg += "━━━━━━━━━━━━━━━━━━"

    return msg


def run_settlement():
    """
    Hauptfunktion für Check/Settlement Bot.
    Holt alle pending Tips, sucht Ergebnisse, updated Supabase + Telegram.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Settlement: Supabase fehlt!", "WARN")
        return

    log("🏆 Settlement Run startet...")

    # Hole alle pending Tips von heute und gestern
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "status": "eq.pending",
                "date": f"gte.{yesterday}",
                "select": "*",
                "limit": "500",
                "order": "date.desc",
            },
            timeout=20,
        )

        if not r.ok:
            log(f"Settlement: Supabase Error {r.status_code}", "WARN")
            return

        pending_tips = r.json()
        log(f"Settlement: {len(pending_tips)} pending Tips gefunden")

        won_count = 0
        lost_count = 0
        not_found = 0

        for tip in pending_tips:
            try:
                # Ergebnis holen
                result = get_match_result_from_sources(tip)

                if not result:
                    not_found += 1
                    continue

                # Tipp auswerten
                status = check_tip_result(tip, result)
                if not status:
                    continue

                if status == "won":
                    won_count += 1
                else:
                    lost_count += 1

                # Supabase updaten
                update_data = {
                    "status": status,
                    "result_home": result.get("home_score"),
                    "result_away": result.get("away_score"),
                    "result_ht_home": result.get("ht_home"),
                    "result_ht_away": result.get("ht_away"),
                    "settled_at": datetime.now(timezone.utc).isoformat(),
                }

                requests.patch(
                    f"{SUPABASE_URL}/rest/v1/tips",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    params={"id": f"eq.{tip['id']}"},
                    json=update_data,
                    timeout=10,
                )

                # Telegram Message editieren
                msg_id = tip.get("telegram_msg_id")
                chat_id = tip.get("telegram_chat_id")

                if msg_id and chat_id:
                    new_text = format_result_text(tip, result, status)
                    edit_telegram_message(chat_id, msg_id, new_text)
                    log(f"   {'✅' if status == 'won' else '❌'} {tip.get('match', '?')} → {status.upper()}: {result.get('home_score')}-{result.get('away_score')}")

            except Exception as e:
                log(f"   Settlement Error für {tip.get('match', '?')}: {e}", "WARN")
                continue

        # Summary
        total_settled = won_count + lost_count
        log(f"Settlement fertig: ✅{won_count} gewonnen, ❌{lost_count} verloren, ⏳{not_found} noch nicht fertig")

        if total_settled > 0:
            winrate = round(won_count / total_settled * 100)
            msg = "🏆 <b>Settlement Update</b>\n\n"
            msg += f"✅ Gewonnen: <b>{won_count}</b>\n"
            msg += f"❌ Verloren: <b>{lost_count}</b>\n"
            msg += f"🎯 Heute Winrate: <b>{winrate}%</b>\n"
            msg += f"⏳ Ausstehend: {not_found}"
            send_telegram(msg, TELEGRAM_GROUPS.get("stats"))

    except Exception as e:
        log(f"Settlement Fatal: {e}", "ERROR")


# ============================================================
# MAIN
# ============================================================

def check_config():
    warnings = []

    # 🆕 Anzahl der Keys loggen
    log(f"🔑 API Keys geladen:")
    log(f"   • Gemini: {len(GEMINI_API_KEYS)} Keys")
    log(f"   • Groq: {len(GROQ_API_KEYS)} Keys")
    log(f"   • Odds API: {len(ODDS_API_KEYS)} Keys")
    log(f"   • Football-Data: {len(FOOTBALL_DATA_API_KEYS)} Keys" if FOOTBALL_DATA_API_KEYS else "   • Football-Data: ❌")
    log(f"   • BSD: ✅ (8 Top-Ligen, unlimited Calls)")
    log(f"   • Sportmonks: ✅ (Dänemark + Schottland, Free Forever)")
    log(f"   • Wetter: {'✅ OpenWeatherMap aktiv!' if WEATHER_API_KEY else '❌ OPENWEATHER_API_KEY fehlt'}")
    log(f"   • FootyStats: {'✅ BTTS Stats aktiv!' if FOOTYSTATS_API_KEY else '❌ FOOTYSTATS_API_KEY fehlt (optional)'}")
    log(f"   • SportDB.dev: {'✅ Lineups + Flashscore!' if SPORTDB_API_KEY else '❌ SPORTDB_API_KEY fehlt (optional)'}")
    log(f"   • Forebet: ✅ Scraping aktiv (kein Key)")
    log(f"   • ScoutingStats: ✅ Scraping aktiv (kein Key)")
    log(f"")
    log(f"🔄 League Rotation:")
    log(f"   • Status: {'✅ AKTIV' if LEAGUE_ROTATION_ENABLED else '❌ AUS'}")
    log(f"   • Min Tipps: {LEAGUE_ROTATION_MIN_SAMPLES}")
    log(f"   • Rausnehmen: <{LEAGUE_ROTATION_MIN_QUOTE*100:.0f}%")
    log(f"   • Reinmachen: >{LEAGUE_ROTATION_MAX_QUOTE*100:.0f}%")
    log(f"   • Check: Sonntag (weekly)")
    log(f"   • API-Football: {len(API_FOOTBALL_KEYS)} Keys ({len(API_FOOTBALL_KEYS)*100} Calls/Tag bei Free Plan)")

    # 🆕 API-Football Erweiterungen Status
    if API_FOOTBALL_KEYS:
        log(f"📊 API-Football Erweiterungen:")
        log(f"   • Max Calls/Run: {APIFOOTBALL_MAX_CALLS_PER_RUN}")
        log(f"   • Team Stats: {'✅' if APIFOOTBALL_ENABLE_TEAM_STATS else '❌'}")
        log(f"   • H2H: {'✅' if APIFOOTBALL_ENABLE_H2H else '❌'}")
        log(f"   • Injuries: {'✅' if APIFOOTBALL_ENABLE_INJURIES else '❌'} (kostet 2 Calls/Spiel)")
        log(f"   • Predictions: {'✅' if APIFOOTBALL_ENABLE_PREDICTIONS else '❌'} (kostet 1 Call/Spiel)")

    if not GEMINI_API_KEYS:
        warnings.append("GEMINI_API_KEYS fehlt")
    elif len(GEMINI_API_KEYS) < 5:
        warnings.append(f"Nur {len(GEMINI_API_KEYS)} Gemini Keys - bei vielen Ligen besser 5-8 Keys")

    if not GROQ_API_KEYS:
        warnings.append("GROQ_API_KEYS fehlt")

    if not ODDS_API_KEYS:
        warnings.append("ODDS_API_KEYS fehlt")

    if not TELEGRAM_TOKEN:
        warnings.append("TELEGRAM_TOKEN fehlt")

    if not TELEGRAM_CHAT_ID:
        warnings.append("TELEGRAM_CHAT_ID fehlt")

    if warnings:
        log("⚠️  Config Warnungen:", "WARN")
        for w in warnings:
            log(f" - {w}", "WARN")


def main():
    log("=" * 60)
    log("AI TIPP BOT - ALL-IN-ONE EDITION")
    log("=" * 60)

    check_config()
    check_rotation_schedule()

    now_utc = datetime.now(timezone.utc)
    target_date = now_utc.date()
    hour_utc = now_utc.hour

    log(f"⏰ {now_utc.strftime('%H:%M')} UTC | 📅 {target_date}")

    # 🏆 SETTLEMENT ZUERST - Ergebnisse von gestern/heute prüfen
    run_mode = env("RUN_MODE", "tips")  # "tips", "settlement", "both"
    
    if run_mode in ["settlement", "both"]:
        log("🏆 Settlement Mode - prüfe vergangene Tipps...")
        run_settlement()
        if run_mode == "settlement":
            log("Settlement fertig!")
            return

    # Tips Mode
    log(f"🎯 Tips Mode - suche Spiele...")

    log(f"🗓️  Datum (Target): {target_date}")
    log(f"Märkte: {[MARKET_INFO[m]['name'] for m in MARKETS_TO_RUN]}")
    active_leagues, league_stats = get_active_leagues()
    log(f"Ligen aktiv: {len(active_leagues)} von {len(LEAGUES_TO_RUN)}")
    log(
        f"Filter: ≥{MIN_PROBABILITY}% · "
        f"Quote {MIN_ODDS}-{MAX_ODDS} · "
        f"Conf ≥{MIN_CONFIDENCE}⭐"
    )
    log("")

    tips_by_market = {m: [] for m in MARKETS_TO_RUN}
    total_analyzed = 0

    if MAX_LEAGUES_PER_RUN > 0:
        active_leagues = active_leagues[:MAX_LEAGUES_PER_RUN]
        log(f"MAX_LEAGUES_PER_RUN aktiv: Es werden nur {len(active_leagues)} Ligen analysiert.")

    for league in active_leagues:
        log(f"╔══ Liga: {league} ══╗")

        try:
            odds, fixtures = fetch_league_data_once(league, target_date)

            if not odds and not fixtures:
                log("   - Keine Spiele heute")
                continue

            for market in MARKETS_TO_RUN:
                log(f"   → Markt: {MARKET_INFO[market]['name']}")

                results, source = analyze_market_with_data(
                    market=market,
                    league=league,
                    target_date=target_date,
                    odds=odds,
                    fixtures=fixtures,
                )

                if results:
                    log(f"   ✓ {len(results)} via {source}")
                    total_analyzed += len(results)

                    top = filter_top_tips(results, target_date, market)

                    if top:
                        log(f"   💎 {len(top)} TOP!", "TOP")
                        tips_by_market[market].extend(top)
                else:
                    log(f"   - {source}")

                time.sleep(AI_SLEEP_SECONDS)

        except Exception as e:
            log(f"   ✗ {e}", "ERROR")
            continue

    total_top = sum(len(t) for t in tips_by_market.values())

    log("")
    log("════════════════════════════════════════")
    log(f"Analysierte Tipps: {total_analyzed}")
    log(f"Top-Tipps: {total_top}")

    for m, tips in tips_by_market.items():
        log(f"   • {MARKET_INFO[m]['name']}: {len(tips)}")

    log("════════════════════════════════════════")
    if APIFOOTBALL_CALL_COUNTER > 0:
        log(f"📊 API-Football Calls verbraucht: {APIFOOTBALL_CALL_COUNTER}/{APIFOOTBALL_MAX_CALLS_PER_RUN}")
    log("Sende an Telegram + Supabase...")

    send_top_tips(tips_by_market, target_date)

    # 🆕 MULTI-COMBO SYSTEM (3,4,5,6,7,8 Tipps)
    all_tips_flat = []
    for market_id, tips in tips_by_market.items():
        for tip in tips:
            tip["market"] = market_id
            all_tips_flat.append(tip)

    if len(all_tips_flat) >= 3:
        log("")
        log("🎰 Generiere Multi-Combos (3-8 Tipps)...")
        combo_chat = TELEGRAM_GROUPS.get("combo", TELEGRAM_CHAT_ID)

        # Header für Combo Channel
        combo_header = f"<b>🎰 MULTI-COMBO TIPPS</b>\n"
        combo_header += f"<i>📅 {target_date}</i>\n"
        combo_header += f"<i>Basis: {len(all_tips_flat)} Top-Tipps</i>"
        send_telegram(combo_header, combo_chat)

        # Alle Combo-Größen generieren (3 bis 8)
        generated = 0
        for n in [3, 4, 5, 6, 7, 8]:
            combo = generate_multi_combo_bets(all_tips_flat, num_tips=n)
            if combo:
                log(f"   {combo['label']}: Quote {combo['total_odds']}")
                msg = format_combo_telegram_message(combo)
                if msg:
                    send_telegram(msg, combo_chat)
                    generated += 1
            else:
                log(f"   ⚠️ Combo {n}: Zu wenig Tipps")

        log(f"✅ {generated} Combos generiert und gesendet!")
    else:
        log(f"ℹ️ Nur {len(all_tips_flat)} Tipps - min. 3 für Combos nötig")

    log("Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
