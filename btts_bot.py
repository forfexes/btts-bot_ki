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
    "combo": env("TELEGRAM_GROUP_COMBO", TELEGRAM_CHAT_ID),
    "combos": env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID),
    "btts_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
    "hz_live": env("TELEGRAM_GROUP_HZ_LIVE", TELEGRAM_CHAT_ID),
    "late_goals": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),
    "advanced_props": env("TELEGRAM_GROUP_ADVANCED_PROPS", env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID)),
}


# ============================================================
# 🆕 DYNAMISCHE SAISON-LOGIK (Juni 2026)
# Sommer-Ligen (MLS, Brasilien, Argentinien etc.) = Saison 2026
# Europäische Winter-Ligen = Saison 2025
# ============================================================

CALENDAR_YEAR_LEAGUE_IDS = {
    # Amerika/MLS
    253,   # MLS
    254,   # USL Championship
    # Südamerika
    71,    # Brasileirao Serie A
    72,    # Brasileirao Serie B
    128,   # Liga Argentinien
    129,   # Argentina Primera B
    268,   # Uruguay Primera
    265,   # Chile Primera
    239,   # Colombia Primera
    240,   # Ecuador Serie A
    281,   # Peru Primera
    243,   # Venezuela Primera
    242,   # Paraguay Division
    321,   # Bolivia Division
    266,   # Costa Rica Primera
    267,   # Guatemala Liga
    # Copa Süd/CONCACAF
    13,    # Copa Libertadores
    14,    # Copa Sudamericana
    26,    # CONCACAF Champions
    262,   # Liga MX
    263,   # Liga MX Expansion
    # Asien/Pazifik
    98,    # J1 League Japan
    99,    # J2 League Japan
    100,   # J3 League Japan
    292,   # K League 1
    293,   # K League 2
    169,   # China Super League
    170,   # China League 1
    323,   # India Super League
    296,   # Thailand League 1
    297,   # Malaysia Super League
    299,   # Indonesia Liga 1
    340,   # Vietnam V-League
    188,   # A-League Australia
    187,   # A-League Women
    189,   # New Zealand NZFC
    # Mittlerer Osten/Afrika
    307,   # Saudi Pro League
    306,   # UAE Pro League
    98,    # Qatar Stars League
    200,   # Morocco Botola
    233,   # Egypt Premier
    288,   # South Africa PSL
    300,   # Nigeria Premier
    302,   # Kenya Premier
    # Internationale Turniere 2026
    1,     # WM 2026
    5,     # UEFA Nations League
    9,     # Copa America
    6,     # Afrika Cup
    10,    # Freundschaftsspiele
}

def get_dynamic_season(league_id=None, league_name=None):
    """
    Bestimmt automatisch die richtige Saison (2026 vs 2025).
    Sommer-Ligen (Südamerika, MLS, Asien, Australien) → 2026
    Europäische Winter-Ligen → 2025
    """
    if league_id and int(league_id) in CALENDAR_YEAR_LEAGUE_IDS:
        return 2026

    # Fallback via Liga-Name
    SUMMER_LEAGUES = [
        "MLS", "Brasileirao", "Liga Argentinien", "J1 League", "J2 League",
        "A-League", "Uruguay Primera", "Chile Primera", "Colombia Primera",
        "Ecuador", "Peru Primera", "Venezuela", "K League", "China Super",
        "India Super", "Vietnam", "Thailand", "Malaysia", "Indonesia",
    ]
    if league_name:
        for sl in SUMMER_LEAGUES:
            if sl.lower() in league_name.lower():
                return 2026

    return 2025

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
AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "false").lower() in ["1", "true", "yes", "on"]  # Aus bis CLV läuft
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "0"))  # 0 = alle Ligen  # 25 pro Run!
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "0.1"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "0.5"))
USE_GROQ_FALLBACK = env("USE_GROQ_FALLBACK", "true").lower() in ["1", "true", "yes", "on"]

ALWAYS_ON_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_ON_LEAGUES", "Champions League,Europa League,Premier League,Bundesliga,La Liga,Serie A,Ligue 1,WM 2026,UEFA Nations League,Copa America,Afrika Cup").split(",")
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
GROQ_MODEL = "llama-3.1-8b-instant"  # Höheres Rate Limit als 70b!
GROQ_MODEL_FALLBACK = "gemma2-9b-it"  # Backup Modell


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
    # 🌍 WM 2026 + Länderspiele
    "WM 2026 Qualifikation Europa",
    "WM 2026 Qualifikation Südamerika",
    "WM 2026 Qualifikation Asien",
    "WM 2026 Qualifikation Afrika",
    "WM 2026 Qualifikation CONCACAF",
    "WM 2026",
    "UEFA Nations League",
    "Copa America",
    "Afrika Cup",
    "Freundschaftsspiele International",

    # ── Europa (fehlend) ──
    "Faroe Islands Premier League",
    "Gibraltar National League",
    "Kosovo Superliga",
    "Luxembourg BGL Ligue",
    "Malta Premier League",
    "Moldova National Division",
    "Montenegro First League",
    "North Macedonia First League",
    "Northern Ireland Premiership",
    "Republic of Ireland Premier Division",
    "Republic of Ireland First Division",
    "Wales Premier League",
    "Albania Superliga",
    "Armenia Premier League",
    "Azerbaijan Premier League",
    "Georgia Erovnuli Liga",
    "Cyprus First Division",
    "Czech 2. Liga",
    "Slovakia Super Liga",
    "Slovenia Prva Liga",
    "Bosnia Premier League",
    "Andorra Primera Divisió",
    "San Marino Campionato",
    "Swiss Challenge League",
    "Austrian Regional Liga",
    "German Regionalliga Bayern",
    "German Regionalliga Nord",
    "German Regionalliga Nordost",
    "German Regionalliga West",
    "German Regionalliga Südwest",
    # ── Afrika (fehlend) ──
    "Algeria Ligue 2",
    "Angola Girabola",
    "Botswana Premier League",
    "Burkina Faso Premier League",
    "Cameroon Elite One",
    "Congo DR Linafoot",
    "Ethiopia Premier League",
    "Gabon Championnat National",
    "Ghana Premier League",
    "Guinea Ligue Professionnelle",
    "Ivory Coast Ligue 1",
    "Libya Premier League",
    "Malawi Super League",
    "Mali Premiere Division",
    "Mauritania Ligue 1",
    "Morocco Botola 2",
    "Mozambique Mocambola",
    "Namibia Premier League",
    "Rwanda Premier League",
    "Senegal Ligue 1",
    "Sierra Leone Premier League",
    "Tanzania Premier League",
    "Togo Championnat National",
    "Uganda Premier League",
    "Zambia Super League",
    "Zimbabwe Premier Soccer League",
    "Zanzibar Premier League",
    "Gambia GFA League",
    "Benin Ligue 1",
    "CAF Champions League",
    "CAF Confederation Cup",
    "COSAFA Cup",
    "CECAFA Cup",
    # ── Asien (fehlend) ──
    "Afghanistan Premier League",
    "Bahrain Premier League",
    "Bangladesh Premier League",
    "Bhutan National League",
    "Cambodia League",
    "Chinese Taipei League",
    "Hong Kong Premier League",
    "India I-League 2",
    "Indonesia Liga 2",
    "Iraq Premier League",
    "Jordan Pro League",
    "Kazakhstan Premier League",
    "Kuwait Premier League",
    "Kyrgyzstan Top League",
    "Laos League",
    "Lebanon Premier League",
    "Lebanon Division 2",
    "Macau League",
    "Maldives Dhivehi Premier League",
    "Mongolia National Premier League",
    "Myanmar National League",
    "Nepal Super League",
    "Oman Professional League",
    "Pakistan Premier League",
    "Palestine Premier League",
    "Philippines United Football League",
    "Qatar Stars League",
    "Saudi Division 1",
    "Singapore Premier League",
    "Sri Lanka Football League",
    "Syria Premier League",
    "Tajikistan League",
    "Thailand Division 1",
    "Timor-Leste Premier League",
    "Turkmenistan Liga",
    "UAE Division 1",
    "Uzbekistan Super League",
    "Uzbekistan Division 1",
    "Vietnam V-League 2",
    "Yemen League",
    "Yemen Super Cup",
    "J-League Play-Offs",
    "K League 3",
    "K League 4",
    "ACL Elite",
    "ASEAN Club Championship",
    "SAFF Championship",
    "West Asian Football Federation",
    # ── Südamerika (fehlend) ──
    "Bolivia Division Profesional",
    "Brazil Serie C",
    "Brazil Serie D",
    "Chile Primera B",
    "Colombia Primera B",
    "Ecuador Liga Pro 2",
    "Paraguay Division Intermedia",
    "Peru Liga 2",
    "Venezuela Segunda Division",
    "CONMEBOL Pre-Olympic",
    "South American Youth Championship",
    "Recopa Sudamericana",
    "Copa Argentina",
    "Campeonato Paulista",
    "Campeonato Carioca",
    "Campeonato Mineiro",
    "Campeonato Gaucho",
    "Argentinian Regional Liga",
    # ── Nordamerika/Karibik (fehlend) ──
    "Canada Premier League",
    "USL League One",
    "USL League Two",
    "NISA National League",
    "Costa Rica Segunda",
    "El Salvador Primera Division",
    "Nicaragua Primera Division",
    "Panama LPF",
    "Trinidad and Tobago Pro League",
    "Jamaica Premier League",
    "Haiti Ligue Haïtienne",
    "Dominican Republic LDF",
    "Cuba National Series",
    # ── Ozeanien (fehlend) ──
    "New Zealand Southern League",
    "New Zealand National League",
    "Fiji Battle of the Giants",
    "Papua New Guinea National Soccer League",
    "Solomon Islands S-League",
    "Vanuatu Premier League",
    "OFC Champions League",
    # ── Youth/Reserve (fehlend) ──
    "Champions League Youth",
    "Bundesliga Reserve",
    "Premier League 2",
    "LaLiga Youth",
    "Serie A Primavera",
    "Ligue 1 Reserve",
    # ── Internationale Cups (fehlend) ──
    "Arab Cup",
    "Gold Cup",
    "CONCACAF Nations League",
    "Pacific Games Football",
    "Island Games",
    "COSAFA Women Cup",
]

# Zeitfenster pro Liga (UTC Stunden)
# LEAGUES_TIME_MAP entfernt — Bot läuft global 24/7



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
    # 🌍 WM 2026 + Länderspiele
    "WM 2026": 1,
    "WM 2026 Qualifikation Europa": 32,
    "WM 2026 Qualifikation Südamerika": 29,
    "WM 2026 Qualifikation Asien": 30,
    "WM 2026 Qualifikation Afrika": 31,
    "WM 2026 Qualifikation CONCACAF": 33,
    "UEFA Nations League": 5,
    "Copa America": 9,
    "Afrika Cup": 6,
    "Freundschaftsspiele International": 10,
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
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 Forebet → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ Forebet via Playwright!")
                else:
                    FOREBET_BLOCKED = True
                    return None
            else:
                log(f"   ℹ️  Forebet nicht erreichbar ({r.status_code})")
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
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 ScoutingStats → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ ScoutingStats via Playwright!")
                else:
                    return _scrape_scoutingstats(home_team, away_team, target_date)
            else:
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
            if PLAYWRIGHT_AVAILABLE:
                log(f"   🎭 ScoutingStats → Playwright...")
                html = scrape_with_playwright(url, timeout=8000)
                if html:
                    log(f"   ✅ ScoutingStats via Playwright!")
                    # Parse HTML
                    import re as _re2
                    btts_m = _re2.search(r'btts[^>]*>(\d+)%', html, _re2.IGNORECASE)
                    over25_m = _re2.search(r'over.?2\.5[^>]*>(\d+)%', html, _re2.IGNORECASE)
                    result = {}
                    if btts_m:
                        result["btts_pct"] = int(btts_m.group(1))
                    if over25_m:
                        result["over25_pct"] = int(over25_m.group(1))
                    if result:
                        return result
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
        
        # Versuche mehrere SofaScore Endpoints
        urls_to_try = [
            f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
            f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
        ]
        
        url = urls_to_try[0]
        
        # Rotate User-Agents um 403 zu vermeiden
        import random as _random
        import time as _time
        _ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        ]
        
        session = requests.Session()
        session.headers.update({
            "User-Agent": _random.choice(_ua_list),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        })
        
        # Erst Homepage "besuchen" um Cookies zu setzen
        try:
            session.get("https://www.sofascore.com/", timeout=5)
        except:
            pass
        
        r = session.get(url, timeout=15)
        
        if r.status_code in [403, 429, 503]:
            if PLAYWRIGHT_AVAILABLE:
                return pw_get_sofascore_fixtures(league_name, target_date)
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
        
        import random as _random2
        _ua_list2 = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]
        r = requests.get(
            url,
            headers={
                "User-Agent": _random2.choice(_ua_list2),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
            },
            timeout=20,
        )
        
        if r.status_code in [403, 429, 503]:
            log(f"   🎭 SofaScore blockiert ({r.status_code}) → Playwright...")
            if PLAYWRIGHT_AVAILABLE:
                html = scrape_with_playwright(url, timeout=15000)
                if html:
                    import json as _pj, re as _pre
                    m = _pre.search(r'"events"\s*:\s*(\[.*?\])\s*[,}]', html, _pre.DOTALL)
                    if m:
                        try:
                            events_raw = _pj.loads(m.group(1))
                            data = {"events": events_raw}
                            log(f"   ✅ SofaScore via Playwright: {len(events_raw)} Events")
                            r = type('R', (), {'ok': True, 'status_code': 200, 'json': lambda self=None: data})()
                        except Exception:
                            pass
            if r.status_code in [403, 429, 503]:
                log("   ℹ️  SofaScore nicht erreichbar → Fallback aktiv", "INFO")
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
            if PLAYWRIGHT_AVAILABLE:
                return pw_get_transfermarkt_injuries(team_name, league_name)
            TRANSFERMARKT_BLOCKED = True
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
    # 🌍 WM + Länderspiele
    "WM 2026": ("soccer", "fifa.world"),
    "UEFA Nations League": ("soccer", "uefa.nations"),
    "Copa America": ("soccer", "conmebol.copa"),
    "Afrika Cup": ("soccer", "caf.nations"),
    "Freundschaftsspiele International": ("soccer", "fifa.friendly"),
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



# ============================================================
# 🆕 FLASHSCORE - Inoffizielle API für Ergebnisse
# ============================================================
FLASHSCORE_CACHE = {}

def fetch_flashscore_fixtures(league_name, target_date):
    """
    Holt Spielpläne von Flashscore (inoffiziell).
    Gute Alternative wenn SofaScore blockiert.
    """
    cache_key = f"flash_{league_name}_{target_date}"
    if cache_key in FLASHSCORE_CACHE:
        return FLASHSCORE_CACHE[cache_key]

    # Flashscore Sport-IDs
    FLASHSCORE_IDS = {
        "Bundesliga": "football/germany/bundesliga",
        "Premier League": "football/england/premier-league",
        "La Liga": "football/spain/laliga",
        "Serie A": "football/italy/serie-a",
        "Ligue 1": "football/france/ligue-1",
        "Champions League": "football/europe/champions-league",
        "Europa League": "football/europe/europa-league",
        "Eredivisie": "football/netherlands/eredivisie",
        "Primeira Liga": "football/portugal/liga-portugal",
        "Süper Lig": "football/turkey/super-lig",
        "J1 League Japan": "football/japan/j1-league",
        "K League 1": "football/south-korea/k-league-1",
        "MLS": "football/usa/mls",
        "Brasileirao Serie A": "football/brazil/serie-a",
    }

    sport_path = FLASHSCORE_IDS.get(league_name)
    if not sport_path:
        return []

    try:
        # Flashscore Widget API
        date_str = str(target_date).replace("-", "")
        url = f"https://d.flashscore.com/x/feed/f_1_{date_str}_1_de_1"
        
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-GeoIP": "1",
                "Referer": "https://www.flashscore.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        # Parse Flashscore format (pipe-separated)
        text = r.text
        fixtures = []
        now_utc = datetime.now(timezone.utc)

        # Flashscore gibt alle Spiele zurück - wir filtern nach Liga
        lines = text.split("¬")
        current_league = ""
        
        for line in lines:
            if "~ZA÷" in line:  # Liga-Name
                current_league = line.split("ZA÷")[-1].split("¬")[0] if "ZA÷" in line else ""
            
            if "~AA÷" in line and league_name.lower()[:6] in current_league.lower():
                # Spiel-Zeile parsen
                parts = {p.split("÷")[0]: p.split("÷")[1] for p in line.split("¬") if "÷" in p}
                
                home = parts.get("AE", "")
                away = parts.get("AF", "")
                timestamp = parts.get("AD", "0")
                
                if not home or not away:
                    continue
                
                try:
                    kickoff = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                    if kickoff <= now_utc:
                        continue
                    
                    fixtures.append({
                        "home": home,
                        "away": away,
                        "match_id": parts.get("AA", ""),
                        "time_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "time_local": get_local_time(kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")),
                        "source": "flashscore",
                    })
                except Exception:
                    continue

        FLASHSCORE_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"Flashscore Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 LIVESCORE API - Echtzeit Fixtures (60 Calls/Stunde gratis)
# ============================================================
LIVESCORE_API_KEY = env("LIVESCORE_API_KEY", "")
LIVESCORE_SECRET = env("LIVESCORE_SECRET", "")
LIVESCORE_CACHE = {}

LIVESCORE_COMPETITION_IDS = {
    "Premier League": 2,
    "Bundesliga": 25,
    "La Liga": 4,
    "Serie A": 13,
    "Ligue 1": 16,
    "Champions League": 1,
    "Europa League": 8,
    "Eredivisie": 21,
    "Primeira Liga": 27,
    "MLS": 45,
    "J1 League Japan": 65,
    "K League 1": 74,
    "Brasileirao Serie A": 38,
    "Liga Argentinien": 39,
    "A-League Australia": 67,
    "Saudi Pro League": 78,
    "EFL League 1": 6,
    "EFL League 2": 7,
    "Championship": 5,
    "Scottish Premiership": 29,
}

def fetch_livescore_fixtures(league_name, target_date):
    """
    Holt Fixtures von Livescore API (livescore-api.com).
    Gratis: 60 Calls/Stunde.
    """
    if not LIVESCORE_API_KEY:
        return []

    comp_id = LIVESCORE_COMPETITION_IDS.get(league_name)
    if not comp_id:
        return []

    cache_key = f"livescore_{league_name}_{target_date}"
    if cache_key in LIVESCORE_CACHE:
        return LIVESCORE_CACHE[cache_key]

    try:
        r = requests.get(
            "https://livescore-api.com/api-client/fixtures/matches.json",
            params={
                "key": LIVESCORE_API_KEY,
                "secret": LIVESCORE_SECRET,
                "competition_id": comp_id,
                "date": str(target_date),
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        matches = data.get("data", {}).get("match", [])

        if not matches:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for m in matches:
            try:
                date_str = m.get("date", "")
                time_str = m.get("time", "00:00")
                kickoff_str = f"{date_str}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

                if kickoff <= now_utc:
                    continue

                fixtures.append({
                    "home": m.get("home_name", ""),
                    "away": m.get("away_name", ""),
                    "match_id": str(m.get("id", "")),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "livescore",
                })
            except Exception:
                continue

        LIVESCORE_CACHE[cache_key] = fixtures
        return fixtures

    except Exception as e:
        log(f"Livescore Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 API-NINJAS Football - Fixtures (10.000 Calls/Monat gratis)
# ============================================================
API_NINJAS_KEY = env("API_NINJAS_KEY", "")
API_NINJAS_CACHE = {}

API_NINJAS_LEAGUES = {
    "Champions League": "UEFA Champions League",
    "Europa League": "UEFA Europa League",
    "Bundesliga": "Bundesliga",
    "2. Bundesliga": "2. Bundesliga",
    "Premier League": "Premier League",
    "Championship": "Championship",
    "EFL League 1": "League One",
    "EFL League 2": "League Two",
    "La Liga": "La Liga",
    "La Liga 2": "La Liga 2",
    "Serie A": "Serie A",
    "Serie B": "Serie B",
    "Ligue 1": "Ligue 1",
    "Ligue 2": "Ligue 2",
    "Eredivisie": "Eredivisie",
    "Primeira Liga": "Primeira Liga",
    "Pro League Belgien": "First Division A",
    "Süper Lig": "Süper Lig",
    "Scottish Premiership": "Scottish Premiership",
    "MLS": "MLS",
    "Brasileirao Serie A": "Série A",
    "Liga Argentinien": "Primera División",
    "J1 League Japan": "J1 League",
    "K League 1": "K League 1",
    "Saudi Pro League": "Saudi Pro League",
    "A-League Australia": "A-League",
    "Danish Superliga": "Superliga",
    "Norway Eliteserien": "Eliteserien",
    "Sweden Allsvenskan": "Allsvenskan",
    "Finland Veikkausliiga": "Veikkausliiga",
    "Greece Super League": "Super League",
    "Poland Ekstraklasa": "Ekstraklasa",
    "Czech First League": "Czech First League",
    "Romania Liga I": "Liga I",
    "Croatia HNL": "HNL",
    "Serbia SuperLiga": "SuperLiga",
    "Ukraine Premier": "Premier League",
    "EFL League 1": "League One",
    "EFL League 2": "League Two",
}

def fetch_api_ninjas_fixtures(league_name, target_date):
    """
    API-Ninjas blockiert GitHub IPs (Host not in allowlist)
    → Deaktiviert bis Lösung gefunden
    """
    return []  # GitHub IPs blockiert

    league_str = API_NINJAS_LEAGUES.get(league_name)
    if not league_str:
        return []

    cache_key = f"ninjas_{league_name}_{target_date}"
    if cache_key in API_NINJAS_CACHE:
        return API_NINJAS_CACHE[cache_key]

    try:
        # API-Ninjas Football endpoint
        for endpoint in [
            "https://api.api-ninjas.com/v1/football",
            "https://api.api-ninjas.com/v1/sports/events",
        ]:
            r = requests.get(
                endpoint,
                headers={
                    "X-Api-Key": API_NINJAS_KEY,
                    "Accept": "application/json",
                },
                params={
                    "league": league_str,
                    "date": str(target_date),
                },
                timeout=12,
            )
            if r.ok and r.json():
                break

        if not r.ok:
            log(f"API-Ninjas Error: {r.status_code}", "WARN")
            return []

        data = r.json()
        if not data:
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in data:
            try:
                home = event.get("home_team", "")
                away = event.get("away_team", "")

                if not home or not away:
                    continue

                # Zeit parsen
                time_str = event.get("time", "")
                date_str = str(target_date)

                kickoff_str = f"{date_str}T{time_str}:00Z" if time_str else f"{date_str}T12:00:00Z"

                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except:
                    pass

                fixtures.append({
                    "home": home,
                    "away": away,
                    "match_id": f"ninjas_{hash(home+away)}",
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "api-ninjas",
                })

            except Exception:
                continue

        API_NINJAS_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🥷 API-Ninjas: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"API-Ninjas Error: {str(e)[:60]}", "WARN")
        return []



# ============================================================
# 🆕 THESPORTSDB - Fixtures (Free Key "123", alle Ligen!)
# ============================================================
THESPORTSDB_FIXTURES_CACHE = {}

THESPORTSDB_LEAGUE_IDS = {
    "Champions League": 4480,
    "Europa League": 4735,
    "Bundesliga": 4331,
    "2. Bundesliga": 4332,
    "Premier League": 4328,
    "Championship": 4329,
    "EFL League 1": 4330,
    "La Liga": 4335,
    "Serie A": 4332,
    "Ligue 1": 4334,
    "Eredivisie": 4337,
    "Primeira Liga": 4344,
    "Pro League Belgien": 4342,
    "Süper Lig": 4340,
    "Scottish Premiership": 4330,
    "MLS": 4346,
    "Brasileirao Serie A": 4351,
    "Liga Argentinien": 4406,
    "J1 League Japan": 4396,
    "K League 1": 4397,
    "Saudi Pro League": 4406,
    "A-League Australia": 4356,
    "Danish Superliga": 4341,
    "Norway Eliteserien": 4345,
    "Sweden Allsvenskan": 4349,
    "Greece Super League": 4336,
    "Poland Ekstraklasa": 4422,
    "Czech First League": 4418,
    "Champions League": 4480,
    "UEFA Youth League": 4481,
}

def fetch_thesportsdb_fixtures(league_name, target_date):
    """
    TheSportsDB mit strengem Datum-Filter.
    Nur Spiele die EXAKT am target_date sind UND in der Zukunft!
    """
    league_id = THESPORTSDB_LEAGUE_IDS.get(league_name)
    if not league_id:
        return []

    cache_key = f"tsdb_{league_name}_{target_date}"
    if cache_key in THESPORTSDB_FIXTURES_CACHE:
        return THESPORTSDB_FIXTURES_CACHE[cache_key]

    try:
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
            params={"d": str(target_date), "s": "Soccer"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events") or []

        if not events:
            return []

        now_utc = datetime.now(timezone.utc)
        target_str = str(target_date)
        fixtures = []

        for event in events:
            try:
                # Strenger Datum Check!
                event_date = event.get("dateEvent", "")
                if event_date != target_str:
                    continue

                # Liga ID Check!
                event_league_id = str(event.get("idLeague", ""))
                if event_league_id != str(league_id):
                    continue

                # Status Check - nur zukünftige!
                status = event.get("strStatus", "")
                if status in ["Match Finished", "FT", "AET", "PEN", "After Extra Time"]:
                    continue

                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")

                if not home or not away:
                    continue

                # Sanity Check - keine bekannten falschen Matches
                if home == away:
                    continue

                # Zeit Check
                time_str = event.get("strTime", "12:00:00")
                kickoff_str = f"{target_str}T{time_str}Z"
                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except Exception:
                    kickoff_str = f"{target_str}T12:00:00Z"

                fixtures.append({
                    "home": home,
                    "away": away,
                    "match_id": event.get("idEvent", ""),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "thesportsdb",
                })

            except Exception:
                continue

        THESPORTSDB_FIXTURES_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🏆 TheSportsDB: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"TheSportsDB Error: {str(e)[:60]}", "WARN")
        return []

    cache_key = f"tsdb_{league_name}_{target_date}"
    if cache_key in THESPORTSDB_FIXTURES_CACHE:
        return THESPORTSDB_FIXTURES_CACHE[cache_key]

    try:
        # TheSportsDB Events by League and Round
        # Oder Events by Date
        r = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php",
            params={
                "d": str(target_date),
                "s": "Soccer",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        events = data.get("events") or []

        if not events:
            THESPORTSDB_FIXTURES_CACHE[cache_key] = []
            return []

        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for event in events:
            try:
                # Liga filtern
                event_league = event.get("strLeague", "")
                event_league_id = event.get("idLeague", "")

                if str(event_league_id) != str(league_id):
                    # Fallback: Liga-Name prüfen
                    league_lower = league_name.lower()
                    if not any(w in event_league.lower() for w in league_lower.split() if len(w) > 4):
                        continue

                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")

                if not home or not away:
                    continue

                # Status prüfen
                status = event.get("strStatus", "")
                if status in ["Match Finished", "FT", "AET", "PEN"]:
                    continue

                # Zeit
                date_str = event.get("dateEvent", str(target_date))
                time_str = event.get("strTime", "12:00:00")
                kickoff_str = f"{date_str}T{time_str}Z"

                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if kickoff <= now_utc:
                        continue
                except:
                    kickoff_str = f"{date_str}T12:00:00Z"

                fixtures.append({
                    "home": home,
       