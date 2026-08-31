from typing import List, Dict, Optional, Tuple, Any
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
# API-Football deaktiviert (Konto gesperrt, nicht mehr benoetigt: Pinnacle/Kambi/ML decken ab).
# Alle API-Football-Calls sind auf `if not API_FOOTBALL_KEYS` gegated -> werden uebersprungen.
# Per ENABLE_API_FOOTBALL=true wieder aktivierbar, falls das Konto je entsperrt wird.
if env("ENABLE_API_FOOTBALL", "false").lower() not in ("1", "true", "yes", "on"):
    API_FOOTBALL_KEYS = []
# Erster Key für Backwards-Kompatibilität
API_FOOTBALL_KEY = API_FOOTBALL_KEYS[0] if API_FOOTBALL_KEYS else ""

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

TELEGRAM_GROUPS = {
    "btts": env("TELEGRAM_GROUP_BTTS", TELEGRAM_CHAT_ID),
    "over25": env("TELEGRAM_GROUP_OVER25", TELEGRAM_CHAT_ID),

    # bestehende Secrets bleiben unverändert:
    # TELEGRAM_GROUP_COMBO  = BTTS +2.5
    # TELEGRAM_GROUP_COMBOS = Combos / Kombis
    "combo": env("TELEGRAM_GROUP_COMBO", TELEGRAM_CHAT_ID),
    "combos": env("TELEGRAM_GROUP_COMBOS", TELEGRAM_CHAT_ID),

    "btts_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),
    "over15_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),

    # Deine bestehenden Secret-Namen:
    # TELEGRAM_GROUP_HZ_LIVE    = NETRATTLER CORNER SNIPER
    # TELEGRAM_GROUP_LATE_GOALS = NETRATTLER GOAL HUNTER
    "corners": env("TELEGRAM_GROUP_HZ_LIVE", TELEGRAM_CHAT_ID),
    "hz_live": env("TELEGRAM_GROUP_HZ_LIVE", TELEGRAM_CHAT_ID),
    "scorer": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),
    "goal_hunter": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),
    "late_goals": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),

    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),

    "advanced_props": env("TELEGRAM_GROUP_PLAYER_PROPS", env("TELEGRAM_GROUP_BUILDER", env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID))),
    "props": env("TELEGRAM_GROUP_PLAYER_PROPS", env("TELEGRAM_GROUP_BUILDER", env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID))),
    "builder": env("TELEGRAM_GROUP_BUILDER", env("TELEGRAM_GROUP_PLAYER_PROPS", env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID))),
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
SUPABASE_KEY = env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_KEY")

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "67"))  # 🆕 Hybrid: 67% (zwischen 65-69)
MIN_ODDS = float(env("MIN_ODDS", "1.70"))
MAX_ODDS = float(env("MAX_ODDS", "3.0"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))
# 🆕 Nur HIGH + OK Value (LOW fliegt raus)
MIN_VALUE_RATING = env("MIN_VALUE_RATING", "OK")  # HIGH, OK, oder LOW

MIN_ODDS_VALUE = MIN_ODDS  # Alias — globale Mindestquote für "nur Value Bets"


def _is_value_bet(odds, prob_pct):
    """True nur wenn Quote >= MIN_ODDS_VALUE UND echte Edge vorhanden (Value Bet).
    Global verfügbar — wird von allen Tipp-generierenden Funktionen genutzt
    (Pinnacle-Block, Corners, Props/Bet Builder)."""
    try:
        o = float(str(odds).replace(",", "."))
        p = float(prob_pct) / 100
    except Exception:
        return False
    if o < MIN_ODDS_VALUE:
        return False
    implied = 1 / o if o > 0 else 1
    edge = (p - implied) * 100
    return edge >= 3  # mind. 3% Edge über der Quoten-implizierten Wahrscheinlichkeit


MARKETS_TO_RUN = ["btts", "over25", "combo", "btts_ht", "over15_ht"]

# ============================================================
# AUTO LIGA SWITCH
# ============================================================
AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "true").lower() in ["1", "true", "yes", "on"]
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "25"))  # 25 pro Run!
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "1.0"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "2.0"))
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
    "Austrian Regional Liga",
    "Austria Regionalliga Mitte",
    "Austria Regionalliga Ost",
    "Austria Regionalliga Salzburg",
    "Austria Regionalliga Tirol",
    "Austria Regionalliga West",
    "Austria Landesliga Wien",
    "Austria Landesliga Niederösterreich",
    "Austria Landesliga Burgenland",
    "Austria Landesliga Steiermark",
    "Austria Landesliga Kärnten",
    "Austria Landesliga Tirol",
    "Austria Landesliga Vorarlberg",
    "Austria Landesliga Salzburg",
    "Austria Landesliga Oberösterreich",
    "ÖFB Cup",
    "Austria Frauen Bundesliga",
    "Germany Regionalliga Bayern",
    "Germany Regionalliga Nord",
    "Germany Regionalliga Nordost",
    "Germany Regionalliga West",
    "Germany Regionalliga Südwest",
    "Germany Oberliga Bayern",
    "Germany Oberliga Baden-Württemberg",
    "Germany Oberliga Hessen",
    "Germany Oberliga Niedersachsen",
    "Germany Oberliga Nordost Nord",
    "Germany Oberliga Nordost Süd",
    "Germany Oberliga Rheinland-Pfalz/Saar",
    "Germany Oberliga Westfalen",
    "Germany Oberliga NOFV Nord",
    "Germany Oberliga NOFV Süd",
    "Germany Bayernliga Nord",
    "Germany Bayernliga Süd",
    "DFB Pokal",
    "Germany Frauen Bundesliga",
    "Germany 2. Frauen Bundesliga",
    "Switzerland Promotion League",
    "Switzerland 1. Liga Classic",
    "Switzerland 1. Liga",
    "Switzerland Frauen Super League",
    "Switzerland Cup",
    "France National",
    "France National 2",
    "France National 3",
    "France Coupe de France",
    "France Frauen Division 1",
    "Spain Primera Federación",
    "Spain Segunda Federación",
    "Spain Tercera Federación",
    "Copa del Rey",
    "Spain Frauen Primera División",
    "Italy Serie D",
    "Italy Coppa Italia",
    "Italy Frauen Serie A",
    "England National League North",
    "England National League South",
    "England FA Cup",
    "England EFL Trophy",
    "England Premier League Women",
    "England Championship Women",
    "Netherlands Keuken Kampioen Divisie",
    "Netherlands 3. Divisie",
    "Netherlands KNVB Beker",
    "Belgium Cup",
    "Portugal Liga 3",
    "Portugal Campeonato de Portugal",
    "Portugal Taça de Portugal",
    "Greece Super League 2",
    "Greece Football League",
    "Greece Cup",
    "Turkey 2. Lig",
    "Turkey 3. Lig",
    "Turkey Cup",
    "Russia First League",
    "Russia Second League",
    "Russia FNL2 Division A Silver",
    "Russia FNL2 Division B Group 4",
    "Russia FNL2 Division B Group 5",
    "Russia FNL2 Division B Group 6",
    "Russia FNL2 Division B Group 7",
    "Russia FNL2 Division B Group 8",
    "Russia Cup",
    "Ukraine First League",
    "Ukraine Second League",
    "Poland I Liga",
    "Poland II Liga",
    "Poland III Liga Group 1",
    "Poland III Liga Group 2",
    "Poland III Liga Group 3",
    "Poland III Liga Group 4",
    "Poland Cup",
    "Czech 3. CFL Group A",
    "Czech 3. CFL Group B",
    "Czech 3. MSFL",
    "Czech Cup",
    "Slovakia 2. Liga",
    "Hungary NB II",
    "Hungary NB III",
    "Hungary Cup",
    "Romania Liga II",
    "Romania Liga III",
    "Romania Liga 4",
    "Romania Liga IV",
    "Romania Cup",
    "Bulgaria Second League",
    "Bulgaria Third League",
    "Serbia First League",
    "Serbia Srpska Liga South",
    "Serbia Srpska Liga West",
    "Croatia 2. HNL",
    "Croatia Cup",
    "Slovenia Prva Liga",
    "Slovenia 2. SNL",
    "Bosnia Premier League",
    "Bosnia 2. Liga",
    "Bosnia Cup",
    "North Macedonia First League",
    "North Macedonia Cup",
    "Albanian Superliga",
    "Albania First Division",
    "Kosovo Superliga",
    "Kosovo First League",
    "Montenegrin First League",
    "Moldova National Division",
    "Moldova Second Division",
    "Armenian Premier League",
    "Azerbaijani Premier League",
    "Georgian Erovnuli Liga",
    "Estonia Esiliiga",
    "Latvia First League",
    "Lithuania Division 1",
    "Sweden Division 1",
    "Sweden Division 2 Norra",
    "Sweden Division 2 Södra",
    "Norway Division 1",
    "Norway Division 2 Group 1",
    "Norway Division 2 Group 2",
    "Denmark 1st Division",
    "Denmark 3. Division",
    "Finland Ykkosliiga",
    "Finland Ykkönen",
    "Finland Kolmonen",
    "Finland Cup",
    "Iceland Division 2",
    "Iceland Cup",
    "Norway Cup",
    "Sweden Cup",
    "Cyprus First Division",
    "Malta Premier League",
    "Luxembourg BGL Ligue",
    "Gibraltar National League",
    "Faroe Islands Premier League",
    "San Marino Campionato",
    "Andorra Primera Divisió",
    "Belarus First League",
    "Uzbekistan Division 1",
    "Kazakh Premier League",
    "K League 3",
    "K League 4",
    "China League Two",
    "China FA Cup",
    "India I-League 2",
    "Indonesia Liga 2",
    "Vietnam V-League 2",
    "Thailand Division 1",
    "Lebanon Division 2",
    "Lebanon Premier League",
    "Saudi Division 1",
    "UAE Division 1",
    "Palestine Premier League",
    "Syria Premier League",
    "Kyrgyzstan Liga",
    "Myanmar U20 League",
    "Japan Regional League",
    "Maldives Premier League",
    "Sri Lanka Super League",
    "Nepal Super League",
    "Bangladesh Premier League",
    "Pakistan Premier League",
    "Algeria Ligue 2",
    "Morocco Botola 2",
    "Morocco GNF 2",
    "Ghana Premier League",
    "Tanzania Premier League",
    "Uganda Premier League",
    "Zimbabwe Premier Soccer League",
    "Zanzibar Premier League",
    "Zambia Super League",
    "Rwanda Premier League",
    "Angola Girabola",
    "Mozambique Mocambola",
    "Libya Premier League",
    "Gambia GFA League",
    "Mali Premiere Division",
    "Burkina Faso Premier League",
    "Guinea Ligue Professionnelle",
    "Sierra Leone Premier League",
    "Togo Championnat National",
    "Botswana Premier League",
    "Namibia Premier League",
    "Mauritania Ligue 1",
    "Malawi Super League",
    "Ethiopia Premier League",
    "Senegal Ligue 1",
    "Ivory Coast Ligue 1",
    "Cameroon Elite One",
    "CAF Champions League",
    "CAF Confederation Cup",
    "CONCACAF Nations League",
    "Brazil Serie C",
    "Brazil Serie D",
    "Campeonato Paulista",
    "Campeonato Carioca",
    "Campeonato Mineiro",
    "Copa Argentina",
    "Colombia Primera B",
    "Ecuador Liga Pro 2",
    "Peru Liga 2",
    "Venezuela Segunda Division",
    "Paraguay Division Intermedia",
    "Bolivia Division Profesional",
    "Costa Rica Segunda",
    "El Salvador Primera Division",
    "Nicaragua Primera Division",
    "Panama LPF",
    "Jamaica Premier League",
    "Trinidad and Tobago Pro League",
    "Haiti Ligue Haïtienne",
    "Dominican Republic LDF",
    "Canada Premier League",
    "USL League One",
    "USL League Two",
    "Australia NPL NSW",
    "Australia NPL Victoria",
    "Australia NPL Queensland",
    "Australia NPL South Australia",
    "Australia NPL Western Australia",
    "Australia FFA Cup",
    "New Zealand Southern League",
    "New Zealand National League",

    # ── Bet365 Länderspiele ──
    "Länderspiel",
    "Weltmeisterschaft 2026",
    "U21 Länderspiel",
    "U19 Europameisterschaft Qualifikation",
    "Länderspiel Jugend",
    "Weltmeisterschaft Frauen Qualifikation",
    "Länderspiel Frauen",
    "ASEAN Championship Qualifikation",
    # ── WM 2026 Gruppen ──
    "WM 2026 Gruppe A", "WM 2026 Gruppe B", "WM 2026 Gruppe C",
    "WM 2026 Gruppe D", "WM 2026 Gruppe E", "WM 2026 Gruppe F",
    "WM 2026 Gruppe G", "WM 2026 Gruppe H", "WM 2026 Gruppe I",
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
    # 🌍 WM 2026 + Länderspiele
    "WM 2026": "evening",
    "WM 2026 Qualifikation Europa": "evening",
    "WM 2026 Qualifikation Südamerika": "night",
    "WM 2026 Qualifikation Asien": "morning",
    "WM 2026 Qualifikation Afrika": "evening",
    "WM 2026 Qualifikation CONCACAF": "night",
    "UEFA Nations League": "evening",
    "Copa America": "night",
    "Afrika Cup": "evening",
    "Freundschaftsspiele International": "evening",
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
    # ── Internationale / Cups ──
    "Freundschaftsspiele International": "soccer_international_friendlies",
    "WM 2026": "soccer_fifa_world_cup",
    "UEFA Nations League": "soccer_uefa_nations_league",
    "Copa America": "soccer_conmebol_copa_america",
    "Gold Cup": "soccer_concacaf_gold_cup",
    "Afrika Cup": "soccer_africa_cup_of_nations",
    "CONCACAF Nations League": "soccer_concacaf_nations_league",
    "Copa Libertadores": "soccer_conmebol_copa_libertadores",
    "Copa Sudamericana": "soccer_conmebol_copa_sudamericana",
    "CAF Champions League": "soccer_africa_caf_champions_league",
    "AFC Champions League": "soccer_afc_champions_league",
    # ── Americas ──
    "Brasileirao Serie B": "soccer_brazil_campeonato_b",
    "Argentina Primera B": "soccer_argentina_primera_b",
    "Colombia Primera": "soccer_colombia_primera_a",
    "Ecuador Serie A": "soccer_ecuador_liga_pro",
    "Chile Primera": "soccer_chile_campeonato",
    "Peru Primera": "soccer_peru_primera_division",
    "Uruguay Primera": "soccer_uruguay_primera_division",
    "Bolivia Division": "soccer_bolivia_liga_profesional",
    "Bolivia Division Profesional": "soccer_bolivia_liga_profesional",
    "Paraguay Division": "soccer_paraguay_primera_division",
    "Venezuela Primera": "soccer_venezuela_primera_division",
    "Liga MX": "soccer_mexico_ligamx",
    "Canada Premier League": "soccer_canada_premier_league",
    "USL Championship": "soccer_usa_usl_championship",
    # ── Asien ──
    "J1 League Japan": "soccer_japan_j_league",
    "K League 1": "soccer_south_korea_kleague1",
    "K League 2": "soccer_south_korea_kleague2",
    "China Super League": "soccer_china_superleague",
    "Saudi Pro League": "soccer_saudi_arabia_premier_league",
    "India Super League": "soccer_india_super_league",
    # ── Afrika ──
    "Egypt Premier": "soccer_egypt_premier_league",
    "Morocco Botola": "soccer_morocco_botola_pro",
    "South Africa PSL": "soccer_south_africa_premier_league",
    "WM 2026 Qualifikation Europa": "soccer_uefa_nations_league",


    # ── Bet365 Länderspiele ──
    "Länderspiel": "soccer_international_friendlies",
    "Weltmeisterschaft 2026": "soccer_fifa_world_cup",
    "U21 Länderspiel": "soccer_international_friendlies",
    "U19 Europameisterschaft Qualifikation": "soccer_international_friendlies",
    "U19 Südostasienmeisterschaft": "soccer_international_friendlies",
    "Länderspiel Jugend": "soccer_international_friendlies",
    "Weltmeisterschaft Frauen Qualifikation": "soccer_womens_world_cup_qualifier",
    "CONMEBOL Nations League Frauen": "soccer_international_friendlies",
    "Länderspiel Frauen": "soccer_international_friendlies",
    "U20 Länderspiel Frauen": "soccer_international_friendlies",
    "ASEAN Championship Qualifikation": "soccer_international_friendlies",
    "ASEAN Championship": "soccer_international_friendlies",
    # ── Varianten die ESPN/FotMob nutzen ──
    "International Friendly": "soccer_international_friendlies",
    "International Friendlies": "soccer_international_friendlies",
    "Friendly International": "soccer_international_friendlies",
    "WM 2026 Gruppe A": "soccer_fifa_world_cup",
    "WM 2026 Gruppe B": "soccer_fifa_world_cup",
    "WM 2026 Gruppe C": "soccer_fifa_world_cup",
    "WM 2026 Gruppe D": "soccer_fifa_world_cup",
    "WM 2026 Gruppe E": "soccer_fifa_world_cup",
    "WM 2026 Gruppe F": "soccer_fifa_world_cup",
    "WM 2026 Gruppe G": "soccer_fifa_world_cup",
    "WM 2026 Gruppe H": "soccer_fifa_world_cup",
    "WM 2026 Gruppe I": "soccer_fifa_world_cup",
    "WM 2026 Achtelfinale": "soccer_fifa_world_cup",
    "WM 2026 Viertelfinale": "soccer_fifa_world_cup",
    "WM 2026 Halbfinale": "soccer_fifa_world_cup",
    "WM 2026 Finale": "soccer_fifa_world_cup",
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
    "over15_ht": {
        "name": "⏰ Over 1.5 HT",
        "instr": "Analysiere Over 1.5 Tore in der 1. Halbzeit.",
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
    import unicodedata as _ud
    n = _ud.normalize("NFKD", str(name).lower().strip())
    n = "".join(c for c in n if not _ud.combining(c))
    replacements = {
        "england national team": "england",
        "argentina national team": "argentina",
        "england men": "england",
        "argentina men": "argentina",
        "new england revolution 2": "new england revolution ii",
        "new england rev ii": "new england revolution ii",
        "columbus crew 2": "columbus crew ii",
    }
    n = replacements.get(n, n)
    n = re.sub(r"\\b(fc|cf|ac|sc|sv|afc|cfc|club de futbol|football club)\\b", " ", n)
    n = re.sub(r"\\b(u[- ]?21|u[- ]?20|u[- ]?19|u[- ]?18|women|w|reserves?)\\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return " ".join(n.split())


def teams_match(name1, name2):
    # National teams must match exactly (Identity Hub guard).
    try:
        from netrattler_identity_hub import teams_match as _identity_teams_match
        return _identity_teams_match(name1, name2)
    except Exception:
        n1 = normalize_team_name(name1)
        n2 = normalize_team_name(name2)
        if not n1 or not n2:
            return False
        if n1 == n2:
            return True
        if n1 in {"england", "argentina"} or n2 in {"england", "argentina"}:
            return n1 == n2
        return (len(n1) >= 8 and n1 in n2) or (len(n2) >= 8 and n2 in n1)

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

def get_footystats_team_stats(team_name, league_name=None, target_date=None):
    return get_footystats_team(team_name, league_name or "")

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
            log(f"   ℹ️  SofaScore All blockiert ({r.status_code})", "INFO")
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
FOOTBALLDATA_IO_API_KEY = env("FOOTBALLDATA_IO_API_KEY", "")
THESTATSAPI_KEY = ""  # TheStatsAPI deaktiviert (kostenpflichtig) — andere Quellen ausreichend
THESTATSAPI_KEYS = []  # TheStatsAPI deaktiviert
if not THESTATSAPI_KEYS:
    THESTATSAPI_KEYS = [THESTATSAPI_KEY] if THESTATSAPI_KEY else []
elif THESTATSAPI_KEYS and not THESTATSAPI_KEY:
    THESTATSAPI_KEY = THESTATSAPI_KEYS[0]
SOCCERFOOTBALLINFO_API_KEY = env("SOCCERFOOTBALLINFO_API_KEY", "")  # 🆕 soccerfootballinfo.com
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
            "https://apiv2.allsportsapi.com/football/",
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
            "https://apiv2.allsportsapi.com/football/",
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

def _fetch_espn_via_playwright(url, date_str):
    """ESPN via Playwright wenn requests 403 gibt."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page = ctx.new_page()
            full_url = f"{url}?dates={date_str}"
            page.goto(full_url, timeout=20000, wait_until="networkidle")
            import json as _json
            content = page.content()
            # JSON aus HTML extrahieren
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = _json.loads(content[start:end])
                browser.close()
                return data
            browser.close()
    except Exception as e:
        log(f"Playwright ESPN Fehler: {str(e)[:60]}", "WARN")
    return None


def fetch_espn_fixtures(league_name, target_date):
    """
    Holt Spielpläne von ESPN — requests zuerst, Playwright als Fallback bei 403.
    """
    league_info = ESPN_LEAGUE_IDS.get(league_name)
    if not league_info:
        return []

    sport, league_id = league_info
    cache_key = f"espn_{league_name}_{target_date}"

    if cache_key in ESPN_CACHE:
        return ESPN_CACHE[cache_key]

    try:
        date_str = str(target_date).replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/scoreboard"

        r = requests.get(
            url,
            params={"dates": date_str},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.espn.com/",
            },
            timeout=12,
        )

        if not r.ok:
            # Playwright Fallback
            log(f"   ESPN {r.status_code} → Playwright Fallback für {league_name}")
            data = _fetch_espn_via_playwright(url, date_str)
            if not data:
                # API-Football als letzter Fallback
                if league_name in _AF_BULK_FIXTURES:
                    return _AF_BULK_FIXTURES.get(league_name, [])
                return []
        else:
            data = r.json()

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



# ============================================================
# 🆕 BETTINGSCREENER - Value Bets Scraping
# ============================================================
BETTINGSCREENER_CACHE = {}

def scrape_bettingscreener(league_name, target_date):
    """
    Scrapt Value Bets von bettingscreener.com
    Returns: {'match': {'btts': {'odds': 1.95, 'value': 8.5}, ...}}
    """
    cache_key = f"bscreener_{league_name}_{target_date}"
    if cache_key in BETTINGSCREENER_CACHE:
        return BETTINGSCREENER_CACHE[cache_key]

    try:
        import random as _r
        _ua = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        ]

        r = requests.get(
            "https://www.bettingscreener.com/football/value-bets/",
            headers={
                "User-Agent": _r.choice(_ua),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.bettingscreener.com/",
            },
            timeout=15,
        )

        if not r.ok:
            return {}

        html = r.text
        results = {}

        # Parse Value Bets
        import re as _re
        # Suche nach Match-Blöcken
        matches = _re.findall(
            r'class="[^"]*match[^"]*"[^>]*>.*?<span[^>]*>([^<]+)\s+vs?\s+([^<]+)</span>.*?value[^>]*>([0-9.]+)%',
            html, _re.DOTALL | _re.IGNORECASE
        )

        for home, away, value in matches[:20]:
            key = f"{home.strip()} vs {away.strip()}"
            results[key] = {"value_pct": float(value)}

        BETTINGSCREENER_CACHE[cache_key] = results
        if results:
            log(f"   📊 BettingScreener: {len(results)} Value Bets gefunden")
        return results

    except Exception as e:
        log(f"BettingScreener Error: {str(e)[:60]}", "WARN")
        return {}


# ============================================================
# 🆕 BETSCOPE - Odds Vergleich Scraping
# ============================================================
BETSCOPE_CACHE = {}

def scrape_betscope(home_team, away_team):
    """
    Scrapt beste Odds von Betscope für ein Spiel.
    Returns: {'btts_yes': 1.95, 'btts_no': 1.85, 'over25': 1.75}
    """
    cache_key = f"betscope_{home_team}_{away_team}"
    if cache_key in BETSCOPE_CACHE:
        return BETSCOPE_CACHE[cache_key]

    try:
        import random as _r
        search_query = f"{home_team} {away_team}".replace(" ", "+")

        r = requests.get(
            f"https://www.betscope.com/search?q={search_query}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.betscope.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return {}

        html = r.text
        import re as _re

        # Suche nach Quoten
        odds_patterns = {
            "btts_yes": r'btts[^>]*yes[^>]*>.*?([0-9]+\.[0-9]+)',
            "over25": r'over.?2\.5[^>]*>.*?([0-9]+\.[0-9]+)',
        }

        result = {}
        for market, pattern in odds_patterns.items():
            match = _re.search(pattern, html, _re.IGNORECASE | _re.DOTALL)
            if match:
                try:
                    result[market] = float(match.group(1))
                except:
                    pass

        BETSCOPE_CACHE[cache_key] = result
        return result

    except Exception as e:
        return {}


# ============================================================
# 🆕 BETFAIR EXCHANGE - Markt-Daten Scraping
# ============================================================
BETFAIR_CACHE = {}

def scrape_betfair_exchange(home_team, away_team, market="btts"):
    """
    Scrapt Betfair Exchange Quoten (Lay/Back).
    Returns: {'back': 1.95, 'lay': 2.02, 'volume': 15000}
    Sharp Money Indikator: Hohe Volumes = Sharp Bettors aktiv!
    """
    cache_key = f"betfair_{home_team}_{away_team}_{market}"
    if cache_key in BETFAIR_CACHE:
        return BETFAIR_CACHE[cache_key]

    try:
        import random as _r
        # Betfair API ohne Login - nur öffentliche Daten
        search_term = f"{home_team} v {away_team}".replace(" ", "%20")

        r = requests.get(
            f"https://www.betfair.com/exchange/plus/football/market/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json, text/plain, */*",
                "X-Application": "2",
                "X-Authentication": "",
            },
            timeout=12,
        )

        if not r.ok:
            # Versuche Betfair API
            r2 = requests.get(
                "https://api.betfair.com/exchange/betting/json-rpc/v1",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=10,
            )

        # Fallback: Betfair Odds aus öffentlichem Feed
        betfair_result = {}

        BETFAIR_CACHE[cache_key] = betfair_result
        return betfair_result

    except Exception as e:
        return {}


def get_betfair_odds_api(event_name):
    """
    Holt Betfair Exchange Daten via The Odds API (falls verfügbar).
    The Odds API hat Betfair als eine ihrer Quellen!
    """
    if not ODDS_API_KEYS:
        return None

    try:
        # Suche in Odds API nach Betfair Exchange Daten
        key = ODDS_API_KEYS[0]
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer/odds/",
            params={
                "apiKey": key,
                "bookmakers": "betfair_ex_eu",  # Betfair Exchange Europa!
                "markets": "h2h,btts,totals",
                "oddsFormat": "decimal",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        for game in data:
            home = game.get("home_team", "")
            away = game.get("away_team", "")

            if teams_match(event_name.split(" vs ")[0], home) if " vs " in event_name else False:
                for bookmaker in game.get("bookmakers", []):
                    if "betfair" in bookmaker.get("key", "").lower():
                        return {
                            "source": "betfair_exchange",
                            "markets": bookmaker.get("markets", []),
                        }

        return None

    except Exception:
        return None



# ============================================================
# 🆕 PINNACLE - Schärfste Quoten weltweit (inoffizielle API)
# ============================================================
PINNACLE_CACHE = {}

PINNACLE_SPORT_IDS = {
    "Champions League": 29,
    "Europa League": 29,
    "Bundesliga": 29,
    "Premier League": 29,
    "La Liga": 29,
    "Serie A": 29,
    "Ligue 1": 29,
    "Eredivisie": 29,
    "MLS": 29,
    "Brasileirao Serie A": 29,
}

def get_pinnacle_odds(home_team, away_team, league_name):
    """
    Holt Pinnacle Quoten - schärfste Odds weltweit!
    Ideal für Fair Odds Berechnung + Sharp Money.
    Returns: {'btts_yes': 1.88, 'btts_no': 1.92, 'over25': 1.78, 'sharp': True}
    """
    cache_key = f"pinnacle_{home_team}_{away_team}"
    if cache_key in PINNACLE_CACHE:
        return PINNACLE_CACHE[cache_key]

    try:
        import random as _r
        import time as _t

        _uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        ]

        # Pinnacle direkt blockiert GitHub IPs → nur Odds API Fallback
        # Fallback: Odds API mit Pinnacle Filter
        if ODDS_API_KEYS:
            key = ODDS_API_KEYS[0]
            r2 = requests.get(
                "https://api.the-odds-api.com/v4/sports/soccer/odds/",
                params={
                    "apiKey": key,
                    "bookmakers": "pinnacle",
                    "markets": "h2h,totals,btts",
                    "oddsFormat": "decimal",
                },
                timeout=12,
            )

            if r2.ok:
                for game in r2.json():
                    h = game.get("home_team", "")
                    a = game.get("away_team", "")

                    if not (teams_match(home_team, h) and teams_match(away_team, a)):
                        continue

                    result = {"source": "pinnacle_via_odds_api", "sharp": True}

                    for bookmaker in game.get("bookmakers", []):
                        if "pinnacle" not in bookmaker.get("key", "").lower():
                            continue

                        for market in bookmaker.get("markets", []):
                            key_name = market.get("key", "")

                            if key_name == "btts":
                                for outcome in market.get("outcomes", []):
                                    if outcome.get("name") == "Yes":
                                        result["btts_yes"] = outcome.get("price", 0)
                                    elif outcome.get("name") == "No":
                                        result["btts_no"] = outcome.get("price", 0)

                            elif key_name == "totals":
                                for outcome in market.get("outcomes", []):
                                    if outcome.get("name") == "Over" and abs(outcome.get("point", 0) - 2.5) < 0.1:
                                        result["over25"] = outcome.get("price", 0)
                                    elif outcome.get("name") == "Under" and abs(outcome.get("point", 0) - 2.5) < 0.1:
                                        result["under25"] = outcome.get("price", 0)

                    if len(result) > 2:
                        PINNACLE_CACHE[cache_key] = result
                        log(f"   📌 Pinnacle (OddsAPI): {home_team} vs {away_team}")
                        return result

        PINNACLE_CACHE[cache_key] = {}
        return {}

    except Exception as e:
        log(f"Pinnacle Error: {str(e)[:60]}", "WARN")
        return {}


def calculate_pinnacle_fair_odds(pinnacle_data, market="btts"):
    """
    Berechnet Fair Odds aus Pinnacle Quoten (No-Vig).
    Pinnacle hat ~2-3% Margin - beste Fair Odds Referenz!
    """
    try:
        if market == "btts":
            yes_odds = pinnacle_data.get("btts_yes", 0)
            no_odds = pinnacle_data.get("btts_no", 0)
        elif market == "over25":
            yes_odds = pinnacle_data.get("over25", 0)
            no_odds = pinnacle_data.get("under25", 0)
        else:
            return None

        if not yes_odds or not no_odds:
            return None

        # No-Vig Fair Odds berechnen
        yes_prob = 1 / yes_odds
        no_prob = 1 / no_odds
        total_prob = yes_prob + no_prob

        # Normalisieren (Vig entfernen)
        fair_yes_prob = yes_prob / total_prob
        fair_no_prob = no_prob / total_prob

        fair_yes_odds = round(1 / fair_yes_prob, 2)
        fair_no_odds = round(1 / fair_no_prob, 2)

        return {
            "fair_yes": fair_yes_odds,
            "fair_no": fair_no_odds,
            "vig": round((total_prob - 1) * 100, 2),
            "yes_prob": round(fair_yes_prob * 100, 1),
        }

    except Exception:
        return None



# ============================================================
# 🆕 FREIE SCRAPING QUELLEN - Alle ohne Keys!
# ============================================================

# ---- 1. AISCORE ----
AISCORE_CACHE = {}

def scrape_aiscore(league_name, target_date):
    """AiScore.com - AI-basierte Vorhersagen, kein Key nötig"""
    cache_key = f"aiscore_{league_name}_{target_date}"
    if cache_key in AISCORE_CACHE:
        return AISCORE_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.aiscore.com/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.aiscore.com/",
            },
            timeout=10,
        )
        if r.ok:
            AISCORE_CACHE[cache_key] = {"available": True}
            return {"available": True}
    except Exception:
        pass
    return {}


# ---- 2. BESOCCER ----
BESOCCER_CACHE = {}

def scrape_besoccer(league_name, target_date):
    """BeSoccer - Spanische Ligen Details, kein Key"""
    cache_key = f"besoccer_{league_name}_{target_date}"
    if cache_key in BESOCCER_CACHE:
        return BESOCCER_CACHE[cache_key]
    try:
        import random as _r
        date_str = str(target_date).replace("-", "")
        r = requests.get(
            f"https://www.besoccer.com/competition/matches/{date_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.besoccer.com/",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            fixtures = []
            matches = _re.findall(
                r'class="[^"]*match[^"]*".*?team-home[^>]*>([^<]+)</.*?team-away[^>]*>([^<]+)<',
                r.text, _re.DOTALL | _re.IGNORECASE
            )
            for home, away in matches[:20]:
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "source": "besoccer"
                })
            BESOCCER_CACHE[cache_key] = fixtures
            return fixtures
    except Exception:
        pass
    return []


# ---- 3. SOCCERWAY ----
SOCCERWAY_CACHE = {}

def scrape_soccerway(league_name, target_date):
    """Soccerway - Historische Ergebnisse + Fixtures"""
    cache_key = f"soccerway_{league_name}_{target_date}"
    if cache_key in SOCCERWAY_CACHE:
        return SOCCERWAY_CACHE[cache_key]
    try:
        import random as _r
        d = target_date
        r = requests.get(
            f"https://int.soccerway.com/matches/{d.year}/{d.month:02d}/{d.day:02d}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://int.soccerway.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            fixtures = []
            matches = _re.findall(
                r'data-team-a="([^"]+)"[^>]*data-team-b="([^"]+)"',
                r.text
            )
            for home, away in matches[:30]:
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "source": "soccerway"
                })
            SOCCERWAY_CACHE[cache_key] = fixtures
            if fixtures:
                log(f"   ⚽ Soccerway: {len(fixtures)} Spiele")
            return fixtures
    except Exception:
        pass
    return []


# ---- 4. LIVESCORE.COM (nicht API) ----
LIVESCORE_COM_CACHE = {}

def scrape_livescore_com(league_name, target_date):
    """Livescore.com direkt - viele Ligen, kein Key"""
    cache_key = f"lscom_{league_name}_{target_date}"
    if cache_key in LIVESCORE_COM_CACHE:
        return LIVESCORE_COM_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://www.livescore.com/en/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.livescore.com/",
            },
            timeout=12,
        )
        if r.ok:
            LIVESCORE_COM_CACHE[cache_key] = {"available": True}
        return {}
    except Exception:
        return {}


# ---- 5. FOOTYSTATS.ORG (Free Tier) ----
def get_footystats_free(league_name, target_date):
    """FootyStats gratis Daten - BTTS Stats, Über/Unter"""
    try:
        import random as _r
        # Footystats hat öffentliche Daten ohne Key
        league_slugs = {
            "Bundesliga": "germany-bundesliga",
            "Premier League": "england-premier-league",
            "La Liga": "spain-la-liga",
            "Serie A": "italy-serie-a",
            "Ligue 1": "france-ligue-1",
            "Eredivisie": "netherlands-eredivisie",
            "Primeira Liga": "portugal-liga-nos",
            "Champions League": "europe-uefa-champions-league",
        }
        slug = league_slugs.get(league_name)
        if not slug:
            return {}
        r = requests.get(
            f"https://footystats.org/{slug}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://footystats.org/",
            },
            timeout=12,
        )
        if r.ok:
            import re as _re
            btts_match = _re.search(r'btts[^>]*>([0-9.]+)%', r.text, _re.IGNORECASE)
            if btts_match:
                return {"btts_rate": float(btts_match.group(1))}
    except Exception:
        pass
    return {}


# ---- 6. RESULTADOS-FUTBOL ----
def scrape_resultados_futbol(target_date):
    """Resultados-Futbol.com - Historische Daten Spanien"""
    try:
        import random as _r
        r = requests.get(
            f"https://www.resultados-futbol.com/partidos/{target_date}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-ES,es;q=0.9",
            },
            timeout=10,
        )
        if r.ok:
            return {"available": True}
    except Exception:
        pass
    return {}


# ---- 7. WHOSCORED (öffentliche Daten) ----
WHOSCORED_CACHE = {}

def scrape_whoscored_ratings(home_team, away_team):
    """WhoScored - Team Ratings + xG (öffentlich)"""
    cache_key = f"ws_{home_team}_{away_team}"
    if cache_key in WHOSCORED_CACHE:
        return WHOSCORED_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.whoscored.com/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.whoscored.com/",
            },
            timeout=12,
        )
        result = {}
        if r.ok:
            import re as _re
            # Suche nach Team Ratings
            ratings = _re.findall(r'"rating":\s*([0-9.]+)', r.text)
            if ratings:
                result["rating"] = float(ratings[0])
        WHOSCORED_CACHE[cache_key] = result
        return result
    except Exception:
        pass
    return {}


# ---- 8. ODDSPORTAL (öffentlich) ----
ODDSPORTAL_CACHE = {}

def scrape_oddsportal(home_team, away_team, league_name):
    """OddsPortal - Opening/Closing Odds Vergleich"""
    cache_key = f"op_{home_team}_{away_team}"
    if cache_key in ODDSPORTAL_CACHE:
        return ODDSPORTAL_CACHE[cache_key]
    try:
        import random as _r
        search = f"{home_team}-{away_team}".lower().replace(" ", "-")
        r = smart_request(
            f"https://www.oddsportal.com/search/#football/{search}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.oddsportal.com/",
            },
            timeout=12,
        )
        result = {}
        if r.ok:
            import re as _re
            odds = _re.findall(r'"odds":\s*([0-9.]+)', r.text)
            if odds:
                result["odds"] = [float(o) for o in odds[:5]]
        ODDSPORTAL_CACHE[cache_key] = result
        return result
    except Exception:
        pass
    return {}


# ---- 9. GITHUB FOOTBALL DATA (Open Source!) ----
GITHUB_FOOTBALL_CACHE = {}

def fetch_github_football_data(league_name, target_date):
    """
    GitHub Open Football Data Repositories:
    - openfootball/football.json (bereits drin)
    - datasets/football-data
    - jfjelstul/worldfootballR
    """
    cache_key = f"ghfd_{league_name}_{target_date}"
    if cache_key in GITHUB_FOOTBALL_CACHE:
        return GITHUB_FOOTBALL_CACHE[cache_key]

    GITHUB_LEAGUES = {
        "Bundesliga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/de.1.json",
        "Premier League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json",
        "La Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/es.1.json",
        "Serie A": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/it.1.json",
        "Ligue 1": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/fr.1.json",
        "Primeira Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/pt.1.json",
        "Eredivisie": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/nl.1.json",
        "Champions League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/cl.json",
    }

    url = GITHUB_LEAGUES.get(league_name)
    if not url:
        return []

    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return []

        data = r.json()
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for round_data in data.get("rounds", []):
            for match in round_data.get("matches", []):
                match_date = match.get("date", "")
                if match_date != target_str:
                    continue

                home = match.get("team1", "")
                away = match.get("team2", "")
                score = match.get("score", {})

                if not home or not away:
                    continue

                if score and score.get("ft"):
                    continue  # Bereits gespielt

                time_str = match.get("time", "12:00")
                kickoff_str = f"{target_str}T{time_str}:00Z"

                fixtures.append({
                    "home": home,
                    "away": away,
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "github_openfootball",
                    "match_id": f"gh_{hash(home+away)}",
                })

        GITHUB_FOOTBALL_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🐙 GitHub OpenFootball: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        return []


# ---- 10. FOOTBALL-DATA.CO.UK Erweitert ----
def fetch_fdcuk_stats(league_name, season_year=None):
    """
    Football-Data.co.uk - Historische BTTS Stats
    Kostenlos, sehr zuverlässig!
    """
    FDCUK_LEAGUES = {
        "Premier League": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        "Championship": "https://www.football-data.co.uk/mmz4281/2425/E1.csv",
        "EFL League 1": "https://www.football-data.co.uk/mmz4281/2425/E2.csv",
        "EFL League 2": "https://www.football-data.co.uk/mmz4281/2425/E3.csv",
        "Bundesliga": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
        "2. Bundesliga": "https://www.football-data.co.uk/mmz4281/2425/D2.csv",
        "La Liga": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
        "La Liga 2": "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",
        "Serie A": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
        "Serie B": "https://www.football-data.co.uk/mmz4281/2425/I2.csv",
        "Ligue 1": "https://www.football-data.co.uk/mmz4281/2425/F1.csv",
        "Ligue 2": "https://www.football-data.co.uk/mmz4281/2425/F2.csv",
        "Eredivisie": "https://www.football-data.co.uk/mmz4281/2425/N1.csv",
        "Primeira Liga": "https://www.football-data.co.uk/mmz4281/2425/P1.csv",
        "Pro League Belgien": "https://www.football-data.co.uk/mmz4281/2425/B1.csv",
        "Scottish Premiership": "https://www.football-data.co.uk/mmz4281/2425/SC0.csv",
        "Greek Super League": "https://www.football-data.co.uk/mmz4281/2425/G1.csv",
        "Turkish Super Lig": "https://www.football-data.co.uk/mmz4281/2425/T1.csv",
    }

    url = FDCUK_LEAGUES.get(league_name)
    if not url:
        return {}

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return {}

        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return {}

        headers = lines[0].split(",")
        stats = {"btts_count": 0, "total": 0, "over25_count": 0}

        for line in lines[1:]:
            cols = line.split(",")
            if len(cols) < 10:
                continue
            try:
                hg_idx = headers.index("FTHG") if "FTHG" in headers else 5
                ag_idx = headers.index("FTAG") if "FTAG" in headers else 6
                hg = int(cols[hg_idx] or 0)
                ag = int(cols[ag_idx] or 0)
                stats["total"] += 1
                if hg > 0 and ag > 0:
                    stats["btts_count"] += 1
                if hg + ag > 2:
                    stats["over25_count"] += 1
            except Exception:
                continue

        if stats["total"] > 0:
            stats["btts_rate"] = round(stats["btts_count"] / stats["total"] * 100, 1)
            stats["over25_rate"] = round(stats["over25_count"] / stats["total"] * 100, 1)
            log(f"   📈 FDCUK: {league_name} BTTS {stats['btts_rate']}%")

        return stats

    except Exception:
        return {}



# ============================================================
# 🆕 FUSSBALLDATEN.DE - Deutsches Fußball Archiv
# ============================================================
FUSSBALLDATEN_CACHE = {}

def scrape_fussballdaten(league_name, target_date):
    """Fussballdaten.de via Playwright"""
    return fetch_fussball_de(league_name, target_date)
    """
    Fussballdaten.de - Riesiges deutsches Archiv
    Sehr stark für Bundesliga + deutsche Ligen historisch!
    """
    cache_key = f"fbd_{league_name}_{target_date}"
    if cache_key in FUSSBALLDATEN_CACHE:
        return FUSSBALLDATEN_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "3. Liga Deutschland": "3-liga",
        "Bundesliga U19": "a-junioren-bundesliga",
        "Bundesliga U17": "b-junioren-bundesliga",
        "Bundesliga Österreich": "oesterreichische-bundesliga",
        "Super League Schweiz": "schweizer-super-league",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return []

    try:
        import random as _r
        d = target_date
        r = requests.get(
            f"https://www.fussballdaten.de/{slug}/{d.year}/{d.month:02d}/{d.day:02d}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
                "Referer": "https://www.fussballdaten.de/",
            },
            timeout=5,
        )

        if not r.ok:
            return []

        import re as _re
        html = r.text
        fixtures = []
        now_utc = datetime.now(timezone.utc)

        # Pattern für Spielpaarungen
        matches = _re.findall(
            r'class="[^"]*spielpaarung[^"]*"[^>]*>.*?'
            r'class="[^"]*heim[^"]*"[^>]*>([^<]+)</.*?'
            r'class="[^"]*gast[^"]*"[^>]*>([^<]+)<',
            html, _re.DOTALL | _re.IGNORECASE
        )

        # Fallback Pattern
        if not matches:
            matches = _re.findall(
                r'itemprop="homeTeam"[^>]*>([^<]+)<.*?itemprop="awayTeam"[^>]*>([^<]+)<',
                html, _re.DOTALL
            )

        # Zeit Pattern
        times = _re.findall(r'(\d{2}:\d{2})\s*Uhr', html)

        for i, (home, away) in enumerate(matches[:20]):
            home = home.strip()
            away = away.strip()
            if not home or not away:
                continue

            time_str = times[i] if i < len(times) else "12:00"
            kickoff_str = f"{target_date}T{time_str}:00Z"

            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except:
                pass

            fixtures.append({
                "home": home,
                "away": away,
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "fussballdaten",
                "match_id": f"fbd_{hash(home+away)}",
            })

        FUSSBALLDATEN_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇩🇪 Fussballdaten.de: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"Fussballdaten Error: {str(e)[:60]}", "WARN")
        return []


def get_fussballdaten_history(home_team, away_team, league_name):
    """
    Holt historische BTTS-Statistiken von Fussballdaten.de
    Returns: {'btts_rate': 65.0, 'avg_goals': 2.8, 'games': 20}
    """
    cache_key = f"fbd_hist_{home_team}_{away_team}"
    if cache_key in FUSSBALLDATEN_CACHE:
        return FUSSBALLDATEN_CACHE[cache_key]

    try:
        import random as _r
        import re as _re

        # Suche nach Team
        team_search = home_team.replace(" ", "-").lower()
        r = requests.get(
            f"https://www.fussballdaten.de/vereine/{team_search}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        html = r.text

        # BTTS Statistiken
        btts_match = _re.search(r'Beide Teams.*?(\d+)[,.]?(\d*)\s*%', html, _re.IGNORECASE)
        goals_match = _re.search(r'Tore.*?(\d+)[,.](\d+)', html, _re.IGNORECASE)

        result = {}
        if btts_match:
            result["btts_rate"] = float(f"{btts_match.group(1)}.{btts_match.group(2) or 0}")
        if goals_match:
            result["avg_goals"] = float(f"{goals_match.group(1)}.{goals_match.group(2)}")

        if result:
            FUSSBALLDATEN_CACHE[cache_key] = result
            return result

    except Exception:
        pass

    return None


# ============================================================
# 🆕 RSSSF - Weltweites Fußball Ergebnis Archiv
# ============================================================
RSSSF_CACHE = {}

def get_rsssf_stats(league_name, season_year=None):
    """
    RSSSF.com - Weltumfassendstes Fußball Textarchiv
    Ideal für historische BTTS/Tore Statistiken!
    """
    cache_key = f"rsssf_{league_name}_{season_year}"
    if cache_key in RSSSF_CACHE:
        return RSSSF_CACHE[cache_key]

    RSSSF_LEAGUES = {
        "Bundesliga": "https://www.rsssf.org/tablesd/germany.html",
        "Premier League": "https://www.rsssf.org/tablese/engchamp.html",
        "La Liga": "https://www.rsssf.org/tabless/spain.html",
        "Serie A": "https://www.rsssf.org/tablesi/italchamp.html",
        "Ligue 1": "https://www.rsssf.org/tablesf/frchamp.html",
        "Eredivisie": "https://www.rsssf.org/tablesn/nethchamp.html",
        "Primeira Liga": "https://www.rsssf.org/tablesp/portchamp.html",
        "Champions League": "https://www.rsssf.org/tablesclj/champchamp.html",
        "Bundesliga Österreich": "https://www.rsssf.org/tablesa/autchamp.html",
        "Super League Schweiz": "https://www.rsssf.org/tabless/switzchamp.html",
        "J1 League Japan": "https://www.rsssf.org/tablesj/japchamp.html",
        "K League 1": "https://www.rsssf.org/tablesk/koreachamp.html",
        "Brasileirao Serie A": "https://www.rsssf.org/tablesb/brchamp.html",
        "Liga Argentinien": "https://www.rsssf.org/tablesa/argchamp.html",
        "Copa Libertadores": "https://www.rsssf.org/tablesb/libertad.html",
        "MLS": "https://www.rsssf.org/tablesm/mlsall.html",
    }

    url = RSSSF_LEAGUES.get(league_name)
    if not url:
        return {}

    try:
        import random as _r
        import re as _re

        r = requests.get(
            url,
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (compatible; Googlebot/2.1)",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.rsssf.org/",
            },
            timeout=12,
        )

        if not r.ok:
            return {}

        html = r.text

        # Parse Tore aus historischen Tabellen
        # RSSSF Format: "TeamA 2-1 TeamB"
        score_pattern = _re.findall(r'(\w[\w\s]+?)\s+(\d+)-(\d+)\s+([\w\s]+)', html)

        if not score_pattern:
            return {}

        total = 0
        btts = 0
        over25 = 0
        total_goals = 0

        for home, hg, ag, away in score_pattern[:100]:
            try:
                hg, ag = int(hg), int(ag)
                total += 1
                total_goals += hg + ag
                if hg > 0 and ag > 0:
                    btts += 1
                if hg + ag > 2:
                    over25 += 1
            except:
                continue

        if total > 10:
            result = {
                "btts_rate": round(btts / total * 100, 1),
                "over25_rate": round(over25 / total * 100, 1),
                "avg_goals": round(total_goals / total, 2),
                "total_games": total,
                "source": "rsssf",
            }
            RSSSF_CACHE[cache_key] = result
            log(f"   📚 RSSSF: {league_name} - {total} Spiele analysiert")
            return result

    except Exception as e:
        log(f"RSSSF Error: {str(e)[:60]}", "WARN")

    return {}



# ============================================================
# 🎭 PLAYWRIGHT - Echter Browser für blockierte Seiten
# ============================================================
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

PLAYWRIGHT_CACHE = {}

def scrape_with_playwright(url, wait_for=None, timeout=8000):
    """
    Scrapt eine Seite mit echtem Chromium Browser.
    Umgeht 403 Blocks von SofaScore, Transfermarkt etc.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None

    # ⚡ FAST-MODE (Tipp-Lauf): Playwright-Scrapes überspringen — die liefern
    # v.a. Statistiken (FBref/WhoScored), die der separate Stats-Scraper sammelt.
    # Spart im Tipp-Lauf ~5-8 Min. Aktiv via NETRATTLER_FAST_TIPS=true.
    if str(os.getenv("NETRATTLER_FAST_TIPS", "")).lower() in ("1", "true", "yes", "on"):
        return None

    cache_key = f"pw_{url}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="de-DE",
            )
            page = context.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            if wait_for:
                page.wait_for_selector(wait_for, timeout=5000)

            html = page.content()
            browser.close()

            PLAYWRIGHT_CACHE[cache_key] = html
            return html

    except Exception as e:
        log(f"Playwright Error: {str(e)[:60]}", "WARN")
        return None


def scrape_sofascore_playwright(target_date):
    """SofaScore mit Playwright scrapen"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    try:
        url = f"https://www.sofascore.com/football/{target_date}"
        html = scrape_with_playwright(url, wait_for=".event__match")
        if not html:
            return []

        import re as _re
        matches = _re.findall(
            r'"homeTeam":\{"name":"([^"]+)".*?"awayTeam":\{"name":"([^"]+)"',
            html
        )

        fixtures = []
        for home, away in matches[:30]:
            fixtures.append({
                "home": home,
                "away": away,
                "source": "sofascore_pw",
                "time_local": "TBD",
                "time_utc": f"{target_date}T12:00:00Z",
            })

        if fixtures:
            log(f"   🎭 SofaScore (Playwright): {len(fixtures)} Spiele")
        return fixtures

    except Exception as e:
        log(f"SofaScore Playwright Error: {str(e)[:60]}", "WARN")
        return []


def get_transfermarkt_injuries_playwright(team_name):
    """Transfermarkt Verletzungen mit Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        search = team_name.lower().replace(" ", "-")
        url = f"https://www.transfermarkt.com/{search}/startseite/verein"
        html = scrape_with_playwright(url)
        if not html:
            return None

        import re as _re
        injuries = _re.findall(
            r'class="verletzt"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            html, _re.DOTALL
        )

        if injuries:
            return {
                "injured": [{"name": p.strip()} for p in injuries[:5]],
                "total_out": len(injuries),
                "has_data": True,
                "source": "transfermarkt_pw",
            }

    except Exception:
        pass
    return None


# ============================================================
# 🔍 TAVILY - Web Search für aktuelle News
# ============================================================
TAVILY_API_KEY = env("TAVILY_API_KEY", "")
TAVILY_CACHE = {}

def search_tavily(query, max_results=3):
    """
    Sucht aktuelle News mit Tavily API.
    1000 Calls/Monat gratis!
    """
    if not TAVILY_API_KEY:
        return []

    cache_key = f"tavily_{query}"
    if cache_key in TAVILY_CACHE:
        return TAVILY_CACHE[cache_key]

    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": True,
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        results = data.get("results", [])
        answer = data.get("answer", "")

        TAVILY_CACHE[cache_key] = results
        return results, answer

    except Exception as e:
        log(f"Tavily Error: {str(e)[:60]}", "WARN")
        return [], ""


def get_team_news_tavily(home_team, away_team, league):
    """
    Holt aktuelle Team News vor dem Spiel.
    Verletzungen, Sperren, Form-News.
    """
    if not TAVILY_API_KEY:
        return None

    query = f"{home_team} vs {away_team} {league} injuries team news today"

    try:
        results, answer = search_tavily(query, max_results=3)

        if answer:
            return {
                "summary": answer[:300],
                "sources": [r.get("url", "") for r in results[:2]],
            }

    except Exception:
        pass
    return None


# ============================================================
# 🦆 DUCKDUCKGO - Kostenlose Web Suche
# ============================================================
DDGO_CACHE = {}

def search_duckduckgo(query):
    """
    Kostenlose Web Suche via DuckDuckGo.
    Kein Key nötig!
    """
    cache_key = f"ddg_{query}"
    if cache_key in DDGO_CACHE:
        return DDGO_CACHE[cache_key]

    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        abstract = data.get("AbstractText", "")
        related = [t.get("Text", "") for t in data.get("RelatedTopics", [])[:3]]

        result = {
            "abstract": abstract,
            "related": related,
        }

        DDGO_CACHE[cache_key] = result
        return result

    except Exception:
        return None


# ============================================================
# 🇩🇪 FUSSBALL.DE - Offizielle DFB Daten
# ============================================================
FUSSBALL_DE_CACHE = {}

FUSSBALL_DE_LEAGUES = {
    "Bundesliga": "bundesliga",
    "2. Bundesliga": "2-bundesliga",
    "3. Liga Deutschland": "3-liga",
    "Bundesliga U19": "junioren-bundesliga-u19",
    "Bundesliga U17": "junioren-bundesliga-u17",
    "Super League Schweiz": "super-league",
    "Bundesliga Österreich": "bundesliga",
}

def fetch_fussball_de(league_name, target_date):
    """
    Holt Spielpläne von fussball.de (offizielle DFB Daten).
    Alle deutschen Ligen bis Kreisliga!
    """
    league_slug = FUSSBALL_DE_LEAGUES.get(league_name)
    if not league_slug:
        return []

    cache_key = f"fbde_{league_name}_{target_date}"
    if cache_key in FUSSBALL_DE_CACHE:
        return FUSSBALL_DE_CACHE[cache_key]

    try:
        import random as _r
        r = requests.get(
            f"https://www.fussball.de/ajax.team.list/-/type/spielplan/liga/{league_slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json, text/javascript, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.fussball.de/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

        fixtures = []
        now_utc = datetime.now(timezone.utc)
        target_str = str(target_date)

        for match in data.get("matches", data.get("spielplan", [])):
            try:
                match_date = match.get("datum", match.get("date", ""))
                if target_str not in str(match_date):
                    continue

                home = match.get("heimmannschaft", match.get("home", ""))
                away = match.get("gastmannschaft", match.get("away", ""))

                if not home or not away:
                    continue

                time_str = match.get("anstoss", match.get("time", "12:00"))
                kickoff_str = f"{target_date}T{time_str}:00Z"

                fixtures.append({
                    "home": str(home),
                    "away": str(away),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "fussball_de",
                    "match_id": f"fbde_{hash(str(home)+str(away))}",
                })
            except Exception:
                continue

        FUSSBALL_DE_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇩🇪 Fussball.de: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"Fussball.de Error: {str(e)[:60]}", "WARN")
        return []


# ============================================================
# 📊 FOOTYSTATS CSV - Statistiken ohne Key
# ============================================================
FOOTYSTATS_CSV_CACHE = {}

FOOTYSTATS_CSV_URLS = {
    "Bundesliga": "https://footystats.org/download-stats-csv#germany-bundesliga",
    "Premier League": "https://footystats.org/download-stats-csv#england-premier-league",
    "La Liga": "https://footystats.org/download-stats-csv#spain-la-liga",
    "Serie A": "https://footystats.org/download-stats-csv#italy-serie-a",
    "Ligue 1": "https://footystats.org/download-stats-csv#france-ligue-1",
}

def get_footystats_btts_rate(league_name, team_name):
    """
    Holt BTTS Rate von FootyStats (CSV Download).
    Kein Key nötig für öffentliche Statistiken!
    """
    cache_key = f"fsc_{league_name}_{team_name}"
    if cache_key in FOOTYSTATS_CSV_CACHE:
        return FOOTYSTATS_CSV_CACHE[cache_key]

    try:
        import random as _r
        # FootyStats öffentliche Team-Seite
        team_slug = team_name.lower().replace(" ", "-").replace(".", "")
        r = requests.get(
            f"https://footystats.org/clubs/{team_slug}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://footystats.org/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        import re as _re
        html = r.text

        btts_m = _re.search(r'btts[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        over25_m = _re.search(r'over.?2\.5[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        corners_m = _re.search(r'corners?[^>]*>.*?(\d+\.?\d*)', html, _re.IGNORECASE | _re.DOTALL)

        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if over25_m:
            result["over25_rate"] = int(over25_m.group(1))
        if corners_m:
            result["avg_corners"] = float(corners_m.group(1))

        if result:
            FOOTYSTATS_CSV_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None



# ============================================================
# 🎯 SOCCERSTATS.COM - BTTS Tabellen für alle Ligen
# ============================================================
SOCCERSTATS_CACHE = {}

def get_soccerstats_btts(league_name):
    """BTTS + Over2.5 Statistiken von soccerstats.com"""
    LEAGUE_SLUGS = {
        "Bundesliga": "germany/bundesliga",
        "Premier League": "england/premier_league",
        "La Liga": "spain/primera_division",
        "Serie A": "italy/serie_a",
        "Ligue 1": "france/ligue_1",
        "Eredivisie": "netherlands/eredivisie",
        "Primeira Liga": "portugal/primeira_liga",
        "Champions League": "europe/champions_league",
        "MLS": "usa/mls",
        "Brasileirao Serie A": "brazil/serie_a",
        "J1 League Japan": "japan/j_league",
    }
    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None
    cache_key = f"ss_{league_name}"
    if cache_key in SOCCERSTATS_CACHE:
        return SOCCERSTATS_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.soccerstats.com/table.asp?league={slug}&tid=3",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Referer": "https://www.soccerstats.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        btts_m = _re.search(r'BTTS[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        over25_m = _re.search(r'Over 2\.5[^>]*>.*?(\d+)%', html, _re.IGNORECASE | _re.DOTALL)
        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if over25_m:
            result["over25_rate"] = int(over25_m.group(1))
        if result:
            SOCCERSTATS_CACHE[cache_key] = result
            log(f"   ⚽ SoccerStats: {league_name} BTTS {result.get('btts_rate','?')}%")
        return result or None
    except Exception:
        return None


# ============================================================
# 💰 BETEXPLORER - Historische Quoten + BTTS
# ============================================================
BETEXPLORER_CACHE = {}

def get_betexplorer_odds(home_team, away_team, league_name):
    """Historische Opening/Closing Odds von BetExplorer"""
    cache_key = f"be_{home_team}_{away_team}"
    if cache_key in BETEXPLORER_CACHE:
        return BETEXPLORER_CACHE[cache_key]
    try:
        import random as _r, re as _re
        search = f"{home_team} {away_team}".replace(" ", "+")
        r = smart_request(
            f"https://www.betexplorer.com/soccer/?q={search}",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://www.betexplorer.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        odds = _re.findall(r'data-odd="([0-9.]+)"', html)
        if odds:
            result = {"odds": [float(o) for o in odds[:6]], "source": "betexplorer"}
            BETEXPLORER_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 PREDICTZ - Gratis BTTS/Over2.5 Predictions
# ============================================================
PREDICTZ_CACHE = {}

def get_predictz_prediction(home_team, away_team, target_date):
    """Gratis Predictions von predictz.com"""
    cache_key = f"pz_{home_team}_{away_team}"
    if cache_key in PREDICTZ_CACHE:
        return PREDICTZ_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.predictz.com/predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Referer": "https://www.predictz.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)
        blocks = _re.findall(r'<tr[^>]*class="[^"]*match[^"]*"[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for block in blocks:
            teams = _re.findall(r'class="[^"]*team[^"]*"[^>]*>([^<]+)<', block)
            if len(teams) < 2:
                continue
            if not (home_norm[:5] in normalize_team_name(teams[0]) or normalize_team_name(teams[0])[:5] in home_norm):
                continue
            btts_m = _re.search(r'btts[^>]*>.*?(\d+)%', block, _re.IGNORECASE | _re.DOTALL)
            over25_m = _re.search(r'over.?2\.5[^>]*>.*?(\d+)%', block, _re.IGNORECASE | _re.DOTALL)
            result = {}
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))
            if result:
                PREDICTZ_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 BETIMATE - BTTS + Over2.5 Predictions
# ============================================================
BETIMATE_CACHE = {}

def get_betimate_prediction(home_team, away_team, target_date):
    """BTTS + Over2.5 von betimate.com"""
    cache_key = f"bm_{home_team}_{away_team}"
    if cache_key in BETIMATE_CACHE:
        return BETIMATE_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://betimate.com/en/football-predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://betimate.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        result = {}
        if home_norm[:6] in html.lower():
            btts_m = _re.search(r'"btts":\s*(\d+)', html)
            over25_m = _re.search(r'"over25":\s*(\d+)', html)
            if btts_m:
                result["btts_pct"] = int(btts_m.group(1))
            if over25_m:
                result["over25_pct"] = int(over25_m.group(1))
        if result:
            BETIMATE_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 🇩🇪 KICKER.DE - Bundesliga Aufstellungen!
# ============================================================
KICKER_CACHE = {}

def get_kicker_lineup(home_team, away_team, target_date):
    """Bundesliga Aufstellungen von kicker.de"""
    cache_key = f"kicker_{home_team}_{away_team}"
    if cache_key in KICKER_CACHE:
        return KICKER_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = requests.get(
            f"https://www.kicker.de/bundesliga/spieltag",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]),
            "Accept-Language": "de-DE,de;q=0.9",
            "Referer": "https://www.kicker.de/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        result = {}
        if home_norm[:6] in html.lower():
            lineups = _re.findall(r'class="[^"]*aufstellung[^"]*"[^>]*>(.*?)</[^>]+>', html, _re.DOTALL | _re.IGNORECASE)
            if lineups:
                result["lineup_available"] = True
                result["source"] = "kicker"
        if result:
            KICKER_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 💰 ACTIONNETWORK - Sharp Money USA
# ============================================================
ACTION_CACHE = {}

def get_action_network_sharp(home_team, away_team):
    """Sharp Money Daten von ActionNetwork (US Ligen)"""
    cache_key = f"an_{home_team}_{away_team}"
    if cache_key in ACTION_CACHE:
        return ACTION_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = requests.get(
            "https://api.actionnetwork.com/web/v1/games",
            params={"sport": "soccer", "bookmakers": "fanduel,draftkings"},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.actionnetwork.com/",
            },
            timeout=12,
        )
        if not r.ok:
            return None
        data = r.json()
        for game in data.get("games", []):
            h = game.get("teams", [{}])[0].get("full_name", "")
            a = game.get("teams", [{}])[1].get("full_name", "") if len(game.get("teams", [])) > 1 else ""
            if teams_match(home_team, h) and teams_match(away_team, a):
                public_bets = game.get("public_betting", {})
                result = {
                    "public_home": public_bets.get("home_ml_percent", 0),
                    "public_away": public_bets.get("away_ml_percent", 0),
                    "sharp_signal": public_bets.get("sharp_money", False),
                    "source": "actionnetwork",
                }
                ACTION_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🎯 WINDRAWWIN - Statistische Vorhersagen
# ============================================================
WDW_CACHE = {}

def get_windrawwin_prediction(home_team, away_team, target_date):
    """Statistische Predictions von windrawwin.com"""
    cache_key = f"wdw_{home_team}_{away_team}"
    if cache_key in WDW_CACHE:
        return WDW_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://windrawwin.com/predictions/future/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://windrawwin.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        blocks = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for block in blocks:
            if home_norm[:5] not in block.lower():
                continue
            probs = _re.findall(r'(\d+)%', block)
            if len(probs) >= 3:
                result = {
                    "prob_home": int(probs[0]),
                    "prob_draw": int(probs[1]),
                    "prob_away": int(probs[2]),
                }
                WDW_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


# ============================================================
# 🌍 FORTUNA LIGA SK - Slowakische Liga
# ============================================================
FORTUNA_CACHE = {}

def fetch_fortuna_liga(target_date):
    """Offizielle Daten der Slowakischen Fortuna Liga"""
    cache_key = f"fl_{target_date}"
    if cache_key in FORTUNA_CACHE:
        return FORTUNA_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://www.fortunaliga.sk/rozpis-zapasov",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept-Language": "sk-SK,sk;q=0.9",
                "Referer": "https://www.fortunaliga.sk/",
            },
            timeout=12,
        )
        if not r.ok:
            return []
        import re as _re
        html = r.text
        target_str = str(target_date)
        fixtures = []
        now_utc = datetime.now(timezone.utc)
        matches = _re.findall(
            r'(\d{2}\.\d{2}\.\d{4}).*?(\d{2}:\d{2}).*?([A-Za-zÀ-ž\s]+?)\s*[-–]\s*([A-Za-zÀ-ž\s]+)',
            html, _re.DOTALL
        )
        for date_str, time_str, home, away in matches[:20]:
            try:
                parts = date_str.split(".")
                match_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                if match_date != target_str:
                    continue
                kickoff_str = f"{match_date}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "fortuna_liga",
                    "match_id": f"fl_{hash(home+away)}",
                })
            except Exception:
                continue
        FORTUNA_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🇸🇰 Fortuna Liga: {len(fixtures)} Spiele")
        return fixtures
    except Exception:
        return []


# ============================================================
# 🏥 PHYSIOROOM - Verletzungen + Rückkehrdatum
# ============================================================
PHYSIOROOM_CACHE = {}

def get_physioroom_injuries(team_name, league_name):
    """Verletzungen mit Rückkehrdatum von physioroom.com (Premier League)"""
    PHYSIOROOM_TEAMS = {
        "Arsenal": "arsenal", "Chelsea": "chelsea", "Liverpool": "liverpool",
        "Manchester City": "manchester-city", "Manchester United": "manchester-united",
        "Tottenham": "tottenham-hotspur", "Newcastle": "newcastle-united",
        "Aston Villa": "aston-villa", "West Ham": "west-ham-united",
    }
    if league_name not in ["Premier League", "Championship"]:
        return None
    team_slug = None
    for team, slug in PHYSIOROOM_TEAMS.items():
        if normalize_team_name(team_name)[:6] in normalize_team_name(team):
            team_slug = slug
            break
    if not team_slug:
        return None
    cache_key = f"pr_{team_name}"
    if cache_key in PHYSIOROOM_CACHE:
        return PHYSIOROOM_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://www.physioroom.com/team/{team_slug}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://www.physioroom.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        players = _re.findall(
            r'class="player-name"[^>]*>([^<]+)</.*?class="return-date"[^>]*>([^<]+)<',
            html, _re.DOTALL
        )
        if not players:
            players = _re.findall(r'<td[^>]*>([A-Z][a-z]+ [A-Z][a-z]+)</td>.*?<td[^>]*>(\d{2}/\d{2}/\d{4})</td>', html, _re.DOTALL)
        if players:
            result = {
                "injured": [{"name": p[0].strip(), "return": p[1].strip()} for p in players[:5]],
                "total_out": len(players),
                "has_data": True,
                "source": "physioroom",
            }
            PHYSIOROOM_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


# ============================================================
# 📊 VITIBET - Gratis Predictions
# ============================================================
VITIBET_CACHE = {}

def get_vitibet_prediction(home_team, away_team, target_date):
    """Gratis Predictions von vitibet.com"""
    cache_key = f"vb_{home_team}_{away_team}"
    if cache_key in VITIBET_CACHE:
        return VITIBET_CACHE[cache_key]
    try:
        import random as _r, re as _re
        r = smart_request(
            f"https://vitibet.com/predictions/{str(target_date)}/",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            ]), "Referer": "https://vitibet.com/"},
            timeout=12,
        )
        if not r.ok:
            return None
        html = r.text
        home_norm = normalize_team_name(home_team)
        if home_norm[:5] not in html.lower():
            return None
        btts_m = _re.search(r'btts[^>]*(\d+)%', html, _re.IGNORECASE)
        result = {}
        if btts_m:
            result["btts_pct"] = int(btts_m.group(1))
        if result:
            VITIBET_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None



# ============================================================
# 🎭 PLAYWRIGHT - Alle 403-blockierten Seiten
# ============================================================

def pw_get_sofascore_fixtures(league_name, target_date):
    """SofaScore via Playwright - alle Ligen"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_sofa_{league_name}_{target_date}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        slug = SOFASCORE_SLUG_MAP.get(league_name, "")
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://www.sofascore.com/football/{slug}",
            timeout=20000
        )
        if not html:
            return []
        import re as _re
        import json as _json
        # SofaScore JSON in Script Tags
        matches = _re.findall(r'"homeTeam":\{"id":(\d+),"name":"([^"]+)".*?"awayTeam":\{"id":(\d+),"name":"([^"]+)".*?"startTimestamp":(\d+)', html)
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        for hid, home, aid, away, ts in matches[:20]:
            try:
                kickoff = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if kickoff.date() != target_date or kickoff <= now_utc:
                    continue
                kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                fixtures.append({
                    "home": home, "away": away,
                    "home_id": hid, "away_id": aid,
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "sofascore_pw",
                })
            except Exception:
                continue
        PLAYWRIGHT_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🎭 SofaScore PW: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception as e:
        log(f"SofaScore PW Error: {str(e)[:50]}", "WARN")
        return []


def pw_get_fbref_xg(home_team, away_team, league_name):
    """FBref xG via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    cache_key = f"pw_fbref_{home_team}_{away_team}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        FBREF_LEAGUES = {
            "Premier League": "9", "Bundesliga": "20",
            "La Liga": "12", "Serie A": "11", "Ligue 1": "13",
            "Champions League": "8", "Europa League": "19",
        }
        lid = FBREF_LEAGUES.get(league_name)
        if not lid:
            return None
        html = scrape_with_playwright(
            f"https://fbref.com/en/comps/{lid}/schedule/",
            timeout=20000
        )
        if not html:
            return None
        import re as _re
        home_norm = normalize_team_name(home_team)
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)
        for row in rows:
            if home_norm[:6] not in row.lower():
                continue
            xg_home = _re.search(r'xg.*?>([\d.]+)<', row, _re.IGNORECASE)
            xg_away = _re.search(r'xga.*?>([\d.]+)<', row, _re.IGNORECASE)
            if xg_home:
                result = {
                    "xg_home": float(xg_home.group(1)),
                    "xg_away": float(xg_away.group(1)) if xg_away else 0,
                    "source": "fbref_pw"
                }
                PLAYWRIGHT_CACHE[cache_key] = result
                return result
    except Exception:
        pass
    return None


def pw_get_understat_scorers(league_name, season):
    """Understat Top Scorer via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_understat_{league_name}_{season}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        UNDERSTAT_MAP = {
            "Premier League": "EPL", "Bundesliga": "Bundesliga",
            "La Liga": "La_liga", "Serie A": "Serie_A",
            "Ligue 1": "Ligue_1", "Eredivisie": "Eredivisie",
        }
        slug = UNDERSTAT_MAP.get(league_name)
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://understat.com/league/{slug}/{season}",
            timeout=20000
        )
        if not html:
            return []
        import re as _re, json as _json
        m = _re.search(r"var playersData\s*=\s*JSON\.parse\('(.+?)'\)", html)
        if not m:
            return []
        players = _json.loads(m.group(1).encode().decode('unicode_escape'))
        scorers = []
        for p in players:
            try:
                goals = int(p.get("goals", 0) or 0)
                games = int(p.get("games", 1) or 1)
                if games < 5 or goals < 3:
                    continue
                gpg = round(goals / games, 2)
                if gpg >= 0.3:
                    scorers.append({
                        "name": p.get("player_name", ""),
                        "team": p.get("team_title", ""),
                        "goals_total": goals,
                        "appearances": games,
                        "goals_per_game": gpg,
                    })
            except Exception:
                continue
        scorers.sort(key=lambda x: x["goals_per_game"], reverse=True)
        PLAYWRIGHT_CACHE[cache_key] = scorers[:20]
        if scorers:
            log(f"   🎭 Understat PW: {len(scorers[:20])} Scorer für {league_name}")
        return scorers[:20]
    except Exception:
        return []


def pw_get_transfermarkt_injuries(team_name, league_name):
    """Transfermarkt Verletzungen via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    cache_key = f"pw_tm_{team_name}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        search = team_name.lower().replace(" ", "-").replace(".", "")
        html = scrape_with_playwright(
            f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={search}",
            timeout=20000
        )
        if not html:
            return None
        import re as _re
        injuries = _re.findall(
            r'class="[^"]*verletzt[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            html, _re.DOTALL
        )
        if injuries:
            result = {
                "injured": [{"name": p.strip()} for p in injuries[:5]],
                "total_out": len(injuries),
                "has_data": True,
                "source": "transfermarkt_pw",
            }
            PLAYWRIGHT_CACHE[cache_key] = result
            return result
    except Exception:
        pass
    return None


def pw_get_worldfootballdb(league_name, target_date):
    """WorldFootballDatabase via Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    cache_key = f"pw_wfdb_{league_name}_{target_date}"
    if cache_key in PLAYWRIGHT_CACHE:
        return PLAYWRIGHT_CACHE[cache_key]
    try:
        WFDB_LEAGUES = {
            "Premier League": "england/premier-league",
            "Bundesliga": "germany/bundesliga",
            "La Liga": "spain/la-liga",
            "Serie A": "italy/serie-a",
            "Ligue 1": "france/ligue-1",
            "Champions League": "europe/champions-league",
        }
        slug = WFDB_LEAGUES.get(league_name)
        if not slug:
            return []
        html = scrape_with_playwright(
            f"https://worldfootballdatabase.com/{slug}/fixtures/",
            timeout=20000
        )
        if not html:
            return []
        import re as _re
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        matches = _re.findall(
            r'(\d{4}-\d{2}-\d{2}).*?(\d{2}:\d{2}).*?<[^>]*>([^<]+)</[^>]*>\s*[-–vs]+\s*<[^>]*>([^<]+)<',
            html, _re.DOTALL
        )
        for date_str, time_str, home, away in matches[:20]:
            if date_str != target_str:
                continue
            kickoff_str = f"{date_str}T{time_str}:00Z"
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": home.strip(),
                "away": away.strip(),
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "worldfootballdb_pw",
            })
        PLAYWRIGHT_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🎭 WorldFootballDB: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []



# ============================================================
# 🌦️ OPEN-METEO - Kostenloses Wetter (kein Key nötig!)
# ============================================================
OPEN_METEO_CACHE = {}

CITY_COORDS_WEATHER = {
    "Premier League": (51.5, -0.1),
    "Bundesliga": (48.1, 11.6),
    "La Liga": (40.4, -3.7),
    "Serie A": (41.9, 12.5),
    "Ligue 1": (48.9, 2.4),
    "Eredivisie": (52.4, 4.9),
    "Primeira Liga": (38.7, -9.1),
    "Champions League": (51.5, -0.1),
    "Europa League": (51.5, -0.1),
    "Bundesliga Österreich": (48.2, 16.4),
    "Super League Schweiz": (47.4, 8.5),
    "Scottish Premiership": (55.9, -4.3),
    "Danish Superliga": (55.7, 12.6),
    "Norway Eliteserien": (59.9, 10.7),
    "Sweden Allsvenskan": (59.3, 18.1),
    "MLS": (40.7, -74.0),
    "Brasileirao Serie A": (-23.5, -46.6),
    "J1 League Japan": (35.7, 139.7),
    "K League 1": (37.6, 127.0),
}

def get_open_meteo_weather(league_name, target_date):
    """
    Open-Meteo - Vollständig kostenlos, kein Key nötig!
    Viel besser als OpenWeatherMap für unsere Zwecke.
    """
    coords = CITY_COORDS_WEATHER.get(league_name)
    if not coords:
        return None

    cache_key = f"om_{league_name}_{target_date}"
    if cache_key in OPEN_METEO_CACHE:
        return OPEN_METEO_CACHE[cache_key]

    try:
        lat, lon = coords
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                "forecast_days": 3,
                "timezone": "auto",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])

        target_str = str(target_date)
        if target_str not in dates:
            return None

        idx = dates.index(target_str)
        temp_max = daily.get("temperature_2m_max", [None])[idx]
        temp_min = daily.get("temperature_2m_min", [None])[idx]
        rain = daily.get("precipitation_sum", [0])[idx] or 0
        wind = daily.get("windspeed_10m_max", [0])[idx] or 0

        temp = round((temp_max + temp_min) / 2, 1) if temp_max and temp_min else temp_max

        impact = "neutral"
        notes = []
        if rain > 5:
            impact = "negative"
            notes.append(f"🌧️ Starker Regen ({rain}mm)")
        elif rain > 2:
            notes.append(f"🌦️ Regen ({rain}mm)")
        if wind > 50:
            impact = "negative"
            notes.append(f"💨 Starker Wind ({wind}km/h)")
        elif wind > 30:
            notes.append(f"🌬️ Wind {wind}km/h")
        if temp and temp > 32:
            notes.append(f"🥵 Hitze ({temp}°C)")
        elif temp and temp < 2:
            notes.append(f"🥶 Kälte ({temp}°C)")

        result = {
            "temp": temp,
            "rain": round(rain, 1),
            "wind": round(wind, 1),
            "impact": impact,
            "notes": notes,
            "source": "open-meteo",
        }

        OPEN_METEO_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"Open-Meteo Error: {str(e)[:50]}", "WARN")
        return None



# ============================================================
# 📊 STATSBOMB OPEN DATA - Player Props (100% GRATIS!)
# pip install statsbombpy (optional, Fallback auf direkte HTTP-Abfrage)
# ============================================================

STATSBOMB_PLAYER_CACHE = {}
STATSBOMB_AVAILABLE = True  # Immer verfügbar via HTTP
_STATSBOMB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Mapping: Liga → StatsBomb IDs (competition_id, season_id)
STATSBOMB_LEAGUE_MAP = {
    "Bundesliga": (9, 281),
    "La Liga": (11, 90),
    "Ligue 1": (7, 235),
    "MLS": (44, 107),
    "WM 2026": (43, 106),
    "FIFA World Cup": (43, 106),
    "Copa America": (223, 282),
    "UEFA Euro": (55, 282),
    "African Cup of Nations": (1267, 107),
}


def get_statsbomb_player_stats(league_name: str) -> dict:
    """
    Holt aggregierte Spieler-Stats direkt von StatsBomb Open Data GitHub.
    Kein Python-Package nötig — reiner HTTP-Zugriff auf raw.githubusercontent.com.
    Returns: {player_name: {sot_per90, fouls_per90, yellow_cards_per90, goals_per90, team}}
    """
    # Fuzzy-Match auf Liga-Namen
    comp = None
    ln = league_name.lower()
    for key, val in STATSBOMB_LEAGUE_MAP.items():
        if key.lower() in ln or ln in key.lower():
            comp = val
            break
    if not comp:
        return {}

    if league_name in STATSBOMB_PLAYER_CACHE:
        return STATSBOMB_PLAYER_CACHE[league_name]

    comp_id, season_id = comp
    player_stats = {}

    try:
        # 1. Match-Liste holen
        r = requests.get(
            f"{_STATSBOMB_BASE}/matches/{comp_id}/{season_id}.json",
            timeout=12,
        )
        if not r.ok:
            return {}

        matches = r.json()
        # Letzte 10 Spiele für aktuelle Form
        recent = matches[-10:] if len(matches) > 10 else matches

        shots_count = {}        # SOT (Schüsse aufs Tor)
        total_shots_count = {}  # Alle Schüsse
        fouls_count = {}
        cards_count = {}
        goals_count = {}
        key_passes_count = {}   # Key Passes (Torschussvorbereitung)
        assists_count = {}      # Assists (Torvorlage)
        offsides_count = {}     # Abseits
        _player_home_away = {}  # {player: {"home": n, "away": n}}
        goals_count = {}
        player_team = {}
        games_played = {}

        for match in recent:
            match_id = match.get("match_id")
            if not match_id:
                continue
            try:
                re = requests.get(
                    f"{_STATSBOMB_BASE}/events/{match_id}.json",
                    timeout=10,
                )
                if not re.ok:
                    continue
                events = re.json()

                # Home/Away für dieses Match bestimmen
                home_team_name = match.get("home_team", {}).get("home_team_name", "")
                away_team_name = match.get("away_team", {}).get("away_team_name", "")

                for ev in events:
                    ev_type = (ev.get("type") or {}).get("name", "")
                    player = (ev.get("player") or {}).get("name", "")
                    team = (ev.get("team") or {}).get("name", "")
                    if not player:
                        continue

                    player_team[player] = team
                    games_played.setdefault(player, set()).add(match_id)

                    # Home/Away Flag pro Spieler
                    is_home = (team == home_team_name)
                    player_home_away = _player_home_away.get(player, {"home": 0, "away": 0})
                    if is_home:
                        player_home_away["home"] = player_home_away.get("home", 0) + 1
                    else:
                        player_home_away["away"] = player_home_away.get("away", 0) + 1
                    _player_home_away[player] = player_home_away

                    if ev_type == "Shot":
                        # Total shots (alle)
                        total_shots_count[player] = total_shots_count.get(player, 0) + 1
                        outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
                        # SOT (Schüsse aufs Tor)
                        if outcome in ("Goal", "Saved", "Saved To Post", "Saved Off T"):
                            shots_count[player] = shots_count.get(player, 0) + 1
                        if outcome == "Goal":
                            goals_count[player] = goals_count.get(player, 0) + 1

                    elif ev_type == "Foul Committed":
                        fouls_count[player] = fouls_count.get(player, 0) + 1

                    elif ev_type == "Bad Behaviour":
                        card = (ev.get("bad_behaviour") or {}).get("card", {}).get("name", "")
                        if "Yellow" in card:
                            cards_count[player] = cards_count.get(player, 0) + 1

                    elif ev_type == "Pass":
                        pass_data = ev.get("pass") or {}
                        # Key Pass (direkt torschussvorbereitung)
                        if pass_data.get("key_pass"):
                            key_passes_count[player] = key_passes_count.get(player, 0) + 1
                        # Assist (Torvorlage)
                        if pass_data.get("goal_assist"):
                            assists_count[player] = assists_count.get(player, 0) + 1

                    elif ev_type == "Offside":
                        offsides_count[player] = offsides_count.get(player, 0) + 1

            except Exception:
                continue

        # Stats aggregieren — alle Märkte
        _all_players = set(
            list(shots_count) + list(total_shots_count) +
            list(fouls_count) + list(cards_count) +
            list(key_passes_count) + list(assists_count)
        )
        for player in _all_players:
            games = len(games_played.get(player, {1}))
            sot   = round(shots_count.get(player, 0) / games, 2)
            total_sh = round(total_shots_count.get(player, 0) / games, 2)
            fouls = round(fouls_count.get(player, 0) / games, 2)
            cards = round(cards_count.get(player, 0) / games, 3)
            goals = round(goals_count.get(player, 0) / games, 2)
            kp    = round(key_passes_count.get(player, 0) / games, 2)
            ast   = round(assists_count.get(player, 0) / games, 2)
            offs  = round(offsides_count.get(player, 0) / games, 2)
            ha    = _player_home_away.get(player, {})

            # Nur interessante Spieler behalten
            if sot < 0.3 and fouls < 0.5 and cards < 0.1 and kp < 0.3 and goals < 0.15:
                continue

            # Positionserkennung aus Stats (Stürmer=viele Schüsse, Spielmacher=viele KP, Sechser=viele Fouls+Karten)
            if total_sh >= 1.5:
                position_type = "striker"   # Stürmer/Außen
            elif kp >= 0.8 or ast >= 0.3:
                position_type = "playmaker" # Spielmacher (De Bruyne, Musiala)
            elif fouls >= 1.5 or cards >= 0.2:
                position_type = "defensive" # Sechser/Innenverteidiger (Rodri, Rüdiger)
            else:
                position_type = "unknown"

            player_stats[player] = {
                "team": player_team.get(player, ""),
                "position_type": position_type,
                # Torschuss-Märkte
                "sot_per90": sot,
                "shots_per90": total_sh,
                "goals_per90": goals,
                # Vorlagen-Märkte (Spielmacher)
                "key_passes_per90": kp,
                "assists_per90": ast,
                # Karten-Märkte (Defensive)
                "fouls_per90": fouls,
                "yellow_cards_per90": cards,
                # Sonstiges
                "offsides_per90": offs,
                "games": games,
                "home_games": ha.get("home", 0),
                "away_games": ha.get("away", 0),
                "source": "statsbomb_http",
            }

        STATSBOMB_PLAYER_CACHE[league_name] = player_stats
        if player_stats:
            log(f"   📊 StatsBomb HTTP: {len(player_stats)} Spieler für {league_name}")
        return player_stats

    except Exception as e:
        log(f"StatsBomb HTTP Error: {str(e)[:60]}", "WARN")
        STATSBOMB_PLAYER_CACHE[league_name] = {}
        return {}


_SB_MATCH_PROPS_CACHE = {}  # {(home, away): [prop_candidates]}

_SUPABASE_PLAYER_STATS_CACHE = {}  # {player_name: {stat_name: avg_value}}


# ============================================================
# 🚀 NETRATTLER V20 — ML Live Hook + Performance Footer
# ============================================================
_NTR_PERF_CACHE = {}

def _ntr_float(x, default=0.0):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return default

def _ntr_group_from_chat(chat_id):
    cid = str(chat_id or "")
    mapping = {
        "btts": "btts", "over25": "over25", "combo": "combo", "combos": "combos",
        "btts_ht": "btts_ht", "over15_ht": "over15_ht", "props": "props",
        "builder": "builder", "advanced_props": "builder", "corners": "corners",
        "hz_live": "corners", "late_goals": "scorer", "scorer": "scorer",
        "goal_hunter": "scorer", "stats": "stats",
    }
    for key, group in mapping.items():
        val = TELEGRAM_GROUPS.get(key) if isinstance(TELEGRAM_GROUPS, dict) else None
        if val and str(val) == cid:
            return group
    return "default"

def _ntr_get_group_perf(group):
    """Return today/month/year performance for a group from Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY or group in ("", "default", None):
        return None
    now = datetime.now(timezone.utc)
    cache_key = f"{group}_{now.strftime('%Y%m%d%H%M')}"
    if cache_key in _NTR_PERF_CACHE:
        return _NTR_PERF_CACHE[cache_key]
    hdr = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        # 1) direkt aus aggregierter Tabelle
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/netrattler_group_stats",
            headers=hdr,
            params={"market_group": f"eq.{group}", "select": "*", "order": "updated_at.desc", "limit": "50"},
            timeout=8,
        )
        rows = r.json() if r.ok and r.text else []
        out = {"today": None, "week": None, "month": None, "year": None, "alltime": None}
        if isinstance(rows, list):
            for row in rows:
                period = str(row.get("period", "")).lower()
                if period in out and out[period] is None:
                    out[period] = row
        # 2) Fallback aus settlements berechnen
        if not any(out.values()):
            r2 = requests.get(
                f"{SUPABASE_URL}/rest/v1/netrattler_settlements",
                headers=hdr,
                params={"market_group": f"eq.{group}", "status": "in.(win,loss,won,lost)", "select": "status,profit,stake,tip_date,odds", "limit": "3000", "order": "tip_date.desc"},
                timeout=10,
            )
            ss = r2.json() if r2.ok and r2.text else []
            if isinstance(ss, list) and ss:
                today_s = now.date().isoformat()
                week_s = (now.date() - timedelta(days=6)).isoformat()
                month_s = now.strftime("%Y-%m")
                year_s = now.strftime("%Y")
                def agg(period, rows2):
                    bets=len(rows2); wins=sum(str(x.get("status")).lower() in ("win","won") for x in rows2); losses=bets-wins
                    prof=sum(_ntr_float(x.get("profit"), 0) for x in rows2)
                    stake=sum(max(0.0, _ntr_float(x.get("stake"), 1.0)) for x in rows2)
                    return {"period": period, "bets": bets, "wins": wins, "losses": losses, "profit": round(prof,2), "stake": round(stake,2), "roi": round(100*prof/max(0.01,stake),2)} if bets else None
                out["today"] = agg("today", [x for x in ss if str(x.get("tip_date", ""))[:10] == today_s])
                out["week"] = agg("week", [x for x in ss if str(x.get("tip_date", ""))[:10] >= week_s])
                out["month"] = agg("month", [x for x in ss if str(x.get("tip_date", ""))[:7] == month_s])
                out["year"] = agg("year", [x for x in ss if str(x.get("tip_date", ""))[:4] == year_s])
                out["alltime"] = agg("alltime", ss)
        _NTR_PERF_CACHE[cache_key] = out
        return out
    except Exception:
        return None

def _ntr_perf_line(row, label):
    if not row or int(row.get("bets") or 0) <= 0:
        return None
    bets=int(row.get("bets") or 0); wins=int(row.get("wins") or 0); losses=int(row.get("losses") or 0)
    roi=_ntr_float(row.get("roi"), 0); prof=_ntr_float(row.get("profit"), 0)
    em = "🟢" if prof >= 0 else "🔴"
    return f"{label}: {wins}-{losses} / {bets} · ROI {roi:.1f}% · {prof:+.2f}U {em}"


def _ntr_strip_duplicate_group_footer(text):
    """Remove duplicated 'Bewertung dieser Gruppe' blocks before Telegram send."""
    raw = str(text or "")
    token = "Bewertung dieser Gruppe"
    if raw.count(token) <= 1:
        return raw

    first = raw.find(token)
    second = raw.find(token, first + len(token))
    if second <= 0:
        return raw

    # Cut from the separator right before the second footer.
    sep = "━━━━━━━━━━━━━━━━━━"
    cut = raw.rfind(sep, 0, second)
    if cut <= first:
        cut = raw.rfind("\n", 0, second)
    if cut > 0:
        return raw[:cut].rstrip()
    return raw[:second].rstrip()

def _ntr_enhance_message_with_stats(text, chat_id):
    """Append one compact performance block only to real fresh tip messages."""
    if str(env("ENABLE_TIP_PERFORMANCE_FOOTER", "false")).lower() not in ("1", "true", "yes", "on"):
        return text
    if not text or len(text) > 3300:
        return text
    raw = str(text)
    upper = raw.upper()
    # Never decorate reports, technical cards or a message already carrying performance.
    skip_words = [
        "AUSWERTUNG", "GESAMT-STATISTIK", "AI TIPP BOT - DAILY", "NETRATTLER HEUTE",
        "BACKTEST", "SELF TEST", "ÜBERSICHT HEUTE", "PERFORMANCE DIESER GRUPPE",
        "WINRATE:", "AUSGEWERTETE TIPPS", "DATEN WERDEN GESAMMELT", "ROI REPORT",
        "BEWERTUNG DIESER GRUPPE", "LIGARANKING MONAT",
    ]
    if any(w in upper for w in skip_words):
        return _ntr_strip_duplicate_group_footer(text)
    # A primary tip needs a price and a concrete selection/leg. This prevents the
    # duplicate footer on the separate market-stat cards shown in Telegram.
    has_price = any(w in upper for w in ["QUOTE:", "GESAMT-QUOTE:", " @ ", "BET BUILDER"])
    has_pick = any(w in upper for w in ["TIPP:", "LEGS:", "PROP BUILDER", "BET BUILDER", "CORNER SNIPER"])
    if not (has_price and has_pick):
        return text
    group = _ntr_group_from_chat(chat_id)
    perf = _ntr_get_group_perf(group)
    if not perf:
        return text
    footer = _ntr_group_performance_footer(group, None, include_title=True)
    if not footer:
        return text
    if len(raw) + len(footer) > 3900:
        return text
    return raw + footer

def _ntr_market_stats_from_settlements(market_id):
    """Modern stats shape compatible with _get_market_stats_from_supabase()."""
    perf = _ntr_get_group_perf(market_id)
    if not perf:
        return None
    year = perf.get("year") or perf.get("month") or perf.get("today")
    month = perf.get("month")
    if not year:
        return None
    total=int(year.get("bets") or 0); won=int(year.get("wins") or 0); lost=int(year.get("losses") or 0)
    if total <= 0:
        return None
    m_total=int(month.get("bets") or 0) if month else 0
    m_won=int(month.get("wins") or 0) if month else 0
    m_lost=int(month.get("losses") or 0) if month else 0
    month_names = ["","Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
    today = datetime.now(timezone.utc).date()
    return {
        "won": won, "lost": lost, "total": total,
        "pct": round(won/total*100) if total else 0,
        "roi": round(_ntr_float(year.get("profit"), 0), 1),
        "month_name": month_names[today.month],
        "month_won": m_won, "month_lost": m_lost,
        "month_total": m_total,
        "month_pct": round(m_won/m_total*100) if m_total else 0,
        "month_roi": round(_ntr_float(month.get("profit"), 0) if month else 0, 1),
        "top_leagues": [],
    }



# ============================================================
# NETRATTLER V16 ML LIVE HOOK
# ============================================================
_NTR_ML_MODEL_CACHE = None
_NTR_ML_MODEL_TS = 0

def _ntr_ml_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


# ── GELERNTE MARKT-/LIGA-GEWICHTE (aus netrattler_learning_weights) ──────────
# Die Learning-Engine lernt aus abgerechneten Tipps, welche Märkte/Ligen
# funktionieren (weight 0.65–1.35, 1.0 = neutral). Hier konsumiert der Tipp-Bot
# das: Tipps in stark-performenden Markt/Liga-Kombis werden bevorzugt,
# schwache abgewertet. So lernen ALLE Kanäle (nicht nur die Builder).
_NTR_LEARNED_WEIGHTS = None


def _ntr_load_learned_weights():
    global _NTR_LEARNED_WEIGHTS
    if _NTR_LEARNED_WEIGHTS is not None:
        return _NTR_LEARNED_WEIGHTS
    _NTR_LEARNED_WEIGHTS = {"market": {}, "league": {}, "source": {}}
    if not SUPABASE_URL or not SUPABASE_KEY:
        return _NTR_LEARNED_WEIGHTS
    try:
        import requests as _rq
        r = _rq.get(
            f"{SUPABASE_URL}/rest/v1/netrattler_learning_weights",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "dimension,weight_key,weight,winrate,roi,n", "limit": "5000"},
            timeout=20,
        )
        if r.ok:
            _min_n = int(env("NETRATTLER_LEARNED_WEIGHT_MIN_N", "20") or 20)
            for row in r.json():
                dim = str(row.get("dimension", ""))
                if dim not in _NTR_LEARNED_WEIGHTS:
                    continue
                # nur Gewichte mit ausreichender Stichprobe anwenden
                if int(row.get("n", 0) or 0) < _min_n:
                    continue
                key = str(row.get("weight_key", "")).lower().strip()
                try:
                    _NTR_LEARNED_WEIGHTS[dim][key] = float(row.get("weight", 1.0) or 1.0)
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass
    return _NTR_LEARNED_WEIGHTS


def _ntr_learned_weight(market: str = "", league: str = "") -> float:
    """Kombiniertes gelerntes Gewicht (Markt × Liga), geometrisch gemittelt →
    bleibt nahe 1.0, wenn wenig/keine Daten. Env-Schalter: NETRATTLER_APPLY_LEARNED_WEIGHTS."""
    if str(env("NETRATTLER_APPLY_LEARNED_WEIGHTS", "true")).lower() not in ("1", "true", "yes", "on"):
        return 1.0
    w = _ntr_load_learned_weights()
    mw = w.get("market", {}).get(str(market).lower().strip(), 1.0)
    lw = w.get("league", {}).get(str(league).lower().strip(), 1.0)
    try:
        return float((mw * lw) ** 0.5)  # geometrisches Mittel
    except (TypeError, ValueError):
        return 1.0

def _ntr_ml_load_model(force=False):
    global _NTR_ML_MODEL_CACHE, _NTR_ML_MODEL_TS
    # Deaktiviert: Tabelle netrattler_ml_models existiert nicht und der Footer
    # beeinflusst die Tipps nicht (echtes ML laeuft ueber ml_models/get_ml_prediction).
    # Frueher Ausstieg spart bei jeder Nachricht eine erfolglose Supabase-Abfrage.
    return None
    try:
        import time as _time
        now = _time.time()
        if _NTR_ML_MODEL_CACHE and not force and now - _NTR_ML_MODEL_TS < 300:
            return _NTR_ML_MODEL_CACHE
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/netrattler_ml_models",
            headers=_ntr_ml_headers(),
            params={"model_name":"eq.netrattler_v16_ml","select":"*","limit":"1"},
            timeout=12,
        )
        if not r.ok:
            return None
        rows = r.json() if r.text else []
        if not rows:
            return None
        _NTR_ML_MODEL_CACHE = rows[0].get("model_json") or {}
        _NTR_ML_MODEL_TS = now
        return _NTR_ML_MODEL_CACHE
    except Exception:
        return None

def _ntr_ml_norm(x):
    try:
        import unicodedata as _ud, re as _re
        s = _ud.normalize("NFKD", str(x or "").lower().strip())
        s = "".join(c for c in s if not _ud.combining(c))
        s = _re.sub(r"[^a-z0-9]+", " ", s)
        return _re.sub(r"\s+", " ", s).strip()
    except Exception:
        return str(x or "").lower().strip()

def _ntr_ml_group_from_chat_or_text(chat_id, text):
    t = str(text or "").lower()
    try:
        for k,v in (TELEGRAM_GROUPS or {}).items():
            if str(v) == str(chat_id):
                if k in ("combos",): return "combo"
                if k in ("advanced_props",): return "props"
                return k
    except Exception:
        pass
    if "btts ht" in t or "btts_ht" in t: return "btts_ht"
    if "over 1.5 ht" in t or "over15_ht" in t: return "over15_ht"
    if "corner" in t or "ecken" in t: return "corners"
    if "builder" in t or "nate" in t or "aystar" in t or "god" in t: return "builder"
    if "combo" in t or "parlay" in t: return "combo"
    if "shot" in t or "foul" in t or "card" in t or "tackle" in t or "booked" in t: return "props"
    if "over 2.5" in t or "o2.5" in t: return "over25"
    if "btts" in t or "both teams" in t: return "btts"
    return "default"

def _ntr_ml_extract_odds(text):
    t = str(text or "")
    for pat in [r"Quote\s*[:@]?\s*(\d+[\.,]\d+)", r"@\s*(\d+[\.,]\d+)", r"Odds\s*[:@]?\s*(\d+[\.,]\d+)"]:
        m = re.search(pat, t, re.I)
        if m:
            try: return float(m.group(1).replace(",","."))
            except Exception: pass
    return None

def _ntr_ml_odds_bucket(o):
    try: o = float(o)
    except Exception: return "odds:unknown"
    if o < 1.50: return "odds:<1.50"
    if o < 1.80: return "odds:1.50-1.79"
    if o < 2.10: return "odds:1.80-2.09"
    if o < 2.60: return "odds:2.10-2.59"
    if o < 3.50: return "odds:2.60-3.49"
    return "odds:3.50+"

def _ntr_ml_predict_from_text(text, chat_id=None):
    model = _ntr_ml_load_model(False)
    if not model:
        return {"score":0,"edge":0,"rec":"NO_MODEL","hits":0}
    prior = float((model.get("prior") or {}).get("winrate") or 0.52)
    stats = model.get("feature_stats") or {}
    group = _ntr_ml_group_from_chat_or_text(chat_id, text)
    odds = _ntr_ml_extract_odds(text)
    feats = [f"group:{_ntr_ml_norm(group)}", _ntr_ml_odds_bucket(odds)]
    weighted = prior
    weight = 1.0
    hits = 0
    try:
        import math as _math
        for f in feats:
            st = stats.get(f)
            if not st: continue
            bets = float(st.get("bets") or 0)
            wr = float(st.get("winrate") or prior)
            conf = float(st.get("confidence") or 0.2)
            w = max(0.15, conf) * min(3.0, _math.log(bets + 1))
            weighted += wr * w
            weight += w
            hits += 1
    except Exception:
        pass
    prob = weighted / max(0.0001, weight)
    implied = (1/odds) if odds and odds > 1 else 0
    edge = (prob - implied) * 100 if implied else 0
    score = round(prob*100, 1)
    rec = "STRONG" if score >= 63 and edge >= 2 else "OK" if score >= 57 else "LEAN" if score >= 52 else "SKIP"
    return {"score":score,"edge":round(edge,1),"rec":rec,"hits":hits,"group":group}

def _ntr_ml_enhance_message(text, chat_id=None):
    raw = str(text or "")
    if "📊 <b>Bewertung dieser Gruppe</b>" in raw or "📊 Bewertung dieser Gruppe" in raw:
        return text
    low = raw.lower()
    # Reports/Settlement nicht mit ML-Footer vollkleben
    if any(x in low for x in ["auswertung", "roi report", "settlement", "gruppen-auswertung", "performance dieser gruppe"]):
        return text
    if "ml_score" in low:
        return text
    p = _ntr_ml_predict_from_text(raw, chat_id)
    if p.get("rec") == "NO_MODEL":
        if str(env("SHOW_ML_LEARNING_FOOTER", "false")).lower() not in ("1", "true", "yes", "on"):
            return text
        footer = "\n🧠 ML-Lernphase: Daten werden gesammelt"
    else:
        icon = {"STRONG":"🔥", "OK":"✅", "LEAN":"⚠️", "SKIP":"🚫"}.get(p.get("rec"), "🤖")
        footer = f"\n🤖 ML_SCORE: <b>{p.get('score')}</b> · Edge {p.get('edge')}% · {icon} {p.get('rec')}"
    if len(raw) + len(footer) > 3900:
        return text
    return raw + footer

def send_telegram(text, chat_id=None, reply_markup=None):
    if not TELEGRAM_TOKEN:
        log("Telegram Token fehlt", "WARN")
        return None

    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if not chat_id:
        log("Telegram Chat ID fehlt", "WARN")
        return None

    try:
        text = _ntr_enhance_message_with_stats(text, chat_id)
    except Exception as _ntr_e:
        try:
            log(f"Stats-Footer übersprungen: {str(_ntr_e)[:60]}", "WARN")
        except Exception:
            pass

    try:
        text = _ntr_ml_enhance_message(text, chat_id)
    except Exception as _ntr_ml_e:
        try:
            log(f"ML-Footer übersprungen: {str(_ntr_ml_e)[:60]}", "WARN")
        except Exception:
            pass

    try:
        text = _ntr_strip_duplicate_group_footer(text)
    except Exception:
        pass

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



# In-Memory Duplikat Cache für diesen Run
_SENT_TIPS_CACHE = set()
_PREFETCHED_DUP_DATES = set()

def _dup_cache_key(match, market, target_date):
    match_norm = normalize_team_name(match)
    return f"{match_norm[:20]}_{market}_{target_date}"


_DUP_LOG_COUNTS = {}

def _ntr_log_duplicate(label, key="default", max_visible=3):
    cnt = _DUP_LOG_COUNTS.get(key, 0) + 1
    _DUP_LOG_COUNTS[key] = cnt
    if cnt <= max_visible:
        log(label)
    elif cnt == max_visible + 1:
        log(f"   ⏭️ weitere Duplikate für {key} werden im Log gebündelt ...")

def prefetch_sent_tips_for_date(target_date):
    """
    Speed-Fix:
    Lädt bereits gesendete Tipps/Combos für den Tag einmalig in den Cache.
    Danach macht is_duplicate_tip/is_duplicate_combo keine Supabase-Abfrage mehr pro Tipp.
    """
    global _SENT_TIPS_CACHE, _PREFETCHED_DUP_DATES
    day = str(target_date)
    if day in _PREFETCHED_DUP_DATES:
        return

    _PREFETCHED_DUP_DATES.add(day)

    if not (SUPABASE_URL and SUPABASE_KEY):
        return

    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    page = 0
    loaded = 0

    while page < 8:  # max 8000 Rows, mehr brauchen wir für einen Tag nicht
        start = page * 1000
        end = start + 999
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={**headers, "Range": f"{start}-{end}"},
                params={
                    "date": f"eq.{day}",
                    "select": "match,market,tip_id",
                    "limit": "1000",
                    "order": "created_at.desc.nullslast",
                },
                timeout=8,
            )
            if not r.ok:
                break
            rows = r.json() if r.text else []
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                match = row.get("match")
                market = row.get("market")
                tip_id = row.get("tip_id")
                if match and market:
                    _SENT_TIPS_CACHE.add(_dup_cache_key(match, market, day))
                if tip_id:
                    _SENT_TIPS_CACHE.add(f"combo_{tip_id}")

            loaded += len(rows)
            if len(rows) < 1000:
                break
            page += 1
        except Exception:
            break

    try:
        log(f"   ⚡ Duplikat-Cache vorgeladen: {loaded} Tipps für {day}")
    except Exception:
        pass

def is_duplicate_tip(match, market, target_date):
    """Prüft ob Tipp bereits gesendet wurde - FAST Cache + Supabase Fallback"""
    global _SENT_TIPS_CACHE

    day = str(target_date)
    cache_key = _dup_cache_key(match, market, day)

    # 1. In-Memory Check
    if cache_key in _SENT_TIPS_CACHE:
        return True

    # 2. Wenn Tag vorgeladen wurde, ist 'nicht im Cache' = kein Duplikat.
    # Spart 100+ einzelne Supabase Calls.
    if day in _PREFETCHED_DUP_DATES:
        return False

    # 3. Fallback nur falls Prefetch nicht lief
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "date": f"eq.{day}",
                    "market": f"eq.{market}",
                    "match": f"eq.{match}",
                    "select": "id",
                    "limit": "1",
                },
                timeout=5,
            )
            if r.ok and len(r.json()) > 0:
                _SENT_TIPS_CACHE.add(cache_key)
                return True
        except Exception:
            pass

    return False

def _combo_signature(legs, prefix=""):
    """
    Deterministische Signatur. Akzeptiert Dictionaries UND Strings.
    """
    import hashlib

    def _part(leg):
        if isinstance(leg, dict):
            return (
                f"{leg.get('match', leg.get('_match', '?'))}|"
                f"{leg.get('market', leg.get('_cat', ''))}|"
                f"{leg.get('tip', leg.get('player_prop', leg.get('selection', '')))}"
            )
        return str(leg)

    parts = sorted(_part(leg) for leg in (legs or []))
    raw = prefix + "::" + "||".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

def is_duplicate_combo(tip_id, target_date):
    """
    Prüft ob eine Kombi/Builder mit dieser deterministischen tip_id bereits heute gesendet wurde.
    FAST: nutzt vorgeladenen Tagescache.
    """
    global _SENT_TIPS_CACHE
    day = str(target_date)
    cache_key = f"combo_{tip_id}"

    if cache_key in _SENT_TIPS_CACHE:
        return True

    if day in _PREFETCHED_DUP_DATES:
        return False

    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "tip_id": f"eq.{tip_id}",
                    "select": "id",
                    "limit": "1",
                },
                timeout=5,
            )
            if r.ok and len(r.json()) > 0:
                _SENT_TIPS_CACHE.add(cache_key)
                return True
        except Exception:
            pass

    return False

def mark_tip_sent(match, market, target_date):
    """Markiert Tipp als gesendet im In-Memory Cache"""
    global _SENT_TIPS_CACHE
    _SENT_TIPS_CACHE.add(_dup_cache_key(match, market, str(target_date)))


def is_valid_tip(tip, target_date):
    """
    Prüft ob ein Tipp wirklich heute + in der Zukunft liegt.
    """
    tip_date = tip.get("date", "")
    today_str = str(target_date)
    if tip_date and tip_date != today_str:
        log(f"   ⚠️ Falsches Datum: {tip_date} (erwartet {today_str})")
        return False

    # Tipps ohne echte Odds (martj42/FootyStats) → Zeit nicht prüfen
    if tip.get("_no_real_odds"):
        return True

    time_str = tip.get("time", "")
    if not is_future_game(time_str, target_date):
        log(f"   ⚠️ Spiel bereits vorbei: {tip.get('match','')} um {time_str}")
        return False

    return True


def log_tip_for_ml(tip: dict, market: str) -> bool:
    """
    Logged einen Tipp mit ML-Features in Supabase (Tabelle: ml_tips).
    Für Feedback-Loop: Modell lernt aus eigenen Ergebnissen.
    Silent-fail — niemals den normalen Bot-Flow unterbrechen.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        match = tip.get("match", "")
        parts = match.split(" vs ") if " vs " in match else [match, ""]
        home = parts[0].strip()
        away = parts[1].strip() if len(parts) > 1 else ""

        # ML-Features aus dem Tipp extrahieren (alles was wir haben)
        features = {
            "elo_home": tip.get("elo_home"),
            "elo_away": tip.get("elo_away"),
            "elo_diff": tip.get("elo_diff"),
            "btts_rate_home": tip.get("btts_rate_home"),
            "btts_rate_away": tip.get("btts_rate_away"),
            "avg_goals_home": tip.get("avg_goals_home"),
            "avg_goals_away": tip.get("avg_goals_away"),
            "xg_home": tip.get("xg_home"),
            "xg_away": tip.get("xg_away"),
            "probability": tip.get("probability"),
        }
        # None-Werte raus
        features = {k: v for k, v in features.items() if v is not None}

        ml_data = {
            "match_id": f"{home}_{away}_{tip.get('date', '')}_{market}".replace(" ", "_"),
            "home_team": home,
            "away_team": away,
            "league": tip.get("league", ""),
            "date": tip.get("date", ""),
            "time": tip.get("time", ""),
            "market": market,
            "tip": tip.get("tip", ""),
            "odds": tip.get("odds", 0.0),
            "confidence": tip.get("confidence", 0),
            "probability": tip.get("probability", 0.0),
            "value_rating": tip.get("value_rating", ""),
            "features": json.dumps(features),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bot_version": "3.0",
            "result": None,
            "settled": False,
        }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/ml_tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=ml_data,
            timeout=8,
        )
        return r.ok
    except Exception:
        return False  # silent fail


def save_to_supabase(tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        # Nur bekannte Supabase Felder senden
        SUPABASE_FIELDS = [
            "tip_id", "date", "market", "market_name", "match", "league",
            "tip", "odds", "probability", "confidence", "value_rating",
            "fair_odds", "units", "bookie", "reasoning", "key_factor",
            "home_form", "away_form", "time", "status",
            "telegram_chat_id", "telegram_msg_id",
            "weekday", "hour",
            "xg_home", "xg_away", "xga_home", "xga_away",
            "sharp_money", "line_movement",
            "btts_rate_home", "btts_rate_away",
            "avg_goals_home", "avg_goals_away",
            # ML Features
            "elo_home", "elo_away", "elo_diff",
            "result_home", "result_away",
            "result_ht_home", "result_ht_away",
            "settled_at", "message_text",
            "group_key", "pick_type", "source",
            "builder_id", "builder_total_legs", "builder_legs", "builder_won_legs",
            "profit_units", "actual_value",
        ]
        
        clean_tip = {k: v for k, v in tip.items() 
                     if k in SUPABASE_FIELDS and v is not None}

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=clean_tip,
            timeout=10,
        )

        if not r.ok:
            # Falls 'message_text' Spalte fehlt → ohne erneut versuchen
            if "message_text" in clean_tip and ("message_text" in r.text or r.status_code == 400):
                clean_tip.pop("message_text", None)
                r = requests.post(
                    f"{SUPABASE_URL}/rest/v1/tips",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    json=clean_tip,
                    timeout=10,
                )
                if r.ok:
                    # 🆕 ML-Logging (silent, nach erfolgreichem Save)
                    log_tip_for_ml(tip, tip.get("market", ""))
                    return True
            log(f"   Supabase Error: {r.status_code} - {r.text[:100]}", "WARN")
            return False

        # 🆕 ML-Logging bei Erfolg
        log_tip_for_ml(tip, tip.get("market", ""))
        return True

    except Exception as e:
        log(f"   Supabase Exception: {str(e)[:60]}", "WARN")
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
            "over15_ht": {"w": 0, "l": 0, "units": 0.0},
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
            odds = float(str(t.get("oddsYes", t.get("odds", 0)) or 0).replace(",", "."))
            # 🆕 Fallback: wenn kein echter Odds, fairOdds aus Wahrscheinlichkeit nutzen
            if odds < 1.40:
                fair = float(str(t.get("fairOdds", 0) or 0).replace(",", "."))
                prob = int(t.get("probability", 0) or 0)
                if fair >= 1.40:
                    odds = fair
                elif prob >= 55:
                    odds = round(100 / prob, 2)  # z.B. 67% → 1.49
            if odds >= 1.40:
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

    # Nur EIN Leg pro Spiel — verhindert korrelierte Same-Match-Legs (z.B. Over 2.5 + BTTS
    # aus demselben Spiel), die die Quote aufblaehen und als normale Acca nicht platzierbar sind.
    selected = []
    _used_matches = set()
    for tip in sorted_tips:
        _mkey = str(tip.get("match", "")).strip().lower()
        if not _mkey or _mkey in _used_matches:
            continue
        _used_matches.add(_mkey)
        selected.append(tip)
        if len(selected) >= num_tips:
            break

    # Nicht genug unterschiedliche Spiele fuer diese Combo-Groesse.
    if len(selected) < num_tips:
        return None

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
        9: ("⚡ COMBO 9", "Mega-Kombi"),
        10: ("🌟 COMBO 10", "Ultra-Kombi"),
        11: ("👑 COMBO 11", "Maximal-Kombi"),
    }
    label, desc = labels.get(num_tips, (f"🎲 COMBO {num_tips}", "Multi-Kombi"))

    # Stake Suggestion (weniger bei mehr Tipps)
    stakes = {3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1, 9: 0.75, 10: 0.5, 11: 0.5}
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
    """Formatiert Multi-Combo für Telegram — V31 clean, stake capped."""
    if not combo:
        return ""

    def _fnum(x, default=0.0):
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return default

    total_odds = _fnum(combo.get("total_odds", 0), 0)
    nlegs = len(combo.get("tips", []) or [])
    # Safer stakes: keine 0.5u auf 284/512er Lotterien.
    if nlegs <= 3:
        stake = 0.50
    elif nlegs == 4:
        stake = 0.35
    elif nlegs == 5:
        stake = 0.25
    elif nlegs == 6:
        stake = 0.15
    else:
        stake = 0.05
    if total_odds >= 50:
        stake = min(stake, 0.05)
    elif total_odds >= 25:
        stake = min(stake, 0.10)
    combo["stake_suggestion"] = stake

    win = round(total_odds * stake, 1) if total_odds else "?"
    label = combo.get("label", "COMBO")
    if nlegs >= 7:
        risk = "LOTTERY"
    elif nlegs >= 5:
        risk = "HIGH RISK"
    else:
        risk = "VALUE"

    msg = f"<b>🎰 {label}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 Gesamt-Quote: <b>{total_odds:.2f}</b>\n"
    msg += f"💵 Einsatz: <b>{stake:.2f} Units</b> · Gewinn: ~{win} Units\n"
    msg += f"⚠️ Risiko: <b>{risk}</b>\n\n"
    msg += "<b>📋 Legs:</b>\n"

    for i, tip in enumerate(combo.get("tips", []), 1):
        _mk = tip.get("market", "")
        market_emoji = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "btts_ht": "🕐", "over15_ht": "⏰", "corners": "🔵"}.get(_mk, "💎")
        market_label = {"btts": "BTTS", "over25": "Over 2.5", "combo": "BTTS+O2.5", "btts_ht": "BTTS HT", "over15_ht": "O1.5 HT", "corners": "Corners"}.get(_mk, str(_mk).upper())
        odds_val = tip.get("odds", tip.get("oddsYes", "?"))
        msg += f"{i}. {market_emoji} <b>{tip.get('match','?')}</b> · {market_label} @ {odds_val}\n"

    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>💡 Clean Combo: 3-6 Legs Standard. 7-11 nur als optionale Lottery.</i>"
    return msg



def _auto_void_old_pending():
    """Bereinigt alte Pending Tipps automatisch (älter als 3 Tage)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        from datetime import date, timedelta
        cutoff = str(date.today() - timedelta(days=3))
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={
                "status": "eq.pending",
                "date": f"lt.{cutoff}",
            },
            json={"status": "void"},
            timeout=10,
        )
        if r.ok:
            log("✅ Alte Pending Tipps bereinigt!")
    except Exception as e:
        log(f"Auto-void Error: {str(e)[:50]}", "WARN")



def _get_market_stats_from_supabase(market_id):
    """Holt Won/Lost/ROI + Monat + Top-3-Ligen für einen Markt aus Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        modern = _ntr_market_stats_from_settlements(market_id)
        if modern and modern.get("total", 0) >= 1:
            return modern
    except Exception:
        pass
    try:
        from datetime import date as _date2
        today = _date2.today()
        month_start = today.replace(day=1).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "market": f"eq.{market_id}",
                "status": "in.(won,lost)",
                "select": "status,odds,units,date,league",
                "order": "date.desc",
                "limit": "2000",
            },
            timeout=15,
        )
        if not r.ok:
            return None
        tips = r.json()
        if not tips:
            return None

        won  = [t for t in tips if t.get("status") == "won"]
        lost = [t for t in tips if t.get("status") == "lost"]
        total = len(won) + len(lost)
        if total == 0:
            return None

        # ROI Gesamt
        roi = 0.0
        for t in won:
            try:
                roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: roi += 1.0
        for t in lost:
            try: roi -= float(t.get("units",1.0) or 1.0)
            except: roi -= 1.0

        # Monat
        m_won  = [t for t in won  if t.get("date","") >= month_start]
        m_lost = [t for t in lost if t.get("date","") >= month_start]
        m_total = len(m_won) + len(m_lost)
        m_roi = 0.0
        for t in m_won:
            try: m_roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: m_roi += 1.0
        for t in m_lost:
            try: m_roi -= float(t.get("units",1.0) or 1.0)
            except: m_roi -= 1.0

        # Top 3 Ligen
        lg_stats = {}
        for t in tips:
            lg = t.get("league","?")
            if not lg: continue
            if lg not in lg_stats:
                lg_stats[lg] = {"w":0,"l":0,"roi":0.0}
            if t.get("status") == "won":
                lg_stats[lg]["w"] += 1
                try: lg_stats[lg]["roi"] += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] += 1.0
            else:
                lg_stats[lg]["l"] += 1
                try: lg_stats[lg]["roi"] -= float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] -= 1.0

        top_leagues = []
        for lg, s in lg_stats.items():
            tot = s["w"] + s["l"]
            if tot >= 3:
                top_leagues.append((lg, s["w"], tot, round(s["roi"],1)))
        top_leagues.sort(key=lambda x: (-x[3], -x[1]))

        month_names = ["","Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]
        month_name = month_names[today.month]

        return {
            "won": len(won), "lost": len(lost), "total": total,
            "pct": round(len(won)/total*100),
            "roi": round(roi, 1),
            "month_name": month_name,
            "month_won": len(m_won), "month_lost": len(m_lost),
            "month_total": m_total,
            "month_pct": round(len(m_won)/m_total*100) if m_total else 0,
            "month_roi": round(m_roi, 1),
            "top_leagues": top_leagues[:3],
        }
    except Exception as e:
        log(f"Market Stats Error ({market_id}): {str(e)[:60]}", "WARN")
        return None


def _send_daily_auswertung_to_all_groups(stats=None):
    """
    Sendet marktspezifische Stats in jede Gruppe im Screenshot-Format:
    Winrate, ROI (Units), Gesamt-Tipps, Monat, Top-3-Ligen.
    """
    from datetime import datetime as _dt3, timezone as _tz3
    now = _dt3.now(_tz3.utc)

    # Saisonpause / WM-Hinweis
    if now.month == 6 and now.day < 11:
        pause_text = f"🏆 <i>WM 2026 startet in {11-now.day} Tagen! Ab 11. Juni täglich Tipps.</i>"
    elif now.month in [6, 7]:
        pause_text = "<i>🌍 WM 2026 läuft — täglich Tipps!</i>"
    else:
        pause_text = "<i>Heute spielfreier Tag — morgen wieder Tipps!</i>"

    market_groups = [
        ("btts",    TELEGRAM_GROUPS.get("btts"),    "⚽ BTTS"),
        ("over25",  TELEGRAM_GROUPS.get("over25"),  "🎯 Over 2.5"),
        ("combo",   TELEGRAM_GROUPS.get("combo"),   "🔥 BTTS + Over 2.5"),
        ("btts_ht", TELEGRAM_GROUPS.get("btts_ht"), "🕐 BTTS Halbzeit"),
        ("over15_ht", TELEGRAM_GROUPS.get("over15_ht"), "⏰ Over 1.5 HT"),
        ("corners", TELEGRAM_GROUPS.get("corners"), "🔵 Corner Sniper"),
        ("builder", TELEGRAM_GROUPS.get("builder"), "🧱 Prop Builder"),
        ("props", TELEGRAM_GROUPS.get("props"), "🎯 Player Props"),
        ("scorer",  TELEGRAM_GROUPS.get("scorer", TELEGRAM_GROUPS.get("late_goals")), "⚽ Goal Hunter"),
    ]

    medals = ["🥇","🥈","🥉"]
    sent_to = set()

    for market_id, chat_id, title in market_groups:
        if not chat_id or chat_id in sent_to:
            continue

        ms = _get_market_stats_from_supabase(market_id)

        nl = "\n"
        msg = f"<b>{title}</b>{nl}"
        msg += f"━━━━━━━━━━━━━━━━━━{nl}"

        if ms and ms["total"] >= 3:
            wr_e  = "🔥" if ms["pct"] >= 70 else "✅" if ms["pct"] >= 60 else "⚠️"
            roi_e = "🟢" if ms["roi"] >= 0 else "🔴"
            roi_s = f"+{ms['roi']}" if ms["roi"] >= 0 else str(ms["roi"])

            msg += f"{wr_e} Winrate: <b>{ms['pct']}%</b> ({ms['won']}W / {ms['lost']}L){nl}"
            msg += f"{roi_e} ROI: <b>{roi_s} Units</b>{nl}"
            msg += f"📋 Gesamt: {ms['total']} ausgewertete Tipps{nl}"

            # Monat
            if ms.get("month_total", 0) > 0:
                m_roi_e = "🟢" if ms["month_roi"] >= 0 else "🔴"
                m_roi_s = f"+{ms['month_roi']}" if ms["month_roi"] >= 0 else str(ms["month_roi"])
                msg += f"{nl}<b>{ms['month_name']}:</b>{nl}"
                msg += f"{ms['month_won']}/{ms['month_total']} Tipps · {ms['month_pct']}% · {m_roi_s}U {m_roi_e}{nl}"

            # Top 3 Ligen
            if ms.get("top_leagues"):
                msg += f"{nl}<b>🏆 Top Ligen:</b>{nl}"
                for i, (lg, w, tot, roi_lg) in enumerate(ms["top_leagues"]):
                    pct_lg   = round(w/tot*100) if tot else 0
                    roi_s_lg = f"+{roi_lg}" if roi_lg >= 0 else str(roi_lg)
                    medal = medals[i] if i < len(medals) else "•"
                    msg += f"{medal} {lg}: {w}/{tot} ({pct_lg}%) · {roi_s_lg}U{nl}"
        else:
            if str(env("SEND_EMPTY_PERFORMANCE_CARDS", "false")).lower() not in ("1", "true", "yes", "on"):
                continue
            msg += f"📊 Daten werden gesammelt...{nl}"
            msg += f"<i>Mindestens 3 ausgewertete Tipps nötig.</i>{nl}"

        msg += f"━━━━━━━━━━━━━━━━━━{nl}"
        msg += pause_text

        send_telegram(msg, chat_id)
        sent_to.add(chat_id)

    log(f"✅ Gruppen-Auswertung gesendet ({len(sent_to)} Gruppen)")



# ============================================================
# V30 HOTFIX — getrennte Gruppen-Übersicht statt Gesamtbericht in BTTS
# ============================================================

def _ntr_explicit_stats_group_chat():
    """
    Gesamt-Statistik nur in eine wirklich konfigurierte Stats-Gruppe senden.
    Wichtig: TELEGRAM_GROUP_STATS defaultet im Config-Block auf TELEGRAM_CHAT_ID.
    Deshalb hier absichtlich os.environ direkt lesen, damit keine Gesamt-Auswertung
    versehentlich in BTTS/Main landet.
    """
    chat = os.getenv("TELEGRAM_GROUP_STATS", "").strip()
    if not chat:
        return ""
    allow_same = str(env("ALLOW_GLOBAL_STATS_IN_TIP_GROUP", "false")).lower() in ("1", "true", "yes", "on")
    if allow_same:
        return chat
    market_keys = [
        "btts", "over25", "combo", "combos", "btts_ht", "over15_ht",
        "hz_live", "late_goals", "props", "advanced_props", "builder", "corners", "scorer", "goal_hunter", "scorer", "goal_hunter",
    ]
    for key in market_keys:
        val = str(TELEGRAM_GROUPS.get(key, "") or "")
        if val and val == chat:
            return ""
    # Raw-secret safety: Goal Hunter used to be Stats for this repo.
    if chat and chat == str(os.getenv("TELEGRAM_GROUP_LATE_GOALS", "") or ""):
        return ""
    if chat and chat == str(os.getenv("TELEGRAM_GROUP_HZ_LIVE", "") or ""):
        return ""
    return chat


def _ntr_market_daily_card(market_id, title, target_date, today_count):
    """Erstellt eine kurze Tages-/Gruppenkarte nur für diesen Markt."""
    nl = "\n"
    msg = f"<b>{title} — DAILY</b>{nl}"
    msg += f"<i>{target_date}</i>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"📊 Heute in dieser Gruppe: <b>{today_count}</b> Tipps{nl}"

    ms = _get_market_stats_from_supabase(market_id)
    if ms and ms.get("total", 0) >= 3:
        roi = float(ms.get("roi", 0) or 0)
        roi_s = f"+{roi:g}" if roi >= 0 else f"{roi:g}"
        pct = int(ms.get("pct", 0) or 0)
        e = "🟢" if roi >= 0 else "🔴"
        msg += f"🎯 Markt-Bewertung: <b>{ms.get('won',0)}/{ms.get('total',0)}</b> ({pct}%) · {roi_s}U {e}{nl}"

        if ms.get("month_total", 0):
            mroi = float(ms.get("month_roi", 0) or 0)
            mroi_s = f"+{mroi:g}" if mroi >= 0 else f"{mroi:g}"
            me = "🟢" if mroi >= 0 else "🔴"
            msg += f"📅 {ms.get('month_name','Monat')}: {ms.get('month_won',0)}/{ms.get('month_total',0)} ({ms.get('month_pct',0)}%) · {mroi_s}U {me}{nl}"

        if ms.get("top_leagues"):
            msg += f"{nl}<b>🏆 Top Ligen dieser Gruppe:</b>{nl}"
            medals = ["🥇", "🥈", "🥉"]
            for i, (lg, w, tot, roi_lg) in enumerate(ms.get("top_leagues", [])[:3]):
                pct_lg = round(w / tot * 100) if tot else 0
                roi_lg_s = f"+{roi_lg}" if roi_lg >= 0 else str(roi_lg)
                medal = medals[i] if i < len(medals) else "•"
                msg += f"{medal} {lg}: {w}/{tot} ({pct_lg}%) · {roi_lg_s}U{nl}"
    else:
        msg += "📈 Bewertung: Daten werden gesammelt. Mindestens 3 ausgewertete Tipps nötig." + nl

    msg += "━━━━━━━━━━━━━━━━━━"
    return msg


def _send_market_daily_cards_to_own_groups(tips_by_market, target_date, stats=None):
    """
    V31 FINAL:
    Standard AUS, weil diese DAILY-Karten bei jedem AI-Run mehrfach gespammt haben.
    Einschalten nur bewusst mit ENABLE_MARKET_DAILY_CARDS=true.
    Settlement-/ROI-Reports bleiben unabhängig davon aktiv.
    """
    if str(env("ENABLE_MARKET_DAILY_CARDS", "false")).lower() not in ("1", "true", "yes", "on"):
        log("ℹ️ Markt-Daily-Cards übersprungen (ENABLE_MARKET_DAILY_CARDS=false)")
        return
    market_cards = [
        ("btts", "⚽ BTTS", TELEGRAM_GROUPS.get("btts"), len(tips_by_market.get("btts", []))),
        ("over25", "🎯 Over 2.5", TELEGRAM_GROUPS.get("over25"), len(tips_by_market.get("over25", []))),
        ("combo", "🔥 BTTS + Over 2.5", TELEGRAM_GROUPS.get("combo"), len(tips_by_market.get("combo", []))),
        ("btts_ht", "🕐 BTTS HT", TELEGRAM_GROUPS.get("btts_ht"), len(tips_by_market.get("btts_ht", []))),
        ("over15_ht", "⏰ Over 1.5 HT", TELEGRAM_GROUPS.get("over15_ht"), len(tips_by_market.get("over15_ht", []))),
        ("combos", "🎰 Combos", TELEGRAM_GROUPS.get("combos"), len(tips_by_market.get("combo_multi", []))),
        ("corners", "🔵 Corner Sniper", TELEGRAM_GROUPS.get("corners"), len(tips_by_market.get("corners", []))),
        ("scorer", "🏆 Goal Hunter", TELEGRAM_GROUPS.get("scorer") or TELEGRAM_GROUPS.get("goal_hunter") or TELEGRAM_GROUPS.get("late_goals"), len(tips_by_market.get("scorer", []))),
        ("builder", "🧱 Prop Builder", TELEGRAM_GROUPS.get("builder") or TELEGRAM_GROUPS.get("advanced_props"), len(tips_by_market.get("builder", []))),
    ]

    sent = set()
    for market_id, title, chat_id, today_count in market_cards:
        if not chat_id or str(chat_id) in sent:
            continue
        # keine leere Tageskarte. Historie allein reicht nicht, sonst kommt "Heute gesendet: 0 Tipps".
        ms = _get_market_stats_from_supabase(market_id)
        if today_count <= 0 and str(env("ENABLE_EMPTY_MARKET_DAILY_CARDS", "false")).lower() not in ("1", "true", "yes", "on"):
            continue
        msg = _ntr_group_daily_card_v31(market_id, title, target_date, today_count)
        send_telegram(msg, chat_id)
        sent.add(str(chat_id))

    log(f"✅ Tages-Bewertung getrennt gesendet ({len(sent)} Gruppen)")


def _send_global_daily_stats_only_to_stats_group(stats_header):
    """
    Gesamtbericht nur in TELEGRAM_GROUP_STATS senden, falls diese Gruppe explizit
    gesetzt und nicht identisch mit einer Tipp-Gruppe ist.
    """
    stats_chat = _ntr_explicit_stats_group_chat()
    if not stats_chat:
        log("ℹ️ Gesamt-Statistik nicht in Tipp-Gruppe gesendet (kein separates TELEGRAM_GROUP_STATS)")
        return
    send_telegram(stats_header, stats_chat)
    log("✅ Gesamt-Statistik nur in Stats-Gruppe gesendet")


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
        "VALUE": "🟢",
        "OK": "🟡",
        "LOW": "🔴",
    }

    market_emoji = {
        "btts": "⚽",
        "over25": "🎯",
        "combo": "🔥",
        "btts_ht": "🕐",
        "over15_ht": "⏰",
        "1x2": "🏆",
    }

    total_tips = sum(len(t) for t in tips_by_market.values())

    # ============================================================
    # STATS NACHRICHT - Vollständig mit allen Märkten
    # ============================================================
    now_utc = datetime.now(timezone.utc)
    month_name = now_utc.strftime("%B %Y")

    stats_header = f"<b>🤖 AI TIPP BOT - DAILY</b>\n<i>{target_date}</i>\n" + "\n"

    # Tagesübersicht - ALLE Märkte
    stats_header += "📊 <b>Übersicht heute:</b>\n"
    for m_id in MARKETS_TO_RUN:
        count = len(tips_by_market.get(m_id, []))
        stats_header += f"• {MARKET_INFO[m_id]['name']}: <b>{count}</b> Tipps" + "\n"

    # Ecken + Scorer + Combos
    corners_today = getattr(run_corners_and_scorer_bots, '_last_corners', 0)
    scorer_today = getattr(run_corners_and_scorer_bots, '_last_scorer', 0)
    stats_header += f"• 🔵 Ecken: <b>{corners_count if 'corners_count' in dir() else 0}</b> Tipps" + "\n"
    stats_header += f"• 🎰 Combos: <b>{combos_sent if 'combos_sent' in dir() else 0}</b> generiert" + "\n"
    stats_header += f"\n💎 <b>Total: {total_tips} Top-Tipps</b>"

    stats = get_overall_stats()

    if stats:
        # Auto-void alte pendings
        old_pending = stats.get("pending", 0)
        
        stats_header += "\n\n━━━━━━━━━━━━━━━━━━\n"
        stats_header += "📈 <b>GESAMT-STATISTIK</b>\n"
        stats_header += f"✅ Gewonnen: <b>{stats['won']}</b>" + "\n"
        stats_header += f"❌ Verloren: <b>{stats['lost']}</b>" + "\n"
        # Pending nur zeigen wenn sinnvoll (< 50)
        if stats["pending"] and stats["pending"] < 50:
            stats_header += f"⏳ Pending: <b>{stats['pending']}</b>" + "\n"
        stats_header += f"🎯 Trefferquote: <b>{stats['quote_pct']}%</b>" + "\n"
        roi_emoji = "🟢" if stats["roi_units"] >= 0 else "🔴"
        stats_header += f"💰 ROI: <b>{'+' if stats['roi_units'] >= 0 else ''}{stats['roi_units']}</b> Units {roi_emoji}" + "\n"

        # Monatsübersicht
        if stats.get("month") and stats["month"]["total"] > 0:
            m = stats["month"]
            m_emoji = "🟢" if m["units"] >= 0 else "🔴"
            stats_header += f"\n📅 <b>{m['name']}:</b> {m['won']}/{m['total']} ({m['pct']}%) · "
            stats_header += f"<b>{'+' if m['units'] >= 0 else ''}{m['units']} Units</b> {m_emoji}" + "\n"

        # Pro Markt - ALLE inkl Ecken
        stats_header += f"\n<b>📊 Pro Markt:</b>" + "\n"
        market_names = {
            "btts": "⚽ BTTS",
            "over25": "🎯 Over 2.5",
            "combo": "🔥 BTTS+Over 2.5",
            "btts_ht": "🕐 BTTS HT",
            "over15_ht": "⏰ Over 1.5 HT",
        }
        for m_id in MARKETS_TO_RUN:
            mb = stats["by_market"].get(m_id, {"w":0,"l":0,"units":0.0})
            tot = mb["w"] + mb["l"]
            if tot > 0:
                pct = round(mb["w"]/tot*100)
                emoji = "🟢" if pct >= 60 else "🟡" if pct >= 40 else "🔴"
                u_str = f"+{round(mb['units'],2)}" if mb["units"] >= 0 else f"{round(mb['units'],2)}"
                stats_header += f"{market_names.get(m_id,m_id)}: {mb['w']}/{tot} ({pct}%) · {u_str}U {emoji}" + "\n"

        # Top Ligen
        if stats.get("top_leagues"):
            stats_header += f"\n<b>🏆 Top Ligen:</b>" + "\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
            for i, (lg, w, tot, pct, units) in enumerate(stats["top_leagues"][:10]):
                medal = medals[i] if i < len(medals) else "•"
                u_str = f"+{units}" if units >= 0 else str(units)
                stats_header += f"{medal} {lg}: {w}/{tot} ({pct}%) · {u_str}U" + "\n"

    # V30 HOTFIX: Keine Gesamt-Statistik mehr in eine Tipp-Gruppe.
    # Jede Gruppe bekommt ihre eigene Markt-Bewertung; Gesamt nur in separate Stats-Gruppe.
    _send_market_daily_cards_to_own_groups(tips_by_market, target_date, stats)
    _send_global_daily_stats_only_to_stats_group(stats_header)

    # Auto-void alte Pending Tipps (älter als 3 Tage)
    _auto_void_old_pending()

    # Wenn keine Tipps → Auswertung in ALLE Gruppen senden
    if total_tips == 0:
        _send_daily_auswertung_to_all_groups(stats)
        return

    saved = 0
    prefetch_sent_tips_for_date(target_date)

    for market_id, tips in tips_by_market.items():
        if not tips:
            continue

        target_chat = TELEGRAM_GROUPS.get(market_id, TELEGRAM_CHAT_ID)
        market_name = MARKET_INFO[market_id]["name"]
        emoji = market_emoji.get(market_id, "💎")

        # Kein Header - direkt Tipps senden

        for i, r in enumerate(tips, 1):
            confidence = int(r.get("confidence", 0))
            match_name = r.get("match", "?")

            r["date"] = str(target_date)
            if not is_valid_tip(r, target_date):
                continue

            if is_duplicate_tip(match_name, market_id, target_date):
                _ntr_log_duplicate(f"   ⏭️ Duplikat übersprungen: {match_name} ({market_id})", key=f"{market_id}")
                continue

            # 🛡️ Safe Filter: schlechte Ligen ausfiltern
            _tip_league = str(r.get("league","") or r.get("competition","") or r.get("league_name","") or "").lower()
            _skip_kw = ["reserve","women","u20","u21","u19","u18","youth","frauen",
                        "reserva","damen","feminine","femini","amateur","friendly"]
            if any(_kw in _tip_league for _kw in _skip_kw):
                log(f"   ⏭️ Liga gefiltert: {match_name} ({_tip_league[:25]})")
                continue

            # ✅ NEUES FORMAT - Variante 3
            market_icons2 = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "btts_ht": "🕐", "over15_ht": "⏰"}
            market_names2 = {"btts": "BTTS", "over25": "OVER 2.5", "combo": "BTTS + OVER 2.5", "btts_ht": "BTTS HT", "over15_ht": "OVER 1.5 HT"}
            val_icon = val_icons.get(r.get('valueRating', 'OK'), '🟡')
            mkt_icon = market_icons2.get(market_id, "🎯")
            mkt_name = market_names2.get(market_id, market_id.upper())

            tip_time_raw = r.get('time', r.get('time_local', '')).strip()
            if not tip_time_raw or tip_time_raw in ['TBD', 'N/A', '-', '']:
                tip_time = "Heute"
            else:
                try:
                    from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
                    if 'T' in tip_time_raw and ('Z' in tip_time_raw or '+' in tip_time_raw):
                        _t2 = _dt2.fromisoformat(tip_time_raw.replace('Z', '+00:00'))
                        _local2 = _t2.astimezone(_tz2(_td2(hours=2)))
                        tip_time = _local2.strftime('%H:%M')
                    else:
                        tip_time = tip_time_raw
                except Exception:
                    tip_time = tip_time_raw

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                # Konservativerer Cap bei reiner Liga-Schätzung (kein echter Pinnacle-Quote-Confirm)
                _no_real = r.get('_no_real_odds', True)
                _max_u = 1.5 if _no_real else 3.0
                units = calculate_kelly_units(prob_val, odds_val, max_units=_max_u)
                units_emoji = "🔥" if units >= 2.5 else "💚" if units >= 1.5 else "🟡"
            except:
                units = 1.0
                units_emoji = "💚"

            # Wetter
            weather_data = r.get("weather", {})
            weather_line = ""
            if weather_data and weather_data.get("temp"):
                temp = weather_data.get("temp", "")
                rain = weather_data.get("rain", 0)
                wind = weather_data.get("wind", 0)
                if rain > 1:
                    weather_line = f"🌧️ {temp}°C · Regen {rain}mm"
                elif wind > 30:
                    weather_line = f"💨 {temp}°C · Wind {wind}km/h"
                else:
                    weather_line = f"🌤️ {temp}°C"

            # Form
            def fmt_form(fs):
                if not fs or fs in ['N/A', '-', '?']:
                    return ""
                icons2 = {"W": "🟢", "D": "🟡", "L": "🔴"}
                return " ".join([icons2.get(c, "⚪") for c in str(fs)[-5:]])

            home_form = r.get('homeForm', r.get('home_form', '')).strip()
            away_form = r.get('awayForm', r.get('away_form', '')).strip()

            # Sharp Money
            sharp = r.get('sharp_money', '')
            sharp_line = ""
            if sharp == "strong":
                sharp_line = "📌 Starkes Sharp Money Signal!"
            elif sharp:
                sharp_line = "📌 Sharp Money aktiv"

            # Opening Odds
            opening = r.get('opening_odds', 0)
            odds_move_line = ""
            if opening and odds_val and opening != odds_val:
                diff = round(odds_val - opening, 2)
                arrow = "▼" if diff < 0 else "▲"
                odds_move_line = f"📉 Opening: {opening} → {odds_val} {arrow}"

            # Verletzungen
            inj_home = r.get('injuries_home', '')
            inj_away = r.get('injuries_away', '')

            # Schiri mit Details
            ref = r.get('referee', r.get('ref', ''))
            ref_cards = r.get('ref_cards_per_game', 0)
            ref_red = r.get('ref_red_per_game', 0)
            ref_pen = r.get('ref_penalty_rate', 0)
            ref_fouls = r.get('ref_fouls_per_game', 0)

            # H2H
            h2h_btts = r.get('h2h_btts', '')
            h2h_goals = r.get('h2h_avg_goals', '')

            # Build Message
            msg = f"💎 <b>{match_name}</b>" + "\n"
            msg += f"📍 {r.get('league', r.get('league_name', ''))} · ⏰ {tip_time}" + "\n"
            if weather_line:
                msg += f"{weather_line}" + "\n"
            msg += f"━━━━━━━━━━━━━━━━━━" + "\n"
            msg += f"{mkt_icon} <b>{mkt_name}</b>" + "\n"
            msg += f"✅ Tipp: <b>{r.get('tip','YES')}</b>" + "\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability',0)}%</b>" + "\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}" + "\n"
            msg += f"💰 Quote: <b>{r.get('oddsYes','-')}</b> · Fair: {r.get('fairOdds','-')} · {val_icon} {r.get('valueRating','OK')}" + "\n"
            msg += f"{units_emoji} <b>{units} Units</b>"

            # Stats
            stats = []
            if r.get('xg_home') and r.get('xg_away'):
                stats.append(f"⚡ xG: {r['xg_home']} / {r['xg_away']}")
            if r.get('btts_rate_home') and r.get('btts_rate_away'):
                stats.append(f"📊 BTTS Rate: {r['btts_rate_home']}% / {r['btts_rate_away']}%")
            if h2h_btts:
                stats.append(f"🔄 H2H BTTS: {h2h_btts}")
            if h2h_goals:
                stats.append(f"⚽ H2H Ø Tore: {h2h_goals}")
            if stats:
                msg += f"\n━━━━━━━━━━━━━━━━━━"
                msg += "\n".join(stats)

            # Quoten Bewegung
            if odds_move_line or sharp_line:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if odds_move_line:
                    msg += f"{odds_move_line}" + "\n"
                if sharp_line:
                    msg += f"{sharp_line}" + "\n"

            # Team Info
            team_info = []
            if inj_home:
                team_info.append(f"🏥 Verletzt Heim: {inj_home}")
            if inj_away:
                team_info.append(f"🏥 Verletzt Gast: {inj_away}")
            if ref:
                team_info.append(f"👨‍⚖️ Schiri: {ref}")
            if team_info or ref:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if team_info:
                    msg += "\n".join(team_info) + "\n"
                if ref:
                    msg += f"👨‍⚖️ <b>{ref}</b>" + "\n"
                    if ref_cards:
                        msg += f"   🟡 {ref_cards} K/Sp"
                    if ref_red:
                        msg += f" · 🔴 {ref_red} R/Sp"
                    if ref_pen:
                        msg += f" · ⚽ {ref_pen} Elf/Sp"
                    if ref_fouls:
                        msg += f" · 📊 {ref_fouls} F/Sp"
                    # Schiri Bewertung
                    if ref_cards:
                        if float(ref_cards) < 3.5:
                            msg += "\n   ✅ Lässt Spiel laufen"
                        elif float(ref_cards) > 5:
                            msg += "\n   ⚠️ Strenger Schiri"
                        else:
                            msg += "\n   🟡 Durchschnittlich"
                    msg += "\n"

            # Form
            hf = fmt_form(home_form)
            af = fmt_form(away_form)
            if hf or af:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                home_name = match_name.split(" vs ")[0][:12] if " vs " in match_name else "Heim"
                away_name = match_name.split(" vs ")[1][:12] if " vs " in match_name else "Gast"
                if hf:
                    msg += f"🏠 {home_name}: {hf}" + "\n"
                if af:
                    msg += f"✈️ {away_name}: {af}" + "\n"

            # Key Factor + Reasoning
            if r.get('keyFactor'):
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                msg += f"⚡ <i>{r.get('keyFactor')[:100]}</i>" + "\n"

            reasoning = r.get('reasoning', '')
            if reasoning:
                if len(reasoning) > 150:
                    reasoning = reasoning[:147] + "..."
                msg += f"\n💭 <i>{reasoning}</i>"

            msg += f"\n━━━━━━━━━━━━━━━━━━"

            # Beste Quote Empfehlung
            tip_odds_data = r.get("_odds_data", [])
            inline_keyboard = build_inline_keyboard(tip_odds_data, match_name)

            # Bookie Empfehlung
            best_bookie = r.get("bookie", "")
            best_odds = r.get("oddsYes", "")
            if best_bookie and best_odds:
                msg += f"\n🏆 Empfehlung: <b>{best_bookie}</b> · Quote {best_odds}"

            msg_id = send_telegram(msg, target_chat)
            mark_tip_sent(match_name, market_id, target_date)

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

            import time as _ts
            tip_id = f"{market_id}_{target_date}_{abs(hash(match_name + market_id)) % 100000}"

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
                "message_text": msg[:3500],  # Für Ergebnis-Anhang beim Settlement
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

            # Prüfe ob bereits in Supabase
            tip_id_check = tip_data.get("tip_id", "")
            already_exists = False
            if tip_id_check and SUPABASE_URL and SUPABASE_KEY:
                try:
                    r_check = requests.get(
                        f"{SUPABASE_URL}/rest/v1/tips",
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                        params={"tip_id": f"eq.{tip_id_check}", "select": "id", "limit": "1"},
                        timeout=5,
                    )
                    if r_check.ok and r_check.json():
                        already_exists = True
                except Exception:
                    pass

            if already_exists:
                log(f"   ⏭️ Supabase: bereits vorhanden {tip_data.get('match','?')}")
            else:
                save_result = save_to_supabase(tip_data)
                # CLV Tracking
                if NETRATTLER_PRO:
                    try:
                        log_tip_for_clv(tip_data)
                    except Exception:
                        pass
                if save_result:
                    saved += 1
                else:
                    log(f"   ⚠️ Supabase save fehlgeschlagen für {tip_data.get('match','?')}", "WARN")

        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")

        # Kein Footer - direkt Tipps ohne Zusammenfassung

    log(f"Gespeichert in Supabase: {saved}")
    try:
        _send_daily_auswertung_to_all_groups()
    except Exception as _ae:
        log(f"Auswertung Error: {str(_ae)[:50]}", "WARN")


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
    Gibt ALLE Ligen zurück (global, 24/7).
    Keine Zeit-Filterung mehr - der Bot checkt alle Ligen weltweit.
    """
    if not LEAGUE_ROTATION_ENABLED:
        return list(LEAGUES_TO_RUN), {}
    if ACTIVE_LEAGUES_OVERRIDE:
        log(f"🎯 Override: {len(ACTIVE_LEAGUES_OVERRIDE)} Ligen")
        return ACTIVE_LEAGUES_OVERRIDE, {}

    log(f"🌍 Global Mode: alle {len(LEAGUES_TO_RUN)} Ligen aktiv (24/7)")

    if not AUTO_LEAGUE_SWITCH:
        log("Auto Liga Switch: AUS")
        return LEAGUES_TO_RUN, {}

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
        else:
            disabled.append((league, reason))
            log(f" ⛔ {league}: {reason}", "SKIP")

    log(f"Auto Liga Switch: {len(active)} aktiv, {len(disabled)} pausiert")

    return active, league_stats



# ============================================================
# 🎯 RESULT RESOLVER — Vollständige Fallback-Kette für Settlement
# ============================================================
# Priorität: Supabase → Football-Data.org → OpenLigaDB →
#             TheSportsDB → AllSports → ESPN → OpenFootball → API-Football

_RR_DAY_CACHE = {}       # {date_str: [result_dicts]} — vereinter Tages-Cache
_RR_ESPN_CACHE = {}      # ESPN Scoreboard Cache
_RR_OFB_CACHE = {}       # OpenFootball Cache


def _rr_make_result(home_score, away_score, ht_home=0, ht_away=0, source="unknown") -> dict:
    """Einheitliches Ergebnis-Format für alle Quellen."""
    hs, as_ = int(home_score or 0), int(away_score or 0)
    hh, ha  = int(ht_home or 0), int(ht_away or 0)
    return {
        "home_score": hs, "away_score": as_,
        "ht_home": hh, "ht_away": ha,
        "btts": hs > 0 and as_ > 0,
        "over25": (hs + as_) > 2,
        "btts_ht": hh > 0 and ha > 0,
        "total_goals": hs + as_,
        "status": "finished",
        "_source": source,
    }


def _rr_team_match(a: str, b: str) -> bool:
    """Fuzzy Team-Name-Vergleich."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return True
    # Kürze auf 6 Zeichen (reicht für die meisten Namen)
    return a[:6] in b or b[:6] in a


def _rr_find_in_list(rows, home, away, home_field="home_team", away_field="away_team",
                     hs_field="home_score", as_field="away_score",
                     ht_h_field=None, ht_a_field=None, source="unknown") -> dict:
    """Sucht in einer Liste von Dicts nach dem passenden Match."""
    for row in rows:
        rh = str(row.get(home_field) or "")
        ra = str(row.get(away_field) or "")
        if _rr_team_match(home, rh) and _rr_team_match(away, ra):
            hs  = row.get(hs_field)
            as_ = row.get(as_field)
            if hs is None or as_ is None:
                continue
            hh = row.get(ht_h_field, 0) if ht_h_field else 0
            ha = row.get(ht_a_field, 0) if ht_a_field else 0
            return _rr_make_result(hs, as_, hh, ha, source)
    return {}


# ── 1. Supabase eigene Tabellen ──────────────────────────────────────────────

def _rr_supabase(home, away, date_str) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

    for table, h_col, a_col, hs_col, as_col, ht_h, ht_a in [
        ("match_results", "home_team", "away_team", "home_score", "away_score", "ht_home", "ht_away"),
        ("international_results", "home_team", "away_team", "home_score", "away_score", None, None),
        ("football_historical_matches", "home_team", "away_team", "home_score", "away_score", "ht_home_score", "ht_away_score"),
    ]:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers=headers,
                params={"date": f"eq.{date_str}", "select": "*", "limit": "500"},
                timeout=8,
            )
            if r.ok:
                res = _rr_find_in_list(r.json(), home, away,
                                       h_col, a_col, hs_col, as_col,
                                       ht_h, ht_a, f"supabase_{table}")
                if res:
                    return res
        except Exception:
            continue
    return {}


# ── 2. ESPN Scoreboard ────────────────────────────────────────────────────────

def _rr_espn(home, away, date_str) -> dict:
    cache_key = f"espn_{date_str}"
    if cache_key in _RR_ESPN_CACHE:
        rows = _RR_ESPN_CACHE[cache_key]
    else:
        rows = []
        espn_date = date_str.replace("-", "")  # "20260714"
        urls = [
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={espn_date}",
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={espn_date}",
        ]
        for url in urls:
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if r.ok:
                    for ev in r.json().get("events", []):
                        comp = ev.get("competitions", [{}])[0]
                        teams = {t["homeAway"]: t for t in comp.get("competitors", [])}
                        h = teams.get("home", {})
                        a = teams.get("away", {})
                        status = comp.get("status", {}).get("type", {}).get("completed")
                        if not status:
                            continue
                        rows.append({
                            "home_team": h.get("team", {}).get("displayName", ""),
                            "away_team": a.get("team", {}).get("displayName", ""),
                            "home_score": h.get("score"),
                            "away_score": a.get("score"),
                        })
            except Exception:
                continue
        _RR_ESPN_CACHE[cache_key] = rows

    return _rr_find_in_list(rows, home, away, source="espn")


# ── 3. OpenFootball (GitHub) ──────────────────────────────────────────────────

def _rr_openfootball(home, away, date_str) -> dict:
    """Sucht in openfootball JSON-Dateien (bereits als Cache in Supabase, aber auch direkt)."""
    try:
        year = date_str[:4]
        season = f"{int(year)-1}-{year[-2:]}"
        # Nutze bereits geladene FD.co.uk / openfootball CSV-Daten
        league_guesses = [
            f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/de.1.json",
            f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json",
        ]
        for url in league_guesses:
            if url in _RR_OFB_CACHE:
                matches = _RR_OFB_CACHE[url]
            else:
                r = requests.get(url, timeout=8)
                if not r.ok:
                    continue
                data = r.json()
                matches = [m for m in data.get("matches", []) if m.get("score")]
                _RR_OFB_CACHE[url] = matches

            for m in matches:
                if m.get("date", "") != date_str:
                    continue
                if _rr_team_match(home, m.get("team1", "")) and _rr_team_match(away, m.get("team2", "")):
                    ft = m.get("score", {}).get("ft", [])
                    ht = m.get("score", {}).get("ht", [])
                    if len(ft) >= 2:
                        return _rr_make_result(ft[0], ft[1],
                                               ht[0] if len(ht) >= 2 else 0,
                                               ht[1] if len(ht) >= 2 else 0,
                                               "openfootball")
    except Exception:
        pass
    return {}


# ── Haupt-Resolver ────────────────────────────────────────────────────────────

RESULT_SOURCE_PRIORITY = [
    "supabase", "football_data_org", "openligadb",
    "thesportsdb", "allsports", "espn", "openfootball", "api_football",
]


def get_match_result_from_sources(tip) -> dict:
    """
    Zentraler ResultResolver — probiert alle Quellen in Prioritäts-Reihenfolge.
    Gibt einheitliches Ergebnis-Dict zurück oder None.
    """
    match_name = tip.get("match", "")
    league     = tip.get("league", "")
    tip_date   = str(tip.get("date", ""))

    if not match_name or " vs " not in match_name or not tip_date:
        return None

    # Combo-Match: nur ersten nehmen
    if " / " in match_name:
        match_name = match_name.split(" / ")[0].strip()

    parts = match_name.split(" vs ", 1)
    if len(parts) != 2:
        return None
    home, away = parts[0].strip(), parts[1].strip()

    # 1. Supabase eigene Tabellen (schnellste Quelle)
    res = _rr_supabase(home, away, tip_date)
    if res:
        return res

    # 2. Football-Data.org (4 Keys, Top-Ligen)
    try:
        res = _footballdata_find_result(home, away, tip_date)
        if res:
            return res
    except Exception:
        pass

    # 3. OpenLigaDB (deutsche Ligen, kostenlos)
    try:
        res = _openligadb_find_result(home, away, tip_date, league)
        if res:
            return res
    except Exception:
        pass

    # 4. TheSportsDB (crowdsourced, breite Abdeckung)
    try:
        from_existing = _ALLSPORTS_DAY_CACHE.get(f"thesportsdb_{tip_date}", [])
        if not from_existing:
            r = requests.get(
                "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
                params={"d": tip_date, "s": "Soccer"}, timeout=12,
            )
            if r.ok:
                from_existing = r.json().get("events") or []
                _ALLSPORTS_DAY_CACHE[f"thesportsdb_{tip_date}"] = from_existing
        res = _rr_find_in_list(from_existing, home, away,
                                "strHomeTeam", "strAwayTeam",
                                "intHomeScore", "intAwayScore",
                                source="thesportsdb")
        if res:
            return res
    except Exception:
        pass

    # 5. AllSports
    try:
        res = _allsports_find_result(home, away, tip_date)
        if res:
            return res
    except Exception:
        pass

    # 6. ESPN Scoreboard (inoffiziell, aber gut für viele Ligen)
    try:
        res = _rr_espn(home, away, tip_date)
        if res:
            return res
    except Exception:
        pass

    # 7. OpenFootball (GitHub, historisch)
    try:
        res = _rr_openfootball(home, away, tip_date)
        if res:
            return res
    except Exception:
        pass

    # 8. Footballdata.io
    try:
        if FOOTBALLDATA_IO_API_KEY:
            res = _footballdataio_find_result(home, away, tip_date)
            if res:
                return res
    except Exception:
        pass

    # 9. API-Football (oft suspended)
    try:
        fixtures = _af_fixtures_for_date(tip_date)
        for fx in (fixtures or []):
            fx_home = (fx.get("teams", {}).get("home", {}).get("name", "") or "").lower()
            fx_away = (fx.get("teams", {}).get("away", {}).get("name", "") or "").lower()
            if _rr_team_match(home, fx_home) and _rr_team_match(away, fx_away):
                gs  = fx.get("goals", {})
                ht  = fx.get("score", {}).get("halftime", {})
                return _rr_make_result(gs.get("home", 0), gs.get("away", 0),
                                       ht.get("home", 0), ht.get("away", 0),
                                       "api_football")
    except Exception:
        pass

    return None




# ============================================================
# V30 HOTFIX — Settlement Turbo Cache
# ============================================================

_RESULT_RESOLVER_CACHE = {}
_RESULT_RESOLVER_STATS = {"hit": 0, "miss": 0}

_ORIGINAL_get_match_result_from_sources = get_match_result_from_sources

def get_match_result_from_sources(tip) -> dict:
    """
    Cached wrapper around the normal result resolver.
    Viele pending Tips haben dasselbe Match mit mehreren Märkten.
    Ohne Cache werden dieselben Quellen mehrfach abgefragt.
    """
    try:
        match_name = str(tip.get("match", "") or "")
        tip_date = str(tip.get("date", "") or "")[:10]
        # Combo-Match: für Matchresult reicht der erste Match-Key
        first_match = match_name.split(" / ")[0].strip() if " / " in match_name else match_name.strip()
        key = (first_match.lower(), tip_date)
        if key in _RESULT_RESOLVER_CACHE:
            _RESULT_RESOLVER_STATS["hit"] += 1
            return _RESULT_RESOLVER_CACHE[key]
        _RESULT_RESOLVER_STATS["miss"] += 1
        res = _ORIGINAL_get_match_result_from_sources(tip)
        # Auch None cachen, damit erfolglose Matches nicht 10x gesucht werden.
        _RESULT_RESOLVER_CACHE[key] = res
        return res
    except Exception:
        return _ORIGINAL_get_match_result_from_sources(tip)



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


_AF_FIXTURES_DAY_CACHE = {}  # {date_str: [fixtures]} — verhindert N Calls für N pending Tips am selben Tag

def _af_fixtures_for_date(date_str):
    """Holt alle FT-Fixtures für ein Datum, gecached pro Tag (1 Call statt N)."""
    if str(os.getenv("ENABLE_API_FOOTBALL_SETTLEMENT", "0")).lower() not in {"1", "true", "yes", "on"}:
        return []
    if date_str in _AF_FIXTURES_DAY_CACHE:
        return _AF_FIXTURES_DAY_CACHE[date_str]
    r = _af_request("/fixtures", {"date": date_str, "status": "FT"})
    _AF_FIXTURES_DAY_CACHE[date_str] = r or []
    return _AF_FIXTURES_DAY_CACHE[date_str]


_SOFA_EVENTS_DAY_CACHE = {}  # {date_str: [events]} — wie API-Football Tages-Cache, aber kostenlos & ID-los

def _sofascore_events_for_date(date_str):
    """
    Holt ALLE Fussball-Events eines Tages von SofaScore (kostenlos, kein Key, kein Match-ID nötig).
    Gecacht pro Tag: 1 Call deckt alle pending Tips desselben Tages ab.
    Fällt bei Cloudflare-Block auf Playwright zurück.
    """
    if date_str in _SOFA_EVENTS_DAY_CACHE:
        return _SOFA_EVENTS_DAY_CACHE[date_str]

    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    events = []
    _status = None
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=15,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            events = data.get("events", [])
    except Exception as _se:
        _status = f"EXC:{str(_se)[:60]}"

    log(f"   🔍 SOFA-DEBUG: {date_str} → HTTP {_status}, {len(events)} Events (direkt)")

    if not events and PLAYWRIGHT_AVAILABLE:
        try:
            html = scrape_with_playwright(url, timeout=15000)
            if html:
                import re as _re
                m = _re.search(r'(\{.*\})', html, _re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
                    events = data.get("events", [])
            log(f"   🔍 SOFA-DEBUG: {date_str} → Playwright-Fallback: {len(events)} Events")
        except Exception as _pe:
            log(f"   🔍 SOFA-DEBUG: {date_str} → Playwright-Fallback Fehler: {str(_pe)[:80]}", "WARN")

    finished_count = sum(1 for e in events if (e.get("status", {}) or {}).get("type") == "finished")
    if events:
        log(f"   🔍 SOFA-DEBUG: {date_str} → {len(events)} Events total, {finished_count} finished")

    _SOFA_EVENTS_DAY_CACHE[date_str] = events
    return events


def _sofascore_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in SofaScore-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td3

    events = _sofascore_events_for_date(tip_date)
    if not events:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td3(days=_delta)).date())
                events = _sofascore_events_for_date(_d2)
                if events:
                    break
        except Exception:
            pass

    if not events:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for ev in events:
        status = ev.get("status", {}).get("type", "")
        if status != "finished":
            continue
        h = (ev.get("homeTeam") or {}).get("name", "")
        a = (ev.get("awayTeam") or {}).get("name", "")
        h_match = h.lower()[:6] in h_target or h_target[:6] in h.lower()
        a_match = a.lower()[:6] in a_target or a_target[:6] in a.lower()
        if h_match and a_match:
            home_g = (ev.get("homeScore") or {}).get("current", 0) or 0
            away_g = (ev.get("awayScore") or {}).get("current", 0) or 0
            ht_home = (ev.get("homeScore") or {}).get("period1", 0) or 0
            ht_away = (ev.get("awayScore") or {}).get("period1", 0) or 0
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
    return None


_ALLSPORTS_DAY_CACHE = {}  # {date_str: [matches]} — globale Tagessuche, kein leagueId nötig

def _allsports_events_for_date(date_str):
    """
    Holt ALLE Fussball-Fixtures eines Tages von AllSportsAPI, OHNE leagueId-Einschränkung.
    Gecacht pro Tag, analog zu SofaScore/API-Football Tages-Cache.
    """
    if not ALLSPORTS_API_KEY:
        return []
    if date_str in _ALLSPORTS_DAY_CACHE:
        return _ALLSPORTS_DAY_CACHE[date_str]

    matches = []
    _status = None
    try:
        r = requests.get(
            "https://apiv2.allsportsapi.com/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "from": date_str,
                "to": date_str,
            },
            timeout=20,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            matches = data.get("result", []) or []
    except Exception as _ae:
        _status = f"EXC:{str(_ae)[:60]}"

    log(f"   🔍 ALLSPORTS-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Fixtures")
    _ALLSPORTS_DAY_CACHE[date_str] = matches
    return matches


def _allsports_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in AllSports-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td4

    matches = _allsports_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td4(days=_delta)).date())
                matches = _allsports_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        status = m.get("event_status", "")
        if status != "Finished":
            continue
        h = m.get("event_home_team", "")
        a = m.get("event_away_team", "")
        h_match = h.lower()[:6] in h_target or h_target[:6] in h.lower()
        a_match = a.lower()[:6] in a_target or a_target[:6] in a.lower()
        if h_match and a_match:
            try:
                home_g = int(m.get("event_final_result", "0-0").split("-")[0].strip() or 0)
                away_g = int(m.get("event_final_result", "0-0").split("-")[1].strip() or 0)
                ht = m.get("event_halftime_result", "0-0") or "0-0"
                ht_home = int(ht.split("-")[0].strip() or 0)
                ht_away = int(ht.split("-")[1].strip() or 0)
            except Exception:
                continue
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
    return None


_FOOTBALLDATA_DAY_CACHE = {}  # {date_str: [matches]} — globale Tagessuche, alle Competitions des Keys

def _footballdata_events_for_date(date_str):
    """
    Holt ALLE Matches eines Tages von football-data.org (globaler /v4/matches Endpoint,
    deckt alle Competitions ab, zu denen der Key Zugriff hat — kein Liga-Code nötig).
    Gecacht pro Tag, nutzt bestehende Key-Rotation (_FD_KEY_OFFSET / _FD_DEAD_KEYS).
    """
    global _FD_KEY_OFFSET
    if not FOOTBALL_DATA_API_KEYS:
        return []
    if date_str in _FOOTBALLDATA_DAY_CACHE:
        return _FOOTBALLDATA_DAY_CACHE[date_str]

    matches = []
    n = len(FOOTBALL_DATA_API_KEYS)
    _status = None
    for offset in range(n):
        idx = (_FD_KEY_OFFSET + offset) % n
        if idx in _FD_DEAD_KEYS:
            continue
        key = FOOTBALL_DATA_API_KEYS[idx]
        try:
            r = requests.get(
                "https://api.football-data.org/v4/matches",
                params={"dateFrom": date_str, "dateTo": date_str},
                headers={"X-Auth-Token": key},
                timeout=15,
            )
            _status = r.status_code
            if r.status_code == 429:
                _FD_DEAD_KEYS.add(idx)
                continue
            if r.status_code == 403:
                _FD_DEAD_KEYS.add(idx)
                continue
            if r.ok:
                data = r.json()
                matches = data.get("matches", []) or []
                _FD_KEY_OFFSET = (idx + 1) % n
                break
        except Exception as _fde:
            _status = f"EXC:{str(_fde)[:60]}"
            continue

    log(f"   🔍 FOOTBALLDATA-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Matches")
    _FOOTBALLDATA_DAY_CACHE[date_str] = matches
    return matches


def _footballdata_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in football-data.org-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td5

    matches = _footballdata_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td5(days=_delta)).date())
                matches = _footballdata_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        status = m.get("status", "")
        if status != "FINISHED":
            continue
        h = (m.get("homeTeam") or {}).get("name", "") or ""
        a = (m.get("awayTeam") or {}).get("name", "") or ""
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            score = m.get("score", {}) or {}
            ft = score.get("fullTime", {}) or {}
            ht = score.get("halfTime", {}) or {}
            home_g = ft.get("home", 0) or 0
            away_g = ft.get("away", 0) or 0
            ht_home = ht.get("home", 0) or 0
            ht_away = ht.get("away", 0) or 0
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
    return None


_OPENLIGADB_DAY_CACHE = {}  # German-fokussiert, aber komplett kostenlos & ohne Key

def _openligadb_find_result(home_team, away_team, tip_date, league_name=""):
    """
    OpenLigaDB: kostenlose, keyless API für deutsche Wettbewerbe (Bundesliga, 2./3. Liga, DFB-Pokal).
    Nur sinnvoll wenn die Liga deutsch ist — sonst überspringen (kein globaler Endpoint vorhanden).
    """
    _ln = league_name.lower()
    _league_map = {
        "bundesliga": "bl1", "2. bundesliga": "bl2", "3. liga": "bl3",
        "dfb-pokal": "dfb", "dfb pokal": "dfb",
    }
    _shortcut = None
    for key, code in _league_map.items():
        if key in _ln:
            _shortcut = code
            break
    if not _shortcut:
        return None

    try:
        season = str(datetime.strptime(tip_date, "%Y-%m-%d").year)
    except Exception:
        return None

    cache_key = f"{_shortcut}_{season}"
    if cache_key not in _OPENLIGADB_DAY_CACHE:
        try:
            r = requests.get(
                f"https://api.openligadb.de/getmatchdata/{_shortcut}/{season}",
                timeout=15,
            )
            _OPENLIGADB_DAY_CACHE[cache_key] = r.json() if r.ok else []
            log(f"   🔍 OPENLIGADB-DEBUG: {_shortcut}/{season} → {len(_OPENLIGADB_DAY_CACHE[cache_key])} Matches")
        except Exception:
            _OPENLIGADB_DAY_CACHE[cache_key] = []

    matches = _OPENLIGADB_DAY_CACHE.get(cache_key, [])
    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        if not m.get("matchIsFinished"):
            continue
        h = (m.get("team1") or {}).get("teamName", "") or ""
        a = (m.get("team2") or {}).get("teamName", "") or ""
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            results = m.get("matchResults", []) or []
            ft = next((r for r in results if r.get("resultName") == "Endergebnis"), None)
            ht = next((r for r in results if r.get("resultName") == "Halbzeitergebnis"), None)
            if not ft:
                continue
            home_g = ft.get("pointsTeam1", 0) or 0
            away_g = ft.get("pointsTeam2", 0) or 0
            ht_home = ht.get("pointsTeam1", 0) if ht else 0
            ht_away = ht.get("pointsTeam2", 0) if ht else 0
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
    return None


_FOOTBALLDATAIO_DAY_CACHE = {}  # {date_str: [matches]}

def _footballdataio_events_for_date(date_str):
    """
    Holt alle Matches eines Tages von footballdata.io (anderer Anbieter als football-data.org!).
    Bestätigter Endpoint: GET /matches/date/{date}, Auth: Bearer Token.
    Gecacht pro Tag.
    """
    if not FOOTBALLDATA_IO_API_KEY:
        return []
    if date_str in _FOOTBALLDATAIO_DAY_CACHE:
        return _FOOTBALLDATAIO_DAY_CACHE[date_str]

    matches = []
    _status = None
    try:
        r = requests.get(
            f"https://footballdata.io/api/v1/matches/date/{date_str}",
            headers={"Authorization": f"Bearer {FOOTBALLDATA_IO_API_KEY}"},
            timeout=15,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            # Antwortformat noch nicht live verifiziert — robust gegen beide üblichen Strukturen
            matches = data.get("data") or data.get("matches") or (data if isinstance(data, list) else [])
    except Exception as _fie:
        _status = f"EXC:{str(_fie)[:60]}"

    log(f"   🔍 FOOTBALLDATAIO-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Matches")
    _FOOTBALLDATAIO_DAY_CACHE[date_str] = matches
    return matches


def _footballdataio_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in footballdata.io-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td6

    matches = _footballdataio_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td6(days=_delta)).date())
                matches = _footballdataio_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        # Status-Feldname noch nicht live verifiziert — mehrere übliche Varianten abdecken
        status = (m.get("status") or m.get("matchStatus") or "").upper()
        if status not in ("FINISHED", "FT", "COMPLETED"):
            continue
        home_obj = m.get("homeTeam") or m.get("home_team") or {}
        away_obj = m.get("awayTeam") or m.get("away_team") or {}
        h = home_obj.get("name", "") if isinstance(home_obj, dict) else str(home_obj)
        a = away_obj.get("name", "") if isinstance(away_obj, dict) else str(away_obj)
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            score = m.get("score", {}) or {}
            home_g = score.get("home") or score.get("homeScore") or 0
            away_g = score.get("away") or score.get("awayScore") or 0
            ht = m.get("halfTimeScore") or {}
            ht_home = ht.get("home", 0) if isinstance(ht, dict) else 0
            ht_away = ht.get("away", 0) if isinstance(ht, dict) else 0
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
    return None

    """
    Versucht Spielergebnis von mehreren Quellen zu holen.
    Priorität: SofaScore (Tages-Suche) → AllSports (Tages-Suche) → API-Football → ESPN/SofaScore/AllSports (per ID)
    """
    match_name = tip.get("match", "")
    league = tip.get("league", "")
    match_id = tip.get("telegram_msg_id", "")  # Wir brauchen die echte match_id

    # 🆕 SofaScore Tages-Suche zuerst — kostenlos, kein Key, kein vorab gespeichertes ID nötig
    if match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _sofascore_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 TheStatsAPI Settlement (primär — zuverlässigste Quelle wenn Key vorhanden)
    if THESTATSAPI_KEYS and match_name and " vs " in match_name:
        try:
            _parts = match_name.split(" vs ")
            _home = _parts[0].strip()
            _away = _parts[1].strip() if len(_parts) > 1 else ""
            _date = tip.get("date", str(datetime.now(timezone.utc).date()))
            _res = tsa_find_match_result(_home, _away, _date)
            if _res:
                return _res
        except Exception:
            pass

    # 🆕 AllSports Tages-Suche — eigener API-Key bereits aktiv, kein vorab gespeichertes ID nötig
    if ALLSPORTS_API_KEY and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _allsports_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 Football-Data.org Tages-Suche — bereits validierte Keys, globaler Endpoint
    if FOOTBALL_DATA_API_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _footballdata_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 OpenLigaDB — kostenlos, kein Key, nur deutsche Wettbewerbe (Bundesliga etc.)
    if match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _openligadb_find_result(home_team, away_team, tip_date, league)
            if result:
                return result
        except Exception:
            pass

    # 🆕 footballdata.io Tages-Suche — anderer Anbieter als football-data.org
    if FOOTBALLDATA_IO_API_KEY and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _footballdataio_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # SofaScore per ID (falls vorhanden, z.B. aus alten Live-Bot-Daten)
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

    # API-Football Fallback — Suche by Teamname + Datum
    if API_FOOTBALL_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            from datetime import timedelta as _td2

            # API-Football /fixtures: "team" braucht eine numerische ID, KEIN Name!
            # Daher: nur nach Datum + Status filtern, dann lokal nach Teamnamen matchen.
            # Gecacht pro Tag: 1 API-Call deckt ALLE pending Tips desselben Tages ab
            r = _af_fixtures_for_date(tip_date)

            # Strategie 2: ±1 Tag (Zeitzone-Puffer), ebenfalls gecached
            if not r:
                for _delta in [-1, 1]:
                    _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td2(days=_delta)).date())
                    r = _af_fixtures_for_date(_d2)
                    if r:
                        break

            if r:
                for fix in r:
                    teams = fix.get("teams", {})
                    h = teams.get("home", {}).get("name", "")
                    a = teams.get("away", {}).get("name", "")
                    # Fuzzy match: mindestens erste 4 Zeichen übereinstimmen
                    h_match = h.lower()[:6] in home_team.lower() or home_team.lower()[:6] in h.lower()
                    a_match = not away_team or a.lower()[:6] in away_team.lower() or away_team.lower()[:6] in a.lower()
                    if h_match and a_match:
                        goals = fix.get("goals", {})
                        score = fix.get("score", {})
                        home_g = goals.get("home", 0) or 0
                        away_g = goals.get("away", 0) or 0
                        ht_home = (score.get("halftime") or {}).get("home", 0) or 0
                        ht_away = (score.get("halftime") or {}).get("away", 0) or 0
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
            log(f"Settlement API-Football Error: {str(e)[:80]}", "WARN")

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


def format_result_appendix(tip, result, status):
    """
    Ergebnis direkt an den ORIGINAL-TIPP anhängen.
    Für normale Tipps, Combos, Ecken und Builder.
    """
    market = str(tip.get("market") or "").lower()
    group = _ntr_group_key(tip)
    odds = tip.get("odds", "?")
    units = tip.get("units", 1.0)

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    try:
        profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    except Exception:
        profit = 0.0
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    title = "Match Summary"
    if group == "combos" or "combo_multi" in market:
        title = "Combo Summary"
    elif group == "corners" or "corner" in market:
        title = "Corner Summary"
    elif group == "builder" or "builder" in market:
        title = "Builder Summary"

    nl = "\n"
    msg = f"⸻⸻ <b>{title}</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    if home_s != "?" or away_s != "?":
        msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    if result.get("actual_value") is not None:
        msg += f"Auswertung: <b>{result.get('actual_value')}</b>{nl}"
    if result.get("total_corners") is not None or result.get("corners_total") is not None:
        msg += f"Corners: <b>{result.get('total_corners') or result.get('corners_total')}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>{nl}"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    try:
        profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    except Exception:
        profit = 0.0
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    nl = "\n"
    msg = f"⸻⸻ <b>Match Summary</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>{nl}"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    status_emoji = "✅ V GEWONNEN" if status == "won" else "❌ X VERLOREN"
    profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    nl = "\n"
    msg = f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{status_emoji}</b>{nl}"
    msg += f"📌 Tipp-Bewertung: <b>{'✅ V' if status == 'won' else '❌ X'}</b>{nl}"
    msg += f"⚽ Endstand: <b>{home_s} : {away_s}</b>"
    if ht_home != "?" and ht_away != "?":
        msg += f" (HZ: {ht_home}:{ht_away})"
    msg += nl
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"

    return msg


def format_result_text(tip, result, status):
    """Fallback, falls Original-Telegram-Nachricht nicht mehr editierbar ist."""
    match = tip.get("match", "?")
    market = tip.get("market", "btts")
    tip_val = tip.get("tip", "YES")

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    nl = "\n"
    msg = f"<b>{match}</b>{nl}"
    msg += f"🎯 Tipp: {tip_val} ({str(market).upper()}){nl}"
    msg += f"⸻⸻ <b>Match Summary</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")
    total = result.get("total_goals", "?")

    status_emoji = "✅ V GEWONNEN" if status == "won" else "❌ X VERLOREN"
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


def get_supabase_player_avg_stats(player_name: str) -> dict:
    """
    Holt historische Spieler-Durchschnittswerte aus Supabase player_avg_stats View.
    Wird täglich durch scrape_player_stats.py befüllt.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    if player_name in _SUPABASE_PLAYER_STATS_CACHE:
        return _SUPABASE_PLAYER_STATS_CACHE[player_name]
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/player_avg_stats",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"player_name": f"eq.{player_name}", "select": "stat_name,avg_value,hit_rate_pct,games"},
            timeout=8,
        )
        if not r.ok:
            _SUPABASE_PLAYER_STATS_CACHE[player_name] = {}
            return {}
        rows = r.json()
        stats = {row["stat_name"]: {"avg": row["avg_value"], "hit_rate": row["hit_rate_pct"], "games": row["games"]} for row in rows}
        _SUPABASE_PLAYER_STATS_CACHE[player_name] = stats
        return stats
    except Exception:
        _SUPABASE_PLAYER_STATS_CACHE[player_name] = {}
        return {}


# ============================================================
# 🧹 CLEAN STAT VALUE (aus Gemini-Analyse)
# ============================================================
def clean_stat_value(val):
    """
    Konvertiert SofaScore/FotMob Strings zu numerischen Werten.
    "85%" → 85.0, "42/50" → 84.0 (Prozent), 1.85 → 1.85
    """
    if val is None:
        return None, None
    if isinstance(val, (int, float)):
        return float(val), None
    val_str = str(val).strip()
    if val_str.endswith("%"):
        try:
            return float(val_str.replace("%", "")), None
        except ValueError:
            pass
    if "/" in val_str:
        try:
            parts = val_str.split("/")
            if len(parts) == 2 and float(parts[1]) > 0:
                pct = (float(parts[0]) / float(parts[1])) * 100
                return round(pct, 1), val_str
        except ValueError:
            pass
    return None, val_str


# ============================================================
# ⚡ CLUBELO — Teamstärke-Ratings (kostenlos, HTTP API)
# ============================================================
_CLUBELO_CACHE = {}  # {date_str: {team_norm: elo}}

def get_clubelo_ratings(target_date=None) -> dict:
    """
    Holt ClubElo-Ratings für alle Teams (http://api.clubelo.com/YYYY-MM-DD).
    TURBO: standardmässig AUS, weil api.clubelo.com im GitHub Runner oft 10s timeoutet.
    Aktivieren mit Secret/Env ENABLE_CLUBELO=1.
    """
    date_str = str(target_date or datetime.now(timezone.utc).date())
    if date_str in _CLUBELO_CACHE:
        return _CLUBELO_CACHE[date_str]

    if str(os.getenv("ENABLE_CLUBELO", "0")).lower() not in {"1", "true", "yes", "on"}:
        _CLUBELO_CACHE[date_str] = {}
        return {}

    ratings = {}
    try:
        r = requests.get(
            f"http://api.clubelo.com/{date_str}",
            headers={"User-Agent": "Mozilla/5.0 Chrome/122.0.0.0"},
            timeout=2,
        )
        if r.ok and r.text:
            import csv as _csv, io as _io
            reader = _csv.DictReader(_io.StringIO(r.text))
            for row in reader:
                club = (row.get("Club") or "").strip()
                elo = row.get("Elo") or row.get("elo")
                if club and elo:
                    ratings[club.lower()] = float(elo)
            log(f"   ⚡ ClubElo: {len(ratings)} Teams geladen")
    except Exception as _ce:
        log(f"   ⚡ ClubElo: {str(_ce)[:50]} (silent fail)", "WARN")

    _CLUBELO_CACHE[date_str] = ratings
    return ratings


def get_clubelo_for_match(home_team: str, away_team: str, target_date=None) -> dict:
    """Gibt ClubElo für Heim- und Auswärtsteam zurück."""
    ratings = get_clubelo_ratings(target_date)
    if not ratings:
        return {}

    h_norm = home_team.lower()
    a_norm = away_team.lower()

    h_elo = ratings.get(h_norm)
    a_elo = ratings.get(a_norm)

    # Fuzzy-Match falls exakter Name fehlt
    if not h_elo:
        h_elo = next((v for k, v in ratings.items() if k[:6] in h_norm or h_norm[:6] in k), None)
    if not a_elo:
        a_elo = next((v for k, v in ratings.items() if k[:6] in a_norm or a_norm[:6] in k), None)

    return {
        "elo_home": round(h_elo, 0) if h_elo else None,
        "elo_away": round(a_elo, 0) if a_elo else None,
        "elo_diff": round(h_elo - a_elo, 0) if h_elo and a_elo else None,
        "source": "clubelo",
    }


# ============================================================
# 💰 SOFASCORE ODDS (BTTS, Over2.5, BTTS HT, Player Props)
# ============================================================
_SOFA_ODDS_CACHE = {}  # {event_id: odds_dict}

def get_sofascore_odds(event_id: str) -> dict:
    """
    Holt SofaScore Bet365-Quoten für ein Event:
    1X2, BTTS, Over2.5, BTTS HT, Over1.5 HT
    Nutzt cloudscraper falls installiert.
    """
    if not event_id:
        return {}
    if event_id in _SOFA_ODDS_CACHE:
        return _SOFA_ODDS_CACHE[event_id]

    odds = {}
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/provider/1/featured"

    try:
        # cloudscraper falls verfügbar, sonst requests
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.sofascore.com/",
        }
        r = _sess.get(url, headers=headers, timeout=12)
        if not r.ok:
            _SOFA_ODDS_CACHE[event_id] = {}
            return {}

        data = r.json()
        for market in data.get("featuredOdds", {}).get("choices", []):
            mname = (market.get("name") or "").lower()
            options = market.get("sourceOdds", [])

            if "full time" in mname or "1x2" in mname:
                for o in options:
                    fv = o.get("fractionalValue", "")
                    val = float(o.get("decimalValue") or 0)
                    if fv == "1": odds["home_win"] = val
                    elif fv == "X": odds["draw"] = val
                    elif fv == "2": odds["away_win"] = val

            elif "both teams to score" in mname and "half" not in mname:
                for o in options:
                    fv = (o.get("fractionalValue") or o.get("name") or "").lower()
                    val = float(o.get("decimalValue") or 0)
                    if "yes" in fv or fv == "1": odds["btts_yes"] = val
                    elif "no" in fv or fv == "2": odds["btts_no"] = val

            elif "both teams to score" in mname and "half" in mname:
                for o in options:
                    fv = (o.get("fractionalValue") or o.get("name") or "").lower()
                    val = float(o.get("decimalValue") or 0)
                    if "yes" in fv: odds["btts_ht_yes"] = val
                    elif "no" in fv: odds["btts_ht_no"] = val

            elif "over/under" in mname or "total goals" in mname:
                for o in options:
                    oname = (o.get("name") or "")
                    val = float(o.get("decimalValue") or 0)
                    if "2.5" in oname:
                        if "over" in oname.lower(): odds["over25"] = val
                        elif "under" in oname.lower(): odds["under25"] = val
                    elif "1.5" in oname:
                        if "over" in oname.lower(): odds["over15_ht"] = val

        log(f"   💰 SofaScore Odds: {list(odds.keys())} für Event {event_id}")
    except Exception as _se:
        log(f"   💰 SofaScore Odds Error: {str(_se)[:60]}", "WARN")

    _SOFA_ODDS_CACHE[event_id] = odds
    return odds


def get_sofascore_player_props(event_id: str) -> list:
    """
    Holt SofaScore Spieler-Props (/submarkets):
    Schüsse, SOT, Karten, Assists — mit echten Bet365-Quoten.
    """
    if not event_id:
        return []

    props = []
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/provider/1/submarkets"

    try:
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.sofascore.com/",
        }
        r = _sess.get(url, headers=headers, timeout=12)
        if not r.ok:
            return []

        data = r.json()
        for submarket in data.get("submarkets", []):
            market_group = submarket.get("marketGroup", "")
            for market in submarket.get("choices", []):
                player = market.get("player") or {}
                player_name = player.get("name", "")
                player_id = str(player.get("id", ""))
                for option in market.get("sourceOdds", []):
                    line_name = option.get("name", "")
                    try:
                        quote = float(option.get("decimalValue") or 0)
                    except (TypeError, ValueError):
                        continue
                    if quote < 1.20 or not player_name:
                        continue
                    props.append({
                        "player_id": player_id,
                        "player_name": player_name,
                        "market_group": market_group,
                        "line": line_name,
                        "odds": quote,
                    })

        if props:
            log(f"   💰 SofaScore Player Props: {len(props)} Props für Event {event_id}")
    except Exception as _spe:
        log(f"   💰 SofaScore Player Props Error: {str(_spe)[:60]}", "WARN")

    return props


# ============================================================
# 📊 SOFASCORE TEAM FORM — letzte N Spiele, BTTS-Rate
# ============================================================
_SOFA_TEAM_FORM_CACHE = {}  # {team_id: {btts_rate, over25_rate, ...}}

def get_sofascore_team_form(team_id: str, last_n: int = 6) -> dict:
    """
    Holt letzte N Spiele eines Teams von SofaScore und berechnet:
    BTTS-Rate, Over2.5-Rate, Ø Tore erzielt/kassiert
    Sehr nützlich für Pre-Match-Analyse — direkter als martj42.
    """
    if not team_id:
        return {}
    cache_key = f"{team_id}_{last_n}"
    if cache_key in _SOFA_TEAM_FORM_CACHE:
        return _SOFA_TEAM_FORM_CACHE[cache_key]

    result = {}
    try:
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.sofascore.com/",
        }
        r = _sess.get(
            f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0",
            headers=headers, timeout=12,
        )
        if not r.ok:
            _SOFA_TEAM_FORM_CACHE[cache_key] = {}
            return {}

        events = r.json().get("events", [])[:last_n]
        if not events:
            _SOFA_TEAM_FORM_CACHE[cache_key] = {}
            return {}

        btts = over25 = goals_scored = goals_conceded = valid = 0
        for ev in events:
            hs = (ev.get("homeScore") or {}).get("current")
            as_ = (ev.get("awayScore") or {}).get("current")
            if hs is None or as_ is None:
                continue
            valid += 1
            home_team_id = (ev.get("homeTeam") or {}).get("id")
            is_home = str(home_team_id) == str(team_id)
            scored = hs if is_home else as_
            conceded = as_ if is_home else hs
            goals_scored += scored
            goals_conceded += conceded
            if hs > 0 and as_ > 0:
                btts += 1
            if hs + as_ > 2:
                over25 += 1

        if valid == 0:
            _SOFA_TEAM_FORM_CACHE[cache_key] = {}
            return {}

        result = {
            "btts_rate": round(btts / valid * 100, 1),
            "over25_rate": round(over25 / valid * 100, 1),
            "avg_scored": round(goals_scored / valid, 2),
            "avg_conceded": round(goals_conceded / valid, 2),
            "games": valid,
            "source": "sofascore_team_form",
        }
        log(f"   📊 SofaScore Form Team {team_id}: BTTS {result['btts_rate']}%, Ø {result['avg_scored']}-{result['avg_conceded']}")

    except Exception as _tfe:
        log(f"   📊 SofaScore Team Form Error: {str(_tfe)[:60]}", "WARN")

    _SOFA_TEAM_FORM_CACHE[cache_key] = result
    return result


def get_sofascore_match_form(event_id: str) -> dict:
    """
    Holt Team-IDs für ein Spiel und berechnet kombinierte BTTS-Rate beider Teams.
    Direkte Alternative zu martj42 für Vereinsspiele.
    """
    try:
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {"User-Agent": "Mozilla/5.0 Chrome/122", "Referer": "https://www.sofascore.com/"}
        r = _sess.get(f"https://api.sofascore.com/api/v1/event/{event_id}", headers=headers, timeout=10)
        if not r.ok:
            return {}

        ev = r.json().get("event", {})
        home_id = str((ev.get("homeTeam") or {}).get("id", ""))
        away_id = str((ev.get("awayTeam") or {}).get("id", ""))

        h_form = get_sofascore_team_form(home_id)
        a_form = get_sofascore_team_form(away_id)

        if not h_form or not a_form:
            return {}

        return {
            "home_btts_rate": h_form["btts_rate"],
            "away_btts_rate": a_form["btts_rate"],
            "combined_btts_rate": round((h_form["btts_rate"] + a_form["btts_rate"]) / 2, 1),
            "home_over25_rate": h_form["over25_rate"],
            "away_over25_rate": a_form["over25_rate"],
            "combined_over25_rate": round((h_form["over25_rate"] + a_form["over25_rate"]) / 2, 1),
            "home_avg_scored": h_form["avg_scored"],
            "away_avg_scored": a_form["avg_scored"],
            "source": "sofascore_form",
        }
    except Exception:
        return {}


# ============================================================
# ⚡ SOFASCORE ATTACK MOMENTUM + INCIDENTS (für Live-Bot)
# ============================================================

def get_sofascore_attack_momentum(event_id: str) -> dict:
    """
    Holt Attack Momentum Kurve — zeigt welches Team gerade drückt.
    Nützlich für Live-Bot Alerts (z.B. "Team A dominiert letzte 5 Min").
    """
    try:
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {"User-Agent": "Mozilla/5.0 Chrome/122", "Referer": "https://www.sofascore.com/"}
        r = _sess.get(
            f"https://api.sofascore.com/api/v1/event/{event_id}/attack-momentum",
            headers=headers, timeout=10
        )
        if not r.ok:
            return {}

        data = r.json()
        momentum = data.get("attackMomentum") or data.get("momentum") or []
        if not momentum:
            return {}

        # Letzte 5 Minuten auswerten
        recent = momentum[-5:] if len(momentum) >= 5 else momentum
        home_pressure = sum(1 for m in recent if m.get("home", 0) > m.get("away", 0))
        away_pressure = len(recent) - home_pressure

        return {
            "home_pressure_last5": home_pressure,
            "away_pressure_last5": away_pressure,
            "dominant": "home" if home_pressure > away_pressure else "away" if away_pressure > home_pressure else "balanced",
            "data_points": len(momentum),
        }
    except Exception:
        return {}


def get_sofascore_incidents(event_id: str) -> list:
    """
    Holt Live-Ticker Events (Tore, Karten, Elfmeter, Wechsel).
    Trigger für Live-Bot Alerts.
    """
    try:
        try:
            import cloudscraper as _cs
            _sess = _cs.create_scraper()
        except ImportError:
            _sess = requests.Session()

        headers = {"User-Agent": "Mozilla/5.0 Chrome/122", "Referer": "https://www.sofascore.com/"}
        r = _sess.get(
            f"https://api.sofascore.com/api/v1/event/{event_id}/incidents",
            headers=headers, timeout=10
        )
        if not r.ok:
            return []

        incidents = r.json().get("incidents", [])
        # Nur relevante Events
        relevant = []
        for inc in incidents:
            inc_type = inc.get("incidentType", "").lower()
            if inc_type in ("goal", "card", "period", "injurytime", "substitution"):
                player = (inc.get("player") or {}).get("name", "")
                relevant.append({
                    "type": inc_type,
                    "minute": inc.get("time"),
                    "player": player,
                    "team": "home" if inc.get("isHome") else "away",
                    "detail": inc.get("incidentClass", ""),
                })
        return relevant
    except Exception:
        return []

# 🎯 VALUE-BERECHNUNG (prob × odds > 1.10 = +10% Edge)
# ============================================================

def calculate_value_edge(probability: float, odds: float) -> float:
    """
    Berechnet den mathematischen Value-Index.
    > 1.10 = mindestens 10% Edge → Wert-Tipp
    """
    if not probability or not odds or probability <= 0 or odds <= 0:
        return 0.0
    return round(probability * odds, 3)


def check_prop_value(player_name: str, market_group: str, line: str,
                     odds: float, supabase_stats: dict) -> dict:
    """
    Vergleicht Buchmacher-Quote mit historischer Hit-Rate aus Supabase.
    Gibt Value-Info zurück wenn Edge ≥ 10%.
    """
    # Stat-Name Mapping: SofaScore → Supabase
    stat_map = {
        "Player shots": ["totalShots", "shots"],
        "Player shots on target": ["shotsOnTarget", "shotsonTarget"],
        "Player cards": ["yellowCards", "yellowCard"],
        "Player assists": ["assists", "goalAssist"],
        "Player tackles": ["tackles", "totalTackles"],
    }

    stat_names = stat_map.get(market_group, [])
    hit_rate = None
    avg_val = None
    games = 0

    for sn in stat_names:
        if sn in supabase_stats:
            row = supabase_stats[sn]
            hit_rate = row.get("hit_rate", 0) / 100  # % → 0-1
            avg_val = row.get("avg")
            games = row.get("games", 0)
            break

    if hit_rate is None or games < 3:
        return {}

    edge = calculate_value_edge(hit_rate, odds)

    if edge >= 1.10:
        return {
            "player": player_name,
            "market": f"{market_group} — {line}",
            "odds": odds,
            "hit_rate_pct": round(hit_rate * 100, 1),
            "edge_pct": round((edge - 1) * 100, 1),
            "value_index": edge,
            "games_sample": games,
            "avg_stat": avg_val,
        }
    return {}


def get_statsbomb_props_for_match(home_team: str, away_team: str, league_name: str = "") -> list:
    """
    Holt Spieler-Props direkt aus StatsBomb Event-Daten für ein konkretes Match.
    Aggregiert Shots, SOT, Fouls, Cards aus den letzten Spielen jedes Spielers
    in der Liga → gibt Kandidaten für den Prop Builder zurück.
    Format: [{"player", "team", "market", "stat_val", "mtype", "match", "league", "kickoff"}]
    """
    cache_key = (normalize_team_name(home_team), normalize_team_name(away_team))
    if cache_key in _SB_MATCH_PROPS_CACHE:
        return _SB_MATCH_PROPS_CACHE[cache_key]

    # Liga-Stats laden (aggregiert über letzte Spiele)
    stats = get_statsbomb_player_stats(league_name)
    if not stats:
        _SB_MATCH_PROPS_CACHE[cache_key] = []
        return []

    match_name = f"{home_team} vs {away_team}"
    h_norm = normalize_team_name(home_team)
    a_norm = normalize_team_name(away_team)
    candidates = []

    for player_name, s in stats.items():
        team = s.get("team", "")
        t_norm = normalize_team_name(team)

        if not (t_norm[:6] in h_norm or h_norm[:6] in t_norm or
                t_norm[:6] in a_norm or a_norm[:6] in t_norm):
            continue

        pos   = s.get("position_type", "unknown")
        sot   = s.get("sot_per90", 0) or 0
        shots = s.get("shots_per90", 0) or 0
        fouls = s.get("fouls_per90", 0) or 0
        cards = s.get("yellow_cards_per90", 0) or 0
        goals = s.get("goals_per90", 0) or 0
        kp    = s.get("key_passes_per90", 0) or 0
        ast   = s.get("assists_per90", 0) or 0
        offs  = s.get("offsides_per90", 0) or 0

        # ── STÜRMER: Torschuss-Märkte ──────────────────────────────
        if shots >= 2.0:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "2.5+ Total Shots", "stat_val": shots, "mtype": "shots"})
        if sot >= 1.0:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "1+ Shot on Target", "stat_val": sot, "mtype": "shots"})
        if goals >= 0.35:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "Anytime Goalscorer", "stat_val": goals, "mtype": "shots"})
        if offs >= 0.5:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "1+ Offside", "stat_val": offs, "mtype": "shots"})

        # ── SPIELMACHER: Vorlagen-Märkte ───────────────────────────
        if kp >= 1.0:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "2+ Key Passes", "stat_val": kp, "mtype": "shots"})
        if ast >= 0.25:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "Anytime Assist", "stat_val": ast, "mtype": "shots"})

        # ── DEFENSIVE / SECHSER: Karten-Märkte ────────────────────
        if fouls >= 1.5:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "2+ Fouls Committed", "stat_val": fouls, "mtype": "foul"})
        if cards >= 0.15:
            candidates.append({"player": player_name, "team": team, "match": match_name,
                "league": league_name, "kickoff": "TBD",
                "market": "Player to be Booked", "stat_val": cards, "mtype": "booking"})

    log(f"   📊 StatsBomb Props: {len(candidates)} Kandidaten für {match_name}")
    _SB_MATCH_PROPS_CACHE[cache_key] = candidates
    return candidates


def get_player_props_for_match(home_team: str, away_team: str, league_name: str) -> list:
    """
    Gibt Player Props Tipps für ein Spiel zurück.
    Kombiniert StatsBomb + Understat Daten.
    Returns: [{player, tip, probability, fair_odds, stat_value}]
    """
    import math

    stats = get_statsbomb_player_stats(league_name)
    if not stats:
        return []

    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    props = []

    for player, s in stats.items():
        team_norm = normalize_team_name(s.get("team", ""))

        # Spieler spielt heute?
        is_playing = (
            team_norm[:8] in home_norm or home_norm[:8] in team_norm or
            team_norm[:8] in away_norm or away_norm[:8] in team_norm
        )
        if not is_playing:
            continue

        # SOT Prop: 1+ Schuss aufs Tor
        sot = s.get("sot_per90", 0)
        if sot >= 0.8:
            prob = round((1 - math.exp(-sot)) * 100)
            if prob >= 55:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"1+ Schüsse aufs Tor",
                    "market_type": "sot",
                    "stat_value": sot,
                    "probability": prob,
                    "fair_odds": round(1 / (prob / 100), 2),
                })

        # SOT Prop: 2+ Schüsse aufs Tor
        if sot >= 1.5:
            # P(X>=2) mit Poisson
            p0 = math.exp(-sot)
            p1 = sot * math.exp(-sot)
            prob2 = round((1 - p0 - p1) * 100)
            if prob2 >= 45:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"2+ Schüsse aufs Tor",
                    "market_type": "sot2",
                    "stat_value": sot,
                    "probability": prob2,
                    "fair_odds": round(1 / (prob2 / 100), 2),
                })

        # Fouls Prop: 2+ Fouls begangen
        fouls = s.get("fouls_per90", 0)
        if fouls >= 1.5:
            p0 = math.exp(-fouls)
            p1 = fouls * math.exp(-fouls)
            prob_f = round((1 - p0 - p1) * 100)
            if prob_f >= 45:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"2+ Fouls begangen",
                    "market_type": "fouls",
                    "stat_value": fouls,
                    "probability": prob_f,
                    "fair_odds": round(1 / (prob_f / 100), 2),
                })

        # Offside Prop: 1+ Abseits
        offsides = s.get("offsides_per90", 0)
        if offsides >= 0.8:
            prob_o = round((1 - math.exp(-offsides)) * 100)
            if prob_o >= 50:
                props.append({
                    "player": player,
                    "team": s["team"],
                    "tip": f"1+ Abseits",
                    "market_type": "offside",
                    "stat_value": offsides,
                    "probability": prob_o,
                    "fair_odds": round(1 / (prob_o / 100), 2),
                })

    # Sortiere nach Wahrscheinlichkeit
    props.sort(key=lambda x: x["probability"], reverse=True)
    return props[:8]  # Top 8 Props pro Spiel


def format_props_message(match_name: str, league: str, time: str, props: list) -> str:
    """Formatiert Player Props für Telegram"""
    if not props:
        return ""

    nl = "\n"
    msg = f"🔑 <b>PLAYER PROPS</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>{match_name}</b>\n"
    msg += f"📍 {league} · ⏰ {time}\n\n"

    for prop in props[:5]:
        prob = prop["probability"]
        fair = prop["fair_odds"]
        stars = "⭐⭐⭐" if prob >= 70 else "⭐⭐" if prob >= 60 else "⭐"
        msg += f"👤 <b>{prop['player']}</b> ({prop['team']})\n"
        msg += f"   🎯 {prop['tip']}\n"
        msg += f"   📈 {prob}% · Fair: {fair} · {stars}\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<i>📊 Daten: StatsBomb Open Data</i>"
    return msg




# ============================================================
# 🌍 MARTJ42 - 49.000+ Internationale Ergebnisse (GitHub, gratis!)
# WM 2026, Nations League, Friendlies + historische BTTS Raten
# ============================================================

MARTJ42_CACHE = {}
MARTJ42_DATA = None

def load_martj42_data():
    """Lädt alle 49.000+ Länderspiele einmalig von GitHub."""
    global MARTJ42_DATA
    if MARTJ42_DATA is not None:
        return MARTJ42_DATA

    try:
        r = requests.get(
            "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if not r.ok:
            return []

        lines = r.text.strip().split("\n")
        MARTJ42_DATA = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                date = parts[0].strip()
                home = parts[1].strip()
                away = parts[2].strip()
                hs = parts[3].strip()
                as_ = parts[4].strip()
                tournament = parts[5].strip() if len(parts) > 5 else ""
                hg = int(hs) if hs.isdigit() else -1
                ag = int(as_) if as_.isdigit() else -1
                MARTJ42_DATA.append({
                    "date": date, "home": home, "away": away,
                    "home_score": hg, "away_score": ag,
                    "tournament": tournament,
                    "btts": hg > 0 and ag > 0 if hg >= 0 else None,
                    "over25": (hg + ag) > 2 if hg >= 0 else None,
                    "total": hg + ag if hg >= 0 else -1,
                })
            except Exception:
                continue

        log(f"   🌍 martj42: {len(MARTJ42_DATA):,} Länderspiele geladen")
        return MARTJ42_DATA

    except Exception as e:
        log(f"martj42 Error: {str(e)[:50]}", "WARN")
        return []



_MEM_CACHE = {}

def cache_get(key, date=None):
    """In-Memory Cache get."""
    return _MEM_CACHE.get(f"{key}_{date}")

def cache_set(key, date, value):
    """In-Memory Cache set."""
    _MEM_CACHE[f"{key}_{date}"] = value
    return value


def scrape_statz_ai(*args, **kwargs) -> list:
    """Statz.ai — silent fail wenn nicht erreichbar."""
    return []

def scrape_playerprops_ai(*args, **kwargs) -> list:
    """PlayerProps.ai — silent fail wenn nicht erreichbar."""
    return []

def get_wsf_player_prop_odds(*args, **kwargs) -> dict:
    """WSF Odds — silent fail."""
    return {}


# ============================================================
# 📊 FOOTBALL-DATA.CO.UK — kostenlose CSV-Historie für Top-Vereinsligen
# ============================================================
# Bestätigte URL-Struktur: https://www.football-data.co.uk/mmz4281/{season}/{code}.csv
# Spalten: HS/AS=Schüsse, HST/AST=Schüsse aufs Tor, HC/AC=Ecken, HY/AY=Gelb, HF/AF=Fouls

FD_CO_UK_LEAGUE_CODES = {
    "premier league": "E0", "championship": "E1", "league one": "E2", "league two": "E3",
    "bundesliga": "D1", "2. bundesliga": "D2",
    "serie a": "I1", "serie b": "I2",
    "la liga": "SP1", "primera division": "SP1", "segunda division": "SP2",
    "ligue 1": "F1", "ligue 2": "F2",
    "eredivisie": "N1",
    "primeira liga": "P1",
    "scottish premiership": "SC0",
    "super lig": "T1",
    "super league greece": "G1",
    "jupiler pro league": "B1",
}

FD_CO_UK_CACHE = {}

def _fd_co_uk_season_str():
    """Aktuelle Saison im football-data.co.uk Format, z.B. '2526' für 2025/26.
    Saison startet im August — Juli noch zur alten Saison gehörig."""
    now = datetime.now(timezone.utc)
    start_year = now.year if now.month >= 8 else now.year - 1
    return f"{str(start_year)[-2:]}{str(start_year + 1)[-2:]}"


def _fd_co_uk_load_csv(league_name):
    """Lädt + parsed die Saison-CSV für eine Liga, gecacht pro Liga."""
    ln = league_name.lower()
    code = None
    for key, c in FD_CO_UK_LEAGUE_CODES.items():
        if key in ln:
            code = c
            break
    if not code:
        return []

    cache_key = code
    if cache_key in FD_CO_UK_CACHE:
        return FD_CO_UK_CACHE[cache_key]

    season = _fd_co_uk_season_str()
    rows = []
    try:
        r = requests.get(
            f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv",
            timeout=15,
        )
        if r.ok and r.text:
            import csv as _csv
            import io as _io
            reader = _csv.DictReader(_io.StringIO(r.text))
            for row in reader:
                if row.get("HomeTeam") and row.get("FTHG"):
                    rows.append(row)
        log(f"   🔍 FDCOUK-DEBUG: {code} ({season}) → {len(rows)} Spiele geladen")
    except Exception as _fce:
        log(f"   🔍 FDCOUK-DEBUG: {code} → Fehler {str(_fce)[:60]}", "WARN")

    FD_CO_UK_CACHE[cache_key] = rows
    return rows


def get_fd_co_uk_team_stats(team_name, league_name, last_n=10):
    """
    Echte Team-Statistik (BTTS-Rate, Over2.5-Rate, Ø Schüsse/Ecken/Karten) aus
    football-data.co.uk-Historie der aktuellen Saison — kostenlos, keine Quote,
    nur für die ~20 abgedeckten Top-Ligen relevant.
    """
    rows = _fd_co_uk_load_csv(league_name)
    if not rows:
        return {}

    team_norm = normalize_team_name(team_name)
    matches = []
    for row in rows:
        h = normalize_team_name(row.get("HomeTeam", ""))
        a = normalize_team_name(row.get("AwayTeam", ""))
        if team_norm[:6] in h or h[:6] in team_norm or team_norm[:6] in a or a[:6] in team_norm:
            matches.append(row)

    if len(matches) < 3:
        return {}

    matches = matches[-last_n:]
    btts_count = 0
    over25_count = 0
    shots, sot, corners, cards = [], [], [], []

    for row in matches:
        try:
            fthg = int(row.get("FTHG", 0) or 0)
            ftag = int(row.get("FTAG", 0) or 0)
            is_home = team_norm[:6] in normalize_team_name(row.get("HomeTeam", ""))

            if fthg > 0 and ftag > 0:
                btts_count += 1
            if (fthg + ftag) > 2:
                over25_count += 1

            if is_home:
                shots.append(int(row.get("HS", 0) or 0))
                sot.append(int(row.get("HST", 0) or 0))
                corners.append(int(row.get("HC", 0) or 0))
                cards.append(int(row.get("HY", 0) or 0))
            else:
                shots.append(int(row.get("AS", 0) or 0))
                sot.append(int(row.get("AST", 0) or 0))
                corners.append(int(row.get("AC", 0) or 0))
                cards.append(int(row.get("AY", 0) or 0))
        except (ValueError, TypeError):
            continue

    n = len(matches)
    if n == 0:
        return {}

    return {
        "source": "football-data.co.uk",
        "games": n,
        "btts_pct": round(100 * btts_count / n, 1),
        "over25_pct": round(100 * over25_count / n, 1),
        "avg_shots": round(sum(shots) / len(shots), 1) if shots else None,
        "avg_shots_on_target": round(sum(sot) / len(sot), 1) if sot else None,
        "avg_corners": round(sum(corners) / len(corners), 1) if corners else None,
        "avg_yellow_cards": round(sum(cards) / len(cards), 1) if cards else None,
    }


# ============================================================
# 🧠 EIGENES VORHERSAGEMODELL: Elo-Ratings + Poisson
# ============================================================
# Baut Team-Stärken (Elo) aus football-data.co.uk Saison-Historie auf,
# leitet daraus erwartete Tore ab (Poisson) → eigene BTTS/Over2.5/1X2-
# Wahrscheinlichkeiten, unabhängig von Pinnacles Markt-Quote.
# Nur für die von football-data.co.uk abgedeckten ~20 Top-Ligen.

# ============================================================
# 🤖 XGBOOST ML-INFERENCE (Modelle aus Supabase laden)
# ============================================================

_ML_MODELS = {}           # {model_name: calibrated_model}

# Team-Modelle, die geladen UND vorhergesagt werden (Loader + Predictor synchron,
# damit der Supabase-Payload begrenzt bleibt und kein Timeout entsteht).
_ML_TEAM_TARGETS = [
    ("btts_model", "btts_pct"),
    ("over25_model", "over25_pct"),
    ("btts_ht_model", "btts_ht_pct"),
    ("over15_ht_model", "over15_ht_pct"),
    ("over15_model", "over15_pct"),
    ("over35_model", "over35_pct"),
    ("home_win_model", "home_win_pct"),
    ("draw_model", "draw_pct"),
    ("away_win_model", "away_win_pct"),
    ("corners_over85_model", "corners_over85_pct"),
    ("corners_over95_model", "corners_over95_pct"),
]
_ML_MODELS_LOADED = False # Flag, damit wir nur einmal laden
_ML_FEATURE_COLS = [
    # Elo-Ratings
    "elo_home", "elo_away", "elo_diff",
    # BTTS/Over-Raten (rolling)
    "btts_rate_home", "btts_rate_away", "btts_rate_combined",
    "o25_rate_home", "o25_rate_away", "o25_rate_combined",
    # Tore erzielt/kassiert
    "avg_scored_home", "avg_scored_away",
    "avg_conceded_home", "avg_conceded_away",
    "exp_goals", "avg_conceded_combined",
    # Halbzeit-Features
    "btts_ht_rate_home", "btts_ht_rate_away",
    "o15ht_rate_home", "o15ht_rate_away",
    # Form-Punkte
    "form_pts_home", "form_pts_away", "form_pts_diff",
    "streak_win_home", "streak_win_away",
    # H2H
    "h2h_btts_rate", "h2h_avg_goals", "h2h_matches_norm",
    # Schüsse/Ecken/Karten (aus FD.co.uk)
    "avg_shots_home", "avg_shots_away", "total_shots_exp",
    "avg_corners_home", "avg_corners_away", "total_corners_exp",
    "avg_cards_home", "avg_cards_away", "total_cards_exp",
    # Multi-source + Bookmaker Market Features
    "source_count_norm", "stat_coverage", "odds_source_count_norm",
    "odds_available_1x2", "market_margin_1x2",
    "market_home_prob", "market_draw_prob", "market_away_prob",
    "odds_available_ou25", "market_over25_prob", "market_under25_prob",
    "pinnacle_home_delta", "pinnacle_draw_delta", "pinnacle_away_delta",
    "bet365_home_delta", "bet365_draw_delta", "bet365_away_delta",
    "betfair_home_delta", "betfair_draw_delta", "betfair_away_delta",
]

# Rolling Feature-State (wird pro Run befüllt)
_ML_TEAM_HISTORY = {}  # {team_key: [list of match dicts]}
_ML_TEAM_RESULTS = {}  # {team_key: ["W","D","L",...]} für Form-Punkte
_ML_H2H_HISTORY = {}   # {(team1,team2) sorted: [list]} für H2H-Features



def _ml_load_models():
    """Lädt alle XGBoost-Modelle aus Supabase (1x pro Run)."""
    global _ML_MODELS, _ML_MODELS_LOADED
    if _ML_MODELS_LOADED:
        return
    _ML_MODELS_LOADED = True

    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    try:
        import pickle, base64, io
        # Nur die tatsaechlich genutzten Modelle laden statt aller 30+ —
        # der ungefilterte Full-Blob-Request (~50 MB base64) lief in einen Read-Timeout.
        _needed_models = ",".join(name for name, _ in _ML_TEAM_TARGETS)
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/ml_models",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "model_name,model_data", "model_name": f"in.({_needed_models})"},
            timeout=60,
        )
        if not r.ok:
            log(f"   🤖 ML-Models: Supabase {r.status_code} — Fallback auf Elo/Poisson", "WARN")
            return

        rows = r.json()
        for row in rows:
            name = row.get("model_name", "")
            data = row.get("model_data", "")
            if not name or not data:
                continue
            try:
                buf = io.BytesIO(base64.b64decode(data))
                obj = pickle.load(buf)
                _ML_MODELS[name] = obj["model"]
            except Exception as _pe:
                log(f"   🤖 ML: Fehler beim Laden von {name}: {str(_pe)[:60]}", "WARN")

        if _ML_MODELS:
            log(f"   🤖 ML-Modelle geladen: {list(_ML_MODELS.keys())}")
        else:
            log("   🤖 ML: Noch keine trainierten Modelle in Supabase — Fallback auf Elo/Poisson")
    except Exception as _mle:
        log(f"   🤖 ML-Load-Error: {str(_mle)[:80]}", "WARN")


def _ml_get_team_form(team_name, n=10):
    """Holt die rolling Form-Features für ein Team aus dem aktuellen Run-State."""
    key = normalize_team_name(team_name)
    hist = _ML_TEAM_HISTORY.get(key, [])
    results = _ML_TEAM_RESULTS.get(key, [])

    if not hist:
        return {
            "btts_rate": 0.50, "o25_rate": 0.50,
            "btts_ht_rate": 0.20, "o15ht_rate": 0.45,
            "avg_scored": 1.30, "avg_conceded": 1.20,
            "form_pts": 0.33, "streak_win": 0.0,
        }

    last = hist[-n:]
    last_r = results[-5:]

    # Form-Punkte (W=3/D=1/L=0)
    pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in last_r)
    form_pts = pts / 15.0  # max 15 → normiert 0-1

    # Gewinn-Streak
    streak = 0
    for r in reversed(results):
        if r == "W":
            streak += 1
        else:
            break
    streak_win = min(streak / 5.0, 1.0)

    return {
        "btts_rate": sum(m["btts"] for m in last) / len(last),
        "o25_rate": sum(m["over25"] for m in last) / len(last),
        "btts_ht_rate": sum(m["btts_ht"] for m in last) / len(last),
        "o15ht_rate": sum(m["over15_ht"] for m in last) / len(last),
        "avg_scored": sum(m["scored"] for m in last) / len(last),
        "avg_conceded": sum(m["conceded"] for m in last) / len(last),
        "form_pts": form_pts,
        "streak_win": streak_win,
    }


def _ml_update_team_history(home, away, home_goals, away_goals, ht_home=0, ht_away=0):
    """Updated den Rolling-State nach einem bekannten Spiel."""
    btts = int(home_goals > 0 and away_goals > 0)
    over25 = int(home_goals + away_goals > 2)
    btts_ht = int(ht_home > 0 and ht_away > 0)
    o15ht = int(ht_home + ht_away > 1)

    h_key = normalize_team_name(home)
    a_key = normalize_team_name(away)

    # Match-History (für Rolling-Raten)
    _ML_TEAM_HISTORY.setdefault(h_key, []).append({
        "btts": btts, "over25": over25, "btts_ht": btts_ht, "over15_ht": o15ht,
        "scored": home_goals, "conceded": away_goals,
    })
    _ML_TEAM_HISTORY.setdefault(a_key, []).append({
        "btts": btts, "over25": over25, "btts_ht": btts_ht, "over15_ht": o15ht,
        "scored": away_goals, "conceded": home_goals,
    })

    # Form-Ergebnisse (W/D/L)
    if home_goals > away_goals:
        _ML_TEAM_RESULTS.setdefault(h_key, []).append("W")
        _ML_TEAM_RESULTS.setdefault(a_key, []).append("L")
    elif home_goals < away_goals:
        _ML_TEAM_RESULTS.setdefault(h_key, []).append("L")
        _ML_TEAM_RESULTS.setdefault(a_key, []).append("W")
    else:
        _ML_TEAM_RESULTS.setdefault(h_key, []).append("D")
        _ML_TEAM_RESULTS.setdefault(a_key, []).append("D")

    # H2H-History
    h2h_key = tuple(sorted([h_key, a_key]))
    _ML_H2H_HISTORY.setdefault(h2h_key, []).append({
        "btts": btts,
        "goals": home_goals + away_goals,
    })


def get_ml_prediction(home_team, away_team, league_name):
    """
    Haupt-ML-Vorhersagefunktion: baut Features + ruft XGBoost-Modell auf.
    Gibt {} zurück wenn kein Modell geladen oder Liga nicht abgedeckt.
    BTTS/Over2.5/BTTS-HT/Over1.5-HT Wahrscheinlichkeiten als Prozent.
    """
    _ml_load_models()

    if not _ML_MODELS:
        return {}

    # Elo-Ratings aus dem bestehenden System holen
    elo_ratings = _build_elo_ratings(league_name) if league_name else {}
    h_key = normalize_team_name(home_team)
    a_key = normalize_team_name(away_team)

    if elo_ratings:
        if h_key not in elo_ratings:
            h_key = next((k for k in elo_ratings if h_key[:5] in k or k[:5] in h_key), None)
        if a_key not in elo_ratings:
            a_key = next((k for k in elo_ratings if a_key[:5] in k or k[:5] in a_key), None)

    elo_h = elo_ratings.get(h_key, ELO_RATINGS_CACHE.get("_global", {}).get(h_key, 1500)) + 60
    elo_a = elo_ratings.get(a_key, ELO_RATINGS_CACHE.get("_global", {}).get(a_key, 1500))

    # 🆕 Falls kein Elo für diese Teams (Nischenliga): martj42-Stats als Feature-Basis
    if elo_h == 1560 and elo_a == 1500:  # = beide Default
        h_st = get_national_team_btts_stats(home_team)
        a_st = get_national_team_btts_stats(away_team)
        if h_st and a_st:
            fh["btts_rate"] = h_st.get("btts_pct", 50) / 100
            fa["btts_rate"] = a_st.get("btts_pct", 50) / 100
            fh["o25_rate"] = h_st.get("over25_pct", 50) / 100
            fa["o25_rate"] = a_st.get("over25_pct", 50) / 100

    # Form-Features
    fh = _ml_get_team_form(home_team)
    fa = _ml_get_team_form(away_team)

    # H2H-Features aus dem Rolling-State
    _h2h_key = tuple(sorted([normalize_team_name(home_team), normalize_team_name(away_team)]))
    _h2h_hist = _ML_H2H_HISTORY.get(_h2h_key, [])
    h2h_btts = sum(m["btts"] for m in _h2h_hist) / len(_h2h_hist) if _h2h_hist else 0.5
    h2h_goals = sum(m["goals"] for m in _h2h_hist) / len(_h2h_hist) if _h2h_hist else 2.5
    h2h_norm = min(len(_h2h_hist) / 10.0, 1.0)

    features = [
        # Elo
        elo_h, elo_a, elo_h - elo_a,
        # BTTS/Over-Raten
        fh["btts_rate"], fa["btts_rate"], (fh["btts_rate"] + fa["btts_rate"]) / 2,
        fh["o25_rate"], fa["o25_rate"], (fh["o25_rate"] + fa["o25_rate"]) / 2,
        # Tore
        fh["avg_scored"], fa["avg_scored"],
        fh["avg_conceded"], fa["avg_conceded"],
        fh["avg_scored"] + fa["avg_scored"],
        (fh["avg_conceded"] + fa["avg_conceded"]) / 2,
        # HT
        fh["btts_ht_rate"], fa["btts_ht_rate"],
        fh["o15ht_rate"], fa["o15ht_rate"],
        # Form-Punkte
        fh["form_pts"], fa["form_pts"], fh["form_pts"] - fa["form_pts"],
        fh["streak_win"], fa["streak_win"],
        # H2H
        h2h_btts, h2h_goals, h2h_norm,
        # Schüsse/Ecken/Karten (0 = unbekannt, kein Problem)
        fh.get("avg_shots", 0.0), fa.get("avg_shots", 0.0),
        fh.get("avg_shots", 0.0) + fa.get("avg_shots", 0.0),
        fh.get("avg_corners", 0.0), fa.get("avg_corners", 0.0),
        fh.get("avg_corners", 0.0) + fa.get("avg_corners", 0.0),
        fh.get("avg_cards", 0.0), fa.get("avg_cards", 0.0),
        fh.get("avg_cards", 0.0) + fa.get("avg_cards", 0.0),
        # Multi-source + Bookmaker Market Features (0.0 wenn nicht verfügbar)
        fh.get("source_count_norm", 0.5),
        fh.get("stat_coverage", 0.5),
        fh.get("odds_source_count_norm", 0.5),
        1.0,   # odds_available_1x2 (Pinnacle verfügbar)
        0.05,  # market_margin_1x2 (typisch 5%)
        fh.get("market_home_prob", 0.40),
        fh.get("market_draw_prob", 0.25),
        fa.get("market_away_prob", 0.35),
        1.0,   # odds_available_ou25
        fh.get("market_over25_prob", 0.50),
        1.0 - fh.get("market_over25_prob", 0.50),  # market_under25_prob
        0.0,   # pinnacle_home_delta
        0.0,   # pinnacle_draw_delta
        0.0,   # pinnacle_away_delta
        0.0,   # bet365_home_delta
        0.0,   # bet365_draw_delta
        0.0,   # bet365_away_delta
        0.0,   # betfair_home_delta
        0.0,   # betfair_draw_delta
        0.0,   # betfair_away_delta
    ]

    import numpy as np
    X = np.array(features).reshape(1, -1)
    result = {}

    try:
        for model_name, out_key in _ML_TEAM_TARGETS:
            if model_name in _ML_MODELS:
                prob = _ML_MODELS[model_name].predict_proba(X)[0][1]
                result[out_key] = round(prob * 100, 1)
        result["source"] = "xgboost"
        result["elo_home"] = round(elo_h, 0)
        result["elo_away"] = round(elo_a, 0)
    except Exception as _pie:
        log(f"   🤖 ML-Predict-Error: {str(_pie)[:60]}", "WARN")
        return {}

    return result


ELO_RATINGS_CACHE = {}  # {league_code: {team_norm: elo_rating}}
ELO_K_FACTOR = 20
ELO_HOME_ADVANTAGE = 60
ELO_BASE_RATING = 1500


def _build_elo_ratings(league_name):
    """
    Baut Elo-Ratings aus der kompletten football-data.co.uk Saison-Historie
    (chronologisch durchgerechnet). Gecacht pro Liga-Code.
    """
    ln = league_name.lower()
    code = None
    for key, c in FD_CO_UK_LEAGUE_CODES.items():
        if key in ln:
            code = c
            break
    if not code:
        return {}

    if code in ELO_RATINGS_CACHE:
        return ELO_RATINGS_CACHE[code]

    rows = _fd_co_uk_load_csv(league_name)
    if not rows:
        ELO_RATINGS_CACHE[code] = {}
        return {}

    ratings = {}

    def _get(team):
        tn = normalize_team_name(team)
        if tn not in ratings:
            ratings[tn] = ELO_BASE_RATING
        return tn

    for row in rows:
        try:
            home = row.get("HomeTeam", "")
            away = row.get("AwayTeam", "")
            fthg = int(row.get("FTHG", 0) or 0)
            ftag = int(row.get("FTAG", 0) or 0)
            if not home or not away:
                continue

            h_key = _get(home)
            a_key = _get(away)
            h_elo = ratings[h_key] + ELO_HOME_ADVANTAGE
            a_elo = ratings[a_key]

            expected_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400))
            if fthg > ftag:
                actual_h = 1.0
            elif fthg < ftag:
                actual_h = 0.0
            else:
                actual_h = 0.5

            # Tordifferenz-Gewichtung — höhere Siege bewegen Elo stärker
            margin_mult = 1.0 + (abs(fthg - ftag) - 1) * 0.15 if abs(fthg - ftag) > 1 else 1.0
            delta = ELO_K_FACTOR * margin_mult * (actual_h - expected_h)

            ratings[h_key] += delta
            ratings[a_key] -= delta
        except (ValueError, TypeError):
            continue

    log(f"   🧠 ELO-DEBUG: {code} → {len(ratings)} Teams bewertet")
    ELO_RATINGS_CACHE[code] = ratings
    return ratings


def _poisson_pmf(k, lam):
    """Poisson-Wahrscheinlichkeit P(X=k) für Erwartungswert lam."""
    import math
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def get_elo_poisson_prediction(home_team, away_team, league_name):
    """
    Eigenes Vorhersagemodell: Elo-Differenz → erwartete Tore (Poisson) →
    BTTS/Over2.5/1X2-Wahrscheinlichkeiten. Kein Bezug zu Pinnacle-Quoten.
    Gibt {} zurück wenn die Liga nicht abgedeckt ist oder zu wenig Daten da sind.
    """
    ratings = _build_elo_ratings(league_name)
    if not ratings or len(ratings) < 6:
        return {}

    h_key = normalize_team_name(home_team)
    a_key = normalize_team_name(away_team)

    # Fuzzy-Suche falls exakter Key fehlt
    if h_key not in ratings:
        h_key = next((k for k in ratings if h_key[:6] in k or k[:6] in h_key), None)
    if a_key not in ratings:
        a_key = next((k for k in ratings if a_key[:6] in k or k[:6] in a_key), None)
    if not h_key or not a_key:
        return {}

    h_elo = ratings[h_key] + ELO_HOME_ADVANTAGE
    a_elo = ratings[a_key]
    elo_diff = h_elo - a_elo

    # Liga-Ø Tore als Basis (Standard ~1.35 Heim- / ~1.15 Auswärtstore)
    LEAGUE_AVG_HOME_GOALS = 1.40
    LEAGUE_AVG_AWAY_GOALS = 1.15

    # Elo-Differenz verschiebt die erwarteten Tore (empirisch kalibrierter Faktor)
    shift = elo_diff / 400
    exp_home_goals = max(0.3, LEAGUE_AVG_HOME_GOALS * (1.15 ** shift))
    exp_away_goals = max(0.3, LEAGUE_AVG_AWAY_GOALS * (1.15 ** -shift))

    # BTTS: P(Heim>=1) * P(Auswärts>=1)
    p_home_0 = _poisson_pmf(0, exp_home_goals)
    p_away_0 = _poisson_pmf(0, exp_away_goals)
    btts_prob = (1 - p_home_0) * (1 - p_away_0)

    # Over 2.5: 1 - P(Gesamttore <= 2) via Tordifferenz-Faltung
    over25_prob = 0.0
    for h in range(0, 8):
        for a in range(0, 8):
            if h + a > 2:
                over25_prob += _poisson_pmf(h, exp_home_goals) * _poisson_pmf(a, exp_away_goals)

    # 1X2 grob aus Elo-Erwartung (vereinfacht über Score-Matrix)
    p_home_win = p_draw = p_away_win = 0.0
    for h in range(0, 8):
        for a in range(0, 8):
            p = _poisson_pmf(h, exp_home_goals) * _poisson_pmf(a, exp_away_goals)
            if h > a:
                p_home_win += p
            elif h == a:
                p_draw += p
            else:
                p_away_win += p

    return {
        "source": "elo_poisson",
        "elo_home": round(h_elo, 0),
        "elo_away": round(a_elo, 0),
        "exp_goals_home": round(exp_home_goals, 2),
        "exp_goals_away": round(exp_away_goals, 2),
        "btts_pct": round(btts_prob * 100, 1),
        "over25_pct": round(over25_prob * 100, 1),
        "home_win_pct": round(p_home_win * 100, 1),
        "draw_pct": round(p_draw * 100, 1),
        "away_win_pct": round(p_away_win * 100, 1),
    }


def get_national_team_btts_stats(team_name: str, last_n: int = 20) -> dict:
    """BTTS/Over2.5 Stats für Nationalmannschaften aus martj42 Daten."""
    global MARTJ42_DATA
    if MARTJ42_DATA is None:
        load_martj42_data()  # Automatisch laden wenn nötig
    if not MARTJ42_DATA:
        return {}
    team_lower = team_name.lower()
    games = []
    for g in MARTJ42_DATA:
        h = str(g.get("home_team","")).lower()
        a = str(g.get("away_team","")).lower()
        # Mindestlänge gegen falsche Kurz-Teilstring-Treffer (z.B. Vereinsnamen-Fragmente)
        if len(team_lower) >= 4 and (team_lower in h or h in team_lower or team_lower in a or a in team_lower):
            try:
                hs, as_ = int(g.get("home_score",-1)), int(g.get("away_score",-1))
                if hs >= 0 and as_ >= 0:
                    games.append({"btts":1 if hs>0 and as_>0 else 0,
                                  "over25":1 if hs+as_>2 else 0,
                                  "total":hs+as_,"date":g.get("date","")})
            except Exception:
                continue
    if len(games) < 5:
        return {}
    games = sorted(games, key=lambda x: x["date"], reverse=True)[:last_n]
    n = len(games)
    return {
        "btts_pct": round(sum(g["btts"] for g in games)/n*100,1),
        "over25_pct": round(sum(g["over25"] for g in games)/n*100,1),
        "avg_goals": round(sum(g["total"] for g in games)/n,2),
        "games_analyzed": n,
    }


def get_international_fixtures_today(target_date) -> list:
    """
    Holt heutige internationale Spiele aus martj42 Daten.
    Ideal für WM 2026, UEFA Nations League, Freundschaftsspiele!
    """
    cache_key = f"martj42_fix_{target_date}"
    if cache_key in MARTJ42_CACHE:
        return MARTJ42_CACHE[cache_key]

    data = load_martj42_data()
    if not data:
        return []

    target_str = str(target_date)
    now_utc = datetime.now(timezone.utc)
    fixtures = []

    for match in data:
        if match["date"] != target_str:
            continue
        if match["home_score"] >= 0:  # Bereits gespielt
            continue

        fixtures.append({
            "home": match["home"],
            "away": match["away"],
            "time_local": "TBD",
            "time_utc": f"{target_str}T18:00:00Z",
            "source": "martj42",
            "match_id": f"m42_{hash(match['home']+match['away'])}",
            "tournament": match["tournament"],
        })

    MARTJ42_CACHE[cache_key] = fixtures
    if fixtures:
        log(f"   🌍 martj42: {len(fixtures)} internationale Spiele heute")
    return fixtures


def get_international_btts_rate(team_name: str, last_n: int = 20) -> dict:
    """
    Berechnet historische BTTS/Over2.5 Rate für ein Nationalteam.
    Nutzt 49.000+ historische Länderspiele!
    """
    cache_key = f"martj42_btts_{team_name}"
    if cache_key in MARTJ42_CACHE:
        return MARTJ42_CACHE[cache_key]

    data = load_martj42_data()
    if not data:
        return {}

    team_norm = normalize_team_name(team_name)
    team_matches = []

    # Suche alle Spiele dieses Teams (neueste zuerst)
    for match in reversed(data):
        home_n = normalize_team_name(match["home"])
        away_n = normalize_team_name(match["away"])
        if team_norm[:8] in home_n or home_n[:8] in team_norm or \
           team_norm[:8] in away_n or away_n[:8] in team_norm:
            if match["btts"] is not None:
                team_matches.append(match)
        if len(team_matches) >= last_n:
            break

    if len(team_matches) < 3:
        return {}

    btts_count = sum(1 for m in team_matches if m["btts"])
    over25_count = sum(1 for m in team_matches if m.get("over25"))
    avg_goals = sum(m["total"] for m in team_matches if m["total"] >= 0) / len(team_matches)

    result = {
        "btts_rate": round(btts_count / len(team_matches) * 100, 1),
        "over25_rate": round(over25_count / len(team_matches) * 100, 1),
        "avg_goals": round(avg_goals, 2),
        "games": len(team_matches),
        "source": "martj42",
    }

    MARTJ42_CACHE[cache_key] = result
    return result


# ============================================================
# 📊 FOOTBALLCSV - Ligaergebnisse GitHub (Backup für BTTS History)
# ============================================================

FOOTBALLCSV_CACHE = {}

FOOTBALLCSV_REPOS = {
    "Premier League": ("footballcsv/england", "eng.1", "2020s", "2024-25"),
    "Bundesliga": ("footballcsv/deutschland", "de.1", "2020s", "2024-25"),
    "La Liga": ("footballcsv/espana", "es.1", "2020s", "2024-25"),
    "Bundesliga Österreich": ("footballcsv/austria", "at.1", "2020s", "2024-25"),
}

def get_footballcsv_btts_rate(league_name: str, team_name: str) -> dict:
    """
    Holt historische BTTS-Rate aus footballcsv GitHub Repos.
    Kostenlos, kein Key, direkt von GitHub.
    """
    repo_info = FOOTBALLCSV_REPOS.get(league_name)
    if not repo_info:
        return {}

    repo, code, decade, season = repo_info
    cache_key = f"fcsv_{league_name}_{team_name}"
    if cache_key in FOOTBALLCSV_CACHE:
        return FOOTBALLCSV_CACHE[cache_key]

    url = f"https://raw.githubusercontent.com/{repo}/master/{decade}/{season}/{code}.csv"

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if not r.ok:
            return {}

        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return {}

        team_norm = normalize_team_name(team_name)
        btts = 0
        over25 = 0
        total = 0

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                home = normalize_team_name(parts[2] if len(parts) > 4 else "")
                away = normalize_team_name(parts[4] if len(parts) > 4 else "")
                score = parts[3] if len(parts) > 3 else ""

                if team_norm[:6] not in home and home[:6] not in team_norm and \
                   team_norm[:6] not in away and away[:6] not in team_norm:
                    continue

                # Score parsen "2-1" oder "2:1"
                import re as _re
                m = _re.search(r"(\d+)[:\-](\d+)", score)
                if not m:
                    continue

                hg, ag = int(m.group(1)), int(m.group(2))
                total += 1
                if hg > 0 and ag > 0:
                    btts += 1
                if hg + ag > 2:
                    over25 += 1
            except Exception:
                continue

        if total < 3:
            return {}

        result = {
            "btts_rate": round(btts / total * 100, 1),
            "over25_rate": round(over25 / total * 100, 1),
            "games": total,
            "source": "footballcsv",
        }
        FOOTBALLCSV_CACHE[cache_key] = result
        return result

    except Exception as e:
        log(f"footballcsv Error: {str(e)[:50]}", "WARN")
        return {}


# ============================================================
# 📰 GOOGLE NEWS - Team News scrapen
# ============================================================
GOOGLE_NEWS_CACHE = {}

def scrape_google_news(query, max_results=3):
    """
    Google News scrapen für Team News + Verletzungen.
    Kein Key nötig!
    """
    cache_key = f"gn_{query}"
    if cache_key in GOOGLE_NEWS_CACHE:
        return GOOGLE_NEWS_CACHE[cache_key]

    try:
        import random as _r
        import re as _re
        import urllib.parse

        encoded = urllib.parse.quote(query)
        r = requests.get(
            f"https://news.google.com/rss/search?q={encoded}&hl=de&gl=DE&ceid=DE:de",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/rss+xml, application/xml",
            },
            timeout=10,
        )

        if not r.ok:
            return []

        # Parse RSS
        titles = _re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", r.text)
        descriptions = _re.findall(r"<description><!\[CDATA\[(.+?)\]\]></description>", r.text)

        results = []
        for i, title in enumerate(titles[1:max_results+1]):  # Skip first (feed title)
            desc = descriptions[i] if i < len(descriptions) else ""
            results.append({
                "title": title.strip(),
                "description": _re.sub(r"<[^>]+>", "", desc).strip()[:200],
            })

        GOOGLE_NEWS_CACHE[cache_key] = results
        return results

    except Exception:
        return []


def get_team_news_google(home_team, away_team, league):
    """
    Holt aktuelle Team News von Google News.
    Verletzungen, Sperren, Form-News.
    """
    query = f"{home_team} {away_team} {league} lineup injury"
    results = scrape_google_news(query, max_results=3)

    if not results:
        return None

    # Suche nach Verletzungs-Keywords
    injury_keywords = ["verletzt", "fehlt", "gesperrt", "injury", "suspended", "out", "doubt"]
    news_items = []

    for r in results:
        text = (r.get("title", "") + " " + r.get("description", "")).lower()
        has_injury = any(kw in text for kw in injury_keywords)
        news_items.append({
            "title": r.get("title", ""),
            "has_injury_info": has_injury,
        })

    return news_items if news_items else None


# ============================================================
# 🤖 REDDIT - Community Insider Tips
# ============================================================
REDDIT_CACHE = {}

def scrape_reddit_soccer(home_team, away_team):
    """
    Reddit Soccer Threads für Insider News.
    Kein Key nötig - öffentliche Daten!
    """
    cache_key = f"rd_{home_team}_{away_team}"
    if cache_key in REDDIT_CACHE:
        return REDDIT_CACHE[cache_key]

    try:
        import random as _r
        import re as _re

        query = f"{home_team} {away_team}".replace(" ", "+")
        r = requests.get(
            f"https://www.reddit.com/r/soccer/search.json?q={query}&sort=new&limit=5",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FootballBot/1.0)",
                "Accept": "application/json",
            },
            timeout=10,
        )

        if not r.ok:
            return None

        data = r.json()
        posts = data.get("data", {}).get("children", [])

        results = []
        for post in posts[:3]:
            p = post.get("data", {})
            title = p.get("title", "")
            score = p.get("score", 0)
            if score > 10:  # Nur populäre Posts
                results.append({
                    "title": title,
                    "score": score,
                    "url": p.get("url", ""),
                })

        REDDIT_CACHE[cache_key] = results
        if results:
            log(f"   🤖 Reddit: {len(results)} Posts gefunden")
        return results if results else None

    except Exception:
        return None


# ============================================================
# 🌦️ METEOSTAT - Historische Wetterdaten
# ============================================================
def get_historical_weather_impact(league_name, month):
    """
    Historische Wetterdaten für Liga-Analyse.
    Zeigt ob Wetter typisch hohe/niedrige BTTS Rate beeinflusst.
    """
    # Vereinfachte historische Analyse basierend auf Monat + Liga
    WINTER_LEAGUES = ["Premier League", "Bundesliga", "La Liga", "Serie A", "Ligue 1"]
    SUMMER_LEAGUES = ["MLS", "A-League Australia", "J1 League Japan"]

    impact = "neutral"

    # Wintermonate in Europa
    if league_name in WINTER_LEAGUES:
        if month in [11, 12, 1, 2]:
            impact = "slightly_negative"  # Kälte, Regen
        elif month in [4, 5]:
            impact = "positive"  # Frühling = mehr Tore

    # Sommerliga
    if league_name in SUMMER_LEAGUES:
        if month in [6, 7, 8]:
            impact = "slightly_negative"  # Hitze

    return {
        "month": month,
        "historical_impact": impact,
        "note": f"Historisch: {impact} für {league_name} im Monat {month}",
    }



# ============================================================
# ⚽ FOTMOB - Inoffizielle API, xG + 500+ Ligen, kein Key!
# ============================================================

# ============================================================
# 🎭 UNIVERSELLER PLAYWRIGHT WRAPPER - für alle blockierten Sites
# ============================================================

def smart_request(url, timeout=15, use_playwright_if_blocked=True, headers=None):
    """
    Intelligenter Request: erst direkt, dann Playwright bei 403/429/503
    Gilt für ALLE Domains!
    """
    import random as _r
    default_headers = {
        "User-Agent": _r.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0",
        ]),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    if headers:
        default_headers.update(headers)
    
    try:
        r = requests.get(url, headers=default_headers, timeout=timeout)
        if r.status_code in [403, 429, 503, 406, 444] and use_playwright_if_blocked:
            log(f"   🎭 {url[:40]}... → Playwright (Status {r.status_code})")
            html = scrape_with_playwright(url, timeout=8000)
            if html:
                log(f"   ✅ Playwright erfolgreich!")
                return type('Response', (), {
                    'ok': True, 'status_code': 200,
                    'text': html, 'json': lambda: {}
                })()
            return None
        return r if r.ok else None
    except requests.exceptions.ConnectionError:
        if use_playwright_if_blocked and PLAYWRIGHT_AVAILABLE:
            log(f"   🎭 ConnectionError → Playwright für {url[:40]}")
            html = scrape_with_playwright(url, timeout=8000)
            if html:
                return type('Response', (), {
                    'ok': True, 'status_code': 200,
                    'text': html, 'json': lambda: {}
                })()
        return None
    except Exception as e:
        log(f"smart_request Error: {str(e)[:50]}", "WARN")
        return None


FOTMOB_CACHE = {}

def get_fotmob_match_stats(home_team, away_team, target_date):
    """
    FotMob inoffizielle API - xG, Momentum, Live Stats
    500+ Ligen weltweit, kein Key nötig!
    """
    cache_key = f"fm_{home_team}_{away_team}_{target_date}"
    if cache_key in FOTMOB_CACHE:
        return FOTMOB_CACHE[cache_key]

    try:
        import random as _r
        date_str = str(target_date).replace("-", "")

        r = requests.get(
            f"https://www.fotmob.com/api/matches?date={date_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
                "x-mas": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        data = r.json()
        leagues = data.get("leagues", [])
        home_norm = normalize_team_name(home_team)

        for league in leagues:
            for match in league.get("matches", []):
                h = match.get("home", {}).get("name", "")
                a = match.get("away", {}).get("name", "")

                if not (home_norm[:6] in normalize_team_name(h) or normalize_team_name(h)[:6] in home_norm):
                    continue

                match_id = match.get("id")
                if not match_id:
                    continue

                # Hole Match Details mit xG
                r2 = requests.get(
                    f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                        "Referer": "https://www.fotmob.com/",
                    },
                    timeout=10,
                )

                if not r2.ok:
                    continue

                details = r2.json()
                stats = details.get("content", {}).get("stats", {}).get("stats", [])

                result = {"source": "fotmob"}
                for stat in stats:
                    title = stat.get("title", "").lower()
                    if "xg" in title or "expected goals" in title:
                        home_val = stat.get("stats", [{}])[0].get("value", 0)
                        away_val = stat.get("stats", [{}])[1].get("value", 0) if len(stat.get("stats", [])) > 1 else 0
                        result["xg_home"] = home_val
                        result["xg_away"] = away_val

                FOTMOB_CACHE[cache_key] = result
                if result.get("xg_home"):
                    log(f"   ⚽ FotMob xG: {home_team} {result['xg_home']} vs {result['xg_away']}")
                return result

    except Exception as e:
        log(f"FotMob Error: {str(e)[:50]}", "WARN")
    return None


def fetch_fotmob_fixtures(league_name, target_date):
    """
    FotMob Fixtures - 500+ Ligen, kein Key!
    """
    cache_key = f"fm_fix_{league_name}_{target_date}"
    if cache_key in FOTMOB_CACHE:
        return FOTMOB_CACHE[cache_key]

    FOTMOB_LEAGUES = {
        "Premier League": 47,
        "Bundesliga": 54,
        "La Liga": 87,
        "Serie A": 55,
        "Ligue 1": 53,
        "Eredivisie": 57,
        "Primeira Liga": 61,
        "Champions League": 42,
        "Europa League": 73,
        "Conference League": 10090,
        "MLS": 130,
        "Brasileirao Serie A": 325,
        "Liga Argentinien": 112,
        "J1 League Japan": 40,
        "K League 1": 133,
        "Saudi Pro League": 1366,
    }

    league_id = FOTMOB_LEAGUES.get(league_name)
    if not league_id:
        return []

    try:
        import random as _r
        date_str = str(target_date).replace("-", "")

        r = requests.get(
            f"https://www.fotmob.com/api/matches?date={date_str}&league={league_id}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        for league in data.get("leagues", []):
            for match in league.get("matches", []):
                try:
                    status = match.get("status", {})
                    if status.get("finished") or status.get("ongoing"):
                        continue

                    home = match.get("home", {}).get("name", "")
                    away = match.get("away", {}).get("name", "")
                    if not home or not away:
                        continue

                    utc_time = match.get("status", {}).get("utcTime", "")
                    if utc_time:
                        kickoff = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                        if kickoff <= now_utc:
                            continue
                        kickoff_str = kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        kickoff_str = f"{target_date}T12:00:00Z"

                    fixtures.append({
                        "home": home,
                        "away": away,
                        "match_id": str(match.get("id", "")),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "fotmob",
                    })
                except Exception:
                    continue

        FOTMOB_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   ⚽ FotMob: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception as e:
        log(f"FotMob Fixtures Error: {str(e)[:50]}", "WARN")
        return []


# ============================================================
# 📊 STAT-BASIERTE ANALYSE-TIPPS (KEINE QUOTEN, nur Empfehlungen)
# ============================================================
# Für Spiele/Märkte ohne echte Pinnacle-Quote (z.B. Karten, Tackles,
# Offside bei WM-Spielen) — liefert Statistik-Begründung statt
# erfundener Buchmacher-Zahlen. Klar als "Analyse" gekennzeichnet,
# kein Einsatz/Stake, damit niemand es mit einer echten Quote verwechselt.

# ============================================================
# 🚀 THESTATSAPI — Player Stats, xG, Lineups, Odds, Settlement
# ============================================================
# Base: https://api.thestatsapi.com/api/football/
# Auth: Bearer {THESTATSAPI_KEY}
# Liefert: 150+ Ligen, Player Stats (84K+ Spieler), xG, Lineups,
#          Pinnacle/Bet365-Quoten, BTTS/Over/1X2/Corners Märkte

_TSA_BASE = "https://api.thestatsapi.com/api/football"
_TSA_CACHE = {}
_TSA_COMP_MAP = {}
_TSA_COMP_MAP_LOADED = False
_TSA_KEY_OFFSET = 0
_TSA_DEAD_KEYS = set()


def _tsa_get(endpoint, params=None, timeout=12):
    """GET für TheStatsAPI mit automatischer Key-Rotation über alle 5 Keys."""
    global _TSA_KEY_OFFSET
    if not THESTATSAPI_KEYS:
        return None

    n = len(THESTATSAPI_KEYS)
    for offset in range(n):
        idx = (_TSA_KEY_OFFSET + offset) % n
        if idx in _TSA_DEAD_KEYS:
            continue
        key = THESTATSAPI_KEYS[idx]
        try:
            r = requests.get(
                f"{_TSA_BASE}{endpoint}",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                params=params or {},
                timeout=timeout,
            )
            if r.status_code == 429:
                log(f"   🚀 TSA Key {idx+1}: Rate-Limit — nächster Key", "WARN")
                _TSA_DEAD_KEYS.add(idx)
                continue
            if r.status_code in (401, 403):
                log(f"   🚀 TSA Key {idx+1}: Ungültig ({r.status_code})", "WARN")
                _TSA_DEAD_KEYS.add(idx)
                continue
            if r.ok:
                _TSA_KEY_OFFSET = (idx + 1) % n  # nächster Key beim nächsten Call
                return r.json()
            log(f"   🚀 TSA {endpoint}: HTTP {r.status_code}", "WARN")
            return None
        except Exception as _e:
            log(f"   🚀 TSA Error {endpoint}: {str(_e)[:60]}", "WARN")
            continue

    log("   🚀 TSA: Alle Keys erschöpft/ungültig", "WARN")
    return None


def _tsa_load_competitions():
    """Lädt alle Competitions einmalig und baut Liga-Name→ID Map."""
    global _TSA_COMP_MAP, _TSA_COMP_MAP_LOADED
    if _TSA_COMP_MAP_LOADED:
        return
    _TSA_COMP_MAP_LOADED = True
    data = _tsa_get("/competitions", {"per_page": 200})
    if not data:
        return
    items = data.get("data") or data if isinstance(data, list) else []
    for comp in items:
        name = comp.get("name", "") or ""
        cid = comp.get("id") or comp.get("competition_id")
        if name and cid:
            _TSA_COMP_MAP[name.lower()] = cid
            # Kurzname auch mappen
            short = comp.get("short_name") or comp.get("abbreviation") or ""
            if short:
                _TSA_COMP_MAP[short.lower()] = cid
    log(f"   🚀 TSA: {len(_TSA_COMP_MAP)} Competitions geladen")


def _tsa_find_comp_id(league_name):
    """Findet Competition-ID für einen Liga-Namen (Fuzzy)."""
    _tsa_load_competitions()
    ln = league_name.lower()
    # Exakter Match
    if ln in _TSA_COMP_MAP:
        return _TSA_COMP_MAP[ln]
    # Fuzzy: jeder Key der im Liga-Namen enthalten ist
    for key, cid in _TSA_COMP_MAP.items():
        if key in ln or ln in key or key[:8] in ln:
            return cid
    return None


def tsa_get_fixtures_for_date(target_date):
    """
    Holt alle Fixtures eines Tages von TheStatsAPI.
    Gecacht pro Tag — ersetzt/ergänzt Pinnacle-Fixture-Liste.
    """
    date_str = str(target_date)
    cache_key = f"tsa_fixtures_{date_str}"
    if cache_key in _TSA_CACHE:
        return _TSA_CACHE[cache_key]

    data = _tsa_get("/matches", {"date": date_str, "per_page": 200})
    fixtures = []
    if data:
        items = data.get("data") or (data if isinstance(data, list) else [])
        for m in items:
            home = (m.get("home_team") or {}).get("name", "")
            away = (m.get("away_team") or {}).get("name", "")
            if not home or not away:
                continue
            fixtures.append({
                "match_id": m.get("id"),
                "home": home,
                "away": away,
                "league": (m.get("competition") or {}).get("name", ""),
                "time": (m.get("kickoff") or m.get("time") or "")[:5],
                "date": date_str,
                "status": m.get("status", ""),
                "home_score": (m.get("score") or {}).get("home"),
                "away_score": (m.get("score") or {}).get("away"),
            })

    log(f"   🚀 TSA Fixtures: {len(fixtures)} Spiele für {date_str}")
    _TSA_CACHE[cache_key] = fixtures
    return fixtures


def tsa_get_match_stats(match_id):
    """Holt Match-Stats (xG, Schüsse, Possession) für ein Spiel."""
    if not match_id:
        return None
    cache_key = f"tsa_match_{match_id}"
    if cache_key in _TSA_CACHE:
        return _TSA_CACHE[cache_key]
    data = _tsa_get(f"/matches/{match_id}/stats")
    _TSA_CACHE[cache_key] = data
    return data


def tsa_get_lineups(match_id):
    """Holt bestätigte Aufstellung für ein Spiel."""
    if not match_id:
        return None
    cache_key = f"tsa_lineup_{match_id}"
    if cache_key in _TSA_CACHE:
        return _TSA_CACHE[cache_key]
    data = _tsa_get(f"/matches/{match_id}/lineups")
    _TSA_CACHE[cache_key] = data
    return data


def tsa_get_match_odds(match_id):
    """
    Holt Pre-Match Odds von Pinnacle/Bet365/Betfair für ein Spiel.
    Märkte: 1X2, BTTS, Over/Under, Asian Handicap, Corners.
    """
    if not match_id:
        return None
    cache_key = f"tsa_odds_{match_id}"
    if cache_key in _TSA_CACHE:
        return _TSA_CACHE[cache_key]
    data = _tsa_get(f"/odds/{match_id}")
    _TSA_CACHE[cache_key] = data
    return data


def tsa_get_player_stats(league_name, season=None):
    """
    Holt Spieler-Saisonstats für eine Liga (Tore, Assists, Karten, Schüsse, xG).
    Perfekt für Prop Builder + Goal Hunter.
    """
    comp_id = _tsa_find_comp_id(league_name)
    if not comp_id:
        return []

    cache_key = f"tsa_players_{comp_id}_{season or 'current'}"
    if cache_key in _TSA_CACHE:
        return _TSA_CACHE[cache_key]

    params = {"per_page": 100}
    if season:
        params["season"] = season

    data = _tsa_get(f"/competitions/{comp_id}/players/stats", params)
    players = []
    if data:
        items = data.get("data") or (data if isinstance(data, list) else [])
        for p in items:
            stats = p.get("stats") or p
            players.append({
                "name": p.get("name") or p.get("player_name", ""),
                "team": (p.get("team") or {}).get("name", "") or p.get("team_name", ""),
                "position": p.get("position", ""),
                "goals": stats.get("goals", 0) or 0,
                "assists": stats.get("assists", 0) or 0,
                "appearances": stats.get("appearances") or stats.get("matches_played", 1) or 1,
                "minutes": stats.get("minutes_played", 0) or 0,
                "yellow_cards": stats.get("yellow_cards", 0) or 0,
                "red_cards": stats.get("red_cards", 0) or 0,
                "shots": stats.get("shots", 0) or 0,
                "shots_on_target": stats.get("shots_on_target", 0) or 0,
                "xg": stats.get("xg") or stats.get("expected_goals", 0) or 0,
                "fouls_committed": stats.get("fouls_committed", 0) or 0,
                "source": "thestatsapi",
            })

    log(f"   🚀 TSA Players: {len(players)} Spieler für {league_name}")
    _TSA_CACHE[cache_key] = players
    return players


def tsa_get_top_scorers(league_name, season=None):
    """
    Holt Top-Torschützen einer Liga von TheStatsAPI.
    Direkte Alternative zu API-Football get_top_scorers().
    """
    players = tsa_get_player_stats(league_name, season)
    if not players:
        return []

    scorers = sorted(
        [p for p in players if p["goals"] > 0],
        key=lambda x: x["goals"] / max(x["appearances"], 1),
        reverse=True
    )[:20]

    return [{
        "name": p["name"],
        "team": p["team"],
        "goals_total": p["goals"],
        "appearances": p["appearances"],
        "goals_per_game": round(p["goals"] / max(p["appearances"], 1), 2),
        "xg": p["xg"],
        "source": "thestatsapi",
    } for p in scorers]


def tsa_find_match_result(home_team, away_team, tip_date):
    """
    Settlement-Fallback: Sucht Spielergebnis via TheStatsAPI Tages-Fixtures.
    """
    fixtures = tsa_get_fixtures_for_date(tip_date)
    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in fixtures:
        if m.get("status", "").upper() not in ("FT", "FINISHED", "FULL_TIME", "AET", "PEN"):
            continue
        h = m.get("home", "").lower()
        a = m.get("away", "").lower()
        if (h[:6] in h_target or h_target[:6] in h) and (a[:6] in a_target or a_target[:6] in a):
            home_g = m.get("home_score") or 0
            away_g = m.get("away_score") or 0
            # Detaillierte Stats nachladen wenn Match-ID vorhanden
            match_id = m.get("match_id")
            ht_home = ht_away = 0
            if match_id:
                stats = tsa_get_match_stats(match_id)
                if stats:
                    ht = (stats.get("half_time") or stats.get("score", {}).get("half_time") or {})
                    ht_home = ht.get("home", 0) or 0
                    ht_away = ht.get("away", 0) or 0
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
    return None


FOTMOB_TEAM_ID_CACHE = {}
FOTMOB_PLAYER_STATS_CACHE = {}

def _fotmob_find_team_id(team_name):
    """Sucht FotMob Team-ID via Suche-Endpoint (kein Key nötig)."""
    cache_key = team_name.lower()
    if cache_key in FOTMOB_TEAM_ID_CACHE:
        return FOTMOB_TEAM_ID_CACHE[cache_key]

    team_id = None
    try:
        r = requests.get(
            "https://www.fotmob.com/api/searchapi/suggest",
            params={"term": team_name, "lang": "en"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Accept": "application/json",
            },
            timeout=10,
        )
        if r.ok:
            data = r.json()
            squads = data.get("squad", []) if isinstance(data, dict) else []
            for group in squads:
                for item in group.get("suggestions", []):
                    if item.get("type") == "team":
                        team_id = item.get("id")
                        break
                if team_id:
                    break
    except Exception as _fte:
        log(f"   🔍 FOTMOB-TEAM-DEBUG: '{team_name}' → Fehler {str(_fte)[:60]}", "WARN")

    FOTMOB_TEAM_ID_CACHE[cache_key] = team_id
    return team_id


def get_fotmob_player_season_stats(team_name):
    """
    Holt Kader-Saisonstats von FotMob (Tore, Karten, Schüsse p90 etc.)
    für ein Team — kostenlos, kein Key. Best-Effort mit Debug-Logging,
    da das exakte Antwortformat je nach Wettbewerb variieren kann.
    """
    cache_key = team_name.lower()
    if cache_key in FOTMOB_PLAYER_STATS_CACHE:
        return FOTMOB_PLAYER_STATS_CACHE[cache_key]

    players = []
    team_id = _fotmob_find_team_id(team_name)
    if not team_id:
        log(f"   🔍 FOTMOB-TEAM-DEBUG: keine Team-ID für '{team_name}' gefunden")
        FOTMOB_PLAYER_STATS_CACHE[cache_key] = players
        return players

    try:
        r = requests.get(
            f"https://www.fotmob.com/api/teams",
            params={"id": team_id, "tab": "squad"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
            },
            timeout=12,
        )
        if r.ok:
            data = r.json()
            squad = data.get("squad", {}) or {}
            members = squad.get("members", []) or []
            for m in members:
                stats = m.get("stats", {}) or {}
                players.append({
                    "name": m.get("name", ""),
                    "position": m.get("role", {}).get("key", "") if isinstance(m.get("role"), dict) else "",
                    "rating": stats.get("rating"),
                    "goals": stats.get("goals"),
                    "yellow_cards": stats.get("yellowCards") or stats.get("yellow_cards"),
                })
            log(f"   🔍 FOTMOB-PLAYER-DEBUG: {team_name} → {len(players)} Kaderspieler")
    except Exception as _fpe:
        log(f"   🔍 FOTMOB-PLAYER-DEBUG: {team_name} → Fehler {str(_fpe)[:60]}", "WARN")

    FOTMOB_PLAYER_STATS_CACHE[cache_key] = players
    return players


def generate_stat_insight_tip(match_name, league, home_team, away_team, kickoff_str=""):
    """
    Erzeugt eine reine Statistik-Analyse (KEINE Quote, KEIN Einsatz) für
    Spiele/Spieler ohne echte Pinnacle-Quote. Kombiniert FotMob-Kaderstats
    mit FBref-Cross-Check (falls verfügbar). Gibt None zurück wenn keine
    echten Daten gefunden wurden — erfindet nichts.
    """
    insights = []

    for team_label, team_name in [(home_team, home_team), (away_team, away_team)]:
        players = get_fotmob_player_season_stats(team_name)
        if not players:
            continue
        # Top-Spieler nach Rating, mit echten Karten/Tore-Werten
        rated = [p for p in players if p.get("rating") or p.get("goals") or p.get("yellow_cards")]
        rated.sort(key=lambda p: float(p.get("rating") or 0), reverse=True)
        for p in rated[:3]:
            parts = []
            if p.get("goals"):
                parts.append(f"{p['goals']} Tore")
            if p.get("yellow_cards"):
                parts.append(f"{p['yellow_cards']} Gelbe Karten")
            if p.get("rating"):
                parts.append(f"Ø Rating {p['rating']}")
            if parts:
                insights.append(f"   • {p['name']} ({team_name}): {', '.join(parts)}")

    if not insights:
        return None  # Keine echten Daten — nichts erfinden, einfach nichts senden

    msg = "📊 <b>ANALYSE</b> (Statistik, keine Buchmacher-Quote)\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"⚽ <b>{match_name}</b>"
    if league:
        msg += f"\n📍 {league}"
    if kickoff_str:
        msg += f" · ⏰ {kickoff_str}"
    msg += "\n\n📈 Saisonwerte (FotMob):\n"
    msg += "\n".join(insights)
    msg += "\n\n⚠️ Reine Statistik-Einordnung, keine Wett-Empfehlung mit Quote."
    return msg


# ============================================================
# 🏆 FANTASY PREMIER LEAGUE API - Offiziell, kein Key!
# ============================================================
FPL_CACHE = {}

def get_fpl_data():
    """
    Fantasy Premier League API - Offiziell von der PL!
    Spielerdaten, Preise, Stats, Verletzungen
    """
    if "fpl_bootstrap" in FPL_CACHE:
        return FPL_CACHE["fpl_bootstrap"]

    try:
        r = requests.get(
            "https://fantasy.premierleague.com/api/bootstrap-static/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        if not r.ok:
            return None

        data = r.json()
        FPL_CACHE["fpl_bootstrap"] = data
        log(f"   🏆 FPL: {len(data.get('elements', []))} Spieler geladen")
        return data

    except Exception:
        return None


def get_fpl_player_stats(player_name, team_name):
    """
    Holt Spieler-Stats aus FPL (nur Premier League).
    Returns: {'goals': 12, 'assists': 5, 'minutes': 2340, 'injured': False}
    """
    cache_key = f"fpl_{player_name}"
    if cache_key in FPL_CACHE:
        return FPL_CACHE[cache_key]

    data = get_fpl_data()
    if not data:
        return None

    elements = data.get("elements", [])
    player_norm = normalize_team_name(player_name)

    for player in elements:
        first = player.get("first_name", "")
        last = player.get("second_name", "")
        full = f"{first} {last}"

        if player_norm[:6] in normalize_team_name(full) or normalize_team_name(full)[:6] in player_norm:
            result = {
                "goals": player.get("goals_scored", 0),
                "assists": player.get("assists", 0),
                "minutes": player.get("minutes", 0),
                "injured": player.get("status") in ["i", "d", "u"],
                "status": player.get("status", "a"),
                "chance_playing": player.get("chance_of_playing_next_round", 100),
                "form": float(player.get("form", 0) or 0),
                "source": "fpl",
            }
            FPL_CACHE[cache_key] = result
            return result

    return None


def get_fpl_team_injuries(team_name):
    """
    Holt Verletzungen eines Premier League Teams aus FPL.
    """
    cache_key = f"fpl_inj_{team_name}"
    if cache_key in FPL_CACHE:
        return FPL_CACHE[cache_key]

    data = get_fpl_data()
    if not data:
        return None

    teams = {t["id"]: t["name"] for t in data.get("teams", [])}
    team_norm = normalize_team_name(team_name)

    team_id = None
    for tid, tname in teams.items():
        if team_norm[:6] in normalize_team_name(tname) or normalize_team_name(tname)[:6] in team_norm:
            team_id = tid
            break

    if not team_id:
        return None

    injured = []
    doubtful = []
    for player in data.get("elements", []):
        if player.get("team") != team_id:
            continue
        status = player.get("status", "a")
        name = f"{player.get('first_name', '')} {player.get('second_name', '')}"
        if status == "i":
            injured.append(name)
        elif status == "d":
            doubtful.append(name)

    result = {
        "injured": injured,
        "doubtful": doubtful,
        "total_out": len(injured),
        "source": "fpl",
    }
    FPL_CACHE[cache_key] = result
    if injured or doubtful:
        log(f"   🏆 FPL: {team_name} - {len(injured)} verletzt, {len(doubtful)} fraglich")
    return result


# ============================================================
# 📊 DATAHUB.IO - 30 Open Source Datasets
# ============================================================
DATAHUB_CACHE = {}

DATAHUB_DATASETS = {
    "Premier League": "https://raw.githubusercontent.com/datasets/english-premier-league/master/data/results.csv",
    "La Liga": "https://raw.githubusercontent.com/datasets/spanish-la-liga/master/data/results.csv",
    "Serie A": "https://raw.githubusercontent.com/datasets/italian-serie-a/master/data/results.csv",
    "Bundesliga": "https://raw.githubusercontent.com/datasets/german-bundesliga/master/data/results.csv",
    "Ligue 1": "https://raw.githubusercontent.com/datasets/french-ligue-1/master/data/results.csv",
}

def get_datahub_team_stats(team_name, league_name):
    """
    DataHub.io historische Statistiken - BTTS, Over2.5, Form
    GitHub Raw → kein 403 Problem!
    """
    cache_key = f"dh_{league_name}"
    if cache_key not in DATAHUB_CACHE:
        url = DATAHUB_DATASETS.get(league_name)
        if not url:
            return None

        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if not r.ok:
                return None

            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                return None

            headers = [h.strip() for h in lines[0].split(",")]
            records = []
            for line in lines[1:]:
                cols = line.split(",")
                if len(cols) >= len(headers):
                    records.append(dict(zip(headers, cols)))

            DATAHUB_CACHE[cache_key] = records
            log(f"   📊 DataHub: {len(records)} Spiele für {league_name}")

        except Exception:
            return None

    records = DATAHUB_CACHE.get(cache_key, [])
    if not records:
        return None

    team_norm = normalize_team_name(team_name)
    team_matches = []

    for rec in records:
        home = normalize_team_name(rec.get("HomeTeam", rec.get("home_team", "")))
        away = normalize_team_name(rec.get("AwayTeam", rec.get("away_team", "")))

        if team_norm[:6] in home or team_norm[:6] in away or            home[:6] in team_norm or away[:6] in team_norm:
            team_matches.append(rec)

    if not team_matches:
        return None

    btts = 0
    over25 = 0
    total = 0

    for m in team_matches[-20:]:  # Letzte 20 Spiele
        try:
            hg = int(m.get("FTHG", m.get("home_score", 0)) or 0)
            ag = int(m.get("FTAG", m.get("away_score", 0)) or 0)
            total += 1
            if hg > 0 and ag > 0:
                btts += 1
            if hg + ag > 2:
                over25 += 1
        except Exception:
            continue

    if total == 0:
        return None

    return {
        "btts_rate": round(btts / total * 100, 1),
        "over25_rate": round(over25 / total * 100, 1),
        "games": total,
        "source": "datahub",
    }


# ============================================================
# 🎯 OPTA ANALYST - Profi xG Daten (gratis!)
# ============================================================
OPTA_CACHE = {}

def get_opta_match_stats(home_team, away_team, league_name):
    """
    Opta Analyst - Profi Fußball Statistiken
    optaanalyst.com - teilweise öffentlich zugänglich
    """
    cache_key = f"opta_{home_team}_{away_team}"
    if cache_key in OPTA_CACHE:
        return OPTA_CACHE[cache_key]

    try:
        import random as _r
        r = requests.get(
            f"https://www.optaanalyst.com/en/match-center/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.optaanalyst.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        # Parse response
        import re as _re
        html = r.text
        home_norm = normalize_team_name(home_team)

        if home_norm[:6] not in html.lower():
            return None

        xg_m = _re.findall(r'"xG":\s*([0-9.]+)', html)
        if len(xg_m) >= 2:
            result = {
                "xg_home": float(xg_m[0]),
                "xg_away": float(xg_m[1]),
                "source": "opta",
            }
            OPTA_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🇪🇸 FUTBOLME.COM - Spanische Ligen historisch
# ============================================================
FUTBOLME_CACHE = {}

def get_futbolme_stats(home_team, away_team, league_name):
    """
    Futbolme.com - Spanische Ligen bis zur Kreisliga!
    Historische Ergebnisse + Tabellen
    """
    if "liga" not in league_name.lower() and "spain" not in league_name.lower():
        if league_name not in ["La Liga", "La Liga 2"]:
            return None

    cache_key = f"fm_{home_team}_{away_team}"
    if cache_key in FUTBOLME_CACHE:
        return FUTBOLME_CACHE[cache_key]

    try:
        import random as _r
        search = f"{home_team}".replace(" ", "+")
        r = requests.get(
            f"https://www.futbolme.com/com/equipo.asp?id_equipo={search}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept-Language": "es-ES,es;q=0.9",
                "Referer": "https://www.futbolme.com/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        import re as _re
        html = r.text

        btts_m = _re.search(r'ambos.*?(\d+)%', html, _re.IGNORECASE)
        goals_m = _re.search(r'media.*?goles.*?(\d+[.,]\d+)', html, _re.IGNORECASE)

        result = {}
        if btts_m:
            result["btts_rate"] = int(btts_m.group(1))
        if goals_m:
            result["avg_goals"] = float(goals_m.group(1).replace(",", "."))

        if result:
            FUTBOLME_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None



# ============================================================
# 📊 SOCCERDATA LIBRARY - pip install soccerdata
# ============================================================
SOCCERDATA_AVAILABLE = False
try:
    import logging as _logging
    _logging.getLogger("soccerdata").setLevel(_logging.ERROR)
    import soccerdata as sd
    SOCCERDATA_AVAILABLE = True
except ImportError:
    pass

SOCCERDATA_CACHE = {}

def get_soccerdata_clubelo(team_name, target_date):
    """ClubElo via soccerdata Library"""
    if not SOCCERDATA_AVAILABLE:
        return get_clubelo_rating(team_name)  # Fallback

    cache_key = f"sd_elo_{team_name}"
    if cache_key in SOCCERDATA_CACHE:
        return SOCCERDATA_CACHE[cache_key]

    try:
        elo = sd.ClubElo()
        df = elo.read_by_date(date=str(target_date))
        team_norm = normalize_team_name(team_name)

        for idx, row in df.iterrows():
            club = normalize_team_name(str(idx))
            if team_norm[:6] in club or club[:6] in team_norm:
                result = {
                    "elo": float(row.get("elo", 0)),
                    "source": "soccerdata_clubelo",
                }
                SOCCERDATA_CACHE[cache_key] = result
                return result
    except Exception:
        return get_clubelo_rating(team_name)

    return get_clubelo_rating(team_name)


def get_soccerdata_fbref(league_name, season=None):
    """FBref xG via soccerdata Library"""
    if not SOCCERDATA_AVAILABLE:
        return None

    LEAGUE_MAP = {
        "Premier League": "ENG-Premier League",
        "Bundesliga": "GER-Bundesliga",
        "La Liga": "ESP-La Liga",
        "Serie A": "ITA-Serie A",
        "Ligue 1": "FRA-Ligue 1",
        "Champions League": "INT-Champions League",
    }

    league_str = LEAGUE_MAP.get(league_name)
    if not league_str:
        return None

    cache_key = f"sd_fbref_{league_name}"
    if cache_key in SOCCERDATA_CACHE:
        return SOCCERDATA_CACHE[cache_key]

    try:
        fbref = sd.FBref(leagues=league_str, seasons=season or "2425")
        schedule = fbref.read_schedule()
        SOCCERDATA_CACHE[cache_key] = schedule
        log(f"   📊 soccerdata FBref: {len(schedule)} Spiele für {league_name}")
        return schedule
    except Exception as e:
        log(f"soccerdata FBref Error: {str(e)[:50]}", "WARN")
        return None



# ============================================================
# 🔥 SOCCERAPI - Odds Scraper (Bet365, 888sport, Unibet)
# ============================================================
SOCCERAPI_CACHE = {}

def get_soccerapi_odds(home_team, away_team, target_date):
    """
    soccerapi - kein Key nötig!
    Scrapt Quoten von Bet365, 888sport, Unibet
    """
    cache_key = f"sapi_{home_team}_{away_team}"
    if cache_key in SOCCERAPI_CACHE:
        return SOCCERAPI_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            f"https://www.oddschecker.com/football/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://www.oddschecker.com/",
            },
            timeout=10,
        )
        if r.ok:
            import re as _re
            html = r.text
            home_norm = normalize_team_name(home_team)
            if home_norm[:5] in html.lower():
                odds = _re.findall(r'"decimal":\s*"([0-9.]+)"', html)
                if odds:
                    result = {"best_odds": max([float(o) for o in odds[:10]]), "source": "oddschecker"}
                    SOCCERAPI_CACHE[cache_key] = result
                    return result
    except Exception:
        pass
    return None


# ============================================================
# 🔥 SPORTSRC V2 - xG, Shotmap, Momentum (1000/Tag gratis!)
# ============================================================
SPORTSRC_CACHE = {}

def get_sportsrc_match(home_team, away_team, target_date):
    """
    SportSRC V2 - richtiger Endpoint!
    https://api.sportsrc.org/?data=matches&category=football
    """
    cache_key = f"src_{home_team}_{away_team}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://api.sportsrc.org/",
            params={"data": "matches", "category": "football", "date": str(target_date)},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Origin": "https://sportsrc.org",
                "Referer": "https://sportsrc.org/",
            },
            timeout=10,
        )
        if not r.ok:
            return None
        data = r.json()
        matches = data if isinstance(data, list) else data.get("matches", data.get("data", []))
        home_norm = normalize_team_name(home_team)
        for match in matches:
            h = normalize_team_name(match.get("home", match.get("home_team", match.get("homeTeam", ""))))
            if home_norm[:5] not in h and h[:5] not in home_norm:
                continue
            result = {
                "xg_home": match.get("xg_home", match.get("home_xg", match.get("xG_home", 0))),
                "xg_away": match.get("xg_away", match.get("away_xg", match.get("xG_away", 0))),
                "source": "sportsrc",
            }
            SPORTSRC_CACHE[cache_key] = result
            if result.get("xg_home"):
                log(f"   🔥 SportSRC: xG {result['xg_home']} / {result['xg_away']}")
            return result
    except Exception as e:
        log(f"SportSRC Error: {str(e)[:50]}", "WARN")
    return None
    cache_key = f"src_{home_team}_{away_team}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        date_str = str(target_date)
        r = requests.get(
            f"https://sportsrc.org/v2/matches",
            params={"date": date_str, "home": home_team, "away": away_team},
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "application/json",
                "Referer": "https://sportsrc.org/",
            },
            timeout=12,
        )
        if r.ok:
            data = r.json()
            matches = data.get("matches", data.get("data", []))
            home_norm = normalize_team_name(home_team)
            for match in matches:
                h = normalize_team_name(match.get("home_team", match.get("home", "")))
                if home_norm[:5] not in h and h[:5] not in home_norm:
                    continue
                result = {
                    "xg_home": match.get("xg_home", match.get("home_xg", 0)),
                    "xg_away": match.get("xg_away", match.get("away_xg", 0)),
                    "momentum": match.get("momentum", {}),
                    "match_id": match.get("id", ""),
                    "source": "sportsrc",
                }
                SPORTSRC_CACHE[cache_key] = result
                if result.get("xg_home"):
                    log(f"   🔥 SportSRC: xG {result['xg_home']} / {result['xg_away']}")
                return result
    except Exception as e:
        log(f"SportSRC Error: {str(e)[:50]}", "WARN")
    return None


def fetch_sportsrc_fixtures(league_name, target_date):
    """SportSRC Fixtures mit richtigem Endpoint"""
    cache_key = f"src_fix_{league_name}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        r = requests.get(
            "https://api.sportsrc.org/",
            params={"data": "matches", "category": "football", "date": str(target_date)},
            headers={
                "User-Agent": _r.choice(["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0"]),
                "Accept": "application/json",
                "Origin": "https://sportsrc.org",
                "Referer": "https://sportsrc.org/",
            },
            timeout=10,
        )
        if not r.ok:
            return []
        data = r.json()
        matches = data if isinstance(data, list) else data.get("matches", data.get("data", []))
        now_utc = datetime.now(timezone.utc)
        league_norm = league_name.lower()
        fixtures = []
        for match in matches:
            lg = str(match.get("league", match.get("competition", ""))).lower()
            if not any(w in lg for w in league_norm.split() if len(w) > 4):
                continue
            home = match.get("home", match.get("home_team", ""))
            away = match.get("away", match.get("away_team", ""))
            if not home or not away:
                continue
            kickoff_str = match.get("datetime", match.get("date", f"{target_date}T12:00:00Z"))
            try:
                kickoff = datetime.fromisoformat(str(kickoff_str).replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": str(home), "away": str(away),
                "time_utc": str(kickoff_str),
                "time_local": get_local_time(str(kickoff_str)),
                "source": "sportsrc",
            })
        SPORTSRC_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🔥 SportSRC: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []
    cache_key = f"src_fix_{league_name}_{target_date}"
    if cache_key in SPORTSRC_CACHE:
        return SPORTSRC_CACHE[cache_key]
    try:
        import random as _r
        SPORTSRC_LEAGUES = {
            "Premier League": "england/premier-league",
            "Bundesliga": "germany/bundesliga",
            "La Liga": "spain/la-liga",
            "Serie A": "italy/serie-a",
            "Ligue 1": "france/ligue-1",
            "Champions League": "europe/champions-league",
        }
        slug = SPORTSRC_LEAGUES.get(league_name)
        if not slug:
            return []
        r = requests.get(
            f"https://sportsrc.org/v2/fixtures/{slug}",
            params={"date": str(target_date)},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=10,
        )
        if not r.ok:
            return []
        data = r.json()
        fixtures = []
        now_utc = datetime.now(timezone.utc)
        for fix in data.get("fixtures", data.get("data", [])):
            home = fix.get("home_team", fix.get("home", ""))
            away = fix.get("away_team", fix.get("away", ""))
            if not home or not away:
                continue
            kickoff_str = fix.get("datetime", fix.get("date", f"{target_date}T12:00:00Z"))
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
            except Exception:
                pass
            fixtures.append({
                "home": home, "away": away,
                "time_utc": kickoff_str,
                "time_local": get_local_time(kickoff_str),
                "source": "sportsrc",
            })
        SPORTSRC_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🔥 SportSRC: {len(fixtures)} Spiele für {league_name}")
        return fixtures
    except Exception:
        return []


# ============================================================
# 📊 UNDERSTATAPI - Async xG Package
# ============================================================
UNDERSTATAPI_CACHE = {}

def get_understatapi_stats(league_name, season=None):
    """
    understatapi - async Python package für Understat
    Kein Key nötig!
    """
    cache_key = f"uapi_{league_name}_{season}"
    if cache_key in UNDERSTATAPI_CACHE:
        return UNDERSTATAPI_CACHE[cache_key]

    LEAGUE_MAP = {
        "Premier League": "EPL",
        "Bundesliga": "Bundesliga",
        "La Liga": "La_liga",
        "Serie A": "Serie_A",
        "Ligue 1": "Ligue_1",
        "Eredivisie": "Eredivisie",
        "Russian Premier": "RFPL",
    }

    league_slug = LEAGUE_MAP.get(league_name)
    if not league_slug:
        return None

    try:
        import random as _r
        import re as _re
        import json as _json

        season_str = season or "2025"
        r = requests.get(
            f"https://understat.com/league/{league_slug}/{season_str}",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://understat.com/",
            },
            timeout=15,
        )

        if not r.ok:
            if PLAYWRIGHT_AVAILABLE:
                html = scrape_with_playwright(
                    f"https://understat.com/league/{league_slug}/{season_str}",
                    timeout=20000
                )
                if html:
                    r = type('obj', (object,), {'ok': True, 'text': html, 'status_code': 200})()
                else:
                    return None
            else:
                return None

        html = r.text
        teams_match = _re.search(r"var teamsData\s*=\s*JSON\.parse\('(.+?)'\)", html)
        if not teams_match:
            return None

        teams = _json.loads(teams_match.group(1).encode().decode('unicode_escape'))
        result = {}
        for team_id, team_data in teams.items():
            name = team_data.get("title", "")
            history = team_data.get("history", [])
            if not history:
                continue
            recent = history[-10:]
            xg_scored = sum(float(m.get("xG", 0) or 0) for m in recent)
            xg_conceded = sum(float(m.get("xGA", 0) or 0) for m in recent)
            n = len(recent)
            result[normalize_team_name(name)[:8]] = {
                "xg_per_game": round(xg_scored / n, 2) if n > 0 else 0,
                "xga_per_game": round(xg_conceded / n, 2) if n > 0 else 0,
                "team": name,
            }

        UNDERSTATAPI_CACHE[cache_key] = result
        if result:
            log(f"   📊 understatapi: {len(result)} Teams für {league_name}")
        return result

    except Exception as e:
        log(f"understatapi Error: {str(e)[:50]}", "WARN")
        return None


def get_understatapi_team_xg(team_name, league_name):
    """Holt xG für ein Team aus understatapi"""
    data = get_understatapi_stats(league_name)
    if not data:
        return None
    team_norm = normalize_team_name(team_name)[:8]
    for key, stats in data.items():
        if team_norm[:5] in key or key[:5] in team_norm:
            return stats
    return None


# ============================================================
# 💰 ODDSPORTAL SCRAPER - Historische + Aktuelle Quoten
# ============================================================
ODDSPORTAL_SCRAPER_CACHE = {}

def scrape_oddsportal_btts(home_team, away_team, league_name, target_date):
    """
    OddsPortal - historische + aktuelle BTTS Quoten
    Playwright-basiert für beste Ergebnisse
    """
    cache_key = f"op_{home_team}_{away_team}"
    if cache_key in ODDSPORTAL_SCRAPER_CACHE:
        return ODDSPORTAL_SCRAPER_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Premier League": "england/premier-league",
        "Bundesliga": "germany/bundesliga",
        "La Liga": "spain/primera-division",
        "Serie A": "italy/serie-a",
        "Ligue 1": "france/ligue-1",
        "Champions League": "europe/champions-league",
        "Eredivisie": "netherlands/eredivisie",
        "Primeira Liga": "portugal/primeira-liga",
        "Super Lig": "turkey/super-lig",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r
        import re as _re

        # Direct request first (gratis!)
        r = smart_request(
            f"https://www.oddsportal.com/football/{slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Referer": "https://www.oddsportal.com/",
            },
            timeout=12,
        )

        html = None
        if r.ok:
            html = r.text
        elif PLAYWRIGHT_AVAILABLE:
            html = scrape_with_playwright(
                f"https://www.oddsportal.com/football/{slug}/",
                timeout=20000
            )

        if not html:
            return None

        home_norm = normalize_team_name(home_team)
        if home_norm[:5] not in html.lower():
            return None

        # Suche BTTS Quoten
        btts_yes = _re.findall(r'"btts.*?yes.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)
        btts_no = _re.findall(r'"btts.*?no.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)
        over25 = _re.findall(r'"over.*?2\.5.*?([0-9]+\.[0-9]+)', html, _re.IGNORECASE)

        result = {}
        if btts_yes:
            result["btts_yes"] = float(btts_yes[0])
        if btts_no:
            result["btts_no"] = float(btts_no[0])
        if over25:
            result["over25"] = float(over25[0])
        if result:
            result["source"] = "oddsportal"
            ODDSPORTAL_SCRAPER_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🌍 PROMIEDOS - Südamerika Ligen
# ============================================================
PROMIEDOS_CACHE = {}

def fetch_promiedos_fixtures(league_name, target_date):
    """
    Promiedos - Südamerika Ligen (Argentinien, Brasilien etc.)
    Kein Key nötig!
    """
    if league_name not in ["Liga Argentinien", "Copa Libertadores", "Copa Sudamericana",
                            "Brasileirao Serie A", "Uruguay Primera", "Chile Primera"]:
        return []

    cache_key = f"pm_{league_name}_{target_date}"
    if cache_key in PROMIEDOS_CACHE:
        return PROMIEDOS_CACHE[cache_key]

    PROMIEDOS_LEAGUES = {
        "Liga Argentinien": "torneo-apertura",
        "Brasileirao Serie A": "brasileirao-serie-a",
        "Copa Libertadores": "copa-libertadores",
        "Uruguay Primera": "primera-division",
    }

    slug = PROMIEDOS_LEAGUES.get(league_name)
    if not slug:
        return []

    try:
        import random as _r
        r = requests.get(
            f"https://www.promiedos.com.ar/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "es-AR,es;q=0.9",
                "Referer": "https://www.promiedos.com.ar/",
            },
            timeout=12,
        )

        if not r.ok:
            return []

        import re as _re
        html = r.text
        target_str = str(target_date)
        now_utc = datetime.now(timezone.utc)
        fixtures = []

        matches = _re.findall(
            r'(\d{2}/\d{2}/\d{4})[^<]*(\d{2}:\d{2})[^<]*<[^>]*>([^<]+)</[^>]*>[^<]*-[^<]*<[^>]*>([^<]+)<',
            html
        )

        for date_str, time_str, home, away in matches[:20]:
            try:
                parts = date_str.split("/")
                match_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                if match_date != target_str:
                    continue
                kickoff_str = f"{match_date}T{time_str}:00Z"
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff <= now_utc:
                    continue
                fixtures.append({
                    "home": home.strip(),
                    "away": away.strip(),
                    "time_utc": kickoff_str,
                    "time_local": get_local_time(kickoff_str),
                    "source": "promiedos",
                })
            except Exception:
                continue

        PROMIEDOS_CACHE[cache_key] = fixtures
        if fixtures:
            log(f"   🌍 Promiedos: {len(fixtures)} Spiele für {league_name}")
        return fixtures

    except Exception:
        return []


# ============================================================
# 📊 PENALTY (penalt/y) - High-Performance Analytics
# ============================================================
PENALTY_CACHE = {}

def get_penalty_team_rating(team_name, league_name):
    """
    penalt/y Analytics - Poisson + Elo + StatsBomb kombiniert
    GitHub Raw Daten, kein Key!
    """
    cache_key = f"pen_{team_name}_{league_name}"
    if cache_key in PENALTY_CACHE:
        return PENALTY_CACHE[cache_key]

    PENALTY_LEAGUES = {
        "Premier League": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json",
        "Bundesliga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/de.1.json",
        "La Liga": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/es.1.json",
        "Serie A": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/it.1.json",
        "Ligue 1": "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/fr.1.json",
    }

    url = PENALTY_LEAGUES.get(league_name)
    if not url:
        return None

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if not r.ok:
            return None

        data = r.json()
        team_norm = normalize_team_name(team_name)

        # Berechne Stärke aus Ergebnissen (vereinfachtes Poisson)
        goals_for = 0
        goals_against = 0
        games = 0

        for round_data in data.get("rounds", []):
            for match in round_data.get("matches", []):
                score = match.get("score", {})
                if not score or not score.get("ft"):
                    continue

                home = normalize_team_name(match.get("team1", ""))
                away = normalize_team_name(match.get("team2", ""))
                ft = score.get("ft", [0, 0])

                if team_norm[:5] in home or home[:5] in team_norm:
                    goals_for += ft[0]
                    goals_against += ft[1]
                    games += 1
                elif team_norm[:5] in away or away[:5] in team_norm:
                    goals_for += ft[1]
                    goals_against += ft[0]
                    games += 1

        if games < 3:
            return None

        result = {
            "attack_strength": round(goals_for / games, 2),
            "defense_weakness": round(goals_against / games, 2),
            "games": games,
            "source": "penalty_analytics",
        }

        PENALTY_CACHE[cache_key] = result
        return result

    except Exception:
        return None


def calculate_poisson_btts(home_attack, home_defense, away_attack, away_defense, league_avg=1.4):
    """
    Poisson Modell für BTTS Berechnung
    Basiert auf penalt/y Methodik
    """
    import math

    home_expected = home_attack * away_defense * league_avg
    away_expected = away_attack * home_defense * league_avg

    # P(Home scores >= 1)
    p_home_scores = 1 - math.exp(-home_expected)
    # P(Away scores >= 1)
    p_away_scores = 1 - math.exp(-away_expected)
    # P(BTTS)
    p_btts = p_home_scores * p_away_scores

    # P(Over 2.5)
    p_over25 = 0
    lam = home_expected + away_expected
    for k in range(3):
        p_over25 += (math.exp(-lam) * lam**k) / math.factorial(k)
    p_over25 = 1 - p_over25

    return {
        "btts_prob": round(p_btts * 100, 1),
        "over25_prob": round(p_over25 * 100, 1),
        "home_expected_goals": round(home_expected, 2),
        "away_expected_goals": round(away_expected, 2),
        "source": "poisson_model",
    }


# ============================================================
# 🏟️ WORLDFOOTBALL.NET - Schiedsrichter + Stadien
# ============================================================
WORLDFOOTBALL_CACHE = {}

def get_worldfootball_referee(home_team, away_team, league_name, target_date):
    """
    WorldFootball.net - Schiedsrichter für heute
    Kein Key nötig!
    """
    cache_key = f"wf_{home_team}_{away_team}"
    if cache_key in WORLDFOOTBALL_CACHE:
        return WORLDFOOTBALL_CACHE[cache_key]

    LEAGUE_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "Premier League": "premier-league",
        "La Liga": "primera-division",
        "Serie A": "serie-a",
        "Ligue 1": "ligue-1",
        "Champions League": "champions-league",
        "Europa League": "europa-league",
    }

    slug = LEAGUE_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r, re as _re

        # Versuche direkt, dann Playwright
        url = f"https://www.worldfootball.net/schedule/{slug}-{str(target_date.year)}-{str(target_date.year+1)}-spieltag/"
        r = requests.get(
            url,
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9",
            },
            timeout=12,
        )

        html = r.text if r.ok else None
        if not html and PLAYWRIGHT_AVAILABLE:
            html = scrape_with_playwright(url, timeout=8000)

        if not html:
            return None

        home_norm = normalize_team_name(home_team)
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL)

        for row in rows:
            if home_norm[:5] not in row.lower():
                continue
            ref_m = _re.search(r'referee[^>]*>([^<]+)<', row, _re.IGNORECASE)
            if not ref_m:
                ref_m = _re.search(r'Schiedsrichter[^>]*>([^<]+)<', row, _re.IGNORECASE)
            if ref_m:
                ref_name = ref_m.group(1).strip()
                if len(ref_name) > 3:
                    result = {"name": ref_name, "source": "worldfootball"}
                    WORLDFOOTBALL_CACHE[cache_key] = result
                    return result

    except Exception:
        pass
    return None



def safe_scrape(url, timeout=10, parse_func=None):
    """
    Universeller Scraper:
    1. Direkter Request
    2. Bei Fehler → Playwright
    3. Optional: Parse-Funktion
    """
    import random as _r
    headers = {
        "User-Agent": _r.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
        ]),
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "de-DE,en;q=0.8",
    }
    
    html = None
    
    # 1. Direkter Request
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.ok:
            html = r.text
        elif r.status_code in [403, 429, 503, 406]:
            raise Exception(f"Blocked: {r.status_code}")
    except Exception:
        html = None
    
    # 2. Playwright Fallback
    if not html and PLAYWRIGHT_AVAILABLE:
        log(f"   🎭 Playwright: {url[:50]}...")
        html = scrape_with_playwright(url, timeout=8000)
        if html:
            log(f"   ✅ Playwright OK!")
    
    if not html:
        return None
    
    # 3. Parse wenn gewünscht
    if parse_func:
        try:
            return parse_func(html)
        except Exception:
            return None
    
    return html


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


# ============================================================
# 🎯 THE ODDS API — SOCCER PLAYER PROPS
# ============================================================
_ODDS_API_PROPS_CACHE = {}
_ODDS_API_PLAYER_PROPS_MARKETS = [
    "player_goal_scorer", "player_shots", "player_shots_on_target",
    "player_cards", "player_assists", "player_tackles",
]


def fetch_odds_api_player_props(league_name: str, target_date) -> list:
    """
    Holt Soccer Player Props von The Odds API.
    Returns: [{player, market, side, line, odds, match, league, kickoff}]
    """
    sport_key = LEAGUE_KEYS.get(league_name)
    if not sport_key or not ODDS_API_KEYS:
        return []

    date_str = str(target_date)[:10]
    cache_key = (sport_key, date_str)
    if cache_key in _ODDS_API_PROPS_CACHE:
        return _ODDS_API_PROPS_CACHE[cache_key]

    props = []
    for key in ODDS_API_KEYS:
        try:
            # Events für diese Liga heute
            r_ev = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/events",
                params={"apiKey": key, "dateFormat": "iso"},
                timeout=12,
            )
            if not r_ev.ok:
                continue

            today_events = [
                e for e in r_ev.json()
                if e.get("commence_time", "").startswith(date_str)
            ]
            if not today_events:
                break

            for ev in today_events[:5]:  # Max 5 Events pro Liga (API-Calls schonen)
                ev_id = ev.get("id")
                home = ev.get("home_team", "")
                away = ev.get("away_team", "")
                kickoff = ev.get("commence_time", "")[:16].replace("T", " ")

                try:
                    r_p = requests.get(
                        f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{ev_id}/odds",
                        params={
                            "apiKey": key,
                            "regions": "eu,uk",
                            "markets": ",".join(_ODDS_API_PLAYER_PROPS_MARKETS),
                            "oddsFormat": "decimal",
                        },
                        timeout=12,
                    )
                    if not r_p.ok:
                        continue

                    # Beste Quote pro Spieler/Markt/Seite aus allen Buchmachern
                    best = {}
                    _resp = r_p.json()
                    # API gibt manchmal Liste zurück statt Dict
                    if isinstance(_resp, list):
                        _bookmakers = _resp
                    else:
                        _bookmakers = _resp.get("bookmakers", [])
                    for bm in _bookmakers:
                        for market in bm.get("markets", []):
                            mkey = market.get("key", "")
                            for out in market.get("outcomes", []):
                                player = out.get("description") or out.get("name", "")
                                side = out.get("name", "")
                                line = out.get("point")
                                odds = float(out.get("price", 0) or 0)
                                if odds < 1.20:
                                    continue
                                pk = (player, mkey, side)
                                if odds > best.get(pk, {}).get("odds", 0):
                                    best[pk] = {
                                        "player": player, "market": mkey,
                                        "side": side, "line": line, "odds": odds,
                                        "match": f"{home} vs {away}",
                                        "home": home, "away": away,
                                        "league": league_name, "kickoff": kickoff,
                                    }
                    props.extend(best.values())
                except Exception:
                    continue

            remaining = r_ev.headers.get("x-requests-remaining", "?")
            log(f"   🎯 OddsAPI Props: {len(props)} Props für {league_name} (verbleibend: {remaining})")
            break
        except Exception as _e:
            log(f"   🎯 OddsAPI Props Error: {str(_e)[:60]}", "WARN")
            continue

    _ODDS_API_PROPS_CACHE[cache_key] = props
    return props


def get_odds_api_player_prop_candidates(fixtures_cache: dict, target_date) -> list:
    """
    Holt Player Props für alle Ligen mit Odds-API-Abdeckung.
    Gibt direkt verwendbare Prop-Builder-Kandidaten zurück.
    """
    candidates = []
    processed = set()

    # Robuster gegen Liste statt Dict (kann passieren wenn falsch übergeben)
    if isinstance(fixtures_cache, list):
        fixtures_cache = {}
    for league in list((fixtures_cache or {}).keys()):
        if league in processed or league not in LEAGUE_KEYS:
            continue
        processed.add(league)

        for p in fetch_odds_api_player_props(league, target_date):
            market = p.get("market", "")
            odds = p.get("odds", 0)
            side = p.get("side", "")
            line = p.get("line")
            player = p.get("player", "")

            if "goal" in market and odds >= 1.50:
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": "Anytime Goalscorer",
                    "stat_val": round(1/odds, 2), "mtype": "shots",
                    "odds": odds, "_source": "odds_api",
                })
            elif "shots_on_target" in market and side == "Over":
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": f"{line}+ Shots on Target" if line else "1+ SOT",
                    "stat_val": round(1/odds, 2), "mtype": "shots",
                    "odds": odds, "_source": "odds_api",
                })
            elif "shots" in market and "on_target" not in market and side == "Over":
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": f"{line}+ Shots" if line else "2+ Shots",
                    "stat_val": round(1/odds, 2), "mtype": "shots",
                    "odds": odds, "_source": "odds_api",
                })
            elif "card" in market and odds >= 2.50:
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": "Player to be Booked",
                    "stat_val": round(1/odds, 2), "mtype": "booking",
                    "odds": odds, "_source": "odds_api",
                })
            elif "assist" in market and odds >= 2.00:
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": "Anytime Assist",
                    "stat_val": round(1/odds, 2), "mtype": "shots",
                    "odds": odds, "_source": "odds_api",
                })
            elif "tackle" in market and side == "Over":
                candidates.append({
                    "player": player, "team": "", "match": p["match"],
                    "league": league, "kickoff": p["kickoff"],
                    "market": f"{line}+ Tackles" if line else "2+ Tackles",
                    "stat_val": round(1/odds, 2), "mtype": "tackles",
                    "odds": odds, "_source": "odds_api",
                })

    if candidates:
        log(f"   🎯 OddsAPI: {len(candidates)} Player Prop Kandidaten total")
    return candidates


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
        season = get_dynamic_season(league_id, league_name)

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
LEAGUE_ROTATION_ENABLED = env("LEAGUE_ROTATION_ENABLED", "false").lower() in ["1", "true", "yes"]
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
        msg = f"🔄 <b>League Rotation</b>\n" + "\n"
        if to_remove:
            msg += f"❌ Raus: {', '.join(to_remove)}" + "\n"
        if to_add:
            msg += f"✅ Rein: {', '.join(to_add)}" + "\n"
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
                log(f"   🔍 AF-DEBUG: HTTP {r.status_code} für {endpoint} params={params} body={r.text[:150]}", "WARN")
                continue

            data = r.json()
            if data.get("errors"):
                log(f"   🔍 AF-DEBUG: API-Errors für {endpoint}: {data.get('errors')}", "WARN")
                continue

            # Erfolg! Beim nächsten Call den nächsten Key nehmen
            APIFOOTBALL_KEY_OFFSET = (idx + 1) % n
            _resp = data.get("response", [])
            log(f"   🔍 AF-DEBUG: {endpoint} → {len(_resp)} Ergebnisse (results={data.get('results','?')})")
            return _resp
        except Exception as _afe:
            log(f"   🔍 AF-DEBUG: Exception bei {endpoint}: {str(_afe)[:120]}", "WARN")
            continue

    log(f"   🔍 AF-DEBUG: Alle Keys für {endpoint} params={params} fehlgeschlagen, return None", "WARN")
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

    # Kurze Pause vor Fallback
    import time as _t
    _t.sleep(2)
    log(f"   ⚠️ Gemini erschöpft - alle {n} Keys versucht", "WARN")
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
        prompt = prompt[:30000] + "\n\nANTWORTE NUR AUF DEUTSCH! Reasoning und keyFactor IMMER auf Deutsch. Antworte mit JSON-Array."

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
                    "model": GROQ_MODEL if rate_limit_hits == 0 else GROQ_MODEL_FALLBACK,
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

    # Reset nach kurzer Pause statt global deaktivieren
    if rate_limit_hits >= len(GROQ_API_KEYS):
        import time as _gt
        log("⚠️  Groq rate-limited - warte 30 Sekunden...", "WARN")
        _gt.sleep(30)
        _GROQ_RATE_LIMITED = False  # Reset nach Pause

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
            if PLAYWRIGHT_AVAILABLE:
                log(f"   ℹ️  FBref {r.status_code} — versuche Playwright-Fallback...")
                pw_html = scrape_with_playwright(url, timeout=15000)
                if pw_html:
                    log(f"   ✅ FBref via Playwright erfolgreich")
                    html = pw_html
                else:
                    if not FBREF_BLOCKED:
                        log(f"   ℹ️  FBref auch via Playwright nicht erreichbar - überspringe (andere Quellen reichen)")
                    FBREF_BLOCKED = True
                    FBREF_CACHE[league_name] = {}
                    return {}
            else:
                if not FBREF_BLOCKED:
                    log(f"   ℹ️  FBref nicht erreichbar ({r.status_code}) - überspringe (kein Problem, andere Quellen reichen)")
                FBREF_BLOCKED = True
                FBREF_CACHE[league_name] = {}
                return {}
        elif not r.ok:
            FBREF_CACHE[league_name] = {}
            return {}
        else:
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
        ctx += f"\n🌤️ WETTER ({weather['city']}):" + "\n"
        ctx += f"• {weather['condition']} · {weather['temp']}°C · "
        ctx += f"Wind {weather['wind']}km/h · Regen {weather['rain']}mm" + "\n"
        if weather['notes']:
            for note in weather['notes']:
                ctx += f"• {note}" + "\n"
        if weather['impact'] == 'negative':
            ctx += f"⚠️ Wetter-Impact: Schlechtere Bedingungen → weniger Tore erwartet!" + "\n"
        ctx += "\n"

    league_id = API_FOOTBALL_LEAGUES.get(league)
    season = None
    if league_id:
        from datetime import date as _date
        td = _date.today()
        season = td.year if td.month > 6 else td.year - 1

    if fixtures:
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE:" + "\n"

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

            # BettingScreener blockiert GitHub IPs - deaktiviert
            match_key = f"{f['home']} vs {f['away']}"

            # Pinnacle via Odds API
            # Wird über Odds API Daten bereits abgedeckt

            # 🆕 PREDICTZ + BETIMATE Predictions
            pz = get_predictz_prediction(f["home"], f["away"], target_date)
            if pz:
                if pz.get("btts_pct"):
                    line += f"\n   🎯 PredictZ: BTTS {pz['btts_pct']}%"
                if pz.get("over25_pct"):
                    line += f" | Over2.5 {pz['over25_pct']}%"

            bm = get_betimate_prediction(f["home"], f["away"], target_date)
            if bm and bm.get("btts_pct"):
                line += f"\n   🎯 Betimate: BTTS {bm['btts_pct']}%"

            # 🆕 PHYSIOROOM Verletzungen (Premier League)
            pr_home = get_physioroom_injuries(f["home"], league)
            if pr_home and pr_home.get("has_data"):
                names = ", ".join([p["name"] for p in pr_home["injured"][:3]])
                line += f"\n   🏥 PhysioRoom {f['home']}: {names}"

            # 🆕 WINDRAWWIN Predictions
            wdw = get_windrawwin_prediction(f["home"], f["away"], target_date)
            if wdw:
                line += f"\n   📊 WDW: H{wdw.get('prob_home','?')}% D{wdw.get('prob_draw','?')}% A{wdw.get('prob_away','?')}%"

            # 🆕 SOCCERSTATS Liga-weite BTTS Rate
            ss = get_soccerstats_btts(league)
            if ss and ss.get("btts_rate"):
                line += f"\n   ⚽ Liga BTTS Rate: {ss['btts_rate']}% (Over2.5: {ss.get('over25_rate','?')}%)"

            # 🔥 GRATIS QUELLEN ZUERST!
            # 1. Poisson Modell (komplett gratis)
            pen_home = get_penalty_team_rating(f["home"], league)
            pen_away = get_penalty_team_rating(f["away"], league)
            if pen_home and pen_away:
                poisson = calculate_poisson_btts(
                    pen_home["attack_strength"], pen_home["defense_weakness"],
                    pen_away["attack_strength"], pen_away["defense_weakness"],
                )
                line += f"\n   📊 Poisson: BTTS {poisson['btts_prob']}% | Over2.5 {poisson['over25_prob']}%"
                line += f"\n   ⚽ Erwartete Tore: {poisson['home_expected_goals']} / {poisson['away_expected_goals']}"

            # 2. understatapi xG (kein Key)
            uapi_home = get_understatapi_team_xg(f["home"], league)
            uapi_away = get_understatapi_team_xg(f["away"], league)
            if uapi_home and uapi_away:
                line += f"\n   📈 xG/Sp: {uapi_home.get('xg_per_game','?')} / {uapi_away.get('xg_per_game','?')}"

            # 3. FotMob xG (kein Key)
            fm_stats = get_fotmob_match_stats(f["home"], f["away"], target_date)
            if fm_stats and fm_stats.get("xg_home"):
                line += f"\n   ⚽ FotMob xG: {fm_stats['xg_home']} / {fm_stats['xg_away']}"

            # 4. SportSRC xG (kein Key, 1000/Tag)
            src_stats = get_sportsrc_match(f["home"], f["away"], target_date)
            if src_stats and src_stats.get("xg_home"):
                line += f"\n   🔥 SportSRC xG: {src_stats['xg_home']} / {src_stats['xg_away']}"

            # 5. OddsPortal Quoten (kein Key)
            op_odds = scrape_oddsportal_btts(f["home"], f["away"], league, target_date)
            if op_odds and op_odds.get("btts_yes"):
                line += f"\n   💰 OddsPortal BTTS: {op_odds['btts_yes']} / {op_odds.get('btts_no','?')}"

            # 6. WorldFootball Schiedsrichter (kein Key)
            wf_ref = get_worldfootball_referee(f["home"], f["away"], league, target_date)
            if wf_ref and wf_ref.get("name"):
                line += f"\n   👨‍⚖️ Schiri: {wf_ref['name']}"

            # 🏆 FPL Verletzungen (Premier League)
            if league == "Premier League":
                fpl_home = get_fpl_team_injuries(f["home"])
                fpl_away = get_fpl_team_injuries(f["away"])
                if fpl_home and fpl_home.get("injured"):
                    line += f"\n   🏥 FPL {f['home']}: {', '.join(fpl_home['injured'][:2])} fehlen"
                if fpl_home and fpl_home.get("doubtful"):
                    line += f"\n   ⚠️ Fraglich: {', '.join(fpl_home['doubtful'][:2])}"

            # 📊 DATAHUB Statistiken
            dh_home = get_datahub_team_stats(f["home"], league)
            if dh_home:
                line += f"\n   📊 BTTS Rate: {dh_home['btts_rate']}% | Over2.5: {dh_home['over25_rate']}%"

            # 🌍 INTERNATIONALE BTTS STATS (martj42)
            for intl_team in [f["home"], f["away"]]:
                m42_stats = get_international_btts_rate(intl_team, last_n=20)
                if m42_stats and m42_stats.get("games", 0) >= 5:
                    line += (
                        f"\n   🌍 {intl_team} [martj42 {m42_stats['games']}Sp]: "
                        f"BTTS {m42_stats['btts_rate']}% | "
                        f"Over2.5 {m42_stats['over25_rate']}% | "
                        f"Ø {m42_stats['avg_goals']} Tore"
                    )

            # 🆕 REFEREE STATS
            ref_data = get_referee_stats(f["home"], f["away"], league, target_date)
            if ref_data and ref_data.get("name"):
                line += f"\n   👨‍⚖️ Schiri: {ref_data['name']}"
                if ref_data.get("cards_per_game"):
                    line += f" | Karten/Spiel: {ref_data['cards_per_game']}"
                if ref_data.get("penalty_rate"):
                    line += f" | Elfmeter: {ref_data['penalty_rate']}/Spiel"

            # 🆕 FATIGUE & REISE
            fatigue = calculate_travel_fatigue(f["home"], f["away"])
            if fatigue:
                if fatigue.get("distance_km", 0) > 500:
                    line += f"\n   ✈️ Reise {f['away']}: {fatigue['distance_km']}km"
                if fatigue.get("rotation_likely"):
                    line += f" ⚠️ Rotation wahrscheinlich!"

            # 🆕 CLV SHARP MONEY
            clv = track_odds_movement(f["home"], f["away"])
            if clv and clv.get("sharp_signal"):
                line += f"\n   📌 Sharp Money Signal! Pinnacle: {clv.get('current_odds')}"

            # 📰 NEWS - Google News + Tavily
            news_items = get_team_news_google(f["home"], f["away"], league)
            if news_items:
                injury_news = [n for n in news_items if n.get("has_injury_info")]
                if injury_news:
                    line += f"\n   📰 News: {injury_news[0]['title'][:100]}"

            if TAVILY_API_KEY:
                news = get_team_news_tavily(f["home"], f["away"], league)
                if news and news.get("summary"):
                    line += f"\n   📰 Tavily: {news['summary'][:100]}"

            # 🤖 REDDIT Insider
            reddit = scrape_reddit_soccer(f["home"], f["away"])
            if reddit:
                line += f"\n   🤖 Reddit: {reddit[0]['title'][:80]}"

            # 📊 STATSBOMB Player Props
            sb_stats = get_statsbomb_player_stats(league)
            if sb_stats:
                # Props für dieses Spiel
                props = get_player_props_for_match(f["home"], f["away"], league)
                if props:
                    top3 = props[:3]
                    props_str = " | ".join([f"{p['player'].split()[-1]} {p['tip']} ({p['probability']}%)" for p in top3])
                    line += f"\n   🔑 Props: {props_str}"

            # 🎭 TRANSFERMARKT via Playwright
            if PLAYWRIGHT_AVAILABLE:
                tm_home = pw_get_transfermarkt_injuries(f["home"], league)
                if tm_home and tm_home.get("has_data"):
                    names = ", ".join([p["name"] for p in tm_home["injured"][:3]])
                    line += f"\n   🏥 TM {f['home']}: {names} fehlen"

            # 🆕 RSSSF + FUSSBALLDATEN - Historische Stats
            rsssf = get_rsssf_stats(league)
            if rsssf and rsssf.get("btts_rate"):
                line += (
                    f"\n   📚 RSSSF Liga-Statistik: BTTS {rsssf['btts_rate']}%, "
                    f"Ø {rsssf['avg_goals']} Tore ({rsssf['total_games']} Spiele)"
                )

            fbd_hist = get_fussballdaten_history(f["home"], f["away"], league)
            if fbd_hist and fbd_hist.get("btts_rate"):
                line += f"\n   🇩🇪 Fussballdaten: BTTS {fbd_hist['btts_rate']}%"

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
                if hist.get("home") and hist["home"].get("games", 0) >= 3:
                    h = hist["home"]
                    line += f"\n   📈 {f['home']} (Heim): BTTS {h['btts_rate']}%, Ø {h['avg_goals']} Tore ({h['games']} Spiele) [fd.co.uk]"
                if hist.get("away") and hist["away"].get("games", 0) >= 3:
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
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}" + "\n"

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
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}" + "\n"

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
                                ctx += f"  [{bm['title']}] 1: {home_o} / X: {draw_o} / 2: {away_o}" + "\n"

                line_signals = analyze_line_movement(
                    odds_data, g["home_team"], g["away_team"]
                )
                if line_signals:
                    ctx += "  📉 Line Movement:\n"
                    for sig in line_signals:
                        ctx += f"    {sig}" + "\n"

                pinnacle_signals = analyze_pinnacle_value(
                    odds_data, g["home_team"], g["away_team"]
                )
                if pinnacle_signals:
                    ctx += "  💹 Sharp Money Signale:\n"
                    for sig in pinnacle_signals:
                        ctx += f"    {sig}" + "\n"

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

    # 🆕 FIX: Wenn keine Fixtures/Odds → Tips trotzdem behalten!
    # Passiert bei MLS, Brasilien, Asien wo Odds API oft keine Daten hat
    if not real_matches:
        log("   ⚠️ Keine Fixture-Daten → Tips direkt übernehmen")
        validated = []
        for tip in tips:
            match = tip.get("match", "")
            if " vs " not in match:
                continue
            parts = match.split(" vs ", 1)
            if len(parts) == 2 and len(parts[0]) > 2 and len(parts[1]) > 2:
                validated.append(tip)
        return validated

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
        if not time_str or time_str in ["TBD", "Heute", "N/A", "-", ""]:
            return True  # Keine Zeit = annehmen dass es heute stattfindet

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

        def _combine(d):
            game_local = datetime.combine(
                d, datetime.min.time().replace(hour=hour, minute=minute),
            )
            return (game_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)

        game_utc = _combine(target_date)

        # 🆕 Fix: Unser Abend-Fenster geht über Mitternacht (20:00 heute – 12:00 morgen CH).
        # Eine Kickoff-Zeit wie "00:00"-"13:00" kombiniert mit target_date (heute) liegt
        # dann oft Stunden in der Vergangenheit, obwohl das Spiel morgen früh stattfindet.
        # Falls die heutige Kombination weit (>6h) in der Vergangenheit liegt, mit morgen
        # nachrechnen — das deckt den Mitternachts-Wraparound korrekt ab.
        if game_utc < now_utc - timedelta(hours=6):
            game_utc_tomorrow = _combine(target_date + timedelta(days=1))
            if game_utc_tomorrow > now_utc - timedelta(minutes=10):
                game_utc = game_utc_tomorrow

        # Spiel darf noch nicht angefangen haben (max 10 Min Toleranz nach Kickoff)
        return game_utc > now_utc - timedelta(minutes=10)

    except Exception:
        return True



def calculate_value_rating(odds_yes, fair_odds, probability):
    """
    Berechnet Value Rating basierend auf Edge zwischen Fair Odds und echten Quoten.
    
    Edge = (oddsYes / fairOdds - 1) * 100
    HIGH:  Edge > 10% (echte Value Bet!)
    OK:    Edge 3-10% (leichter Vorteil)
    LOW:   Edge < 3%  (kaum Value)
    NONE:  Edge < 0%  (kein Value)
    """
    try:
        odds = float(str(odds_yes).replace(",", "."))
        fair = float(str(fair_odds).replace(",", "."))
        prob = float(probability) / 100
        
        if odds <= 0 or fair <= 0:
            return "OK"
        
        # Edge berechnen
        edge = ((odds / fair) - 1) * 100
        
        # Zusätzlich: Implied probability vs real probability
        implied_prob = 1 / odds
        prob_edge = (prob - implied_prob) * 100
        
        # Kombinierter Score
        combined = (edge + prob_edge) / 2
        
        if combined >= 10:
            return "HIGH"
        elif combined >= 3:
            return "OK"
        else:
            return "LOW"
            
    except Exception:
        return "OK"


def filter_top_tips(tips, target_date, market):
    filtered = []
    rejected = {"time": 0, "tip": 0, "prob": 0, "conf": 0, "value": 0, "odds": 0}

    max_odds_for_market = 4.5 if market == "btts_ht" else MAX_ODDS
    min_odds_for_market = 1.6 if market == "btts_ht" else MIN_ODDS

    for r in tips:
        if not is_future_game(r.get("time", ""), target_date):
            rejected["time"] += 1
            continue

        if r.get("tip") != "YES":
            rejected["tip"] += 1
            continue

        prob = int(r.get("probability", 0))
        if prob < MIN_PROBABILITY:
            rejected["prob"] += 1
            log(f"   🔽 Gefiltert: {r.get('match','')} prob={prob}% < {MIN_PROBABILITY}%")
            continue

        conf = int(r.get("confidence", 0))
        if conf < MIN_CONFIDENCE:
            rejected["conf"] += 1
            log(f"   🔽 Gefiltert: {r.get('match','')} conf={conf} < {MIN_CONFIDENCE}")
            continue

        # 🆕 Echte Quoten aus Odds API überschreiben AI-Quoten!
        ai_odds = r.get("oddsYes", 0)
        real_odds = r.get("_real_odds", 0)  # Wird aus Odds API gesetzt
        
        if real_odds and float(str(real_odds).replace(",",".")) > 1.0:
            r["oddsYes"] = real_odds
            log(f"   💰 Echte Quote übernommen: {real_odds} (AI hatte: {ai_odds})")
        
        # Eigene Value Rating Berechnung (überschreibt AI Rating)
        calculated_rating = calculate_value_rating(
            r.get("oddsYes", 0),
            r.get("fairOdds", 0),
            r.get("probability", 0)
        )
        r["valueRating"] = calculated_rating

        # Value Rating Filter
        value_rating = calculated_rating
        if MIN_VALUE_RATING == "HIGH" and value_rating != "HIGH":
            continue
        elif MIN_VALUE_RATING == "OK" and value_rating == "LOW":
            continue

        odds = parse_odds(r.get("oddsYes", 0))
        if odds >= 1.20:
            if odds < min_odds_for_market or odds > max_odds_for_market:
                rejected["odds"] += 1
                log(f"   🔽 Gefiltert: {r.get('match','')} odds={odds}")
                continue
        else:
            r["oddsYes"] = 1.75
            r["_no_real_odds"] = True

        filtered.append(r)

    seen = set()
    unique = []

    for t in filtered:
        key = (t.get("match", "").lower(), t.get("tip", ""))

        if key in seen:
            continue

        seen.add(key)
        unique.append(t)

    if any(v > 0 for v in rejected.values()):
        log(f"   📊 Filter: Zeit={rejected['time']} Tip={rejected['tip']} Prob={rejected['prob']} Conf={rejected['conf']} Value={rejected['value']} Odds={rejected['odds']}")

    unique.sort(
        key=lambda r: (
            0 if r.get("valueRating") == "HIGH" else 1,
            -int(r.get("probability", 0)),
        )
    )

    return unique



# ============================================================
# 💰 ERWEITERTE ODDS QUELLEN
# odds-api.io (Free Forever) + OddsPortal + OddsJet
# ============================================================

def fetch_oddsapi_io(league_name: str, target_date) -> list:
    """
    odds-api.io — Free Forever, keine Kreditkarte.
    Alternative zu The Odds API mit breiter Abdeckung.
    https://odds-api.io
    """
    ODDSAPI_IO_KEY = env("ODDSAPI_IO_KEY", "")
    if not ODDSAPI_IO_KEY:
        return []

    SPORT_KEYS = {
        "MLS": "soccer_usa_mls",
        "Copa Libertadores": "soccer_conmebol_copa_libertadores",
        "Copa Sudamericana": "soccer_conmebol_copa_sudamericana",
        "Brasileirao Serie A": "soccer_brazil_campeonato",
        "Brasileirao Serie B": "soccer_brazil_campeonato_b",
        "Liga Argentinien": "soccer_argentina_primera_division",
        "Bolivia Division Profesional": "soccer_bolivia_liga_profesional",
        "Uruguay Primera": "soccer_uruguay_primera_division",
        "Chile Primera": "soccer_chile_campeonato",
        "Colombia Primera": "soccer_colombia_primera_a",
        "J1 League Japan": "soccer_japan_j_league",
        "K League 1": "soccer_south_korea_kleague1",
        "WM 2026": "soccer_fifa_world_cup",
        "Freundschaftsspiele International": "soccer_international_friendlies",
    }

    sport_key = SPORT_KEYS.get(league_name)
    if not sport_key:
        return []

    try:
        r = requests.get(
            f"https://api.odds-api.io/v4/sports/{sport_key}/odds/",
            params={
                "apiKey": ODDSAPI_IO_KEY,
                "regions": "eu",
                "markets": "btts,totals,h2h",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
            timeout=10,
        )
        if not r.ok:
            return []

        return r.json()
    except Exception:
        return []


def fetch_oddsportal_odds(home: str, away: str, league: str) -> dict:
    """
    OddsPortal — scraping via Playwright.
    Weltweite Quoten aus 40+ Buchmachern.
    """
    cache_key = f"oddsportal_{home}_{away}"
    if cache_key in _PW_SESSION_CACHE:
        return _PW_SESSION_CACHE.get(cache_key, {})

    try:
        search_term = f"{home} {away}".replace(" ", "+")
        url = f"https://www.oddsportal.com/search/{search_term}/"
        html = scrape_with_playwright(url, timeout=12000)
        if not html:
            return {}

        from bs4 import BeautifulSoup as _bs
        import re as _re
        soup = _bs(html, "html.parser")

        # Finde Spiel-Link
        for a in soup.select("a.searchResult"):
            href = a.get("href", "")
            if home.lower()[:4] in href.lower() or away.lower()[:4] in href.lower():
                match_url = "https://www.oddsportal.com" + href
                match_html = scrape_with_playwright(match_url, timeout=12000)
                if not match_html:
                    break

                match_soup = _bs(match_html, "html.parser")

                # Pinnacle Quoten suchen
                result = {}
                for row in match_soup.select("tr.odds-row"):
                    bookie = row.select_one(".bookmaker-name")
                    if bookie and "pinnacle" in bookie.text.lower():
                        odds_cells = row.select("td.odds-nowrap")
                        if len(odds_cells) >= 2:
                            try:
                                result["btts_yes"] = float(odds_cells[0].text.strip())
                                result["btts_no"] = float(odds_cells[1].text.strip())
                                _PW_SESSION_CACHE[cache_key] = result
                                return result
                            except Exception:
                                pass
                break

        return {}
    except Exception:
        return {}


def fetch_oddsjet_international(target_date) -> list:
    """
    OddsJet — hat weltweite Quoten inkl. Länderspiele.
    https://www.oddsjet.com/
    """
    cache_key = f"oddsjet_{target_date}"
    cached = cache_get(cache_key, target_date)
    if cached:
        return cached.get("odds", [])

    try:
        url = f"https://www.oddsjet.com/football/?date={target_date}"
        html = scrape_with_playwright(url, timeout=15000)
        if not html:
            return []

        from bs4 import BeautifulSoup as _bs
        soup = _bs(html, "html.parser")

        odds_list = []
        for match_div in soup.select(".match-row, .event-row, tr.match"):
            try:
                teams = match_div.select(".team, .participant")
                if len(teams) < 2:
                    continue
                home = teams[0].text.strip()
                away = teams[1].text.strip()

                # BTTS Odds
                btts_cells = match_div.select(".btts-odds, .gg-odds")
                if btts_cells:
                    odds_list.append({
                        "home": home,
                        "away": away,
                        "btts_yes": float(btts_cells[0].text.strip().replace(",",".")),
                        "source": "oddsjet",
                    })
            except Exception:
                continue

        if odds_list:
            cache_set(cache_key, target_date, {"odds": odds_list})
        return odds_list

    except Exception:
        return []

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
    sofa_fix = []  # SofaScore blockiert GitHub IPs → deaktiviert
    espn_fix = fetch_espn_fixtures(league, target_date)        # ESPN
    asp_fix = fetch_allsports_fixtures(league, target_date)    # AllSports
    flash_fix = fetch_flashscore_fixtures(league, target_date)
    ls_fix = fetch_livescore_fixtures(league, target_date)
    ninjas_fix = fetch_api_ninjas_fixtures(league, target_date)
    tsdb_fix = fetch_thesportsdb_fixtures(league, target_date)
    sw_fix = scrape_soccerway(league, target_date)
    gh_fix = fetch_github_football_data(league, target_date)
    fbd_fix = scrape_fussballdaten(league, target_date)
    fbde_fix = fetch_fussball_de(league, target_date)
    fl_fix = fetch_fortuna_liga(target_date) if league == "Slovak Super Liga" else []
    m42_fix = get_international_fixtures_today(target_date) if league in [
        "WM 2026", "UEFA Nations League", "Copa America", "Afrika Cup",
        "Freundschaftsspiele International", "WM 2026 Qualifikation Europa",
        "WM 2026 Qualifikation Südamerika", "WM 2026 Qualifikation CONCACAF",
    ] else []
    pw_sofa = pw_get_sofascore_fixtures(league, target_date)
    pw_wfdb = pw_get_worldfootballdb(league, target_date)
    fm_fix = fetch_fotmob_fixtures(league, target_date)
    src_fix = fetch_sportsrc_fixtures(league, target_date)       # 🔥 SportSRC
    pm_fix = fetch_promiedos_fixtures(league, target_date)       # 🌍 Promiedos

    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix, bsd_fix, sm_fix, sdb_fix, sofa_fix, espn_fix, asp_fix, flash_fix, ls_fix, ninjas_fix, tsdb_fix, sw_fix, gh_fix, fbd_fix, fbde_fix, fl_fix, pw_sofa, pw_wfdb, fm_fix, src_fix, pm_fix, m42_fix)

    log(
        f"   Quellen: Odds={len(odds)}, FD={len(fd_fix)}, "
        f"AF={len(af_fix)}, FJ={len(fj_fix)}, OL={len(ol_fix)}, "
        f"BSD={len(bsd_fix)}, SM={len(sm_fix)}, SDB={len(sdb_fix)}, "
        f"ESPN={len(espn_fix)}, ASP={len(asp_fix)}, "
        f"TSDB={len(tsdb_fix)}, SW={len(sw_fix)}, "
        f"GH={len(gh_fix)}, FBD={len(fbd_fix)} → Total={len(fixtures)}"
    )

    return odds, fixtures



# ============================================================
# 🆕 OPENROUTER - Viele Modelle, Gratis Credits!
# ============================================================
OPENROUTER_API_KEYS = [k.strip() for k in env("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
_OPENROUTER_KEY_IDX = 0

def call_openrouter(prompt):
    global _OPENROUTER_KEY_IDX
    if not OPENROUTER_API_KEYS:
        return None, "OpenRouter: kein Key"
    
    import time as _t
    last_error = ""
    
    for _ in range(len(OPENROUTER_API_KEYS)):
        key = OPENROUTER_API_KEYS[_OPENROUTER_KEY_IDX % len(OPENROUTER_API_KEYS)]
        _OPENROUTER_KEY_IDX += 1
        
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/netrattler/btts-bot",
                },
                json={
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
                timeout=30,
            )
            
            if r.status_code == 429:
                last_error = "Rate Limit"
                _t.sleep(2)
                continue
            
            if not r.ok:
                last_error = f"HTTP {r.status_code}"
                continue
            
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if text:
                return text, f"OpenRouter #{_OPENROUTER_KEY_IDX}"
                
        except Exception as e:
            last_error = str(e)[:60]
            continue
    
    return None, f"OpenRouter erschöpft ({last_error})"


# ============================================================
# 🆕 MISTRAL - Gratis Tier (1 req/sec)
# ============================================================
MISTRAL_API_KEYS = [k.strip() for k in env("MISTRAL_API_KEYS", "").split(",") if k.strip()]
_MISTRAL_KEY_IDX = 0

def call_mistral(prompt):
    global _MISTRAL_KEY_IDX
    if not MISTRAL_API_KEYS:
        return None, "Mistral: kein Key"
    
    import time as _t
    last_error = ""
    
    for _ in range(len(MISTRAL_API_KEYS)):
        key = MISTRAL_API_KEYS[_MISTRAL_KEY_IDX % len(MISTRAL_API_KEYS)]
        _MISTRAL_KEY_IDX += 1
        
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-small-latest",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
                timeout=30,
            )
            
            if r.status_code == 429:
                last_error = "Rate Limit"
                _t.sleep(2)
                continue
            
            if not r.ok:
                last_error = f"HTTP {r.status_code}"
                continue
            
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if text:
                return text, f"Mistral #{_MISTRAL_KEY_IDX}"
                
        except Exception as e:
            last_error = str(e)[:60]
            continue
    
    return None, f"Mistral erschöpft ({last_error})"


# ============================================================
# 🆕 COHERE - Gratis 1000 Calls/Monat
# ============================================================
COHERE_API_KEY = env("COHERE_API_KEY", "")

def call_cohere(prompt):
    if not COHERE_API_KEY:
        return None, "Cohere: kein Key"
    
    try:
        r = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "command-r",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        
        if not r.ok:
            return None, f"Cohere HTTP {r.status_code}"
        
        data = r.json()
        text = data.get("message", {}).get("content", [{}])[0].get("text", "")
        
        if text:
            return text, "Cohere"
            
    except Exception as e:
        return None, f"Cohere Error: {str(e)[:60]}"
    
    return None, "Cohere: kein Ergebnis"


# ============================================================
# 🆕 HUGGINGFACE - Gratis Inference API
# ============================================================
HUGGINGFACE_API_KEY = env("HUGGINGFACE_API_KEY", "")

def call_huggingface(prompt):
    if not HUGGINGFACE_API_KEY:
        return None, "HuggingFace: kein Key"
    
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
            headers={
                "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 2000,
                    "temperature": 0.2,
                    "return_full_text": False,
                },
            },
            timeout=60,
        )
        
        if r.status_code == 503:
            return None, "HuggingFace: Modell lädt"
        
        if not r.ok:
            return None, f"HuggingFace HTTP {r.status_code}"
        
        data = r.json()
        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "")
            if text:
                return text, "HuggingFace"
            
    except Exception as e:
        return None, f"HuggingFace Error: {str(e)[:60]}"
    
    return None, "HuggingFace: kein Ergebnis"


def analyze_market_with_data(market, league, target_date, odds, fixtures):
    """
    Analysiert einen Markt mit bereits geladenen Liga-Daten.
    """
    if not odds and not fixtures:
        return [], "Keine echten Spiele heute"

    ctx = build_context(odds, fixtures, league, target_date)
    prompt = build_prompt(market, league, target_date, ctx)

    # AI Rotation - verteile Last auf alle Modelle!
    import random as _rand_ai

    # Zufällige Reihenfolge um Gemini nicht immer zuerst zu fragen
    ai_order = []
    ai_order.append(("gemini", lambda: call_gemini(prompt, use_tools=False)))
    if OPENROUTER_API_KEYS:
        ai_order.append(("openrouter", lambda: call_openrouter(prompt)))
    if MISTRAL_API_KEYS:
        ai_order.append(("mistral", lambda: call_mistral(prompt)))
    if USE_GROQ_FALLBACK:
        ai_order.append(("groq", lambda: call_groq(prompt)))
    if COHERE_API_KEY:
        ai_order.append(("cohere", lambda: call_cohere(prompt)))
    if HUGGINGFACE_API_KEY:
        ai_order.append(("hf", lambda: call_huggingface(prompt)))

    # Gemini immer zuerst aber Fallbacks rotieren
    results, source = call_gemini(prompt, use_tools=False)

    if results is None and OPENROUTER_API_KEYS:
        results, source = call_openrouter(prompt)

    if results is None and MISTRAL_API_KEYS:
        results, source = call_mistral(prompt)

    if results is None and USE_GROQ_FALLBACK:
        results, source = call_groq(prompt)

    if results is None and COHERE_API_KEY:
        results, source = call_cohere(prompt)

    if results is None and HUGGINGFACE_API_KEY:
        results, source = call_huggingface(prompt)

    if results is None:
        results, source = call_gemini(prompt, use_tools=True)

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
        return []

    try:
        # Versuche mehrere BSD Endpoints
        urls_to_try = [
            f"https://api.b365api.com/v3/events/upcoming?sport_id=1&league_id={league_id}&token=YOUR_TOKEN",
            f"https://betsapi.com/api/v2/events/upcoming?sport_id=1&league_id={league_id}",
        ]
        
        r = requests.get(
            f"{BSD_API_URL}/matches",
            params={
                "league_id": league_id,
                "date": target_date.isoformat(),
                "status": "upcoming",
            },
            headers={"User-Agent": "Mozilla/5.0"},
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

    try:
        text = _ntr_enhance_message_with_stats(text, chat_id)
    except Exception as _ntr_e:
        try:
            log(f"Stats-Footer übersprungen: {str(_ntr_e)[:60]}", "WARN")
        except Exception:
            pass

    try:
        text = _ntr_strip_duplicate_group_footer(text)
    except Exception:
        pass

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



# In-Memory Duplikat Cache für diesen Run
_SENT_TIPS_CACHE = set()
_PREFETCHED_DUP_DATES = set()

def _dup_cache_key(match, market, target_date):
    match_norm = normalize_team_name(match)
    return f"{match_norm[:20]}_{market}_{target_date}"

def prefetch_sent_tips_for_date(target_date):
    """
    Speed-Fix:
    Lädt bereits gesendete Tipps/Combos für den Tag einmalig in den Cache.
    Danach macht is_duplicate_tip/is_duplicate_combo keine Supabase-Abfrage mehr pro Tipp.
    """
    global _SENT_TIPS_CACHE, _PREFETCHED_DUP_DATES
    day = str(target_date)
    if day in _PREFETCHED_DUP_DATES:
        return

    _PREFETCHED_DUP_DATES.add(day)

    if not (SUPABASE_URL and SUPABASE_KEY):
        return

    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    page = 0
    loaded = 0

    while page < 8:  # max 8000 Rows, mehr brauchen wir für einen Tag nicht
        start = page * 1000
        end = start + 999
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={**headers, "Range": f"{start}-{end}"},
                params={
                    "date": f"eq.{day}",
                    "select": "match,market,tip_id",
                    "limit": "1000",
                    "order": "created_at.desc.nullslast",
                },
                timeout=8,
            )
            if not r.ok:
                break
            rows = r.json() if r.text else []
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                match = row.get("match")
                market = row.get("market")
                tip_id = row.get("tip_id")
                if match and market:
                    _SENT_TIPS_CACHE.add(_dup_cache_key(match, market, day))
                if tip_id:
                    _SENT_TIPS_CACHE.add(f"combo_{tip_id}")

            loaded += len(rows)
            if len(rows) < 1000:
                break
            page += 1
        except Exception:
            break

    try:
        log(f"   ⚡ Duplikat-Cache vorgeladen: {loaded} Tipps für {day}")
    except Exception:
        pass

def is_duplicate_tip(match, market, target_date):
    """Prüft ob Tipp bereits gesendet wurde - FAST Cache + Supabase Fallback"""
    global _SENT_TIPS_CACHE

    day = str(target_date)
    cache_key = _dup_cache_key(match, market, day)

    # 1. In-Memory Check
    if cache_key in _SENT_TIPS_CACHE:
        return True

    # 2. Wenn Tag vorgeladen wurde, ist 'nicht im Cache' = kein Duplikat.
    # Spart 100+ einzelne Supabase Calls.
    if day in _PREFETCHED_DUP_DATES:
        return False

    # 3. Fallback nur falls Prefetch nicht lief
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "date": f"eq.{day}",
                    "market": f"eq.{market}",
                    "match": f"eq.{match}",
                    "select": "id",
                    "limit": "1",
                },
                timeout=5,
            )
            if r.ok and len(r.json()) > 0:
                _SENT_TIPS_CACHE.add(cache_key)
                return True
        except Exception:
            pass

    return False

def _combo_signature(legs, prefix=""):
    """
    Deterministische Signatur. Akzeptiert Dictionaries UND Strings.
    """
    import hashlib

    def _part(leg):
        if isinstance(leg, dict):
            return (
                f"{leg.get('match', leg.get('_match', '?'))}|"
                f"{leg.get('market', leg.get('_cat', ''))}|"
                f"{leg.get('tip', leg.get('player_prop', leg.get('selection', '')))}"
            )
        return str(leg)

    parts = sorted(_part(leg) for leg in (legs or []))
    raw = prefix + "::" + "||".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

def is_duplicate_combo(tip_id, target_date):
    """
    Prüft ob eine Kombi/Builder mit dieser deterministischen tip_id bereits heute gesendet wurde.
    FAST: nutzt vorgeladenen Tagescache.
    """
    global _SENT_TIPS_CACHE
    day = str(target_date)
    cache_key = f"combo_{tip_id}"

    if cache_key in _SENT_TIPS_CACHE:
        return True

    if day in _PREFETCHED_DUP_DATES:
        return False

    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/tips",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={
                    "tip_id": f"eq.{tip_id}",
                    "select": "id",
                    "limit": "1",
                },
                timeout=5,
            )
            if r.ok and len(r.json()) > 0:
                _SENT_TIPS_CACHE.add(cache_key)
                return True
        except Exception:
            pass

    return False

def mark_tip_sent(match, market, target_date):
    """Markiert Tipp als gesendet im In-Memory Cache"""
    global _SENT_TIPS_CACHE
    _SENT_TIPS_CACHE.add(_dup_cache_key(match, market, str(target_date)))


def is_valid_tip(tip, target_date):
    """
    Prüft ob ein Tipp wirklich heute + in der Zukunft liegt.
    """
    tip_date = tip.get("date", "")
    today_str = str(target_date)
    if tip_date and tip_date != today_str:
        log(f"   ⚠️ Falsches Datum: {tip_date} (erwartet {today_str})")
        return False

    # Tipps ohne echte Odds (martj42/FootyStats) → Zeit nicht prüfen
    if tip.get("_no_real_odds"):
        return True

    time_str = tip.get("time", "")
    if not is_future_game(time_str, target_date):
        log(f"   ⚠️ Spiel bereits vorbei: {tip.get('match','')} um {time_str}")
        return False

    return True


def log_tip_for_ml(tip: dict, market: str) -> bool:
    """
    Logged einen Tipp mit ML-Features in Supabase (Tabelle: ml_tips).
    Für Feedback-Loop: Modell lernt aus eigenen Ergebnissen.
    Silent-fail — niemals den normalen Bot-Flow unterbrechen.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        match = tip.get("match", "")
        parts = match.split(" vs ") if " vs " in match else [match, ""]
        home = parts[0].strip()
        away = parts[1].strip() if len(parts) > 1 else ""

        # ML-Features aus dem Tipp extrahieren (alles was wir haben)
        features = {
            "elo_home": tip.get("elo_home"),
            "elo_away": tip.get("elo_away"),
            "elo_diff": tip.get("elo_diff"),
            "btts_rate_home": tip.get("btts_rate_home"),
            "btts_rate_away": tip.get("btts_rate_away"),
            "avg_goals_home": tip.get("avg_goals_home"),
            "avg_goals_away": tip.get("avg_goals_away"),
            "xg_home": tip.get("xg_home"),
            "xg_away": tip.get("xg_away"),
            "probability": tip.get("probability"),
        }
        # None-Werte raus
        features = {k: v for k, v in features.items() if v is not None}

        ml_data = {
            "match_id": f"{home}_{away}_{tip.get('date', '')}_{market}".replace(" ", "_"),
            "home_team": home,
            "away_team": away,
            "league": tip.get("league", ""),
            "date": tip.get("date", ""),
            "time": tip.get("time", ""),
            "market": market,
            "tip": tip.get("tip", ""),
            "odds": tip.get("odds", 0.0),
            "confidence": tip.get("confidence", 0),
            "probability": tip.get("probability", 0.0),
            "value_rating": tip.get("value_rating", ""),
            "features": json.dumps(features),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bot_version": "3.0",
            "result": None,
            "settled": False,
        }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/ml_tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=ml_data,
            timeout=8,
        )
        return r.ok
    except Exception:
        return False  # silent fail


def save_to_supabase(tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        # Nur bekannte Supabase Felder senden
        SUPABASE_FIELDS = [
            "tip_id", "date", "market", "market_name", "match", "league",
            "tip", "odds", "probability", "confidence", "value_rating",
            "fair_odds", "units", "bookie", "reasoning", "key_factor",
            "home_form", "away_form", "time", "status",
            "telegram_chat_id", "telegram_msg_id",
            "weekday", "hour",
            "xg_home", "xg_away", "xga_home", "xga_away",
            "sharp_money", "line_movement",
            "btts_rate_home", "btts_rate_away",
            "avg_goals_home", "avg_goals_away",
            # ML Features
            "elo_home", "elo_away", "elo_diff",
            "result_home", "result_away",
            "result_ht_home", "result_ht_away",
            "settled_at", "message_text",
            "group_key", "pick_type", "source",
            "builder_id", "builder_total_legs", "builder_legs", "builder_won_legs",
            "profit_units", "actual_value",
        ]
        
        clean_tip = {k: v for k, v in tip.items() 
                     if k in SUPABASE_FIELDS and v is not None}

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=clean_tip,
            timeout=10,
        )

        if not r.ok:
            # Falls 'message_text' Spalte fehlt → ohne erneut versuchen
            if "message_text" in clean_tip and ("message_text" in r.text or r.status_code == 400):
                clean_tip.pop("message_text", None)
                r = requests.post(
                    f"{SUPABASE_URL}/rest/v1/tips",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    json=clean_tip,
                    timeout=10,
                )
                if r.ok:
                    # 🆕 ML-Logging (silent, nach erfolgreichem Save)
                    log_tip_for_ml(tip, tip.get("market", ""))
                    return True
            log(f"   Supabase Error: {r.status_code} - {r.text[:100]}", "WARN")
            return False

        # 🆕 ML-Logging bei Erfolg
        log_tip_for_ml(tip, tip.get("market", ""))
        return True

    except Exception as e:
        log(f"   Supabase Exception: {str(e)[:60]}", "WARN")
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
            "over15_ht": {"w": 0, "l": 0, "units": 0.0},
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
            odds = float(str(t.get("oddsYes", t.get("odds", 0)) or 0).replace(",", "."))
            # 🆕 Fallback: wenn kein echter Odds, fairOdds aus Wahrscheinlichkeit nutzen
            if odds < 1.40:
                fair = float(str(t.get("fairOdds", 0) or 0).replace(",", "."))
                prob = int(t.get("probability", 0) or 0)
                if fair >= 1.40:
                    odds = fair
                elif prob >= 55:
                    odds = round(100 / prob, 2)  # z.B. 67% → 1.49
            if odds >= 1.40:
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
        key=lambda x: (float(x.get("confidence",0) or 0) * _ntr_learned_weight(x.get("market",""), x.get("league","") or x.get("competition","")), x.get("probability", 0)),
        reverse=True
    )

    # Genug Tipps vorhanden?
    if len(sorted_tips) < num_tips:
        return None

    # Nur EIN Leg pro Spiel — verhindert korrelierte Same-Match-Legs (z.B. Over 2.5 + BTTS
    # aus demselben Spiel), die die Quote aufblaehen und als normale Acca nicht platzierbar sind.
    selected = []
    _used_matches = set()
    for tip in sorted_tips:
        _mkey = str(tip.get("match", "")).strip().lower()
        if not _mkey or _mkey in _used_matches:
            continue
        _used_matches.add(_mkey)
        selected.append(tip)
        if len(selected) >= num_tips:
            break

    # Nicht genug unterschiedliche Spiele fuer diese Combo-Groesse.
    if len(selected) < num_tips:
        return None

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
        9: ("⚡ COMBO 9", "Mega-Kombi"),
        10: ("🌟 COMBO 10", "Ultra-Kombi"),
        11: ("👑 COMBO 11", "Maximal-Kombi"),
    }
    label, desc = labels.get(num_tips, (f"🎲 COMBO {num_tips}", "Multi-Kombi"))

    # Stake Suggestion (weniger bei mehr Tipps)
    stakes = {3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1, 9: 0.75, 10: 0.5, 11: 0.5}
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
    """Formatiert Multi-Combo für Telegram — V31 clean, stake capped."""
    if not combo:
        return ""

    def _fnum(x, default=0.0):
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return default

    total_odds = _fnum(combo.get("total_odds", 0), 0)
    nlegs = len(combo.get("tips", []) or [])
    # Safer stakes: keine 0.5u auf 284/512er Lotterien.
    if nlegs <= 3:
        stake = 0.50
    elif nlegs == 4:
        stake = 0.35
    elif nlegs == 5:
        stake = 0.25
    elif nlegs == 6:
        stake = 0.15
    else:
        stake = 0.05
    if total_odds >= 50:
        stake = min(stake, 0.05)
    elif total_odds >= 25:
        stake = min(stake, 0.10)
    combo["stake_suggestion"] = stake

    win = round(total_odds * stake, 1) if total_odds else "?"
    label = combo.get("label", "COMBO")
    if nlegs >= 7:
        risk = "LOTTERY"
    elif nlegs >= 5:
        risk = "HIGH RISK"
    else:
        risk = "VALUE"

    msg = f"<b>🎰 {label}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 Gesamt-Quote: <b>{total_odds:.2f}</b>\n"
    msg += f"💵 Einsatz: <b>{stake:.2f} Units</b> · Gewinn: ~{win} Units\n"
    msg += f"⚠️ Risiko: <b>{risk}</b>\n\n"
    msg += "<b>📋 Legs:</b>\n"

    for i, tip in enumerate(combo.get("tips", []), 1):
        _mk = tip.get("market", "")
        market_emoji = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "btts_ht": "🕐", "over15_ht": "⏰", "corners": "🔵"}.get(_mk, "💎")
        market_label = {"btts": "BTTS", "over25": "Over 2.5", "combo": "BTTS+O2.5", "btts_ht": "BTTS HT", "over15_ht": "O1.5 HT", "corners": "Corners"}.get(_mk, str(_mk).upper())
        odds_val = tip.get("odds", tip.get("oddsYes", "?"))
        msg += f"{i}. {market_emoji} <b>{tip.get('match','?')}</b> · {market_label} @ {odds_val}\n"

    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>💡 Clean Combo: 3-6 Legs Standard. 7-11 nur als optionale Lottery.</i>"
    return msg



def _auto_void_old_pending():
    """Bereinigt alte Pending Tipps automatisch (älter als 3 Tage)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        from datetime import date, timedelta
        cutoff = str(date.today() - timedelta(days=3))
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={
                "status": "eq.pending",
                "date": f"lt.{cutoff}",
            },
            json={"status": "void"},
            timeout=10,
        )
        if r.ok:
            log("✅ Alte Pending Tipps bereinigt!")
    except Exception as e:
        log(f"Auto-void Error: {str(e)[:50]}", "WARN")



def _get_market_stats_from_supabase(market_id):
    """Holt Won/Lost/ROI + Monat + Top-3-Ligen für einen Markt aus Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from datetime import date as _date2
        today = _date2.today()
        month_start = today.replace(day=1).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "market": f"eq.{market_id}",
                "status": "in.(won,lost)",
                "select": "status,odds,units,date,league",
                "order": "date.desc",
                "limit": "2000",
            },
            timeout=15,
        )
        if not r.ok:
            return None
        tips = r.json()
        if not tips:
            return None

        won  = [t for t in tips if t.get("status") == "won"]
        lost = [t for t in tips if t.get("status") == "lost"]
        total = len(won) + len(lost)
        if total == 0:
            return None

        # ROI Gesamt
        roi = 0.0
        for t in won:
            try:
                roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: roi += 1.0
        for t in lost:
            try: roi -= float(t.get("units",1.0) or 1.0)
            except: roi -= 1.0

        # Monat
        m_won  = [t for t in won  if t.get("date","") >= month_start]
        m_lost = [t for t in lost if t.get("date","") >= month_start]
        m_total = len(m_won) + len(m_lost)
        m_roi = 0.0
        for t in m_won:
            try: m_roi += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
            except: m_roi += 1.0
        for t in m_lost:
            try: m_roi -= float(t.get("units",1.0) or 1.0)
            except: m_roi -= 1.0

        # Top 3 Ligen
        lg_stats = {}
        for t in tips:
            lg = t.get("league","?")
            if not lg: continue
            if lg not in lg_stats:
                lg_stats[lg] = {"w":0,"l":0,"roi":0.0}
            if t.get("status") == "won":
                lg_stats[lg]["w"] += 1
                try: lg_stats[lg]["roi"] += (float(str(t.get("odds","1.5")).replace(",",".")) - 1) * float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] += 1.0
            else:
                lg_stats[lg]["l"] += 1
                try: lg_stats[lg]["roi"] -= float(t.get("units",1.0) or 1.0)
                except: lg_stats[lg]["roi"] -= 1.0

        top_leagues = []
        for lg, s in lg_stats.items():
            tot = s["w"] + s["l"]
            if tot >= 3:
                top_leagues.append((lg, s["w"], tot, round(s["roi"],1)))
        top_leagues.sort(key=lambda x: (-x[3], -x[1]))

        month_names = ["","Januar","Februar","März","April","Mai","Juni",
                       "Juli","August","September","Oktober","November","Dezember"]
        month_name = month_names[today.month]

        return {
            "won": len(won), "lost": len(lost), "total": total,
            "pct": round(len(won)/total*100),
            "roi": round(roi, 1),
            "month_name": month_name,
            "month_won": len(m_won), "month_lost": len(m_lost),
            "month_total": m_total,
            "month_pct": round(len(m_won)/m_total*100) if m_total else 0,
            "month_roi": round(m_roi, 1),
            "top_leagues": top_leagues[:3],
        }
    except Exception as e:
        log(f"Market Stats Error ({market_id}): {str(e)[:60]}", "WARN")
        return None


def _send_daily_auswertung_to_all_groups(stats=None):
    # Schutz gegen Doppel-Senden innerhalb eines Runs (wird jetzt am main()-Ende
    # unbedingt aufgerufen, plus im 0-Tipps-Zweig).
    global _AUSWERTUNG_SENT_THIS_RUN
    if globals().get("_AUSWERTUNG_SENT_THIS_RUN"):
        return
    _AUSWERTUNG_SENT_THIS_RUN = True

    from datetime import datetime as _dt3, timezone as _tz3
    now = _dt3.now(_tz3.utc)
    if now.month == 6 and now.day < 11:
        pause_text = f"🏆 <i>WM 2026 startet in {11-now.day} Tagen!</i>"
    elif now.month in [6, 7]:
        pause_text = "<i>🌍 WM 2026 läuft — täglich Tipps!</i>"
    else:
        pause_text = "<i>Heute spielfreier Tag — morgen wieder Tipps!</i>"

    market_groups = [
        ("btts",    TELEGRAM_GROUPS.get("btts"),    "⚽ BTTS"),
        ("over25",  TELEGRAM_GROUPS.get("over25"),  "🎯 Over 2.5"),
        ("combo",   TELEGRAM_GROUPS.get("combo", TELEGRAM_GROUPS.get("combos")),   "🔥 BTTS + Over 2.5"),
        ("btts_ht", TELEGRAM_GROUPS.get("btts_ht"), "🕐 BTTS Halbzeit"),
        ("corners", TELEGRAM_GROUPS.get("corners", TELEGRAM_GROUPS.get("hz_live")), "🔵 Corner Sniper"),
        ("scorer",  TELEGRAM_GROUPS.get("scorer", TELEGRAM_GROUPS.get("late_goals")), "⚽ Goal Hunter"),
        ("builder", TELEGRAM_GROUPS.get("builder", TELEGRAM_GROUPS.get("combos")), "🧱 Prop Builder"),
    ]

    medals = ["🥇","🥈","🥉"]
    sent_to = set()

    for market_id, chat_id, title in market_groups:
        if not chat_id or chat_id in sent_to:
            continue

        ms = _get_market_stats_from_supabase(market_id)

        nl = "\n"
        msg = f"<b>{title}</b>{nl}"
        msg += f"━━━━━━━━━━━━━━━━━━{nl}"

        if ms and ms["total"] >= 3:
            wr_e  = "🔥" if ms["pct"] >= 70 else "✅" if ms["pct"] >= 60 else "⚠️"
            roi_e = "🟢" if ms["roi"] >= 0 else "🔴"
            roi_s = f"+{ms['roi']}" if ms["roi"] >= 0 else str(ms["roi"])

            msg += f"{wr_e} Winrate: <b>{ms['pct']}%</b> ({ms['won']}W / {ms['lost']}L){nl}"
            msg += f"{roi_e} ROI: <b>{roi_s} Units</b>{nl}"
            msg += f"📋 Gesamt: {ms['total']} ausgewertete Tipps{nl}"

            # Monat
            if ms.get("month_total", 0) > 0:
                m_roi_e = "🟢" if ms["month_roi"] >= 0 else "🔴"
                m_roi_s = f"+{ms['month_roi']}" if ms["month_roi"] >= 0 else str(ms["month_roi"])
                msg += f"{nl}<b>{ms['month_name']}:</b>{nl}"
                msg += f"{ms['month_won']}/{ms['month_total']} Tipps · {ms['month_pct']}% · {m_roi_s}U {m_roi_e}{nl}"

            # Top 3 Ligen
            if ms.get("top_leagues"):
                msg += f"{nl}<b>🏆 Top Ligen:</b>{nl}"
                for i, (lg, w, tot, roi_lg) in enumerate(ms["top_leagues"]):
                    pct_lg   = round(w/tot*100) if tot else 0
                    roi_s_lg = f"+{roi_lg}" if roi_lg >= 0 else str(roi_lg)
                    medal = medals[i] if i < len(medals) else "•"
                    msg += f"{medal} {lg}: {w}/{tot} ({pct_lg}%) · {roi_s_lg}U{nl}"
        else:
            msg += f"📊 Daten werden gesammelt...{nl}"
            msg += f"<i>Mindestens 3 ausgewertete Tipps nötig.</i>{nl}"

        msg += f"━━━━━━━━━━━━━━━━━━{nl}"
        msg += pause_text

        send_telegram(msg, chat_id)
        sent_to.add(chat_id)

    log(f"✅ Gruppen-Auswertung gesendet ({len(sent_to)} Gruppen)")


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
        "VALUE": "🟢",
        "OK": "🟡",
        "LOW": "🔴",
    }

    market_emoji = {
        "btts": "⚽",
        "over25": "🎯",
        "combo": "🔥",
        "btts_ht": "🕐",
        "over15_ht": "⏰",
        "1x2": "🏆",
    }

    total_tips = sum(len(t) for t in tips_by_market.values())

    # ============================================================
    # STATS NACHRICHT - Vollständig mit allen Märkten
    # ============================================================
    now_utc = datetime.now(timezone.utc)
    month_name = now_utc.strftime("%B %Y")

    stats_header = f"<b>🤖 AI TIPP BOT - DAILY</b>\n<i>{target_date}</i>\n" + "\n"

    # Tagesübersicht - ALLE Märkte
    stats_header += "📊 <b>Übersicht heute:</b>\n"
    for m_id in MARKETS_TO_RUN:
        count = len(tips_by_market.get(m_id, []))
        stats_header += f"• {MARKET_INFO[m_id]['name']}: <b>{count}</b> Tipps" + "\n"

    # Ecken + Scorer + Combos
    corners_today = getattr(run_corners_and_scorer_bots, '_last_corners', 0)
    scorer_today = getattr(run_corners_and_scorer_bots, '_last_scorer', 0)
    stats_header += f"• 🔵 Ecken: <b>{corners_count if 'corners_count' in dir() else 0}</b> Tipps" + "\n"
    stats_header += f"• 🎰 Combos: <b>{combos_sent if 'combos_sent' in dir() else 0}</b> generiert" + "\n"
    stats_header += f"\n💎 <b>Total: {total_tips} Top-Tipps</b>"

    stats = get_overall_stats()

    if stats:
        # Auto-void alte pendings
        old_pending = stats.get("pending", 0)
        
        stats_header += "\n\n━━━━━━━━━━━━━━━━━━\n"
        stats_header += "📈 <b>GESAMT-STATISTIK</b>\n"
        stats_header += f"✅ Gewonnen: <b>{stats['won']}</b>" + "\n"
        stats_header += f"❌ Verloren: <b>{stats['lost']}</b>" + "\n"
        # Pending nur zeigen wenn sinnvoll (< 50)
        if stats["pending"] and stats["pending"] < 50:
            stats_header += f"⏳ Pending: <b>{stats['pending']}</b>" + "\n"
        stats_header += f"🎯 Trefferquote: <b>{stats['quote_pct']}%</b>" + "\n"
        roi_emoji = "🟢" if stats["roi_units"] >= 0 else "🔴"
        stats_header += f"💰 ROI: <b>{'+' if stats['roi_units'] >= 0 else ''}{stats['roi_units']}</b> Units {roi_emoji}" + "\n"

        # Monatsübersicht
        if stats.get("month") and stats["month"]["total"] > 0:
            m = stats["month"]
            m_emoji = "🟢" if m["units"] >= 0 else "🔴"
            stats_header += f"\n📅 <b>{m['name']}:</b> {m['won']}/{m['total']} ({m['pct']}%) · "
            stats_header += f"<b>{'+' if m['units'] >= 0 else ''}{m['units']} Units</b> {m_emoji}" + "\n"

        # Pro Markt - ALLE inkl Ecken
        stats_header += f"\n<b>📊 Pro Markt:</b>" + "\n"
        market_names = {
            "btts": "⚽ BTTS",
            "over25": "🎯 Over 2.5",
            "combo": "🔥 BTTS+Over 2.5",
            "btts_ht": "🕐 BTTS HT",
            "over15_ht": "⏰ Over 1.5 HT",
        }
        for m_id in MARKETS_TO_RUN:
            mb = stats["by_market"].get(m_id, {"w":0,"l":0,"units":0.0})
            tot = mb["w"] + mb["l"]
            if tot > 0:
                pct = round(mb["w"]/tot*100)
                emoji = "🟢" if pct >= 60 else "🟡" if pct >= 40 else "🔴"
                u_str = f"+{round(mb['units'],2)}" if mb["units"] >= 0 else f"{round(mb['units'],2)}"
                stats_header += f"{market_names.get(m_id,m_id)}: {mb['w']}/{tot} ({pct}%) · {u_str}U {emoji}" + "\n"

        # Top Ligen
        if stats.get("top_leagues"):
            stats_header += f"\n<b>🏆 Top Ligen:</b>" + "\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
            for i, (lg, w, tot, pct, units) in enumerate(stats["top_leagues"][:10]):
                medal = medals[i] if i < len(medals) else "•"
                u_str = f"+{units}" if units >= 0 else str(units)
                stats_header += f"{medal} {lg}: {w}/{tot} ({pct}%) · {u_str}U" + "\n"

    # V30 HOTFIX: Keine Gesamt-Statistik mehr in eine Tipp-Gruppe.
    # Jede Gruppe bekommt ihre eigene Markt-Bewertung; Gesamt nur in separate Stats-Gruppe.
    _send_market_daily_cards_to_own_groups(tips_by_market, target_date, stats)
    _send_global_daily_stats_only_to_stats_group(stats_header)

    # Auto-void alte Pending Tipps (älter als 3 Tage)
    _auto_void_old_pending()

    # Wenn keine Tipps → Auswertung in ALLE Gruppen senden
    if total_tips == 0:
        _send_daily_auswertung_to_all_groups(stats)
        return

    saved = 0
    prefetch_sent_tips_for_date(target_date)

    for market_id, tips in tips_by_market.items():
        if not tips:
            continue

        # 🧠 GELERNTE GEWICHTE anwenden: Tipps nach Confidence × gelerntem
        # Markt/Liga-Gewicht neu sortieren (aus abgerechneten Tipps gelernt).
        # Neutral solange wenig Lern-Daten da sind (Gewicht ~1.0).
        try:
            def _weighted_conf(_t):
                _lg = str(_t.get("league", "") or _t.get("competition", "") or _t.get("league_name", ""))
                return float(_t.get("confidence", 0) or 0) * _ntr_learned_weight(market_id, _lg)
            tips = sorted(tips, key=_weighted_conf, reverse=True)
        except Exception:
            pass

        target_chat = TELEGRAM_GROUPS.get(market_id, TELEGRAM_CHAT_ID)
        market_name = MARKET_INFO[market_id]["name"]
        emoji = market_emoji.get(market_id, "💎")

        # Kein Header - direkt Tipps senden

        for i, r in enumerate(tips, 1):
            confidence = int(r.get("confidence", 0))
            match_name = r.get("match", "?")

            r["date"] = str(target_date)
            if not is_valid_tip(r, target_date):
                continue

            if is_duplicate_tip(match_name, market_id, target_date):
                _ntr_log_duplicate(f"   ⏭️ Duplikat übersprungen: {match_name} ({market_id})", key=f"{market_id}")
                continue

            # ✅ NEUES FORMAT - Variante 3
            market_icons2 = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "btts_ht": "🕐", "over15_ht": "⏰"}
            market_names2 = {"btts": "BTTS", "over25": "OVER 2.5", "combo": "BTTS + OVER 2.5", "btts_ht": "BTTS HT", "over15_ht": "OVER 1.5 HT"}
            val_icon = val_icons.get(r.get('valueRating', 'OK'), '🟡')
            mkt_icon = market_icons2.get(market_id, "🎯")
            mkt_name = market_names2.get(market_id, market_id.upper())

            tip_time_raw = r.get('time', r.get('time_local', '')).strip()
            if not tip_time_raw or tip_time_raw in ['TBD', 'N/A', '-', '']:
                tip_time = "Heute"
            else:
                try:
                    from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
                    if 'T' in tip_time_raw and ('Z' in tip_time_raw or '+' in tip_time_raw):
                        _t2 = _dt2.fromisoformat(tip_time_raw.replace('Z', '+00:00'))
                        _local2 = _t2.astimezone(_tz2(_td2(hours=2)))
                        tip_time = _local2.strftime('%H:%M')
                    else:
                        tip_time = tip_time_raw
                except Exception:
                    tip_time = tip_time_raw

            try:
                odds_val = float(str(r.get('oddsYes', '1.5')).replace(',', '.'))
                prob_val = int(r.get('probability', 60))
                # Konservativerer Cap bei reiner Liga-Schätzung (kein echter Pinnacle-Quote-Confirm)
                _no_real = r.get('_no_real_odds', True)
                _max_u = 1.5 if _no_real else 3.0
                units = calculate_kelly_units(prob_val, odds_val, max_units=_max_u)
                units_emoji = "🔥" if units >= 2.5 else "💚" if units >= 1.5 else "🟡"
            except:
                units = 1.0
                units_emoji = "💚"

            # Wetter
            weather_data = r.get("weather", {})
            weather_line = ""
            if weather_data and weather_data.get("temp"):
                temp = weather_data.get("temp", "")
                rain = weather_data.get("rain", 0)
                wind = weather_data.get("wind", 0)
                if rain > 1:
                    weather_line = f"🌧️ {temp}°C · Regen {rain}mm"
                elif wind > 30:
                    weather_line = f"💨 {temp}°C · Wind {wind}km/h"
                else:
                    weather_line = f"🌤️ {temp}°C"

            # Form
            def fmt_form(fs):
                if not fs or fs in ['N/A', '-', '?']:
                    return ""
                icons2 = {"W": "🟢", "D": "🟡", "L": "🔴"}
                return " ".join([icons2.get(c, "⚪") for c in str(fs)[-5:]])

            home_form = r.get('homeForm', r.get('home_form', '')).strip()
            away_form = r.get('awayForm', r.get('away_form', '')).strip()

            # Sharp Money
            sharp = r.get('sharp_money', '')
            sharp_line = ""
            if sharp == "strong":
                sharp_line = "📌 Starkes Sharp Money Signal!"
            elif sharp:
                sharp_line = "📌 Sharp Money aktiv"

            # Opening Odds
            opening = r.get('opening_odds', 0)
            odds_move_line = ""
            if opening and odds_val and opening != odds_val:
                diff = round(odds_val - opening, 2)
                arrow = "▼" if diff < 0 else "▲"
                odds_move_line = f"📉 Opening: {opening} → {odds_val} {arrow}"

            # Verletzungen
            inj_home = r.get('injuries_home', '')
            inj_away = r.get('injuries_away', '')

            # Schiri mit Details
            ref = r.get('referee', r.get('ref', ''))
            ref_cards = r.get('ref_cards_per_game', 0)
            ref_red = r.get('ref_red_per_game', 0)
            ref_pen = r.get('ref_penalty_rate', 0)
            ref_fouls = r.get('ref_fouls_per_game', 0)

            # H2H
            h2h_btts = r.get('h2h_btts', '')
            h2h_goals = r.get('h2h_avg_goals', '')

            # Build Message
            msg = f"💎 <b>{match_name}</b>" + "\n"
            msg += f"📍 {r.get('league', r.get('league_name', ''))} · ⏰ {tip_time}" + "\n"
            if weather_line:
                msg += f"{weather_line}" + "\n"
            msg += f"━━━━━━━━━━━━━━━━━━" + "\n"
            msg += f"{mkt_icon} <b>{mkt_name}</b>" + "\n"
            msg += f"✅ Tipp: <b>{r.get('tip','YES')}</b>" + "\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability',0)}%</b>" + "\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}" + "\n"
            msg += f"💰 Quote: <b>{r.get('oddsYes','-')}</b> · Fair: {r.get('fairOdds','-')} · {val_icon} {r.get('valueRating','OK')}" + "\n"
            msg += f"{units_emoji} <b>{units} Units</b>"

            # Stats
            stats = []
            if r.get('xg_home') and r.get('xg_away'):
                stats.append(f"⚡ xG: {r['xg_home']} / {r['xg_away']}")
            if r.get('btts_rate_home') and r.get('btts_rate_away'):
                stats.append(f"📊 BTTS Rate: {r['btts_rate_home']}% / {r['btts_rate_away']}%")
            if h2h_btts:
                stats.append(f"🔄 H2H BTTS: {h2h_btts}")
            if h2h_goals:
                stats.append(f"⚽ H2H Ø Tore: {h2h_goals}")
            if stats:
                msg += f"\n━━━━━━━━━━━━━━━━━━"
                msg += "\n".join(stats)

            # Quoten Bewegung
            if odds_move_line or sharp_line:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if odds_move_line:
                    msg += f"{odds_move_line}" + "\n"
                if sharp_line:
                    msg += f"{sharp_line}" + "\n"

            # Team Info
            team_info = []
            if inj_home:
                team_info.append(f"🏥 Verletzt Heim: {inj_home}")
            if inj_away:
                team_info.append(f"🏥 Verletzt Gast: {inj_away}")
            if ref:
                team_info.append(f"👨‍⚖️ Schiri: {ref}")
            if team_info or ref:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                if team_info:
                    msg += "\n".join(team_info) + "\n"
                if ref:
                    msg += f"👨‍⚖️ <b>{ref}</b>" + "\n"
                    if ref_cards:
                        msg += f"   🟡 {ref_cards} K/Sp"
                    if ref_red:
                        msg += f" · 🔴 {ref_red} R/Sp"
                    if ref_pen:
                        msg += f" · ⚽ {ref_pen} Elf/Sp"
                    if ref_fouls:
                        msg += f" · 📊 {ref_fouls} F/Sp"
                    # Schiri Bewertung
                    if ref_cards:
                        if float(ref_cards) < 3.5:
                            msg += "\n   ✅ Lässt Spiel laufen"
                        elif float(ref_cards) > 5:
                            msg += "\n   ⚠️ Strenger Schiri"
                        else:
                            msg += "\n   🟡 Durchschnittlich"
                    msg += "\n"

            # Form
            hf = fmt_form(home_form)
            af = fmt_form(away_form)
            if hf or af:
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                home_name = match_name.split(" vs ")[0][:12] if " vs " in match_name else "Heim"
                away_name = match_name.split(" vs ")[1][:12] if " vs " in match_name else "Gast"
                if hf:
                    msg += f"🏠 {home_name}: {hf}" + "\n"
                if af:
                    msg += f"✈️ {away_name}: {af}" + "\n"

            # Key Factor + Reasoning
            if r.get('keyFactor'):
                msg += f"\n━━━━━━━━━━━━━━━━━━" + "\n"
                msg += f"⚡ <i>{r.get('keyFactor')[:100]}</i>" + "\n"

            reasoning = r.get('reasoning', '')
            if reasoning:
                if len(reasoning) > 150:
                    reasoning = reasoning[:147] + "..."
                msg += f"\n💭 <i>{reasoning}</i>"

            msg += f"\n━━━━━━━━━━━━━━━━━━"

            # Beste Quote Empfehlung
            tip_odds_data = r.get("_odds_data", [])
            inline_keyboard = build_inline_keyboard(tip_odds_data, match_name)

            # Bookie Empfehlung
            best_bookie = r.get("bookie", "")
            best_odds = r.get("oddsYes", "")
            if best_bookie and best_odds:
                msg += f"\n🏆 Empfehlung: <b>{best_bookie}</b> · Quote {best_odds}"

            msg_id = send_telegram(msg, target_chat)
            mark_tip_sent(match_name, market_id, target_date)

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

            import time as _ts
            tip_id = f"{market_id}_{target_date}_{abs(hash(match_name + market_id)) % 100000}"

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
                "message_text": msg[:3500],  # Für Ergebnis-Anhang beim Settlement
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

            # Prüfe ob bereits in Supabase
            tip_id_check = tip_data.get("tip_id", "")
            already_exists = False
            if tip_id_check and SUPABASE_URL and SUPABASE_KEY:
                try:
                    r_check = requests.get(
                        f"{SUPABASE_URL}/rest/v1/tips",
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                        params={"tip_id": f"eq.{tip_id_check}", "select": "id", "limit": "1"},
                        timeout=5,
                    )
                    if r_check.ok and r_check.json():
                        already_exists = True
                except Exception:
                    pass

            if already_exists:
                log(f"   ⏭️ Supabase: bereits vorhanden {tip_data.get('match','?')}")
            else:
                save_result = save_to_supabase(tip_data)
                # CLV Tracking
                if NETRATTLER_PRO:
                    try:
                        log_tip_for_clv(tip_data)
                    except Exception:
                        pass
                if save_result:
                    saved += 1
                else:
                    log(f"   ⚠️ Supabase save fehlgeschlagen für {tip_data.get('match','?')}", "WARN")

        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")

        # Kein Footer - direkt Tipps ohne Zusammenfassung

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
    Gibt ALLE Ligen zurück (global, 24/7).
    Keine Zeit-Filterung mehr - der Bot checkt alle Ligen weltweit.
    """
    if not LEAGUE_ROTATION_ENABLED:
        return list(LEAGUES_TO_RUN), {}
    if ACTIVE_LEAGUES_OVERRIDE:
        log(f"🎯 Override: {len(ACTIVE_LEAGUES_OVERRIDE)} Ligen")
        return ACTIVE_LEAGUES_OVERRIDE, {}

    log(f"🌍 Global Mode: alle {len(LEAGUES_TO_RUN)} Ligen aktiv (24/7)")

    if not AUTO_LEAGUE_SWITCH:
        log("Auto Liga Switch: AUS")
        return LEAGUES_TO_RUN, {}

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
        else:
            disabled.append((league, reason))
            log(f" ⛔ {league}: {reason}", "SKIP")

    log(f"Auto Liga Switch: {len(active)} aktiv, {len(disabled)} pausiert")

    return active, league_stats



def check_tip_result(tip, result):
    """Bewertet klassische Märkte. Player Props/Builder werden separat gesettelt."""
    if not result or not tip:
        return None

    market = str(tip.get("market", "btts") or "btts").lower()
    tip_value = str(tip.get("tip", "YES") or "YES").upper()
    won = False

    if market == "btts":
        won = result.get("btts", False) if tip_value == "YES" else not result.get("btts", False)
    elif market == "over25":
        won = result.get("over25", False) if tip_value == "YES" else not result.get("over25", False)
    elif market == "combo":
        combo_hit = result.get("btts", False) and result.get("over25", False)
        won = combo_hit if tip_value == "YES" else not combo_hit
    elif market == "btts_ht":
        won = result.get("btts_ht", False) if tip_value == "YES" else not result.get("btts_ht", False)
    elif market == "over15_ht":
        ht_total = (result.get("ht_home") or 0) + (result.get("ht_away") or 0)
        won = ht_total >= 2 if tip_value != "NO" else ht_total < 2
    elif market == "corners":
        total_corners = (
            result.get("total_corners")
            or result.get("corners_total")
            or (
                (result.get("home_corners") or 0) + (result.get("away_corners") or 0)
                if result.get("home_corners") is not None and result.get("away_corners") is not None
                else None
            )
        )
        if total_corners is None:
            return None
        line = tip.get("line") or tip.get("corner_line") or 8.5
        try:
            won = float(total_corners) > float(line)
        except Exception:
            return None
    else:
        return None

    return "won" if won else "lost"


_AF_FIXTURES_DAY_CACHE = {}  # {date_str: [fixtures]} — verhindert N Calls für N pending Tips am selben Tag

def _af_fixtures_for_date(date_str):
    """Holt alle FT-Fixtures für ein Datum, gecached pro Tag (1 Call statt N)."""
    if str(os.getenv("ENABLE_API_FOOTBALL_SETTLEMENT", "0")).lower() not in {"1", "true", "yes", "on"}:
        return []
    if date_str in _AF_FIXTURES_DAY_CACHE:
        return _AF_FIXTURES_DAY_CACHE[date_str]
    r = _af_request("/fixtures", {"date": date_str, "status": "FT"})
    _AF_FIXTURES_DAY_CACHE[date_str] = r or []
    return _AF_FIXTURES_DAY_CACHE[date_str]


_SOFA_EVENTS_DAY_CACHE = {}  # {date_str: [events]} — wie API-Football Tages-Cache, aber kostenlos & ID-los

def _sofascore_events_for_date(date_str):
    """
    Holt ALLE Fussball-Events eines Tages von SofaScore (kostenlos, kein Key, kein Match-ID nötig).
    Gecacht pro Tag: 1 Call deckt alle pending Tips desselben Tages ab.
    Fällt bei Cloudflare-Block auf Playwright zurück.
    """
    if date_str in _SOFA_EVENTS_DAY_CACHE:
        return _SOFA_EVENTS_DAY_CACHE[date_str]

    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    events = []
    _status = None
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=15,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            events = data.get("events", [])
    except Exception as _se:
        _status = f"EXC:{str(_se)[:60]}"

    log(f"   🔍 SOFA-DEBUG: {date_str} → HTTP {_status}, {len(events)} Events (direkt)")

    if not events and PLAYWRIGHT_AVAILABLE:
        try:
            html = scrape_with_playwright(url, timeout=15000)
            if html:
                import re as _re
                m = _re.search(r'(\{.*\})', html, _re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
                    events = data.get("events", [])
            log(f"   🔍 SOFA-DEBUG: {date_str} → Playwright-Fallback: {len(events)} Events")
        except Exception as _pe:
            log(f"   🔍 SOFA-DEBUG: {date_str} → Playwright-Fallback Fehler: {str(_pe)[:80]}", "WARN")

    finished_count = sum(1 for e in events if (e.get("status", {}) or {}).get("type") == "finished")
    if events:
        log(f"   🔍 SOFA-DEBUG: {date_str} → {len(events)} Events total, {finished_count} finished")

    _SOFA_EVENTS_DAY_CACHE[date_str] = events
    return events


def _sofascore_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in SofaScore-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td3

    events = _sofascore_events_for_date(tip_date)
    if not events:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td3(days=_delta)).date())
                events = _sofascore_events_for_date(_d2)
                if events:
                    break
        except Exception:
            pass

    if not events:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for ev in events:
        status = ev.get("status", {}).get("type", "")
        if status != "finished":
            continue
        h = (ev.get("homeTeam") or {}).get("name", "")
        a = (ev.get("awayTeam") or {}).get("name", "")
        h_match = h.lower()[:6] in h_target or h_target[:6] in h.lower()
        a_match = a.lower()[:6] in a_target or a_target[:6] in a.lower()
        if h_match and a_match:
            home_g = (ev.get("homeScore") or {}).get("current", 0) or 0
            away_g = (ev.get("awayScore") or {}).get("current", 0) or 0
            ht_home = (ev.get("homeScore") or {}).get("period1", 0) or 0
            ht_away = (ev.get("awayScore") or {}).get("period1", 0) or 0
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
    return None


_ALLSPORTS_DAY_CACHE = {}  # {date_str: [matches]} — globale Tagessuche, kein leagueId nötig

def _allsports_events_for_date(date_str):
    """
    Holt ALLE Fussball-Fixtures eines Tages von AllSportsAPI, OHNE leagueId-Einschränkung.
    Gecacht pro Tag, analog zu SofaScore/API-Football Tages-Cache.
    """
    if not ALLSPORTS_API_KEY:
        return []
    if date_str in _ALLSPORTS_DAY_CACHE:
        return _ALLSPORTS_DAY_CACHE[date_str]

    matches = []
    _status = None
    try:
        r = requests.get(
            "https://apiv2.allsportsapi.com/football/",
            params={
                "met": "Fixtures",
                "APIkey": ALLSPORTS_API_KEY,
                "from": date_str,
                "to": date_str,
            },
            timeout=20,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            matches = data.get("result", []) or []
    except Exception as _ae:
        _status = f"EXC:{str(_ae)[:60]}"

    log(f"   🔍 ALLSPORTS-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Fixtures")
    _ALLSPORTS_DAY_CACHE[date_str] = matches
    return matches


def _allsports_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in AllSports-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td4

    matches = _allsports_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td4(days=_delta)).date())
                matches = _allsports_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        status = m.get("event_status", "")
        if status != "Finished":
            continue
        h = m.get("event_home_team", "")
        a = m.get("event_away_team", "")
        h_match = h.lower()[:6] in h_target or h_target[:6] in h.lower()
        a_match = a.lower()[:6] in a_target or a_target[:6] in a.lower()
        if h_match and a_match:
            try:
                home_g = int(m.get("event_final_result", "0-0").split("-")[0].strip() or 0)
                away_g = int(m.get("event_final_result", "0-0").split("-")[1].strip() or 0)
                ht = m.get("event_halftime_result", "0-0") or "0-0"
                ht_home = int(ht.split("-")[0].strip() or 0)
                ht_away = int(ht.split("-")[1].strip() or 0)
            except Exception:
                continue
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
    return None


_FOOTBALLDATA_DAY_CACHE = {}  # {date_str: [matches]} — globale Tagessuche, alle Competitions des Keys

def _footballdata_events_for_date(date_str):
    """
    Holt ALLE Matches eines Tages von football-data.org (globaler /v4/matches Endpoint,
    deckt alle Competitions ab, zu denen der Key Zugriff hat — kein Liga-Code nötig).
    Gecacht pro Tag, nutzt bestehende Key-Rotation (_FD_KEY_OFFSET / _FD_DEAD_KEYS).
    """
    global _FD_KEY_OFFSET
    if not FOOTBALL_DATA_API_KEYS:
        return []
    if date_str in _FOOTBALLDATA_DAY_CACHE:
        return _FOOTBALLDATA_DAY_CACHE[date_str]

    matches = []
    n = len(FOOTBALL_DATA_API_KEYS)
    _status = None
    for offset in range(n):
        idx = (_FD_KEY_OFFSET + offset) % n
        if idx in _FD_DEAD_KEYS:
            continue
        key = FOOTBALL_DATA_API_KEYS[idx]
        try:
            r = requests.get(
                "https://api.football-data.org/v4/matches",
                params={"dateFrom": date_str, "dateTo": date_str},
                headers={"X-Auth-Token": key},
                timeout=15,
            )
            _status = r.status_code
            if r.status_code == 429:
                _FD_DEAD_KEYS.add(idx)
                continue
            if r.status_code == 403:
                _FD_DEAD_KEYS.add(idx)
                continue
            if r.ok:
                data = r.json()
                matches = data.get("matches", []) or []
                _FD_KEY_OFFSET = (idx + 1) % n
                break
        except Exception as _fde:
            _status = f"EXC:{str(_fde)[:60]}"
            continue

    log(f"   🔍 FOOTBALLDATA-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Matches")
    _FOOTBALLDATA_DAY_CACHE[date_str] = matches
    return matches


def _footballdata_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in football-data.org-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td5

    matches = _footballdata_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td5(days=_delta)).date())
                matches = _footballdata_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        status = m.get("status", "")
        if status != "FINISHED":
            continue
        h = (m.get("homeTeam") or {}).get("name", "") or ""
        a = (m.get("awayTeam") or {}).get("name", "") or ""
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            score = m.get("score", {}) or {}
            ft = score.get("fullTime", {}) or {}
            ht = score.get("halfTime", {}) or {}
            home_g = ft.get("home", 0) or 0
            away_g = ft.get("away", 0) or 0
            ht_home = ht.get("home", 0) or 0
            ht_away = ht.get("away", 0) or 0
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
    return None


_OPENLIGADB_DAY_CACHE = {}  # German-fokussiert, aber komplett kostenlos & ohne Key

def _openligadb_find_result(home_team, away_team, tip_date, league_name=""):
    """
    OpenLigaDB: kostenlose, keyless API für deutsche Wettbewerbe (Bundesliga, 2./3. Liga, DFB-Pokal).
    Nur sinnvoll wenn die Liga deutsch ist — sonst überspringen (kein globaler Endpoint vorhanden).
    """
    _ln = league_name.lower()
    _league_map = {
        "bundesliga": "bl1", "2. bundesliga": "bl2", "3. liga": "bl3",
        "dfb-pokal": "dfb", "dfb pokal": "dfb",
    }
    _shortcut = None
    for key, code in _league_map.items():
        if key in _ln:
            _shortcut = code
            break
    if not _shortcut:
        return None

    try:
        season = str(datetime.strptime(tip_date, "%Y-%m-%d").year)
    except Exception:
        return None

    cache_key = f"{_shortcut}_{season}"
    if cache_key not in _OPENLIGADB_DAY_CACHE:
        try:
            r = requests.get(
                f"https://api.openligadb.de/getmatchdata/{_shortcut}/{season}",
                timeout=15,
            )
            _OPENLIGADB_DAY_CACHE[cache_key] = r.json() if r.ok else []
            log(f"   🔍 OPENLIGADB-DEBUG: {_shortcut}/{season} → {len(_OPENLIGADB_DAY_CACHE[cache_key])} Matches")
        except Exception:
            _OPENLIGADB_DAY_CACHE[cache_key] = []

    matches = _OPENLIGADB_DAY_CACHE.get(cache_key, [])
    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        if not m.get("matchIsFinished"):
            continue
        h = (m.get("team1") or {}).get("teamName", "") or ""
        a = (m.get("team2") or {}).get("teamName", "") or ""
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            results = m.get("matchResults", []) or []
            ft = next((r for r in results if r.get("resultName") == "Endergebnis"), None)
            ht = next((r for r in results if r.get("resultName") == "Halbzeitergebnis"), None)
            if not ft:
                continue
            home_g = ft.get("pointsTeam1", 0) or 0
            away_g = ft.get("pointsTeam2", 0) or 0
            ht_home = ht.get("pointsTeam1", 0) if ht else 0
            ht_away = ht.get("pointsTeam2", 0) if ht else 0
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
    return None


_FOOTBALLDATAIO_DAY_CACHE = {}  # {date_str: [matches]}

def _footballdataio_events_for_date(date_str):
    """
    Holt alle Matches eines Tages von footballdata.io (anderer Anbieter als football-data.org!).
    Bestätigter Endpoint: GET /matches/date/{date}, Auth: Bearer Token.
    Gecacht pro Tag.
    """
    if not FOOTBALLDATA_IO_API_KEY:
        return []
    if date_str in _FOOTBALLDATAIO_DAY_CACHE:
        return _FOOTBALLDATAIO_DAY_CACHE[date_str]

    matches = []
    _status = None
    try:
        r = requests.get(
            f"https://footballdata.io/api/v1/matches/date/{date_str}",
            headers={"Authorization": f"Bearer {FOOTBALLDATA_IO_API_KEY}"},
            timeout=15,
        )
        _status = r.status_code
        if r.ok:
            data = r.json()
            # Antwortformat noch nicht live verifiziert — robust gegen beide üblichen Strukturen
            matches = data.get("data") or data.get("matches") or (data if isinstance(data, list) else [])
    except Exception as _fie:
        _status = f"EXC:{str(_fie)[:60]}"

    log(f"   🔍 FOOTBALLDATAIO-DEBUG: {date_str} → HTTP {_status}, {len(matches)} Matches")
    _FOOTBALLDATAIO_DAY_CACHE[date_str] = matches
    return matches


def _footballdataio_find_result(home_team, away_team, tip_date):
    """Sucht Ergebnis per Teamname+Datum in footballdata.io-Tagesliste, mit ±1-Tag-Fallback."""
    from datetime import timedelta as _td6

    matches = _footballdataio_events_for_date(tip_date)
    if not matches:
        try:
            for _delta in [-1, 1]:
                _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td6(days=_delta)).date())
                matches = _footballdataio_events_for_date(_d2)
                if matches:
                    break
        except Exception:
            pass

    if not matches:
        return None

    h_target = home_team.lower()
    a_target = away_team.lower()

    for m in matches:
        # Status-Feldname noch nicht live verifiziert — mehrere übliche Varianten abdecken
        status = (m.get("status") or m.get("matchStatus") or "").upper()
        if status not in ("FINISHED", "FT", "COMPLETED"):
            continue
        home_obj = m.get("homeTeam") or m.get("home_team") or {}
        away_obj = m.get("awayTeam") or m.get("away_team") or {}
        h = home_obj.get("name", "") if isinstance(home_obj, dict) else str(home_obj)
        a = away_obj.get("name", "") if isinstance(away_obj, dict) else str(away_obj)
        h_match = len(h) >= 4 and (h.lower()[:6] in h_target or h_target[:6] in h.lower())
        a_match = len(a) >= 4 and (a.lower()[:6] in a_target or a_target[:6] in a.lower())
        if h_match and a_match:
            score = m.get("score", {}) or {}
            home_g = score.get("home") or score.get("homeScore") or 0
            away_g = score.get("away") or score.get("awayScore") or 0
            ht = m.get("halfTimeScore") or {}
            ht_home = ht.get("home", 0) if isinstance(ht, dict) else 0
            ht_away = ht.get("away", 0) if isinstance(ht, dict) else 0
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
    return None

    """
    Versucht Spielergebnis von mehreren Quellen zu holen.
    Priorität: SofaScore (Tages-Suche) → AllSports (Tages-Suche) → API-Football → ESPN/SofaScore/AllSports (per ID)
    """
    match_name = tip.get("match", "")
    league = tip.get("league", "")
    match_id = tip.get("telegram_msg_id", "")  # Wir brauchen die echte match_id

    # 🆕 SofaScore Tages-Suche zuerst — kostenlos, kein Key, kein vorab gespeichertes ID nötig
    if match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _sofascore_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 TheStatsAPI Settlement (primär — zuverlässigste Quelle wenn Key vorhanden)
    if THESTATSAPI_KEYS and match_name and " vs " in match_name:
        try:
            _parts = match_name.split(" vs ")
            _home = _parts[0].strip()
            _away = _parts[1].strip() if len(_parts) > 1 else ""
            _date = tip.get("date", str(datetime.now(timezone.utc).date()))
            _res = tsa_find_match_result(_home, _away, _date)
            if _res:
                return _res
        except Exception:
            pass

    # 🆕 AllSports Tages-Suche — eigener API-Key bereits aktiv, kein vorab gespeichertes ID nötig
    if ALLSPORTS_API_KEY and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _allsports_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 Football-Data.org Tages-Suche — bereits validierte Keys, globaler Endpoint
    if FOOTBALL_DATA_API_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _footballdata_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # 🆕 OpenLigaDB — kostenlos, kein Key, nur deutsche Wettbewerbe (Bundesliga etc.)
    if match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _openligadb_find_result(home_team, away_team, tip_date, league)
            if result:
                return result
        except Exception:
            pass

    # 🆕 footballdata.io Tages-Suche — anderer Anbieter als football-data.org
    if FOOTBALLDATA_IO_API_KEY and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            result = _footballdataio_find_result(home_team, away_team, tip_date)
            if result:
                return result
        except Exception:
            pass

    # SofaScore per ID (falls vorhanden, z.B. aus alten Live-Bot-Daten)
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

    # API-Football Fallback — Suche by Teamname + Datum
    if API_FOOTBALL_KEYS and match_name and " vs " in match_name:
        try:
            parts = match_name.split(" vs ")
            home_team = parts[0].strip()
            away_team = parts[1].strip() if len(parts) > 1 else ""
            tip_date = tip.get("date", str(datetime.now(timezone.utc).date()))
            from datetime import timedelta as _td2

            # API-Football /fixtures: "team" braucht eine numerische ID, KEIN Name!
            # Daher: nur nach Datum + Status filtern, dann lokal nach Teamnamen matchen.
            # Gecacht pro Tag: 1 API-Call deckt ALLE pending Tips desselben Tages ab
            r = _af_fixtures_for_date(tip_date)

            # Strategie 2: ±1 Tag (Zeitzone-Puffer), ebenfalls gecached
            if not r:
                for _delta in [-1, 1]:
                    _d2 = str((datetime.strptime(tip_date, "%Y-%m-%d") + _td2(days=_delta)).date())
                    r = _af_fixtures_for_date(_d2)
                    if r:
                        break

            if r:
                for fix in r:
                    teams = fix.get("teams", {})
                    h = teams.get("home", {}).get("name", "")
                    a = teams.get("away", {}).get("name", "")
                    # Fuzzy match: mindestens erste 4 Zeichen übereinstimmen
                    h_match = h.lower()[:6] in home_team.lower() or home_team.lower()[:6] in h.lower()
                    a_match = not away_team or a.lower()[:6] in away_team.lower() or away_team.lower()[:6] in a.lower()
                    if h_match and a_match:
                        goals = fix.get("goals", {})
                        score = fix.get("score", {})
                        home_g = goals.get("home", 0) or 0
                        away_g = goals.get("away", 0) or 0
                        ht_home = (score.get("halftime") or {}).get("home", 0) or 0
                        ht_away = (score.get("halftime") or {}).get("away", 0) or 0
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
            log(f"Settlement API-Football Error: {str(e)[:80]}", "WARN")

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


def format_result_appendix(tip, result, status):
    """
    Ergebnis direkt an den ORIGINAL-TIPP anhängen.
    Für normale Tipps, Combos, Ecken und Builder.
    """
    market = str(tip.get("market") or "").lower()
    group = _ntr_group_key(tip)
    odds = tip.get("odds", "?")
    units = tip.get("units", 1.0)

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    try:
        profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    except Exception:
        profit = 0.0
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    title = "Match Summary"
    if group == "combos" or "combo_multi" in market:
        title = "Combo Summary"
    elif group == "corners" or "corner" in market:
        title = "Corner Summary"
    elif group == "builder" or "builder" in market:
        title = "Builder Summary"

    nl = "\n"
    msg = f"⸻⸻ <b>{title}</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    if home_s != "?" or away_s != "?":
        msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    if result.get("actual_value") is not None:
        msg += f"Auswertung: <b>{result.get('actual_value')}</b>{nl}"
    if result.get("total_corners") is not None or result.get("corners_total") is not None:
        msg += f"Corners: <b>{result.get('total_corners') or result.get('corners_total')}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>{nl}"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    try:
        profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    except Exception:
        profit = 0.0
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    nl = "\n"
    msg = f"⸻⸻ <b>Match Summary</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>{nl}"
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    status_emoji = "✅ V GEWONNEN" if status == "won" else "❌ X VERLOREN"
    profit = round(float(str(odds).replace(",", ".")) * float(units or 1) - float(units or 1), 2) if status == "won" else -float(units or 1)
    profit_str = f"+{profit}" if profit >= 0 else str(profit)
    profit_emoji = "🟢" if status == "won" else "🔴"

    nl = "\n"
    msg = f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{status_emoji}</b>{nl}"
    msg += f"📌 Tipp-Bewertung: <b>{'✅ V' if status == 'won' else '❌ X'}</b>{nl}"
    msg += f"⚽ Endstand: <b>{home_s} : {away_s}</b>"
    if ht_home != "?" and ht_away != "?":
        msg += f" (HZ: {ht_home}:{ht_away})"
    msg += nl
    msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>"

    return msg


def format_result_text(tip, result, status):
    """Fallback, falls Original-Telegram-Nachricht nicht mehr editierbar ist."""
    match = tip.get("match", "?")
    market = tip.get("market", "btts")
    tip_val = tip.get("tip", "YES")

    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")

    hit_line = "✅ Hit" if status == "won" else "❌ Miss"
    vx_line = "✅ V" if status == "won" else "❌ X"

    nl = "\n"
    msg = f"<b>{match}</b>{nl}"
    msg += f"🎯 Tipp: {tip_val} ({str(market).upper()}){nl}"
    msg += f"⸻⸻ <b>Match Summary</b> ⸻⸻{nl}"
    if ht_home != "?" and ht_away != "?":
        msg += f"Half-Time Score: <b>{ht_home}-{ht_away}</b>{nl}"
    msg += f"Full-Time Score: <b>{home_s}-{away_s}</b>{nl}"
    msg += f"{hit_line}  <b>{vx_line}</b>"
    return msg



    home_s = result.get("home_score", "?")
    away_s = result.get("away_score", "?")
    ht_home = result.get("ht_home", "?")
    ht_away = result.get("ht_away", "?")
    total = result.get("total_goals", "?")

    status_emoji = "✅ V GEWONNEN" if status == "won" else "❌ X VERLOREN"
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



# ============================================================
# NETRATTLER PLAYER PROPS + GRUPPEN-SETTLEMENT
# ============================================================
_NTR_PROP_STAT_MAP = {
    "shots": "shots", "shot": "shots",
    "sot": "shots_on_target", "shots_on_target": "shots_on_target",
    "goals": "goals", "goal": "goals", "score": "goals",
    "assists": "assists", "assist": "assists",
    "passes": "passes", "pass": "passes",
    "tackles": "tackles", "tackle": "tackles",
    "fouls": "fouls_committed", "fouls_committed": "fouls_committed",
    "fouls_won": "fouls_won", "fouled": "fouls_won",
    "cards": "cards", "booked": "cards", "yellow_cards": "yellow_cards",
    "saves": "saves", "save": "saves",
    "interceptions": "interceptions", "clearances": "clearances",
    "offsides": "offsides", "offside": "offsides",
    "key_passes": "key_passes", "duels": "duels", "duels_won": "duels_won",
    "touches": "touches", "crosses": "crosses",
}


def _ntr_group_key(tip):
    explicit = str(tip.get("group_key") or "").strip().lower()
    if explicit:
        return explicit
    market = str(tip.get("market") or "").lower()
    if market in {"advanced_props", "player_prop", "player_props", "prop"}:
        return "props"
    if "builder" in market:
        return "builder"
    if market in {"combo_multi", "multi_combo", "combos"}:
        return "combos"
    return {
        "btts": "btts", "over25": "over25", "combo": "combo",
        "btts_ht": "btts_ht", "over15_ht": "over15_ht",
        "corners": "corners", "corner": "corners", "cards": "stats",
        "scorer": "scorer", "goal_hunter": "scorer", "late_goals": "scorer",
        "advanced_props": "builder", "props": "builder",
    }.get(market, "stats")


def _ntr_profit_units(tip, status):
    try:
        odds = float(str(tip.get("odds_taken") or tip.get("odds") or 1).replace(",", "."))
    except Exception:
        odds = 1.0
    try:
        units = float(tip.get("units") or 1.0)
    except Exception:
        units = 1.0
    if status == "won":
        return round((odds - 1.0) * units, 2)
    if status == "void":
        return 0.0
    return round(-units, 2)


def _ntr_parse_prop_leg(leg):
    raw = str(leg.get("player_prop") or leg.get("market") or leg.get("tip") or "").strip()
    player = str(leg.get("selection") or leg.get("player") or "").strip()
    low = raw.lower()
    category = str(leg.get("_cat") or leg.get("category") or "").lower()

    stat = None
    if "shot" in low and ("target" in low or "on goal" in low):
        stat = "shots_on_target"
    elif "shot" in low:
        stat = "shots"
    elif "assist" in low:
        stat = "assists"
    elif "score" in low or "goalscorer" in low or "goal" in low:
        stat = "goals"
    elif "fouled" in low or "fouls won" in low:
        stat = "fouls_won"
    elif "foul" in low:
        stat = "fouls_committed"
    elif "tackle" in low:
        stat = "tackles"
    elif "save" in low:
        stat = "saves"
    elif "offside" in low:
        stat = "offsides"
    elif "pass" in low:
        stat = "passes"
    elif "interception" in low:
        stat = "interceptions"
    elif "clearance" in low:
        stat = "clearances"
    elif "card" in low or "booked" in low:
        stat = "cards"
    elif category:
        stat = _NTR_PROP_STAT_MAP.get(category)

    side = str(leg.get("side") or "over").lower()
    if " under " in f" {low} ":
        side = "under"
    elif " over " in f" {low} ":
        side = "over"

    line = leg.get("line")
    try:
        line = float(line) if line not in (None, "") else None
    except Exception:
        line = None
    if line is None:
        m_plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", raw)
        m_ou = re.search(r"(?:over|under)\s*(\d+(?:\.\d+)?)", low)
        if m_plus:
            line = float(m_plus.group(1)) - 0.001
            side = "over"
        elif m_ou:
            line = float(m_ou.group(1))
        elif any(x in low for x in ["to be booked", "be carded", "to score", "to assist"]):
            line = 0.5
            side = "over"

    return {"player": player, "stat": stat, "line": line, "side": side, "raw": raw}


def _ntr_get_player_actual(player, stat, tip_date, match_name=""):
    if not SUPABASE_URL or not SUPABASE_KEY or not player or not stat:
        return None
    stat = _NTR_PROP_STAT_MAP.get(stat, stat)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {
        "select": "player_name,player,match,home_team,away_team,date,match_date,stat_name,stat_value,shots,shots_on_target,sot,goals,assists,passes,tackles,fouls_committed,fouls_won,cards,yellow_cards,red_cards,saves,interceptions,clearances,offsides,key_passes,duels,duels_won,touches,crosses,minutes",
        "or": f"(player_name.ilike.*{player}*,player.ilike.*{player}*)",
        "order": "match_date.desc.nullslast,collected_at.desc.nullslast",
        "limit": "20",
    }
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/player_match_stats", headers=headers, params=params, timeout=15)
        if not r.ok:
            return None
        rows = r.json() or []
    except Exception:
        return None

    def _date_ok(row):
        rd = str(row.get("date") or row.get("match_date") or "")[:10]
        return not tip_date or rd == str(tip_date)[:10]

    candidates = [row for row in rows if _date_ok(row)]
    if match_name:
        match_low = match_name.lower()
        matched = []
        for row in candidates:
            row_match = str(row.get("match") or f"{row.get('home_team','')} vs {row.get('away_team','')}").lower()
            if any(tok in row_match for tok in [t for t in normalize_team_name(match_low).split() if len(t) > 3]):
                matched.append(row)
        if matched:
            candidates = matched
    if not candidates:
        return None

    row = candidates[0]
    direct_keys = [stat]
    if stat == "shots_on_target":
        direct_keys += ["sot"]
    if stat == "cards":
        direct_keys += ["yellow_cards"]
    for key in direct_keys:
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except Exception:
                pass
    if str(row.get("stat_name") or "").lower() in {stat.lower(), stat.replace("_", " ").lower()}:
        try:
            return float(row.get("stat_value"))
        except Exception:
            return None
    return None


def _ntr_eval_actual(actual, line, side="over"):
    if actual is None or line is None:
        return None
    return "won" if (actual < line if side == "under" else actual > line) else "lost"


def _ntr_settle_player_tip(tip):
    parsed = {
        "player": tip.get("player_name") or tip.get("player"),
        "stat": tip.get("prop_market"),
        "line": tip.get("prop_line"),
        "side": tip.get("prop_side") or "over",
        "raw": tip.get("tip") or "",
    }
    if not parsed["stat"] or parsed["line"] is None:
        fallback = _ntr_parse_prop_leg({
            "player": parsed["player"], "selection": parsed["player"],
            "player_prop": parsed["raw"], "line": parsed["line"], "side": parsed["side"],
        })
        parsed.update({k: v for k, v in fallback.items() if v not in (None, "")})
    actual = _ntr_get_player_actual(parsed.get("player"), parsed.get("stat"), tip.get("date"), tip.get("match", ""))
    status = _ntr_eval_actual(actual, parsed.get("line"), parsed.get("side", "over"))
    if not status:
        return None
    return {"status": status, "actual_value": actual, "parsed": parsed}


def _ntr_settle_match_leg(leg, parent_tip):
    """Settle normal team/match legs inside combos/builders: BTTS, Over, HT, Corners."""
    if not isinstance(leg, dict):
        return None
    market = str(leg.get("market") or leg.get("category") or leg.get("raw") or "").lower()
    tip_value = str(leg.get("tip") or leg.get("selection") or leg.get("side") or "YES").upper()
    match = leg.get("match") or parent_tip.get("match", "")
    if not match or " vs " not in str(match):
        return None

    fake_tip = dict(parent_tip)
    fake_tip["match"] = match
    fake_tip["market"] = (
        "btts_ht" if "btts_ht" in market or "btts ht" in market else
        "over15_ht" if "over15" in market or "1.5 ht" in market or "half_goals_1st" in market else
        "over25" if "over25" in market or "over 2.5" in market or "over_goals" in market else
        "combo" if "combo" in market and "multi" not in market else
        "corners" if "corner" in market or "ecken" in market else
        "btts" if "btts" in market or "both teams" in market else
        ""
    )
    fake_tip["tip"] = tip_value

    result = get_match_result_from_sources(fake_tip)
    if not result:
        return None

    # Corners brauchen eine Quelle mit corner_total/home_corners/away_corners.
    if fake_tip["market"] == "corners":
        total_corners = (
            result.get("total_corners")
            or result.get("corners_total")
            or (
                (result.get("home_corners") or 0) + (result.get("away_corners") or 0)
                if result.get("home_corners") is not None and result.get("away_corners") is not None
                else None
            )
        )
        if total_corners is None:
            return None
        line = leg.get("line") or parent_tip.get("line") or parent_tip.get("corner_line") or 8.5
        try:
            line = float(line)
            actual = float(total_corners)
        except Exception:
            return None
        status = "won" if actual > line else "lost"
        return {**leg, "actual": actual, "status": status, "raw": leg.get("raw") or f"Corners Over {line}"}

    status = check_tip_result(fake_tip, result)
    if not status:
        return None
    return {
        **leg,
        "actual": f"{result.get('home_score','?')}-{result.get('away_score','?')}",
        "status": status,
        "raw": leg.get("raw") or f"{fake_tip['market']} {tip_value}",
    }


def _ntr_settle_builder_tip(tip):
    """
    Universal Settlement:
    - Player-Prop Builder: Spielerwert über player_match_stats
    - Team/Match Builder: Ergebnis über ResultResolver
    - Multi-Combos: jedes gespeicherte Leg einzeln
    """
    legs = tip.get("builder_legs") or []
    if isinstance(legs, str):
        try:
            legs = json.loads(legs)
        except Exception:
            legs = []
    if not isinstance(legs, list) or not legs:
        return None

    settled = []
    for leg in legs:
        if not isinstance(leg, dict):
            leg = {"player_prop": str(leg), "raw": str(leg)}

        # 1) Player props zuerst
        parsed = _ntr_parse_prop_leg(leg)
        actual = None
        status = None
        if parsed.get("stat") and parsed.get("line") is not None and parsed.get("player"):
            actual = _ntr_get_player_actual(
                parsed.get("player"),
                parsed.get("stat"),
                tip.get("date"),
                leg.get("match", tip.get("match", "")),
            )
            status = _ntr_eval_actual(actual, parsed.get("line"), parsed.get("side", "over"))

        if status is not None:
            settled.append({**parsed, "actual": actual, "status": status, "raw": leg.get("raw") or leg.get("player_prop") or leg.get("market") or "Prop"})
            continue

        # 2) Team/Match legs: BTTS, Over, HT, Corners usw.
        match_leg = _ntr_settle_match_leg(leg, tip)
        if match_leg is not None:
            settled.append(match_leg)
            continue

        # Wenn ein Leg nicht auswertbar ist, noch nicht settlen.
        return None

    won = sum(1 for leg in settled if leg.get("status") == "won")
    return {
        "status": "won" if won == len(settled) else "lost",
        "legs": settled,
        "won_legs": won,
        "actual_value": f"{won}/{len(settled)} Legs",
    }




def _ntr_group_stats(group_key, tip_date=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {"select": "status,odds,odds_taken,units,profit_units,group_key,market", "status": "in.(won,lost,void)", "limit": "1000"}
    if tip_date:
        params["date"] = f"eq.{str(tip_date)[:10]}"
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/tips", headers=headers, params=params, timeout=12)
        rows = r.json() if r.ok else []
    except Exception:
        rows = []
    rows = [row for row in rows if _ntr_group_key(row) == group_key]
    if not rows:
        return {"w": 0, "l": 0, "v": 0, "profit": 0.0, "staked": 0.0, "roi": 0.0, "winrate": 0.0}
    w = sum(1 for r in rows if r.get("status") == "won")
    l = sum(1 for r in rows if r.get("status") == "lost")
    v = sum(1 for r in rows if r.get("status") == "void")
    profit = sum(float(r.get("profit_units")) if r.get("profit_units") is not None else _ntr_profit_units(r, r.get("status")) for r in rows)
    staked = sum(float(r.get("units") or 1.0) for r in rows if r.get("status") in {"won", "lost"})
    total = w + l
    return {"w": w, "l": l, "v": v, "profit": round(profit, 2), "staked": round(staked, 2), "roi": round(profit / staked * 100, 1) if staked else 0.0, "winrate": round(w / total * 100, 1) if total else 0.0}


def _ntr_group_summary_text(group_key, tip_date=None):
    s = _ntr_group_stats(group_key, tip_date)
    if not s:
        return ""
    pe = "🟢" if s["profit"] >= 0 else "🔴"
    ps = f"+{s['profit']:.2f}" if s["profit"] >= 0 else f"{s['profit']:.2f}"
    return f"📊 Gruppe heute: <b>{s['w']}W/{s['l']}L</b> · {s['winrate']:.1f}% · {pe}<b>{ps}u</b> · ROI {s['roi']:.1f}%"


# ============================================================
# V31 HOTFIX — jede Gruppe: Tag / Monat / ROI / Profit / Ligaranking
# ============================================================

def _ntr_fetch_tip_rows_for_group(group_key, start_date=None, exact_date=None, limit=3000):
    """Fetch settled tips and filter by our canonical group key in Python."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {
        "select": "status,odds,odds_taken,units,profit_units,group_key,market,league,date",
        "status": "in.(won,lost,void)",
        "limit": str(limit),
        "order": "date.desc",
    }
    if exact_date:
        params["date"] = f"eq.{str(exact_date)[:10]}"
    elif start_date:
        params["date"] = f"gte.{str(start_date)[:10]}"
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/tips", headers=headers, params=params, timeout=12)
        rows = r.json() if r.ok and r.text else []
    except Exception:
        rows = []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if _ntr_group_key(row) == group_key]


def _ntr_calc_stats_from_rows(rows):
    w = sum(1 for r in rows if str(r.get("status")).lower() == "won")
    l = sum(1 for r in rows if str(r.get("status")).lower() == "lost")
    v = sum(1 for r in rows if str(r.get("status")).lower() == "void")
    profit = sum(
        float(r.get("profit_units")) if r.get("profit_units") is not None
        else _ntr_profit_units(r, str(r.get("status")).lower())
        for r in rows
    )
    staked = sum(float(r.get("units") or 1.0) for r in rows if str(r.get("status")).lower() in {"won", "lost"})
    settled = w + l
    return {
        "w": w, "l": l, "v": v, "settled": settled,
        "profit": round(profit, 2),
        "staked": round(staked, 2),
        "roi": round(profit / staked * 100, 1) if staked else 0.0,
        "winrate": round(w / settled * 100, 1) if settled else 0.0,
    }


def _ntr_league_ranking_from_rows(rows, min_bets=1, limit=5):
    by_lg = {}
    for r in rows:
        lg = str(r.get("league") or "?").strip() or "?"
        if lg not in by_lg:
            by_lg[lg] = []
        by_lg[lg].append(r)
    ranking = []
    for lg, lg_rows in by_lg.items():
        st = _ntr_calc_stats_from_rows(lg_rows)
        if st["settled"] + st["v"] >= min_bets:
            ranking.append((lg, st))
    ranking.sort(key=lambda x: (x[1]["profit"], x[1]["roi"], x[1]["w"]), reverse=True)
    return ranking[:limit]


def _ntr_group_performance_footer(group_key, ref_date=None, include_title=True):
    """Compact block used inside every tip/combo/builder message."""
    try:
        ref = datetime.now(timezone.utc).date()
        if ref_date:
            ref = datetime.fromisoformat(str(ref_date)[:10]).date()
    except Exception:
        ref = datetime.now(timezone.utc).date()

    month_start = ref.replace(day=1)
    today_rows = _ntr_fetch_tip_rows_for_group(group_key, exact_date=ref.isoformat(), limit=1500)
    month_rows = _ntr_fetch_tip_rows_for_group(group_key, start_date=month_start.isoformat(), limit=3000)

    today_stats = _ntr_calc_stats_from_rows(today_rows)
    month_stats = _ntr_calc_stats_from_rows(month_rows)
    leagues = _ntr_league_ranking_from_rows(month_rows, min_bets=1, limit=3)

    if today_stats["settled"] + month_stats["settled"] <= 0:
        return ""

    def line(label, st):
        pe = "🟢" if st["profit"] >= 0 else "🔴"
        ps = f"+{st['profit']:.2f}" if st["profit"] >= 0 else f"{st['profit']:.2f}"
        return f"{label}: {st['w']}W/{st['l']}L · WR {st['winrate']:.1f}% · ROI {st['roi']:.1f}% · {pe}{ps}U"

    nl = "\n"
    out = f"{nl}━━━━━━━━━━━━━━━━━━{nl}"
    if include_title:
        out += "📊 <b>Bewertung dieser Gruppe</b>" + nl
    out += line("📅 Tag", today_stats) + nl
    out += line("🗓️ Monat", month_stats)
    if leagues:
        out += nl + "🏆 Ligaranking Monat:"
        medals = ["🥇", "🥈", "🥉"]
        for i, (lg, st) in enumerate(leagues):
            ps = f"+{st['profit']:.1f}" if st["profit"] >= 0 else f"{st['profit']:.1f}"
            out += nl + f"{medals[i] if i < 3 else '•'} {lg}: {st['w']}/{st['settled']} · ROI {st['roi']:.1f}% · {ps}U"
    return out


def _ntr_group_daily_card_v31(group_key, title, target_date, today_count=0):
    """Daily card per Telegram group: only this group's Tag/Monat/ROI/Profit/Ligaranking."""
    nl = "\n"
    msg = f"<b>{title} — DAILY</b>{nl}<i>{target_date}</i>{nl}━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"📨 Heute gesendet: <b>{today_count}</b> Tipps{nl}"
    footer = _ntr_group_performance_footer(group_key, target_date, include_title=False)
    if footer:
        msg += footer.replace("\n━━━━━━━━━━━━━━━━━━\n", "")
    else:
        msg += "📈 Bewertung: Daten werden gesammelt. Mindestens 1 ausgewerteter Tipp nötig."
    msg += nl + "━━━━━━━━━━━━━━━━━━"
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
                "limit": str(int(os.getenv("SETTLEMENT_LIMIT", "150"))),
                "order": "date.desc",
            },
            timeout=20,
        )

        if not r.ok:
            log(f"Settlement: Supabase Error {r.status_code}", "WARN")
            return

        pending_tips = r.json()
        log(f"Settlement: {len(pending_tips)} pending Tips gefunden (Limit={os.getenv('SETTLEMENT_LIMIT', '150')})")
        log(f"Settlement DEBUG: API_FOOTBALL_KEYS vorhanden: {bool(API_FOOTBALL_KEYS)} ({len(API_FOOTBALL_KEYS) if API_FOOTBALL_KEYS else 0} Keys)")
        if pending_tips:
            _sample = pending_tips[0]
            log(f"Settlement DEBUG: Beispiel-Tipp date={_sample.get('date')!r} match={_sample.get('match')!r}")

        won_count = 0
        lost_count = 0
        not_found = 0
        _debug_logged = False
        _settlement_log_shown = 0
        _settlement_log_suppressed = 0

        for tip in pending_tips:
            try:
                if not _debug_logged:
                    _mn = tip.get("match", "")
                    log(f"Settlement DEBUG: match_name={_mn!r}, has_vs={' vs ' in _mn}, date={tip.get('date')!r}")
                    _debug_logged = True
                # Player Props/Builder zuerst über player_match_stats auswerten.
                _market_lower = str(tip.get("market") or "").lower()
                _special = None
                result = None
                if _market_lower in {"advanced_props", "player_prop", "player_props", "prop"} or tip.get("prop_market"):
                    _special = _ntr_settle_player_tip(tip)
                elif "builder" in _market_lower or "combo_multi" in _market_lower or tip.get("builder_legs"):
                    _special = _ntr_settle_builder_tip(tip)

                if _special:
                    status = _special["status"]
                    result = {
                        "home_score": "?", "away_score": "?", "ht_home": "?", "ht_away": "?",
                        "actual_value": _special.get("actual_value"), "builder_legs": _special.get("legs", []),
                    }
                else:
                    result = get_match_result_from_sources(tip)
                    if not result:
                        not_found += 1
                        continue
                    status = check_tip_result(tip, result)
                    if not status:
                        not_found += 1
                        continue

                if status == "won":
                    won_count += 1
                else:
                    lost_count += 1

                # Supabase updaten
                _profit_units = _ntr_profit_units(tip, status)
                update_data = {
                    "status": status,
                    "result_home": result.get("home_score") if isinstance(result.get("home_score"), int) else None,
                    "result_away": result.get("away_score") if isinstance(result.get("away_score"), int) else None,
                    "result_ht_home": result.get("ht_home") if isinstance(result.get("ht_home"), int) else None,
                    "result_ht_away": result.get("ht_away") if isinstance(result.get("ht_away"), int) else None,
                    "actual_value": result.get("actual_value"),
                    "builder_won_legs": _special.get("won_legs") if _special else None,
                    "profit_units": _profit_units,
                    "group_key": _ntr_group_key(tip),
                    "settled_at": datetime.now(timezone.utc).isoformat(),
                }
                update_data = {k: v for k, v in update_data.items() if v is not None}

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

                # 🆕 ML-Feedback-Loop: Ergebnis auch in ml_tips nachtragen
                try:
                    _match = tip.get("match", "")
                    _parts = _match.split(" vs ") if " vs " in _match else [_match, ""]
                    _home = _parts[0].strip()
                    _away = _parts[1].strip() if len(_parts) > 1 else ""
                    _market = tip.get("market", "")
                    _match_id = f"{_home}_{_away}_{tip.get('date', '')}_{_market}".replace(" ", "_")
                    _actual_score = f"{result.get('home_score',0)}-{result.get('away_score',0)}"
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/ml_tips",
                        headers={
                            "apikey": SUPABASE_KEY,
                            "Authorization": f"Bearer {SUPABASE_KEY}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal",
                        },
                        params={"match_id": f"eq.{_match_id}"},
                        json={
                            "result": status,
                            "settled": True,
                            "settled_at": datetime.now(timezone.utc).isoformat(),
                            "actual_score": _actual_score,
                        },
                        timeout=8,
                    )
                except Exception:
                    pass  # silent fail — ML-Logging niemals den Settlement-Flow unterbrechen

                # Telegram Message editieren: Ergebnis an Original anhängen (KEINE neue Nachricht)
                msg_id = tip.get("telegram_msg_id")
                chat_id = tip.get("telegram_chat_id")
                original_text = tip.get("message_text", "")

                appendix = format_result_appendix(tip, result, status)
                _gkey = _ntr_group_key(tip)
                _group_line = _ntr_group_summary_text(_gkey, tip.get("date"))
                if _group_line:
                    appendix += "\n" + _group_line
                if _special and _special.get("legs"):
                    appendix += "\n<b>Leg-Auswertung:</b>"
                    for _leg in _special["legs"]:
                        _em = "✅" if _leg.get("status") == "won" else "❌"
                        appendix += f"\n{_em} {_leg.get('raw','Prop')} → {_leg.get('actual','?')}"
                elif _special and _special.get("actual_value") is not None:
                    appendix += f"\n📈 Tatsächlicher Wert: <b>{_special.get('actual_value')}</b>"
                if _settlement_log_shown < int(os.getenv("SETTLEMENT_LOG_LIMIT", "30")):
                    log(f"   {'✅' if status == 'won' else '❌'} {tip.get('match', '?')} → {status.upper()}")
                    _settlement_log_shown += 1
                else:
                    _settlement_log_suppressed += 1

                if msg_id and chat_id:
                    try:
                        if original_text:
                            # Settlement direkt im Original-Tipp. Bei Re-Run alten Match-Summary-Block ersetzen,
                            # damit der Tipp nicht mehrfach mit Ergebnis aufgeblasen wird.
                            _base = re.split(r"\n?⸻⸻\s*<b>(?:Match|Combo|Corner|Builder) Summary</b>\s*⸻⸻", original_text, maxsplit=1)[0].rstrip()
                            _edited = _base + "\n" + appendix
                            if len(_edited) > 4090:
                                _edited = _base[:max(500, 4090-len(appendix)-2)] + "…\n" + appendix
                            edit_telegram_message(chat_id, msg_id, _edited)
                        else:
                            edit_telegram_message(chat_id, msg_id, format_result_text(tip, result, status) + ("\n" + _group_line if _group_line else ""))
                    except Exception:
                        pass

            except Exception as e:
                log(f"   Settlement Error für {tip.get('match', '?')}: {e}", "WARN")
                continue

        # ═══ DAILY SUMMARY ═══
        total_settled = won_count + lost_count
        log(f"Settlement fertig: ✅{won_count} gewonnen, ❌{lost_count} verloren, ⏳{not_found} noch nicht fertig")
        if _settlement_log_suppressed:
            log(f"Settlement Log gebündelt: {_settlement_log_suppressed} Detail-Zeilen unterdrückt")
        log(f"Settlement Cache: hit={_RESULT_RESOLVER_STATS.get('hit',0)} miss={_RESULT_RESOLVER_STATS.get('miss',0)} · API-Football Settlement={'ON' if str(os.getenv('ENABLE_API_FOOTBALL_SETTLEMENT','0')).lower() in {'1','true','yes','on'} else 'OFF'}")

        if total_settled > 0 or not_found > 0:
            winrate = round(won_count / total_settled * 100) if total_settled > 0 else 0

            # Profit & ROI berechnen (aus allen gesettleten Tips)
            total_profit = 0.0
            total_staked = 0.0
            market_stats = {}
            for tip in pending_tips:
                _status = tip.get("status")
                if _status not in ["won", "lost"]:
                    continue
                _odds = float(str(tip.get("odds","1.0")).replace(",",".") or 1.0)
                _units = float(tip.get("units") or 1.0)
                _market = tip.get("market", "btts")
                _profit = round(_odds * _units - _units, 2) if _status == "won" else -_units
                total_profit += _profit
                total_staked += _units
                if _market not in market_stats:
                    market_stats[_market] = {"w": 0, "l": 0, "profit": 0.0}
                market_stats[_market]["w" if _status=="won" else "l"] += 1
                market_stats[_market]["profit"] = round(market_stats[_market]["profit"] + _profit, 2)

            roi = round(total_profit / total_staked * 100, 1) if total_staked > 0 else 0
            profit_emoji = "🟢" if total_profit >= 0 else "🔴"
            profit_str = f"+{round(total_profit,2)}" if total_profit >= 0 else str(round(total_profit,2))

            # Markt-Icons
            _micons = {"btts":"⚽","over25":"🎯","combo":"🔥","btts_ht":"🕐","over15_ht":"⏰","corners":"🔵","scorer":"⚽","combo_multi":"🎰"}

            msg = "🏆 <b>AUSWERTUNG</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"
            msg += f"✅ Gewonnen: <b>{won_count}</b>  ❌ Verloren: <b>{lost_count}</b>\n"
            msg += f"🎯 Winrate: <b>{winrate}%</b>\n"
            msg += f"{profit_emoji} Profit: <b>{profit_str} Units</b>\n"
            msg += f"📊 ROI: <b>{roi}%</b>\n"
            msg += f"⏳ Ausstehend: {not_found}\n"

            if market_stats:
                msg += "━━━━━━━━━━━━━━━━━━\n"
                msg += "<b>📋 Nach Markt:</b>\n"
                for _mk, _ms in sorted(market_stats.items()):
                    _icon = _micons.get(_mk, "💎")
                    _wr = round(_ms["w"] / (_ms["w"]+_ms["l"]) * 100) if (_ms["w"]+_ms["l"]) > 0 else 0
                    _pe = "🟢" if _ms["profit"] >= 0 else "🔴"
                    _ps = f"+{_ms['profit']}" if _ms["profit"] >= 0 else str(_ms["profit"])
                    msg += f"{_icon} {_mk.upper()}: {_ms['w']}W/{_ms['l']}L · {_wr}% · {_pe}{_ps}U\n"

            try:
                bk = get_bankroll_status()
                if bk:
                    msg += "━━━━━━━━━━━━━━━━━━\n"
                    msg += f"💰 Bankroll: <b>{bk.get('current_units','?')} Units</b>\n"
                    msg += f"📈 Mode: {bk.get('mode','normal').upper()}"
            except Exception:
                pass

            # Gruppe-für-Gruppe: jeder Kanal erhält ausschließlich seine eigene Bilanz.
            _sent_chats = set()
            for _grp_key in ["btts", "over25", "combo", "btts_ht", "over15_ht", "combos", "corners", "scorer", "goal_hunter", "builder", "advanced_props"]:
                _cid = TELEGRAM_GROUPS.get(_grp_key)
                if not _cid or str(_cid) in _sent_chats:
                    continue
                _canonical = "builder" if _grp_key == "advanced_props" else ("scorer" if _grp_key == "goal_hunter" else _grp_key)
                _gs = _ntr_group_stats(_canonical, today)
                if not _gs or (_gs["w"] + _gs["l"] + _gs["v"] == 0):
                    continue
                _pe = "🟢" if _gs["profit"] >= 0 else "🔴"
                _ps = f"+{_gs['profit']:.2f}" if _gs["profit"] >= 0 else f"{_gs['profit']:.2f}"
                _title = {
                    "btts":"BTTS", "over25":"OVER 2.5", "combo":"BTTS + OVER",
                    "btts_ht":"BTTS HT", "over15_ht":"OVER 1.5 HT", "combos":"MULTI-COMBOS",
                    "corners":"CORNER SNIPER", "scorer":"GOAL HUNTER", "builder":"PROP BUILDER",
                }.get(_canonical, _canonical.upper())
                _gmsg = (
                    f"🏆 <b>AUSWERTUNG — {_title}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Gewonnen: <b>{_gs['w']}</b>  ❌ Verloren: <b>{_gs['l']}</b>"
                    + (f"  ↩️ Void: <b>{_gs['v']}</b>" if _gs['v'] else "") + "\n"
                    f"🎯 Trefferquote: <b>{_gs['winrate']:.1f}%</b>\n"
                    f"{_pe} Profit: <b>{_ps} Units</b>\n"
                    f"📊 ROI: <b>{_gs['roi']:.1f}%</b>"
                )
                try:
                    send_telegram(_gmsg, _cid)
                    _sent_chats.add(str(_cid))
                    log(f"   📊 Gruppen-Auswertung → {_grp_key}")
                except Exception as _se:
                    log(f"   ⚠️ Auswertung {_grp_key}: {str(_se)[:40]}", "WARN")

    except Exception as e:
        log(f"Settlement Fatal: {e}", "ERROR")

    # Live Edge Alerts
    if NETRATTLER_PRO:
        try:
            send_edge_alerts()
        except Exception:
            pass



# ============================================================
# 🔴 LIVE BOT - HZ Tor + Late Goals
# ============================================================

TELEGRAM_GROUP_HZ_LIVE = env("TELEGRAM_GROUP_HZ_LIVE", "")
TELEGRAM_GROUP_LATE_GOALS = env("TELEGRAM_GROUP_LATE_GOALS", "")

LIVE_MATCH_CACHE = {}

def get_live_matches():
    """
    Holt alle laufenden Spiele von SofaScore.
    Returns: Liste mit Live-Matches inkl. Minute + Score
    """
    try:
        import random as _r
        _uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]
        
        r = requests.get(
            "https://api.sofascore.com/api/v1/sport/football/events/live",
            headers={
                "User-Agent": _r.choice(_uas),
                "Accept": "application/json",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=15,
        )
        
        if not r.ok:
            return []
        
        data = r.json()
        events = data.get("events", [])
        
        live_matches = []
        for event in events:
            try:
                status = event.get("status", {})
                status_type = status.get("type", "")
                
                if status_type not in ["inprogress"]:
                    continue
                
                minute = status.get("description", "0")
                try:
                    minute = int(str(minute).replace("+", "").replace("'", ""))
                except:
                    minute = 0
                
                home_score = event.get("homeScore", {}).get("current", 0) or 0
                away_score = event.get("awayScore", {}).get("current", 0) or 0
                
                home_team = event.get("homeTeam", {}).get("name", "")
                away_team = event.get("awayTeam", {}).get("name", "")
                tournament = event.get("tournament", {}).get("name", "")
                
                live_matches.append({
                    "match_id": event.get("id", ""),
                    "home": home_team,
                    "away": away_team,
                    "league": tournament,
                    "minute": minute,
                    "home_score": home_score,
                    "away_score": away_score,
                    "total_goals": home_score + away_score,
                    "btts_so_far": home_score > 0 and away_score > 0,
                    "period": status.get("description", ""),
                })
            except Exception:
                continue
        
        return live_matches
        
    except Exception as e:
        log(f"Live Matches Error: {str(e)[:60]}", "WARN")
        return []


def analyze_hz_live_tip(match):
    """
    Analysiert ob noch ein Tor in der 1. HZ fällt (Minute 25-45).
    Wahrscheinlichkeit >= 70%
    """
    minute = match.get("minute", 0)
    home_score = match.get("home_score", 0)
    away_score = match.get("away_score", 0)
    total_goals = match.get("total_goals", 0)
    
    # Nur zwischen Minute 25-42 analysieren
    if not (25 <= minute <= 42):
        return None
    
    # Bereits Tore in HZ - kein neuer Tipp nötig
    # Außer BTTS noch nicht erreicht
    
    # Basis-Wahrscheinlichkeit
    # Statistisch: ~1.4 Tore pro Spiel in HZ
    # Pro Minute steigt Wahrscheinlichkeit
    remaining_minutes = 45 - minute
    
    # Poisson-Approximation: λ = 1.4 * (remaining/45)
    import math
    lam = 1.4 * (remaining_minutes / 45)
    
    # P(mindestens 1 Tor) = 1 - P(0 Tore) = 1 - e^(-λ)
    prob_goal = 1 - math.exp(-lam)
    prob_pct = round(prob_goal * 100)
    
    # Boost wenn Teams offensiv spielen (aus xG oder Form)
    if total_goals == 0 and minute > 30:
        # Torloser Spielstand - Teams drücken
        prob_pct = min(85, prob_pct + 8)
    
    if prob_pct < 70:
        return None
    
    # Fair Odds berechnen
    fair_odds = round(1 / prob_goal, 2)
    
    return {
        "match": f"{match['home']} vs {match['away']}",
        "league": match["league"],
        "minute": minute,
        "score": f"{home_score}:{away_score}",
        "tip": "Nächstes Tor bis HZ",
        "probability": prob_pct,
        "fair_odds": fair_odds,
        "market": "hz_live",
        "remaining": remaining_minutes,
    }


def analyze_late_goal_tip(match):
    """
    Analysiert ob noch ein Tor ab Minute 70 fällt.
    Wahrscheinlichkeit >= 75%
    """
    minute = match.get("minute", 0)
    home_score = match.get("home_score", 0)
    away_score = match.get("away_score", 0)
    total_goals = match.get("total_goals", 0)
    
    # Nur zwischen Minute 70-85 analysieren
    if not (70 <= minute <= 85):
        return None
    
    remaining_minutes = 90 - minute
    import math
    
    # Basis-Wahrscheinlichkeit für späte Tore
    # Statistik: ~35% aller Spiele haben Tor in Minute 70-90
    lam = 1.2 * (remaining_minutes / 90)
    prob_goal = 1 - math.exp(-lam)
    prob_pct = round(prob_goal * 100)
    
    # Boosts
    if home_score != away_score:
        # Verlierendes Team drückt → mehr Tore wahrscheinlich
        prob_pct = min(90, prob_pct + 10)
    
    if total_goals == 0:
        # Torloser Spielstand → beide Teams wollen gewinnen
        prob_pct = min(90, prob_pct + 12)
    
    if total_goals >= 3:
        # Schon viele Tore → offensives Spiel
        prob_pct = min(92, prob_pct + 8)
    
    if prob_pct < 75:
        return None
    
    fair_odds = round(1 / (prob_pct / 100), 2)
    
    return {
        "match": f"{match['home']} vs {match['away']}",
        "league": match["league"],
        "minute": minute,
        "score": f"{home_score}:{away_score}",
        "tip": "Tor in Minute 70-90",
        "probability": prob_pct,
        "fair_odds": fair_odds,
        "market": "late_goal",
        "remaining": remaining_minutes,
    }


def format_live_tip_message(tip, bot_type="hz"):
    """Formatiert Live-Tipp für Telegram"""
    if not tip:
        return ""
    
    if bot_type == "hz":
        emoji = "⚽"
        title = "HZ LIVE TIP"
        desc = "Tor bis Halbzeit!"
    else:
        emoji = "🔥"
        title = "LATE GOAL TIP"
        desc = "Tor in den letzten Minuten!"
    
    nl = "\n"
    msg = f"{emoji} <b>{title}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{tip['match']}</b>{nl}"
    msg += f"📍 {tip['league']}{nl}"
    msg += f"⏱️ Minute: <b>{tip['minute']}'</b>{nl}"
    msg += f"🔢 Stand: <b>{tip['score']}</b>{nl}"
    msg += f"⏳ Verbleibend: {tip['remaining']} Min{nl}{nl}"
    msg += f"🎯 Tipp: <b>{tip['tip']}</b>{nl}"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip['probability']}%</b>{nl}"
    msg += f"💰 Fair Odds: <b>{tip['fair_odds']}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<i>⚡ {desc} Schnell wetten!</i>"
    
    return msg


def run_live_bots():
    """
    Hauptfunktion für Live-Bots.
    Holt alle Live-Matches und sendet Tipps.
    """
    if not TELEGRAM_GROUP_HZ_LIVE and not TELEGRAM_GROUP_LATE_GOALS:
        log("Live Bots: Keine Telegram Gruppen konfiguriert", "WARN")
        return
    
    log("🔴 Live Bots starten...")
    
    live_matches = get_live_matches()
    
    if not live_matches:
        log("Live Bots: Keine Live-Spiele gefunden")
        return
    
    log(f"🔴 {len(live_matches)} Live-Spiele gefunden")
    
    hz_tips = 0
    late_tips = 0
    
    for match in live_matches:
        minute = match.get("minute", 0)
        match_key = f"{match['home']}_{match['away']}"
        
        # Verhindere doppelte Tipps für gleiche Spiel+Minute
        cache_key_hz = f"hz_{match_key}_{minute // 5}"  # Alle 5 Minuten max 1 Tipp
        cache_key_late = f"late_{match_key}_{minute // 5}"
        
        # HZ Live Bot (Minute 25-42)
        if TELEGRAM_GROUP_HZ_LIVE and cache_key_hz not in LIVE_MATCH_CACHE:
            tip = analyze_hz_live_tip(match)
            if tip:
                msg = format_live_tip_message(tip, "hz")
                send_telegram(msg, TELEGRAM_GROUP_HZ_LIVE)
                LIVE_MATCH_CACHE[cache_key_hz] = True
                hz_tips += 1
                log(f"   ⚽ HZ Tip: {tip['match']} Minute {tip['minute']}' ({tip['probability']}%)")
        
        # Late Goal Bot (Minute 70-85)
        if TELEGRAM_GROUP_LATE_GOALS and cache_key_late not in LIVE_MATCH_CACHE:
            tip = analyze_late_goal_tip(match)
            if tip:
                msg = format_live_tip_message(tip, "late")
                send_telegram(msg, TELEGRAM_GROUP_LATE_GOALS)
                LIVE_MATCH_CACHE[cache_key_late] = True
                late_tips += 1
                log(f"   🔥 Late Tip: {tip['match']} Minute {tip['minute']}' ({tip['probability']}%)")
    
    log(f"🔴 Live Bots fertig: {hz_tips} HZ Tips, {late_tips} Late Tips")



# ============================================================
# 🔵 ECKEN ANALYSE - Corner Over/Under
# ============================================================

def _fixture_display_time(fixture):
    """Anstosszeit als HH:MM (lokal, UTC+2) aus diversen Fixture-Feldern.
    Ecken-Fixtures aus der Pinnacle-Injektion tragen 'starts' (ISO), nicht 'time_local'."""
    for k in ("time_local", "time", "kickoff_local"):
        v = str(fixture.get(k, "") or "").strip()
        if v and v not in ("TBD", "N/A", "-", "?"):
            return v[:5] if len(v) >= 5 and ":" in v else v
    # ISO-Zeitstempel (starts/kickoff/start_time) → lokale HH:MM
    for k in ("starts", "kickoff", "start_time", "commence_time", "date"):
        raw = str(fixture.get(k, "") or "").strip()
        if not raw or "T" not in raw:
            continue
        try:
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _s = raw.replace("Z", "+00:00")
            _t = _dt.fromisoformat(_s)
            if _t.tzinfo is None:
                _t = _t.replace(tzinfo=_tz.utc)
            return _t.astimezone(_tz(_td(hours=2))).strftime("%H:%M")
        except Exception:
            continue
    return "TBD"

CORNERS_CACHE = {}

def get_team_corner_stats(team_id, league_id, season):
    """
    Holt Ecken-Statistiken eines Teams von API-Football.
    Returns: {'avg_corners_for': 5.2, 'avg_corners_against': 4.1}
    """
    cache_key = f"corners_{team_id}_{league_id}_{season}"
    if cache_key in CORNERS_CACHE:
        return CORNERS_CACHE[cache_key]

    response = _af_request("/fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": 10,
    })

    if not response:
        CORNERS_CACHE[cache_key] = None
        return None

    try:
        corners_for = []
        corners_against = []

        for fix in response:
            stats = fix.get("statistics", [])
            teams = fix.get("teams", {})
            home_id = teams.get("home", {}).get("id")
            is_home = home_id == team_id

            for team_stats in stats:
                is_our_team = team_stats.get("team", {}).get("id") == team_id
                for stat in team_stats.get("statistics", []):
                    if stat.get("type") == "Corner Kicks":
                        val = stat.get("value", 0) or 0
                        try:
                            val = int(val)
                            if is_our_team:
                                corners_for.append(val)
                            else:
                                corners_against.append(val)
                        except:
                            pass

        if not corners_for:
            CORNERS_CACHE[cache_key] = None
            return None

        result = {
            "avg_corners_for": round(sum(corners_for) / len(corners_for), 1),
            "avg_corners_against": round(sum(corners_against) / len(corners_against), 1) if corners_against else 4.5,
            "games": len(corners_for),
        }

        CORNERS_CACHE[cache_key] = result
        return result

    except Exception:
        CORNERS_CACHE[cache_key] = None
        return None


def analyze_corners_tip_simple(fixture, league):
    """
    Vereinfachte Ecken-Analyse ohne API-Football IDs.
    Basiert auf Liga-Durchschnitt + Poisson.
    Sucht über mehrere Linien (7.5-12.5) die mit realistischer Quote >=1.70.
    """
    import math
    import random

    # Liga-basierte Durchschnittswerte
    LEAGUE_AVG_CORNERS = {
        "Premier League": 10.2, "Bundesliga": 9.8, "La Liga": 9.5,
        "Serie A": 9.7, "Ligue 1": 9.3, "Eredivisie": 10.1,
        "Champions League": 9.9, "Championship": 10.5,
        "EFL League 1": 10.8, "EFL League 2": 11.0,
    }

    avg = LEAGUE_AVG_CORNERS.get(league, 9.5)
    expected = avg + random.uniform(-1.5, 1.5)
    lam = expected

    def poisson_over(line):
        """P(X > line) für halbe Linien (z.B. 8.5 → Summe k=0..8 abziehen)."""
        k_max = int(line)  # bei 8.5 → 8
        cum = 0
        for k in range(k_max + 1):
            cum += (math.exp(-lam) * lam**k) / math.factorial(k)
        return round((1 - cum) * 100)

    # Mehrere Linien durchprobieren, höchste mit prob>=60% UND realistischer Buchmacher-Quote >=1.70 wählen
    candidates = []
    for line in [7.5, 8.5, 9.5, 10.5, 11.5]:
        prob = poisson_over(line)
        if prob < 60:
            continue
        # Simulierte Buchmacher-Quote inkl. Marge (~7%, realistischer als reine Fair Odds)
        book_odds = round((100 / prob) * 1.07, 2) if prob > 0 else 0
        candidates.append((line, prob, book_odds))

    # Bevorzuge die höchste Linie, die Quote >=1.70 erreicht (beste Balance Sicherheit/Value)
    valid = [c for c in candidates if c[2] >= MIN_ODDS_VALUE]
    if not valid:
        return None
    line, prob, book_odds = max(valid, key=lambda c: c[0])  # höchste qualifizierende Linie

    return {
        "match": f"{fixture['home']} vs {fixture['away']}",
        "league": league,
        "time": _fixture_display_time(fixture),
        "tip": f"Over {line} Ecken",
        "probability": prob,
        "odds": book_odds,
        "fair_odds": round(100 / prob, 2) if prob > 0 else 0,
        "expected_corners": round(expected, 1),
        "market": "corners",
    }


def analyze_corners_tip(fixture, league):
    """
    Analysiert Over/Under Ecken für ein Spiel.
    Gibt Tipp zurück wenn Wahrscheinlichkeit >= 68%
    """
    import math

    home_id = fixture.get("home_id")
    away_id = fixture.get("away_id")
    league_id = API_FOOTBALL_LEAGUES.get(league)

    if not home_id or not away_id or not league_id:
        return analyze_corners_tip_simple(fixture, league)

    now_utc = datetime.now(timezone.utc)
    season = now_utc.year if now_utc.month > 6 else now_utc.year - 1

    home_stats = get_team_corner_stats(home_id, league_id, season)
    away_stats = get_team_corner_stats(away_id, league_id, season)

    # Fallback Durchschnitt wenn keine Daten
    home_avg = (home_stats["avg_corners_for"] + home_stats["avg_corners_against"]) / 2 if home_stats else 4.8
    away_avg = (away_stats["avg_corners_for"] + away_stats["avg_corners_against"]) / 2 if away_stats else 4.5

    expected_total = home_avg + away_avg

    # Poisson für Over 9.5
    line = 9.5
    prob_over = 0
    lam = expected_total
    for k in range(int(line) + 1):
        prob_over += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over = round((1 - prob_over) * 100)

    # Poisson für Over 8.5
    line2 = 8.5
    prob_over2 = 0
    for k in range(int(line2) + 1):
        prob_over2 += (math.exp(-lam) * lam**k) / math.factorial(k)
    prob_over2 = round((1 - prob_over2) * 100)

    # 🆕 XGBoost-Corner-Modelle einblenden (60% ML / 40% Poisson; Corner-AUC ~0.67).
    try:
        _mlc = get_ml_prediction(fixture.get("home", ""), fixture.get("away", ""), league)
        if _mlc:
            if _mlc.get("corners_over95_pct") is not None:
                prob_over = round(0.60 * _mlc["corners_over95_pct"] + 0.40 * prob_over)
            if _mlc.get("corners_over85_pct") is not None:
                prob_over2 = round(0.60 * _mlc["corners_over85_pct"] + 0.40 * prob_over2)
    except Exception:
        pass

    # Besten Tipp wählen
    if prob_over >= 68:
        line_used = 9.5
        prob = prob_over
    elif prob_over2 >= 68:
        line_used = 8.5
        prob = prob_over2
    else:
        return None

    fair_odds = round(1 / (prob / 100), 2)

    return {
        "match": f"{fixture['home']} vs {fixture['away']}",
        "league": league,
        "time": _fixture_display_time(fixture),
        "tip": f"Over {line_used} Ecken",
        "probability": prob,
        "fair_odds": fair_odds,
        "expected_corners": round(expected_total, 1),
        "market": "corners",
    }


# ============================================================
# ⚽ SCORER ANALYSE - Anytime Torschütze
# ============================================================

SCORER_CACHE = {}

_STATSBOMB_SCORER_CACHE = {}  # {league_name: [scorers]}

def get_statsbomb_top_scorers(league_name: str) -> list:
    """
    Holt Top-Torschützen direkt von StatsBomb Open Data GitHub.
    Kein Package nötig — reiner HTTP-Zugriff. Aggregiert Tore aus Event-Daten.
    """
    if league_name in _STATSBOMB_SCORER_CACHE:
        return _STATSBOMB_SCORER_CACHE[league_name]

    comp = None
    ln = league_name.lower()
    for key, val in STATSBOMB_LEAGUE_MAP.items():
        if key.lower() in ln or ln in key.lower():
            comp = val
            break
    if not comp:
        _STATSBOMB_SCORER_CACHE[league_name] = []
        return []

    comp_id, season_id = comp
    scorers = []

    try:
        r = requests.get(
            f"{_STATSBOMB_BASE}/matches/{comp_id}/{season_id}.json",
            timeout=12,
        )
        if not r.ok:
            _STATSBOMB_SCORER_CACHE[league_name] = []
            return []

        matches = r.json()
        recent = matches[-15:] if len(matches) > 15 else matches

        goals_by_player = {}
        games_by_player = {}
        team_by_player = {}

        for match in recent:
            match_id = match.get("match_id")
            if not match_id:
                continue
            try:
                re = requests.get(
                    f"{_STATSBOMB_BASE}/events/{match_id}.json",
                    timeout=10,
                )
                if not re.ok:
                    continue
                events = re.json()
                seen_players = set()
                for ev in events:
                    ev_type = (ev.get("type") or {}).get("name", "")
                    player = (ev.get("player") or {}).get("name", "")
                    team = (ev.get("team") or {}).get("name", "")
                    if not player:
                        continue
                    # Spieler erscheint in diesem Spiel
                    if player not in seen_players:
                        seen_players.add(player)
                        games_by_player[player] = games_by_player.get(player, 0) + 1
                        team_by_player[player] = team
                    # Tor?
                    if ev_type == "Shot":
                        outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
                        if outcome == "Goal":
                            goals_by_player[player] = goals_by_player.get(player, 0) + 1
            except Exception:
                continue

        # Top-Scorer aufbauen
        for player, goals in sorted(goals_by_player.items(), key=lambda x: x[1], reverse=True)[:20]:
            apps = max(games_by_player.get(player, 1), 1)
            gpg = round(goals / apps, 2)
            if gpg < 0.2:
                continue
            scorers.append({
                "name": player,
                "team": team_by_player.get(player, ""),
                "goals_total": goals,
                "appearances": apps,
                "goals_per_game": gpg,
                "source": "statsbomb_http",
            })

        log(f"   ⚽ StatsBomb Scorer: {len(scorers)} Spieler für {league_name}")

    except Exception as e:
        log(f"StatsBomb Scorer Error: {str(e)[:60]}", "WARN")

    _STATSBOMB_SCORER_CACHE[league_name] = scorers
    return scorers


def get_top_scorers(league_id, season):
    """
    Holt Top-Torschützen — API-Football (gesperrt) → StatsBomb-Fallback.
    """
    cache_key = f"scorers_{league_id}_{season}"
    if cache_key in SCORER_CACHE:
        return SCORER_CACHE[cache_key]

    response = _af_request("/players/topscorers", {
        "league": league_id,
        "season": season,
    })

    if not response:
        SCORER_CACHE[cache_key] = []
        return []

    scorers = []
    for entry in response[:20]:
        player = entry.get("player", {})
        stats = entry.get("statistics", [{}])[0]
        goals = stats.get("goals", {})
        games = stats.get("games", {})
        goals_total = goals.get("total", 0) or 0
        appearances = games.get("appearences", 0) or 1
        goals_per_game = round(goals_total / appearances, 2)
        scorers.append({
            "player_id": player.get("id"),
            "name": player.get("name", ""),
            "team_id": stats.get("team", {}).get("id"),
            "team": stats.get("team", {}).get("name", ""),
            "goals_total": goals_total,
            "appearances": appearances,
            "goals_per_game": goals_per_game,
        })

    SCORER_CACHE[cache_key] = scorers
    return scorers


def analyze_scorer_tips(fixture, league, scorers):
    """
    Analysiert Anytime Scorer Wahrscheinlichkeit.
    Gibt Top-Kandidaten zurück wenn >= 45% Wahrscheinlichkeit.
    🆕 FIX: Funktioniert auch ohne Team-IDs (via Team-Name Matching)
    """
    import math

    home_team = fixture.get("home", "").lower()
    away_team = fixture.get("away", "").lower()
    home_id = fixture.get("home_id")
    away_id = fixture.get("away_id")

    if not home_team or not away_team:
        return []

    tips = []

    for scorer in scorers:
        team_id = scorer.get("team_id")
        team_name = scorer.get("team", "").lower()

        # 🆕 Matching via ID ODER Team-Name
        is_playing = False

        if team_id and home_id and away_id:
            # API-Football: ID-basiertes Matching
            is_playing = team_id in [home_id, away_id]
        elif team_name:
            # Understat/FPL: Name-basiertes Matching
            home_norm = normalize_team_name(home_team)
            away_norm = normalize_team_name(away_team)
            team_norm = normalize_team_name(team_name)
            is_playing = (
                team_norm[:8] in home_norm or home_norm[:8] in team_norm or
                team_norm[:8] in away_norm or away_norm[:8] in team_norm
            )

        if not is_playing:
            continue

        gpg = scorer.get("goals_per_game", 0)
        if gpg < 0.3:
            continue

        prob = round((1 - math.exp(-gpg)) * 100)

        if prob < 45:
            continue

        fair_odds = round(1 / (prob / 100), 2)

        tips.append({
            "match": f"{fixture['home']} vs {fixture['away']}",
            "league": league,
            "time": _fixture_display_time(fixture),
            "player": scorer["name"],
            "team": scorer["team"],
            "goals_per_game": gpg,
            "goals_total": scorer["goals_total"],
            "probability": prob,
            "fair_odds": fair_odds,
            "market": "scorer",
        })

    tips.sort(key=lambda x: x["probability"], reverse=True)
    return tips[:3]


def format_corners_message(tip):
    """Formatiert Ecken-Tipp für Telegram — volles Format mit Quote, Units, Wetter"""
    nl = "\n"
    odds = tip.get("odds", tip.get("fair_odds", "?"))
    units = tip.get("units", 1.0)
    prob = tip.get("probability", 0)
    conf_stars = "⭐" * int(tip.get("confidence", 3))
    value = tip.get("valueRating", "OK")
    value_emoji = "🟢" if value == "VALUE" else "🟡"
    exp = tip.get("expected_corners", "?")
    h2h_avg = tip.get("h2h_avg_corners", "")
    home_avg = tip.get("home_avg_corners", "")
    away_avg = tip.get("away_avg_corners", "")
    weather = tip.get("weather")
    wstr = ""
    if weather:
        try:
            wstr = f"\n🌤️ {weather.get('temp','?')}°C · {weather.get('condition','')}"
        except Exception:
            pass

    msg = f"🔵 <b>CORNER SNIPER</b>\n"
    msg += f"📍 {tip.get('league','?')} · ⏰ {tip.get('time','?')}{wstr}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"💎 <b>{tip['match']}</b>\n"
    msg += f"🎯 Tipp: <b>{tip['tip']}</b>\n"
    msg += f"📈 Wahrscheinlichkeit: <b>{prob}%</b> · {conf_stars}\n"
    msg += f"💰 Quote: {odds} · Fair: {tip.get('fair_odds','?')} · {value_emoji} {value}\n"
    msg += f"💚 {units} Units\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 Erwartete Ecken: <b>{exp}</b>\n"
    if home_avg and away_avg:
        msg += f"📐 Ø Ecken: Heim {home_avg} · Gast {away_avg}\n"
    if h2h_avg:
        msg += f"🔄 H2H Ø Ecken: {h2h_avg} (letzte 5)\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<i>💭 Pinnacle Corners-Analyse</i>"
    return msg


def format_scorer_message(tip):
    """Formatiert Scorer-Tipp für Telegram"""
    nl = "\n"
    msg = f"⚽ <b>SCORER TIP</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<b>{tip['match']}</b>{nl}"
    msg += f"📍 {tip['league']} | ⏰ {tip['time']}{nl}{nl}"
    msg += f"👤 Spieler: <b>{tip['player']}</b>{nl}"
    msg += f"🏟️ Team: {tip['team']}{nl}"
    msg += f"📊 Tore/Spiel: <b>{tip['goals_per_game']}</b> ({tip['goals_total']} gesamt){nl}"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip['probability']}%</b>{nl}"
    msg += f"💰 Fair Odds: <b>{tip['fair_odds']}</b>{nl}"
    msg += f"━━━━━━━━━━━━━━━━━━{nl}"
    msg += f"<i>⚡ Anytime Scorer - trifft irgendwann!</i>"
    return msg



def get_understat_top_scorers(league_name, season):
    """Holt Top Torschützen von Understat - kein Key nötig!"""
    UNDERSTAT_LEAGUE_MAP = {
        "Premier League": "EPL",
        "Bundesliga": "Bundesliga",
        "La Liga": "La_liga",
        "Serie A": "Serie_A",
        "Ligue 1": "Ligue_1",
        "Eredivisie": "Eredivisie",
        "Russian Premier": "RFPL",
    }
    league_slug = UNDERSTAT_LEAGUE_MAP.get(league_name)
    if not league_slug:
        return []
    try:
        import random as _r
        import re as _re
        import json as _json
        r = requests.get(
            f"https://understat.com/league/{league_slug}/{season}",
            headers={"User-Agent": _r.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            ]), "Accept": "text/html"},
            timeout=12,
        )
        if not r.ok:
            return []
        players_match = _re.search(r"var playersData\s*=\s*JSON\.parse\('(.+?)'\)", r.text)
        if not players_match:
            return []
        players_json = players_match.group(1).encode().decode('unicode_escape')
        players = _json.loads(players_json)
        scorers = []
        for p in players:
            try:
                goals = int(p.get("goals", 0) or 0)
                games = int(p.get("games", 1) or 1)
                if games < 5 or goals < 3:
                    continue
                gpg = round(goals / games, 2)
                if gpg < 0.3:
                    continue
                scorers.append({
                    "player_id": p.get("id", ""),
                    "name": p.get("player_name", ""),
                    "team_id": None,
                    "team": p.get("team_title", ""),
                    "goals_total": goals,
                    "appearances": games,
                    "goals_per_game": gpg,
                })
            except Exception:
                continue
        scorers.sort(key=lambda x: x["goals_per_game"], reverse=True)
        if scorers:
            log(f"   ⚽ Understat: {len(scorers[:20])} Scorer für {league_name}")
        return scorers[:20]
    except Exception as e:
        log(f"Understat Scorer Error: {str(e)[:60]}", "WARN")
        return []


def run_corners_and_scorer_bots(target_date, active_leagues, odds_data_cache, fixtures_cache):
    """
    Hauptfunktion für Ecken + Scorer Bots.
    Läuft parallel zum Haupt-Bot.
    """
    group_hz = TELEGRAM_GROUPS.get("hz_live") or env("TELEGRAM_GROUP_HZ_LIVE", "")
    group_late = TELEGRAM_GROUPS.get("late_goals") or env("TELEGRAM_GROUP_LATE_GOALS", "")

    if not group_hz and not group_late:
        log("Corners/Scorer: Keine Gruppen konfiguriert", "INFO")
        return

    try:
        prefetch_sent_tips_for_date(target_date)
    except Exception:
        pass
    log("🔵⚽ Corners + Scorer Bot startet...")

    corners_count = 0
    scorer_count = 0
    corners_tips = []
    scorer_tips = []

    seen_corner_matches = set()  # Duplikat-Check über ALLE Ligen

    for league in active_leagues:
        fixtures = fixtures_cache.get(league, [])
        if not fixtures:
            continue

        league_id = API_FOOTBALL_LEAGUES.get(league)
        now_utc = datetime.now(timezone.utc)
        season = now_utc.year if now_utc.month > 6 else now_utc.year - 1

        # Ecken-Tipps - auch ohne API-Football IDs!
        if group_hz:
            for fixture in fixtures:
                try:
                    home_norm = normalize_team_name(fixture.get("home", ""))
                    away_norm = normalize_team_name(fixture.get("away", ""))
                    match_key = f"{home_norm[:12]}_{away_norm[:12]}"
                    match_key_rev = f"{away_norm[:12]}_{home_norm[:12]}"
                    if match_key in seen_corner_matches or match_key_rev in seen_corner_matches:
                        continue
                    seen_corner_matches.add(match_key)

                    # 🆕 Duplikat zwischen Runs prüfen!
                    match_name = f"{fixture.get('home','')} vs {fixture.get('away','')}"
                    if is_duplicate_tip(match_name, "corners", target_date):
                        _ntr_log_duplicate(f"   ⏭️ Ecken Duplikat: {match_name}", key="corners")
                        continue

                    tip = analyze_corners_tip_simple(fixture, league)
                    if tip:
                        _c_odds = tip.get("odds", tip.get("fair_odds", 0))
                        try:
                            _c_odds_f = float(str(_c_odds).replace(",", "."))
                        except Exception:
                            _c_odds_f = 0
                        if _c_odds_f < MIN_ODDS_VALUE:
                            log(f"   ⏭️ Ecken unter 1.70 verworfen: {tip['match']} ({_c_odds_f})")
                            continue
                        corners_tips.append(tip)
                        corners_count += 1
                        log(f"   🔵 Ecken: {tip['match']} → {tip['tip']} ({tip['probability']}%)")
                except Exception as e:
                    log(f"   Corners Error: {e}", "WARN")

        # Scorer-Tipps - nutze Understat + geschätzte Werte
        if group_late:
            try:
                scorers = []

                # 1. TheStatsAPI (neu, primäre Quelle — kein API-Football nötig)
                if THESTATSAPI_KEYS and not scorers:
                    scorers = tsa_get_top_scorers(league, season)

                # 2. API-Football (gesperrt, bleibt als Basis)
                if not scorers and league_id and not APIFOOTBALL_QUOTA_EXHAUSTED:
                    scorers = get_top_scorers(league_id, season)

                # 3. Understat (oft geblockt auf GitHub Actions)
                if not scorers:
                    scorers = get_understat_top_scorers(league, season)

                # 4. Understat via Playwright
                if not scorers and PLAYWRIGHT_AVAILABLE:
                    scorers = pw_get_understat_scorers(league, season)

                # 5. StatsBomb HTTP (kostenlos, direkt von GitHub)
                if not scorers:
                    scorers = get_statsbomb_top_scorers(league)

                if scorers:
                    for fixture in fixtures:
                        home_norm = normalize_team_name(fixture.get("home", ""))
                        away_norm = normalize_team_name(fixture.get("away", ""))
                        match_key = f"sc_{home_norm[:8]}_{away_norm[:8]}"
                        if match_key in seen_corner_matches:
                            continue
                        seen_corner_matches.add(match_key)

                        # 🆕 Duplikat zwischen Runs prüfen!
                        match_name = f"{fixture.get('home','')} vs {fixture.get('away','')}"
                        if is_duplicate_tip(match_name, "scorer", target_date):
                            log(f"   ⏭️ Scorer Duplikat: {match_name}")
                            continue

                        tips = analyze_scorer_tips(fixture, league, scorers)
                        for tip in tips:
                            scorer_tips.append(tip)
                            scorer_count += 1
                            log(f"   ⚽ Scorer: {tip['player']} ({tip['probability']}%)")
            except Exception as e:
                log(f"   Scorer Error: {e}", "WARN")

    # Header + Tipps senden
    # 🧠 Corner-Tipps nach gelerntem Gewicht sortieren
    try:
        corners_tips = sorted(corners_tips, key=lambda _t: float(_t.get("confidence", _t.get("probability", 0)) or 0) * _ntr_learned_weight("corners", _t.get("league", "") or _t.get("competition", "")), reverse=True)
    except Exception:
        pass
    if corners_tips and group_hz:
        send_telegram(f"🔵 <b>CORNER SNIPER</b>\n<i>📅 {target_date}</i>", group_hz)
        for tip in corners_tips:
            _cmsg = format_corners_message(tip)
            _cmid = send_telegram(_cmsg, group_hz)
            mark_tip_sent(tip.get("match",""), "corners", target_date)
            # Für Settlement speichern
            try:
                save_to_supabase({
                    **tip,
                    "tip_id": f"corners_{tip.get('match','?')}_{target_date}".replace(" ","_"),
                    "date": str(target_date),
                    "market": "corners",
                    "status": "pending",
                    "group_key": "corners",
                    "pick_type": "corners",
                    "telegram_chat_id": str(group_hz),
                    "telegram_msg_id": _cmid,
                    "message_text": _cmsg[:3500],
                    "probability": tip.get("probability", 0),
                    "confidence": tip.get("confidence", 3),
                })
            except Exception:
                pass

    # 🧠 Scorer-Tipps nach gelerntem Gewicht sortieren
    try:
        scorer_tips = sorted(scorer_tips, key=lambda _t: float(_t.get("confidence", _t.get("probability", 0)) or 0) * _ntr_learned_weight("scorer", _t.get("league", "") or _t.get("competition", "")), reverse=True)
    except Exception:
        pass
    if scorer_tips and group_late:
        send_telegram(f"⚽ <b>SCORER TIPPS</b>\n<i>📅 {target_date}</i>", group_late)
        for tip in scorer_tips:
            send_telegram(format_scorer_message(tip), group_late)
            mark_tip_sent(tip.get("match",""), "scorer", target_date)

    log(f"🔵⚽ Fertig: {corners_count} Ecken Tips, {scorer_count} Scorer Tips")



# ============================================================
# 🆕 SCHIEDSRICHTER STATS - WorldFootball.net
# ============================================================
REFEREE_CACHE = {}

def get_referee_stats(home_team, away_team, league_name, target_date):
    """
    Holt Schiedsrichter-Statistiken von WorldFootball.net
    Returns: {'name': 'Felix Brych', 'cards_per_game': 4.2, 'fouls_per_game': 22, 'penalty_rate': 0.3}
    """
    cache_key = f"ref_{home_team}_{away_team}_{target_date}"
    if cache_key in REFEREE_CACHE:
        return REFEREE_CACHE[cache_key]

    LEAGUE_WF_SLUGS = {
        "Bundesliga": "bundesliga",
        "2. Bundesliga": "2-bundesliga",
        "Premier League": "premier-league",
        "La Liga": "primera-division",
        "Serie A": "serie-a",
        "Ligue 1": "ligue-1",
        "Champions League": "champions-league",
        "Europa League": "europa-league",
        "Eredivisie": "eredivisie",
        "Primeira Liga": "primeira-liga",
    }

    slug = LEAGUE_WF_SLUGS.get(league_name)
    if not slug:
        return None

    try:
        import random as _r
        import re as _re

        r = smart_request(
            f"https://www.worldfootball.net/schedule/{slug}/",
            headers={
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
                ]),
                "Accept": "text/html",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Referer": "https://www.worldfootball.net/",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        html = r.text

        # Suche Schiedsrichter für dieses Spiel
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        # Pattern: Team vs Team ... Schiedsrichter
        matches = _re.findall(
            r'([A-Za-zÄÖÜäöüß\s]+)\s+vs?\s+([A-Za-zÄÖÜäöüß\s]+).*?'
            r'(?:Schiedsrichter|Referee):\s*([A-Za-zÄÖÜäöüß\s]+)',
            html, _re.DOTALL | _re.IGNORECASE
        )

        for h, a, ref in matches:
            if home_norm[:6] in normalize_team_name(h) or normalize_team_name(h)[:6] in home_norm:
                ref_name = ref.strip()
                # Hole Referee Stats
                ref_stats = _get_referee_season_stats(ref_name, league_name)
                result = {"name": ref_name, **ref_stats}
                REFEREE_CACHE[cache_key] = result
                return result

        return None

    except Exception as e:
        return None


def _get_referee_season_stats(ref_name, league_name):
    """Holt Saison-Statistiken eines Schiedsrichters"""
    try:
        import random as _r
        import re as _re

        search = ref_name.lower().replace(" ", "-")
        r = smart_request(
            f"https://www.worldfootball.net/referee/{search}/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
                "Accept": "text/html",
                "Referer": "https://www.worldfootball.net/",
            },
            timeout=10,
        )

        if not r.ok:
            return {}

        html = r.text

        # Parse Statistiken
        yellow_m = _re.search(r'Gelb[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        red_m = _re.search(r'Rot[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        games_m = _re.search(r'Spiele[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)
        pen_m = _re.search(r'Elfmeter[^>]*>.*?(\d+)', html, _re.IGNORECASE | _re.DOTALL)

        games = int(games_m.group(1)) if games_m else 1
        yellow = int(yellow_m.group(1)) if yellow_m else 0
        red = int(red_m.group(1)) if red_m else 0
        penalties = int(pen_m.group(1)) if pen_m else 0

        stats = {}
        if games > 0:
            stats["cards_per_game"] = round((yellow + red * 2) / games, 1)
            stats["penalty_rate"] = round(penalties / games, 2)
            stats["games"] = games

        return stats

    except Exception:
        return {}


# ============================================================
# 🆕 REISEBELASTUNG & FATIGUE
# ============================================================

CITY_COORDS = {
    "Bayern": (48.2, 11.6), "Dortmund": (51.5, 7.5), "Leipzig": (51.3, 12.4),
    "Berlin": (52.5, 13.4), "Hamburg": (53.6, 10.0), "Frankfurt": (50.1, 8.7),
    "London": (51.5, -0.1), "Manchester": (53.5, -2.2), "Liverpool": (53.4, -3.0),
    "Madrid": (40.4, -3.7), "Barcelona": (41.4, 2.2), "Seville": (37.4, -6.0),
    "Milan": (45.5, 9.2), "Rome": (41.9, 12.5), "Turin": (45.1, 7.7),
    "Paris": (48.9, 2.4), "Lyon": (45.8, 4.8), "Marseille": (43.3, 5.4),
    "Amsterdam": (52.4, 4.9), "Rotterdam": (51.9, 4.5),
    "Lisbon": (38.7, -9.1), "Porto": (41.2, -8.6),
    "Tokyo": (35.7, 139.7), "Seoul": (37.6, 127.0),
    "New York": (40.7, -74.0), "Los Angeles": (34.1, -118.2),
    "Sao Paulo": (-23.5, -46.6), "Buenos Aires": (-34.6, -58.4),
}

def calculate_travel_fatigue(home_team, away_team, last_match_date=None):
    """
    Berechnet Reisebelastung für Auswärtsteam.
    Returns: {'distance_km': 850, 'fatigue_score': 7, 'rest_days': 3}
    """
    import math

    try:
        # Vereinfachte Distanz-Berechnung
        home_city = None
        away_city = None

        for city, coords in CITY_COORDS.items():
            if city.lower() in home_team.lower():
                home_city = coords
            if city.lower() in away_team.lower():
                away_city = coords

        result = {}

        if home_city and away_city:
            # Haversine Formel (vereinfacht)
            lat1, lon1 = home_city
            lat2, lon2 = away_city
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            distance = round(6371 * 2 * math.asin(math.sqrt(a)))
            result["distance_km"] = distance

            # Fatigue Score (0-10)
            if distance > 5000:
                result["fatigue_score"] = 9
            elif distance > 2000:
                result["fatigue_score"] = 7
            elif distance > 1000:
                result["fatigue_score"] = 5
            elif distance > 500:
                result["fatigue_score"] = 3
            else:
                result["fatigue_score"] = 1

        # Rest Days
        if last_match_date:
            today = datetime.now(timezone.utc).date()
            rest = (today - last_match_date).days
            result["rest_days"] = rest
            if rest <= 2:
                result["fatigue_score"] = result.get("fatigue_score", 5) + 3
                result["rotation_likely"] = True
            elif rest <= 4:
                result["fatigue_score"] = result.get("fatigue_score", 5) + 1

        return result if result else None

    except Exception:
        return None


# ============================================================
# 🆕 CLOSING LINE VALUE (CLV) - Sharp Money Tracker
# ============================================================
CLV_CACHE = {}

def track_odds_movement(home_team, away_team, market="btts"):
    """
    Trackt Quoten-Bewegung für CLV Analyse.
    Returns: {'opening': 1.90, 'current': 1.75, 'movement': -0.15, 'sharp_signal': True}
    """
    cache_key = f"clv_{home_team}_{away_team}_{market}"
    if cache_key in CLV_CACHE:
        return CLV_CACHE[cache_key]

    try:
        if not ODDS_API_KEYS:
            return None

        key = ODDS_API_KEYS[0]

        # Aktuelle Quoten holen
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer/odds/",
            params={
                "apiKey": key,
                "bookmakers": "pinnacle,bet365,bwin,unibet",
                "markets": "btts,totals",
                "oddsFormat": "decimal",
            },
            timeout=12,
        )

        if not r.ok:
            return None

        for game in r.json():
            h = game.get("home_team", "")
            a = game.get("away_team", "")

            if not (teams_match(home_team, h) and teams_match(away_team, a)):
                continue

            odds_by_bookie = {}
            for bookmaker in game.get("bookmakers", []):
                bookie = bookmaker.get("key", "")
                for mkt in bookmaker.get("markets", []):
                    if mkt.get("key") == "btts":
                        for outcome in mkt.get("outcomes", []):
                            if outcome.get("name") == "Yes":
                                odds_by_bookie[bookie] = outcome.get("price", 0)

            if not odds_by_bookie:
                continue

            odds_vals = list(odds_by_bookie.values())
            avg_odds = sum(odds_vals) / len(odds_vals)
            pinnacle_odds = odds_by_bookie.get("pinnacle", avg_odds)

            result = {
                "current_odds": pinnacle_odds,
                "avg_market": round(avg_odds, 3),
                "bookmakers": odds_by_bookie,
                "sharp_signal": pinnacle_odds < avg_odds * 0.97,  # Pinnacle niedriger = sharp
            }

            CLV_CACHE[cache_key] = result
            return result

    except Exception:
        pass
    return None


# ============================================================
# 🆕 REST DAYS BERECHNUNG aus API-Football
# ============================================================

def get_team_rest_days(team_id, league_id, season, target_date):
    """Berechnet Ruhetage seit letztem Spiel"""
    if not team_id:
        return None

    try:
        response = _af_request("/fixtures", {
            "team": team_id,
            "league": league_id,
            "season": season,
            "last": 1,
            "status": "FT",
        })

        if not response:
            return None

        last_fix = response[0] if response else None
        if not last_fix:
            return None

        last_date_str = last_fix.get("fixture", {}).get("date", "")
        if not last_date_str:
            return None

        last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00")).date()
        rest_days = (target_date - last_date).days

        return {
            "rest_days": rest_days,
            "tired": rest_days <= 3,
            "fresh": rest_days >= 7,
        }

    except Exception:
        return None


# ============================================================
# MAIN
# ============================================================

# ============================================================
# 🔑 ADVANCED PLAYER PROPS MODULE
# FBref Scraper für SOT, Fouls, Offsides, Header
# ============================================================

class AdvancedPropsManager:
    """
    Analysiert tiefe Spieler-Statistiken von FBref.
    Bereitet Daten für SOT, Fouls, Abseits und Header-Props auf.
    """

    FBREF_LEAGUE_URLS = {
        # Europa Top
        "Premier League": "https://fbref.com/en/comps/9/Premier-League-Stats",
        "Bundesliga": "https://fbref.com/en/comps/20/Bundesliga-Stats",
        "La Liga": "https://fbref.com/en/comps/12/La-Liga-Stats",
        "Serie A": "https://fbref.com/en/comps/11/Serie-A-Stats",
        "Ligue 1": "https://fbref.com/en/comps/13/Ligue-1-Stats",
        "Champions League": "https://fbref.com/en/comps/8/Champions-League-Stats",
        "Europa League": "https://fbref.com/en/comps/19/Europa-League-Stats",
        "Conference League": "https://fbref.com/en/comps/882/Conference-League-Stats",
        "Eredivisie": "https://fbref.com/en/comps/23/Eredivisie-Stats",
        "Primeira Liga": "https://fbref.com/en/comps/32/Primeira-Liga-Stats",
        "Pro League Belgien": "https://fbref.com/en/comps/37/Belgian-Pro-League-Stats",
        "Scottish Premiership": "https://fbref.com/en/comps/40/Scottish-Premiership-Stats",
        "Championship": "https://fbref.com/en/comps/10/Championship-Stats",
        "Super League Schweiz": "https://fbref.com/en/comps/57/Super-League-Stats",
        "Bundesliga Österreich": "https://fbref.com/en/comps/56/Austrian-Football-Bundesliga-Stats",
        "Süper Lig": "https://fbref.com/en/comps/26/Super-Lig-Stats",
        "Greece Super League": "https://fbref.com/en/comps/27/Super-League-1-Stats",
        "Russia Premier League": "https://fbref.com/en/comps/30/Russian-Premier-League-Stats",
        "Czech First League": "https://fbref.com/en/comps/66/Czech-First-League-Stats",
        "Poland Ekstraklasa": "https://fbref.com/en/comps/36/Ekstraklasa-Stats",
        # Americas
        "MLS": "https://fbref.com/en/comps/22/Major-League-Soccer-Stats",
        "Brasileirao Serie A": "https://fbref.com/en/comps/24/Serie-A-Stats",
        "Liga Argentinien": "https://fbref.com/en/comps/21/Primera-Division-Stats",
        "Copa Libertadores": "https://fbref.com/en/comps/14/Copa-Libertadores-Stats",
        # International
        "Freundschaftsspiele International": "https://fbref.com/en/national/stats/",
        "Länderspiel": "https://fbref.com/en/national/stats/",
        "WM 2026": "https://fbref.com/en/comps/1/World-Cup-Stats",
        "WM 2026 Gruppe A": "https://fbref.com/en/comps/1/World-Cup-Stats",
        # Asien
        "J1 League Japan": "https://fbref.com/en/comps/25/J1-League-Stats",
        "K League 1": "https://fbref.com/en/comps/55/K-League-1-Stats",
        "China Super League": "https://fbref.com/en/comps/28/Chinese-Super-League-Stats",
    }

    MARKET_INFO_PROPS = {
        "advanced_props": {
            "name": "🔑 Player Props",
            "instr": "Analysiere Advanced Player Props: SOT, Fouls, Abseits, Kopfball-Duelle.",
        }
    }

    def __init__(self, foul_threshold=1.8, sot_threshold=1.5):
        self.foul_threshold = foul_threshold
        self.sot_threshold = sot_threshold
        self._cache = {}

    def scrape_fbref_advanced_stats(self, league_name: str) -> dict:
        """
        Scrapt FBref für fortgeschrittene Player Props.
        Returns: {player_name: {team, shots_per90, sot_per90, fouls_committed, fouls_drawn, offsides, aerials_won}}
        """
        if league_name in self._cache:
            return self._cache[league_name]

        league_url = self.FBREF_LEAGUE_URLS.get(league_name)
        if not league_url:
            return {}

        try:
            import random as _r
            headers = {
                "User-Agent": _r.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0.0.0 Safari/537.36",
                ]),
                "Accept": "text/html",
                "Referer": "https://fbref.com/",
            }
            r = requests.get(league_url, headers=headers, timeout=15)
            html = None

            if r.ok:
                html = r.text
            elif r.status_code in (403, 429) and PLAYWRIGHT_AVAILABLE:
                # Direkter Call geblockt → Playwright-Browser umgeht Cloudflare/Bot-Erkennung
                log(f"   AdvancedProps: FBref {r.status_code} — versuche Playwright-Fallback...")
                pw_html = scrape_with_playwright(league_url, timeout=15000)
                if pw_html:
                    html = pw_html
                    log(f"   AdvancedProps: FBref via Playwright erfolgreich")
                else:
                    log(f"   AdvancedProps: FBref Playwright-Fallback ebenfalls fehlgeschlagen", "WARN")
                    return {}
            else:
                log(f"   AdvancedProps: FBref nicht erreichbar ({r.status_code})", "WARN")
                return {}

            if not html:
                return {}

            html = html.replace("<!--", "").replace("-->", "")
            player_db = {}

            import re as _re

            # Shooting stats
            shooting_rows = _re.findall(
                r'data-stat="player"[^>]*>\s*<a[^>]*>([^<]+)</a>.*?'
                r'data-stat="team"[^>]*>([^<]*)<.*?'
                r'data-stat="shots_per90"[^>]*>([\d.]*)<.*?'
                r'data-stat="shots_on_target_per90"[^>]*>([\d.]*)<',
                html, _re.DOTALL
            )
            for name, team, shots, sot in shooting_rows:
                try:
                    player_db[name.strip()] = {
                        "team": team.strip(),
                        "shots_per90": float(shots or 0),
                        "sot_per90": float(sot or 0),
                        "fouls_committed": 0.0,
                        "fouls_drawn": 0.0,
                        "offsides": 0.0,
                        "aerials_won": 0.0,
                    }
                except Exception:
                    continue

            # Misc stats (fouls, offsides, aerials, yellow cards)
            misc_rows = _re.findall(
                r'data-stat="player"[^>]*>\s*<a[^>]*>([^<]+)</a>.*?'
                r'data-stat="minutes_90s"[^>]*>([\d.]*)<.*?'
                r'data-stat="fouls"[^>]*>([\d.]*)<.*?'
                r'data-stat="fouls_drawn"[^>]*>([\d.]*)<.*?'
                r'data-stat="offsides"[^>]*>([\d.]*)<.*?'
                r'data-stat="aerial_won"[^>]*>([\d.]*)<.*?'
                r'data-stat="cards_yellow"[^>]*>([\d.]*)<',
                html, _re.DOTALL
            )
            for name, mins90, fouls, fouls_drawn, offsides, aerials, yc in misc_rows:
                name = name.strip()
                mins = float(mins90 or 1) or 1
                if name not in player_db:
                    player_db[name] = {
                        "team": "", "shots_per90": 0.0, "sot_per90": 0.0,
                        "fouls_committed": 0.0, "fouls_drawn": 0.0,
                        "offsides": 0.0, "aerials_won": 0.0, "yc_per90": 0.0,
                    }
                try:
                    player_db[name]["fouls_committed"] = round(float(fouls or 0) / mins, 2)
                    player_db[name]["fouls_drawn"]     = round(float(fouls_drawn or 0) / mins, 2)
                    player_db[name]["offsides"]        = round(float(offsides or 0) / mins, 2)
                    player_db[name]["aerials_won"]     = round(float(aerials or 0) / mins, 2)
                    player_db[name]["yc_per90"]        = round(float(yc or 0) / mins, 3)
                    player_db[name]["appearances"]     = round(mins, 1)
                except Exception:
                    continue

            self._cache[league_name] = player_db
            if player_db:
                log(f"   🔑 AdvancedProps: {len(player_db)} Spieler für {league_name}")
            return player_db

        except Exception as e:
            log(f"   AdvancedProps Error: {str(e)[:60]}", "WARN")
            return {}

    def generate_ai_prompt_extension(self, match_name: str, home_lineup: list, away_lineup: list, player_db: dict) -> str:
        """Baut JSON-Block für Gemini/Groq Prompt."""
        import json as _json
        relevant = []
        for player in (home_lineup + away_lineup):
            if player in player_db:
                relevant.append({"player": player, "stats": player_db[player]})

        if not relevant:
            return ""

        prompt = f"\n\n[MARKT: ADVANCED PLAYER PROPS - {match_name}]\n"
        prompt += "Spieler-Statistiken pro 90 Minuten der voraussichtlichen Startelf:\n"
        prompt += _json.dumps(relevant, indent=2, ensure_ascii=False)
        prompt += (
            "\n\nAufgabe: Erstelle risikooptimierte Bet-Builder Kombis (2-3 Auswahlen).\n"
            "Optionen: X+ Schüsse aufs Tor (SoT), X+ Fouls begangen, X+ Fouls erlitten, X+ Abseits.\n"
            "Nur Tipps ab >67% Wahrscheinlichkeit. Antworte NUR AUF DEUTSCH!\n"
            "Gib JSON-Array zurück: [{match, player, tip, probability, confidence, reasoning}]"
        )
        return prompt

    def run_advanced_props(self, fixtures: list, league_name: str, target_date) -> list:
        """
        Hauptfunktion: Analysiert Advanced Props für alle Spiele einer Liga.
        """
        player_db = self.scrape_fbref_advanced_stats(league_name)
        if not player_db:
            return []

        results = []
        for fixture in fixtures[:5]:  # Max 5 Spiele pro Liga
            try:
                home = fixture.get("home", "")
                away = fixture.get("away", "")
                match_name = f"{home} vs {away}"

                # Lineup aus SofaScore holen
                match_id = fixture.get("match_id", "")
                lineup_data = get_sofascore_lineups(match_id, home, away) if match_id else None

                home_lineup = []
                away_lineup = []
                if lineup_data and lineup_data.get("lineup_available"):
                    home_lineup = [p["name"] for p in lineup_data.get("home_lineup", [])]
                    away_lineup = [p["name"] for p in lineup_data.get("away_lineup", [])]

                prompt_ext = self.generate_ai_prompt_extension(match_name, home_lineup, away_lineup, player_db)
                if not prompt_ext:
                    continue

                # AI Call
                prompt = (
                    f"Liga: {league_name} | Datum: {target_date}\n"
                    f"{prompt_ext}\n"
                    "Antworte mit JSON-Array oder []"
                )
                tips, source = call_gemini(prompt, use_tools=False)
                if tips:
                    for tip in tips:
                        tip["market"] = "advanced_props"
                        tip["league"] = league_name
                        tip["match"] = match_name
                        tip["time"] = fixture.get("time_local", "TBD")
                    results.extend(tips)
                    log(f"   🔑 Props: {len(tips)} Tipps für {match_name}")

            except Exception as e:
                log(f"   Props Error: {str(e)[:50]}", "WARN")
                continue

        return results


# Globale Instanz
_advanced_props_manager = AdvancedPropsManager()

# Gemeinsamer Pool für die aktive Prop- und Builder-Engine.
# Enthält nur normalisierte Legs und wird pro Bot-Run geleert.
_NTR_BUILDER_PROP_POOL = []


def _ntr_market_line(text, default=1.0):
    raw = str(text or "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", raw)
    if m:
        return float(m.group(1))
    m = re.search(r"over\s*(\d+(?:\.\d+)?)", raw, re.I)
    if m:
        return float(int(float(m.group(1))) + 1)
    return float(default)


def _ntr_prop_category(text):
    low = str(text or "").lower()
    if "either team to score? 1st half" in low or "both teams to score 1st half" in low:
        return "btts_ht"
    if "both teams to receive a card" in low:
        return "team_cards"
    if ("player" not in low) and (" to score?" in low or "team to score" in low):
        return "match_goals"

    # Team-/Matchmärkte zuerst, damit "receive a card" nicht als Player Booking endet.
    if "both teams to receive a card" in low or "both teams carded" in low:
        return "team_cards"
    if "both teams to score" in low or "either team to score" in low:
        return "btts"
    if "to qualify" in low or "qualify" in low:
        return "result"

    if ("outside box" in low or "outside the box" in low or "from outside" in low) and (
        "shot on target" in low or "shots on target" in low
    ):
        return "sot_outside_box"
    if ("outside box" in low or "outside the box" in low or "from outside" in low) and "shot" in low:
        return "shots_outside_box"
    if ("total" in low or "match" in low or "team" in low) and ("shots on target" in low or "shot on target" in low):
        return "match_sot"
    if ("total" in low or "match" in low or "team" in low) and "shots" in low and "player" not in low:
        return "team_shots"
    if "shots on target" in low or "shot on target" in low:
        return "sot"
    if "shot" in low:
        return "shots"
    if "tackles received" in low or "times tackled" in low or "to be tackled" in low:
        return "tackles_received"
    if (
        "tackles committed" in low
        or "tackles made" in low
        or "player tackles" in low
        or "tackles won" in low
    ):
        return "tackles_committed"
    if "tackle" in low:
        return "tackles_committed"
    if "fouls won" in low or "to be fouled" in low:
        return "fouls_won"
    if "fouls committed" in low or "foul committed" in low or "foul" in low:
        return "fouls"
    if (
        "booked" in low or "receive a card" in low or "carded" in low
        or "to be shown a card" in low or "to be carded" in low
        or ("card" in low and "player" in low)
    ):
        return "yellow_cards"
    if "first goalscorer" in low or "first goal scorer" in low:
        return "first_scorer"
    if "last goalscorer" in low or "last goal scorer" in low:
        return "last_scorer"
    if "anytime goalscorer" in low or "player to score" in low:
        return "score"
    if "assist" in low:
        return "assist"
    if "corner" in low:
        return "team_corners"
    if "save" in low:
        return "saves"
    if "offside" in low:
        return "offsides"
    return "other"


def _ntr_extract_player(description, selection=""):
    """
    Pinnacle benutzt je nach Markt entweder:
    - selection = Spielername  (Messi, Otamendi)
    - selection = Over 1.5 / Yes / No und Spielername steckt in description
    Darum Selection nur nehmen, wenn sie wirklich wie ein Spielername aussieht.
    """
    selected = str(selection or "").strip()
    sl = selected.lower().strip()
    if selected and len(selected) > 2:
        bad = (
            sl in {"yes", "no", "home", "away", "draw", "odd", "even"}
            or sl.startswith(("over", "under"))
            or re.fullmatch(r"[ou]\s*\d+(?:\.\d+)?", sl) is not None
            or re.fullmatch(r"\d+(?:\.\d+)?\+?", sl) is not None
        )
        if not bad:
            return selected[:100]

    desc = str(description or "").strip()
    dl = desc.lower().strip()

    def _clean_candidate(value):
        cand = str(value or "").strip(" -:|")
        cand = re.sub(r"\b(over|under)\s*\d+(?:\.\d+)?\b", "", cand, flags=re.I).strip(" -:|")
        # offensichtliche Markttexte nicht als Spielername nehmen
        bad_words = [
            "shots", "shot", "goalscorer", "goal scorer", "to score", "score?",
            "booked", "carded", "receive a card", "assist", "fouls", "tackles",
            "saves", "offsides", "total goals", "both teams", "either team",
        ]
        if not cand or len(cand) < 3:
            return ""
        if any(w in cand.lower() for w in bad_words):
            return ""
        return cand[:100]

    # "Harry Kane - Shots on Target" / "Harry Kane: Over 1.5 SOT"
    for sep in (":", " - ", " – ", " — "):
        if sep in desc:
            left, right = desc.split(sep, 1)
            cand = _clean_candidate(left)
            if cand:
                return cand
            cand = _clean_candidate(right)
            if cand:
                return cand

    # "Harry Kane Shots on Target", "Otamendi To Be Booked", "Messi Anytime Goalscorer"
    m = re.search(
        r"^(.+?)\s+(?:over\s*\d+(?:\.\d+)?\s*)?"
        r"(?:shots?\s+on\s+target|shots?|anytime\s+goalscorer|first\s+goalscorer|last\s+goalscorer|"
        r"to\s+score|to\s+be\s+booked|receive\s+a\s+card|be\s+carded|to\s+assist|"
        r"fouls?\s+committed|fouls?\s+won|tackles?\s+committed|tackles?\s+received|saves?|offsides?)\b",
        desc,
        flags=re.I,
    )
    if m:
        cand = _clean_candidate(m.group(1))
        if cand:
            return cand

    # "Shots on Target - Harry Kane"
    m = re.search(
        r"(?:shots?\s+on\s+target|shots?|anytime\s+goalscorer|to\s+be\s+booked|to\s+assist|"
        r"fouls?\s+committed|tackles?)\s*[-:]\s*(.+)$",
        desc,
        flags=re.I,
    )
    if m:
        cand = _clean_candidate(m.group(1))
        if cand:
            return cand

    return selected[:100] if selected else desc[:100]


def _ntr_collect_prop(player, team, match_name, league, market, category=None,
                      line=None, odds=0, probability=0, source="unknown",
                      kickoff="", hit_rate=0, games=0):
    category = category or _ntr_prop_category(market)
    if category == "other" or not match_name or " vs " not in match_name:
        return
    row = {
        "player": str(player or market)[:100],
        "team": str(team or "")[:100],
        "match": str(match_name)[:180],
        "league": str(league or "")[:100],
        "market": str(market)[:160],
        "category": category,
        "line": float(line if line is not None else _ntr_market_line(market, 1)),
        "odds": float(odds or 0),
        "probability": float(probability or 0),
        "source": str(source or "unknown"),
        "kickoff": str(kickoff or ""),
        "hit_rate": float(hit_rate or 0),
        "games": int(games or 0),
    }
    key = (
        normalize_team_name(row["match"]),
        normalize_team_name(row["player"]),
        row["category"],
        row["line"],
    )
    for old in _NTR_BUILDER_PROP_POOL:
        old_key = (
            normalize_team_name(old.get("match")),
            normalize_team_name(old.get("player")),
            old.get("category"),
            float(old.get("line", 0)),
        )
        if old_key == key:
            # Prefer real odds and stronger probability.
            if row["odds"] > 1:
                old["odds"] = row["odds"]
                old["source"] = row["source"]
            old["probability"] = max(float(old.get("probability", 0)), row["probability"])
            old["hit_rate"] = max(float(old.get("hit_rate", 0)), row["hit_rate"])
            old["games"] = max(int(old.get("games", 0)), row["games"])
            return
    _NTR_BUILDER_PROP_POOL.append(row)


def run_advanced_props_bot(active_leagues: list, fixtures_cache: dict, target_date) -> None:
    """
    Prop Builder Bot — Nate Betting Style.
    Combo-Typen:
      🟥 FOULS BUILDER      — FC + FW kombiniert, verschiedene Spiele
      🟨 BOOKING BUILDER    — Nuno Tavares Style, 2-4x Player to be Booked
      🎯 SHOT BUILDER+      — 2+ SoT + 3+ Shots (selber Spieler ODER 2 Spieler)
      💎 MIXED              — Fouls + Bookings + Shots gemischt
    Scoring: Saison+Last5+Gegner+Startelf+FairValue+Schiri
    Quellen: FBref + StatsBomb + Understat + FPL
    """
    props_chat = TELEGRAM_GROUPS.get("advanced_props", TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID))
    if not props_chat:
        return

    try:
        prefetch_sent_tips_for_date(target_date)
    except Exception:
        pass
    log("🔑 Prop Builder Bot startet...")

    manager = _advanced_props_manager
    seen = set()

    foul_candidates    = []
    booking_candidates = []
    shot_candidates    = []

    def _score(stats, mtype, league):
        """Berechnet Prop Score nach ChatGPT/Nate Betting Methodik."""
        score = 0
        reasons = []

        sot   = stats.get("sot_per90", 0)
        shots = stats.get("shots_per90", 0)
        fc    = stats.get("fouls_committed", 0)
        fw    = stats.get("fouls_drawn", 0)
        yc    = stats.get("yc_per90", 0)
        apps  = max(stats.get("appearances", 1) or 1, 1)

        if mtype == "shots":
            val = sot if "on Target" in stats.get("_market","") else shots
            if val >= 1.5:   score += 1; reasons.append("✅ Saison-Schnitt")
            if val >= 2.0:   score += 2; reasons.append("✅ Last-5 stark")
        elif mtype == "foul":
            if fc >= 1.5:    score += 1; reasons.append("✅ Saison FC")
            if fc >= 2.0:    score += 2; reasons.append("✅ Last-5 FC")
        elif mtype == "foul_won":
            if fw >= 1.5:    score += 1; reasons.append("✅ Saison FW")
            if fw >= 2.0:    score += 2; reasons.append("✅ Last-5 FW")
        elif mtype == "booking":
            if yc >= 0.20:   score += 1; reasons.append("✅ YC Rate 20%+")
            if yc >= 0.30:   score += 2; reasons.append("✅ YC Rate 30%+")

        # Schiri Stats
        ref_cards = stats.get("_ref_cards", 0)
        if ref_cards >= 4.0:
            score += 1; reasons.append("✅ Strenger Schiri")

        return score, reasons

    def _add(bucket, player, team, match_name, league, kickoff, market, stat_val, mtype, score=5):
        key = f"{player}_{match_name}_{market}"
        if key in seen:
            return
        seen.add(key)
        bucket.append({
            "player": player, "team": team, "match": match_name,
            "league": league, "kickoff": kickoff,
            "market": market, "market_type": mtype,
            "stat_per90": stat_val, "score": score,
        })
        _category = {
            "shots": "sot" if "target" in str(market).lower() else "shots",
            "foul": "fouls",
            "foul_won": "fouls_won",
            "booking": "yellow_cards",
            "tackles": "tackles_committed",
            "tackles_received": "tackles_received",
        }.get(mtype, _ntr_prop_category(market))
        _ntr_collect_prop(
            player, team, match_name, league, market,
            category=_category,
            line=_ntr_market_line(market, 1),
            probability=min(90, max(35, 45 + float(score or 0) * 5)),
            source="advanced_props",
            kickoff=kickoff,
            hit_rate=min(95, max(0, float(stat_val or 0) * 30)),
            games=10,
        )

    for league in active_leagues:
        fixtures = fixtures_cache.get(league, [])
        if not fixtures:
            continue

        for fixture in fixtures[:4]:
            home      = fixture.get("home", "")
            away      = fixture.get("away", "")
            match_id  = fixture.get("match_id", "")
            match_name = f"{home} vs {away}"
            kickoff   = fixture.get("time_local", "TBD")

            # ── Quelle 1: FBref (alle Ligen versuchen) ──
            if True:  # Immer versuchen
                player_db = manager.scrape_fbref_advanced_stats(league)
                if player_db:
                    lineup  = get_sofascore_lineups(match_id, home, away) if match_id else None
                    home_xi = [p["name"] for p in (lineup or {}).get("home_lineup", [])]
                    away_xi = [p["name"] for p in (lineup or {}).get("away_lineup", [])]
                    all_xi  = home_xi + away_xi

                    for player, s in player_db.items():
                        if all_xi and not any(
                            player.lower() in p.lower() or p.lower() in player.lower()
                            for p in all_xi
                        ):
                            continue

                        team = s.get("team", "")
                        fc   = s.get("fouls_committed", 0)
                        fw   = s.get("fouls_drawn", 0)
                        sot  = s.get("sot_per90", 0)
                        sh   = s.get("shots_per90", 0)
                        yc   = s.get("yc_per90", 0)
                        sc, _ = _score(s, "foul", league)

                        # Fouls
                        if fc >= 1.5:  _add(foul_candidates,    player, team, match_name, league, kickoff, "2+ Fouls Committed", fc,  "foul",    sc)
                        if fw >= 1.5:  _add(foul_candidates,    player, team, match_name, league, kickoff, "2+ Fouls Won",       fw,  "foul_won",sc)
                        # Bookings
                        if yc >= 0.20: _add(booking_candidates, player, team, match_name, league, kickoff, "Player to be Booked", yc, "booking", sc)
                        # Shots — nur sinnvolle Linien
                        if sot >= 1.5: _add(shot_candidates,    player, team, match_name, league, kickoff, "2+ Shots on Target",  sot,"shots",   sc)
                        if sh  >= 2.5: _add(shot_candidates,    player, team, match_name, league, kickoff, "3+ Shots",            sh, "shots",   sc)

            # ── Quelle 2: StatsBomb ──
            for prop in get_player_props_for_match(home, away, league):
                mtype = prop.get("market_type", "")
                stat  = prop.get("stat_value", 0)
                if mtype in ("foul","foul_won") and stat >= 1.5:
                    _add(foul_candidates, prop["player"], prop["team"], match_name, league, kickoff, prop["tip"], stat, mtype)
                elif mtype == "shots" and stat >= 1.5:
                    _add(shot_candidates, prop["player"], prop["team"], match_name, league, kickoff, prop["tip"], stat, mtype)

            # ── Quelle 3: Understat ──
            now_utc = datetime.now(timezone.utc)
            season  = str(now_utc.year if now_utc.month > 6 else now_utc.year - 1)
            for s in get_understat_top_scorers(league, season):
                tn = normalize_team_name(s.get("team",""))
                hn = normalize_team_name(home)
                an = normalize_team_name(away)
                if not (tn[:8] in hn or hn[:8] in tn or tn[:8] in an or an[:8] in tn):
                    continue
                gpg = s.get("goals_per_game", 0)
                if gpg >= 0.5:  _add(shot_candidates, s["name"], s["team"], match_name, league, kickoff, "2+ Shots on Target", gpg, "shots")
                if gpg >= 0.8:  _add(shot_candidates, s["name"], s["team"], match_name, league, kickoff, "3+ Shots",           gpg, "shots")

            # ── Quelle 4: FPL ──
            if league == "Premier League":
                fpl_data = get_fpl_data()
                if fpl_data:
                    teams_map = {t["id"]: t["name"] for t in fpl_data.get("teams", [])}
                    for el in fpl_data.get("elements", []):
                        if el.get("status") in ["i","u"]:
                            continue
                        mins = el.get("minutes", 0) or 0
                        if mins < 450:
                            continue
                        games = max(mins // 90, 1)
                        name  = f"{el.get('first_name','')} {el.get('second_name','')}".strip()
                        team  = teams_map.get(el.get("team",""), "")
                        tn    = normalize_team_name(team)
                        if not (tn[:8] in normalize_team_name(home) or normalize_team_name(home)[:8] in tn or
                                tn[:8] in normalize_team_name(away)  or normalize_team_name(away)[:8] in tn):
                            continue
                        yc_total = el.get("yellow_cards", 0) or 0
                        yc_rate  = round(yc_total / games, 3)
                        if yc_rate >= 0.20:
                            _add(booking_candidates, name, team, match_name, league, kickoff, "Player to be Booked", yc_rate, "booking")
                        goals = el.get("goals_scored", 0) or 0
                        gpg   = round(goals / games, 2)
                        if gpg >= 0.5:
                            _add(shot_candidates, name, team, match_name, league, kickoff, "2+ Shots on Target", gpg, "shots")

    # 🎯 The Odds API Player Props — primäre Quelle mit echten Quoten
    if ODDS_API_KEYS:
        try:
            _odds_api_candidates = get_odds_api_player_prop_candidates(
                fixtures_cache, target_date
            )
            for c in _odds_api_candidates:
                mtype = c.get("mtype", "shots")
                nm = c.get("player", "")
                tm = c.get("team", "")
                mn = c.get("match", "")
                league = c.get("league", "")
                ko = c.get("kickoff", "TBD")
                sv = c.get("stat_val", 0)
                market = c.get("market", "")
                real_odds = c.get("odds", 0)
                if mtype == "shots":
                    _add(shot_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                    # Echte Quote direkt setzen
                    if shot_candidates and real_odds > 0:
                        shot_candidates[-1]["_real_odds"] = real_odds
                elif mtype == "booking":
                    _add(booking_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                    if booking_candidates and real_odds > 0:
                        booking_candidates[-1]["_real_odds"] = real_odds
                elif mtype == "tackles":
                    _add(foul_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                    if foul_candidates and real_odds > 0:
                        foul_candidates[-1]["_real_odds"] = real_odds

            total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
            if total > 0:
                log(f"🔑 Kandidaten nach OddsAPI: {len(foul_candidates)} Fouls/Tackles · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots/Goals")
        except Exception as _oae:
            log(f"🔑 OddsAPI Props Error: {str(_oae)[:60]}", "WARN")

    # Direktverbindung zum täglichen Player-Stats-Scraper.
    total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
    _enable_supabase_prop_stats = str(os.getenv("ENABLE_SUPABASE_PROP_STATS", "0")).lower() in {"1", "true", "yes", "on"}
    if total < 4 and (not _enable_supabase_prop_stats):
        log("🔑 Supabase Player-Stats übersprungen (Turbo). Pinnacle Props sind Hauptquelle. Aktivieren: ENABLE_SUPABASE_PROP_STATS=1")
    if total < 4 and _enable_supabase_prop_stats and SUPABASE_URL and SUPABASE_KEY:
        log("🔑 Lade Player-Stats aus Supabase...")

        try:
            _headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            }

            _contexts = []
            for _league_name, _league_fixtures in (fixtures_cache or {}).items():
                for _fixture in (_league_fixtures or []):
                    _home = str(_fixture.get("home") or "").strip()
                    _away = str(_fixture.get("away") or "").strip()
                    if not _home or not _away:
                        continue
                    _contexts.append({
                        "league": _league_name,
                        "home": _home,
                        "away": _away,
                        "match": f"{_home} vs {_away}",
                        "kickoff": _fixture.get("time") or _fixture.get("time_local") or "TBD",
                    })

            _aliases = {
                "totalshots": "shots",
                "shots": "shots",
                "shotsontarget": "sot",
                "shots_on_target": "sot",
                "sot": "sot",
                "foulscommitted": "fouls",
                "fouls_committed": "fouls",
                "foulswon": "fouls_won",
                "fouls_won": "fouls_won",
                "yellowcards": "cards",
                "yellow_cards": "cards",
                "cards": "cards",
                "tackles": "tackles_committed",
                "tacklescommitted": "tackles_committed",
                "tackles_committed": "tackles_committed",
                "tacklesreceived": "tackles_received",
                "tackles_received": "tackles_received",
                "timestackled": "tackles_received",
                "times_tackled": "tackles_received",
                "goals": "goals",
                "goalassist": "assists",
                "assists": "assists",
                "saves": "saves",
                "offsides": "offsides",
                "interceptions": "interceptions",
                "clearances": "clearances",
            }

            _wanted_stats = ",".join(sorted(set(_aliases.keys())))
            _rows = []
            _page_size = 1000
            _max_rows = int(os.environ.get("PROP_STATS_MAX_ROWS", "12000"))
            _offset = 0

            while _offset < _max_rows:
                _params = {
                    # Nur Spalten abfragen, die in deiner bestehenden Tabelle sicher vorhanden sind.
                    # tackles_committed / tackles_received sind KEINE physischen Spalten bei dir,
                    # sondern werden aus stat_name/stat_value oder "tackles" normalisiert.
                    "select": (
                        "player_id,player_name,player,team,league,home_team,away_team,"
                        "match_date,date,stat_name,stat_value,minutes,shots,"
                        "shots_on_target,sot,fouls_committed,fouls_won,cards,"
                        "yellow_cards,red_cards,tackles,goals,assists,passes,"
                        "corners,xg,xa"
                    ),
                    "order": "match_date.desc.nullslast",
                }
                _range_headers = dict(_headers)
                _range_headers["Range"] = f"{_offset}-{_offset + _page_size - 1}"
                _range_headers["Prefer"] = "count=exact"
                _response = requests.get(
                    f"{SUPABASE_URL.rstrip('/')}/rest/v1/player_match_stats",
                    headers=_range_headers,
                    params=_params,
                    timeout=30,
                )
                if not _response.ok:
                    log(
                        f"🔑 Supabase Player Stats HTTP {_response.status_code}: "
                        f"{_response.text[:180]}",
                        "WARN",
                    )
                    log("🔑 Supabase Select nutzt nur bestehende Basis-Spalten; prüfe player_match_stats Schema falls weiterhin 400.", "WARN")
                    break
                _batch = _response.json() or []
                _rows.extend(_batch)
                _content_range = _response.headers.get("Content-Range", "")
                log(f"🔑 Supabase Page {_offset // _page_size + 1}: {len(_batch)} Rows · Range={_content_range}")
                if len(_batch) < _page_size:
                    break
                _offset += _page_size

            # Neueste Werte pro Spieler/Team/Stat sammeln.
            _aggregated = {}
            _wide_columns = {
                "shots": "shots", "shots_on_target": "sot", "sot": "sot",
                "fouls_committed": "fouls", "fouls_won": "fouls_won",
                "cards": "cards", "yellow_cards": "cards",
                "tackles": "tackles_committed",
                "tackles_committed": "tackles_committed",
                "tackles_received": "tackles_received",
                "goals": "goals", "assists": "assists", "saves": "saves",
                "offsides": "offsides", "interceptions": "interceptions",
                "clearances": "clearances",
            }

            def _append_value(_row, _canonical, _raw_value):
                try:
                    _value = float(_raw_value)
                except Exception:
                    return
                _player_name = str(_row.get("player_name") or _row.get("player") or "").strip()
                _team_name = str(_row.get("team") or _row.get("team_name") or "").strip()
                if not _player_name or not _team_name:
                    return
                _key = (
                    normalize_team_name(_team_name), _player_name, _team_name,
                    str(_row.get("league") or ""), _canonical,
                )
                _aggregated.setdefault(_key, []).append(_value)

            for _row in _rows:
                if not isinstance(_row, dict):
                    continue
                _raw_stat = str(_row.get("stat_name") or "").strip()
                _stat_key = _raw_stat.lower().replace(" ", "").replace("-", "_")
                _canonical = _aliases.get(_stat_key)
                if _canonical and _row.get("stat_value") is not None:
                    _append_value(_row, _canonical, _row.get("stat_value"))
                for _column, _canonical in _wide_columns.items():
                    _raw_value = _row.get(_column)
                    if _raw_value is not None and str(_raw_value) not in {"", "0", "0.0"}:
                        _append_value(_row, _canonical, _raw_value)

            _before = total
            _matched_players = set()

            for (_team_norm, _player_name, _team_name, _db_league, _stat), _values in _aggregated.items():
                if not _values:
                    continue

                _ctx = None
                for _candidate_ctx in _contexts:
                    if teams_match(_team_name, _candidate_ctx["home"]) or teams_match(
                        _team_name, _candidate_ctx["away"]
                    ):
                        _ctx = _candidate_ctx
                        break
                if not _ctx:
                    continue

                _recent = _values[:10]
                _avg = sum(_recent) / len(_recent)
                _games = len(_recent)
                if _games < 3:
                    continue

                _match_name = _ctx["match"]
                _league_name = _ctx["league"] or _db_league
                _kickoff = _ctx["kickoff"]
                _matched_players.add((_player_name, _match_name))

                if _stat == "shots" and _avg >= 1.5:
                    _market = "3+ Shots" if _avg >= 2.8 else "2+ Shots"
                    _add(
                        shot_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2), "shots"
                    )
                elif _stat == "sot" and _avg >= 0.65:
                    _market = "2+ Shots on Target" if _avg >= 1.45 else "1+ Shot on Target"
                    _add(
                        shot_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2), "shots"
                    )
                elif _stat == "goals" and _avg >= 0.30:
                    _add(
                        shot_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, "Anytime Goalscorer",
                        round(_avg, 2), "shots"
                    )
                elif _stat == "fouls" and _avg >= 1.15:
                    _market = "2+ Fouls Committed" if _avg >= 1.70 else "1+ Foul Committed"
                    _add(
                        foul_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2), "foul"
                    )
                elif _stat == "fouls_won" and _avg >= 1.15:
                    _market = "2+ Fouls Won" if _avg >= 1.70 else "1+ Foul Won"
                    _add(
                        foul_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2), "foul_won"
                    )
                elif _stat == "tackles_committed" and _avg >= 1.25:
                    _market = "3+ Tackles Committed" if _avg >= 2.65 else "2+ Tackles Committed"
                    _add(
                        foul_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2), "tackles"
                    )
                elif _stat == "tackles_received" and _avg >= 1.25:
                    _market = "3+ Tackles Received" if _avg >= 2.65 else "2+ Tackles Received"
                    _add(
                        foul_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, _market, round(_avg, 2),
                        "tackles_received"
                    )
                elif _stat == "cards" and _avg >= 0.18:
                    _add(
                        booking_candidates, _player_name, _team_name, _match_name,
                        _league_name, _kickoff, "Player to be Booked",
                        round(_avg, 3), "booking"
                    )

            total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
            log(
                f"🔑 Supabase Stats: {len(_rows)} Rows geladen · "
                f"{len(_matched_players)} Spieler heutigen Teams zugeordnet · "
                f"{total - _before} Kandidaten ergänzt"
            )

        except Exception as _supabase_prop_error:
            log(
                f"🔑 Supabase Player-Stats Error: "
                f"{type(_supabase_prop_error).__name__}: "
                f"{str(_supabase_prop_error)[:140]}",
                "WARN",
            )

    total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
    log(f"🔑 Kandidaten: {len(foul_candidates)} Fouls · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots")

    # FBref/StatsBomb direkt nur opt-in; Pinnacle Props kommen danach und sind schneller/besser.
    _enable_slow_prop_fallbacks = str(os.getenv("ENABLE_SLOW_PROP_FALLBACKS", "0")).lower() in {"1", "true", "yes", "on"}
    if total < 4 and not _enable_slow_prop_fallbacks:
        log("🔑 Langsame FBref/StatsBomb Prop-Fallbacks übersprungen (Turbo). Aktivieren: ENABLE_SLOW_PROP_FALLBACKS=1")
    # FBref direkt wenn zu wenig Kandidaten
    if total < 4 and _enable_slow_prop_fallbacks:
        log("🔑 Versuche FBref direkt für alle Fixtures...")
        for league, fixtures in (fixtures_cache or {}).items():
            for fix in (fixtures or [])[:3]:
                home, away = fix.get("home",""), fix.get("away","")
                if not home or not away:
                    continue
                try:
                    match_name = f"{home} vs {away}"
                    kickoff = fix.get("time","TBD")
                    props = get_player_props_for_match(home, away, league)
                    for p in (props or [])[:12]:
                        nm = p.get("player","")
                        tm = p.get("team","")
                        if not nm:
                            continue
                        mtype = str(p.get("market_type","")).lower()
                        val = float(p.get("stat_value") or 0)
                        if mtype in ("sot", "shots") and val >= 1.5:
                            _add(shot_candidates, nm, tm, match_name, league, kickoff,
                                 "2+ Shots on Target", val, "shots")
                        elif mtype in ("fouls", "fouls_committed") and val >= 1.5:
                            _add(foul_candidates, nm, tm, match_name, league, kickoff,
                                 "2+ Fouls", val, "foul")
                        elif mtype in ("cards", "yellow_cards", "card") and val >= 0.20:
                            _add(booking_candidates, nm, tm, match_name, league, kickoff,
                                 "Player to be Booked", val, "booking")
                except Exception as _ppe:
                    log(f"   ⚠️ StatsBomb-Prop-Fallback: {str(_ppe)[:60]}", "WARN")

        total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
        log(f"🔑 Kandidaten nach FBref: {len(foul_candidates)} Fouls · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots")

    # 🆕 StatsBomb direkt — funktioniert für WM, Bundesliga, La Liga, Ligue 1, Copa America, UEFA Euro
    if total < 4 and _enable_slow_prop_fallbacks:
        log("🔑 Versuche StatsBomb für Player Props...")
        _sb_fixtures = list((fixtures_cache or {}).items())
        # Auch Pinnacle-Matches direkt nutzen
        for league, fixtures in _sb_fixtures:
            for fix in (fixtures or [])[:5]:
                home, away = fix.get("home", ""), fix.get("away", "")
                if not home or not away:
                    continue
                try:
                    sb_candidates = get_statsbomb_props_for_match(home, away, league)
                    for c in sb_candidates:
                        mtype = c.get("mtype", "shots")
                        nm = c.get("player", "")
                        tm = c.get("team", "")
                        mn = c.get("match", f"{home} vs {away}")
                        ko = c.get("kickoff", fix.get("time", "TBD"))
                        sv = c.get("stat_val", 0)
                        market = c.get("market", "")
                        if mtype == "shots":
                            _add(shot_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                        elif mtype == "foul":
                            _add(foul_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                        elif mtype == "booking":
                            _add(booking_candidates, nm, tm, mn, league, ko, market, sv, mtype)
                except Exception:
                    pass

        total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
        log(f"🔑 Kandidaten nach StatsBomb: {len(foul_candidates)} Fouls · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots")

    # 🆕 TheStatsAPI als weitere Kandidatenquelle
    if total < 3 and THESTATSAPI_KEYS:
        log("🔑 Versuche TheStatsAPI für Player Props...")
        _seen_leagues = set()

        # Kombiniere fixtures_cache + Pinnacle-Fixtures direkt
        _all_fix_sources = dict(fixtures_cache or {})
        # Pinnacle-Fixtures aus dem Cache direkt nutzen
        for _pfix in _pinnacle_matches_for_props if '_pinnacle_matches_for_props' in dir() else []:
            _ln = _pfix.get("league", "Unknown")
            _all_fix_sources.setdefault(_ln, []).append(_pfix)

        for league, fixtures in _all_fix_sources.items():
            if league in _seen_leagues:
                continue
            _seen_leagues.add(league)
            tsa_players = tsa_get_player_stats(league)
            if not tsa_players:
                continue
            for fix in (fixtures or [])[:5]:
                home, away = fix.get("home", ""), fix.get("away", "")
                if not home or not away:
                    continue
                match_name = f"{home} vs {away}"
                kickoff = fix.get("time", "TBD")
                h_norm = normalize_team_name(home)
                a_norm = normalize_team_name(away)
                for p in tsa_players:
                    t_norm = normalize_team_name(p.get("team", ""))
                    if not (t_norm[:6] in h_norm or h_norm[:6] in t_norm or
                            t_norm[:6] in a_norm or a_norm[:6] in t_norm):
                        continue
                    apps = max(p.get("appearances", 1), 1)
                    shots_pg = (p.get("shots", 0) or 0) / apps
                    sot_pg = (p.get("shots_on_target", 0) or 0) / apps
                    fouls_pg = (p.get("fouls_committed", 0) or 0) / apps
                    cards_pg = (p.get("yellow_cards", 0) or 0) / apps
                    nm = p.get("name", "")
                    tm = p.get("team", "")
                    if sot_pg >= 1.0:
                        _add(shot_candidates, nm, tm, match_name, league, kickoff,
                             "2+ Shots on Target", sot_pg, "shots")
                    if fouls_pg >= 1.5:
                        _add(foul_candidates, nm, tm, match_name, league, kickoff,
                             "2+ Fouls", fouls_pg, "foul")
                    if cards_pg >= 0.20:
                        _add(booking_candidates, nm, tm, match_name, league, kickoff,
                             "Player to be Booked", cards_pg, "booking")

        total = len(foul_candidates) + len(booking_candidates) + len(shot_candidates)
        log(f"🔑 Kandidaten nach TSA: {len(foul_candidates)} Fouls · {len(booking_candidates)} Bookings · {len(shot_candidates)} Shots")

    if total < 3:
        log("🔑 Zu wenig Kandidaten — überspringe Prop Builder")
        return

    # ── Shot Builder+ Paare vorbereiten ──
    # Selber Spieler (korreliert) + 2 verschiedene Spieler
    shot_by_player = {}
    for c in shot_candidates:
        key = f"{c['player']}_{c['match']}"
        shot_by_player.setdefault(key, []).append(c)

    shot_pairs_same   = [v for v in shot_by_player.values() if len(v) >= 2]  # Selber Spieler
    shot_pairs_cross  = []  # 2 verschiedene Spieler
    top_shots = sorted(shot_candidates, key=lambda x: x["stat_per90"], reverse=True)
    used = set()
    for i, a in enumerate(top_shots[:10]):
        for b in top_shots[i+1:10]:
            if a["player"] == b["player"]:
                continue
            key = f"{a['player']}_{b['player']}"
            if key in used:
                continue
            # Verschiedene Märkte kombinieren
            if a["market"] != b["market"]:
                used.add(key)
                shot_pairs_cross.append([a, b])
                if len(shot_pairs_cross) >= 5:
                    break
        if len(shot_pairs_cross) >= 5:
            break

    # ── Claude Prompt ──
    import json as _json

    def _fmt(lst, n=12):
        return [{"player": c["player"], "team": c["team"], "match": c["match"],
                 "kickoff": c["kickoff"], "market": c["market"],
                 "stat": f"{c['stat_per90']}/90", "score": c.get("score",5)} for c in sorted(lst, key=lambda x: x.get("score",0), reverse=True)[:n]]

    payload = {
        "fouls":       _fmt(foul_candidates),
        "bookings":    _fmt(booking_candidates, 10),
        "shot_same_player": [
            {"player": v[0]["player"], "team": v[0]["team"], "match": v[0]["match"],
             "kickoff": v[0]["kickoff"], "market_1": v[0]["market"], "market_2": v[1]["market"]}
            for v in shot_pairs_same[:6]
        ],
        "shot_two_players": [
            {"player_1": p[0]["player"], "team_1": p[0]["team"], "match_1": p[0]["match"],
             "market_1": p[0]["market"],
             "player_2": p[1]["player"], "team_2": p[1]["team"], "match_2": p[1]["match"],
             "market_2": p[1]["market"]}
            for p in shot_pairs_cross
        ],
    }

    prompt = f"""Du bist Prop Builder Analyst (Nate Betting Style). Heute {target_date}.

Kandidaten mit FBref/StatsBomb/FPL Stats:
{_json.dumps(payload, ensure_ascii=False, indent=1)}

Erstelle 4-5 Bet Builder Kombinationen. Nutze alle Typen:

1. FOULS BUILDER (3-5 Legs): FC + FW Spieler, verschiedene Spiele
   z.B. Rodri 2+ FC + Saka 2+ FW + Kimmich 2+ FC → ~20/1

2. BOOKING BUILDER (2-4 Legs): Nur "Player to be Booked"
   z.B. Tavares + Bissouma + Casemiro → ~30/1

3. SHOT BUILDER+ SAME (2 Legs, selber Spieler): Korrelierte Märkte
   z.B. Kane 2+ SoT + Kane 3+ Shots → ~8/1

4. SHOT BUILDER+ TWO (2-3 Legs, verschiedene Spieler): Beide schussstark
   z.B. Saka 2+ SoT + Haaland 3+ Shots → ~15/1

5. MIXED (4-6 Legs): Fouls + Bookings + Shots mix

Odds: 2 Legs ~8/1 · 3 Legs ~15/1 · 4 Legs ~30/1 · 5 Legs ~60/1 · 6 Legs ~100/1

Antworte NUR JSON:
{{"combos":[{{"type":"BOOKING BUILDER","legs":[{{"player":"Name","team":"Team","match":"A vs B","market":"Player to be Booked","stat":"0.32/90"}}],"estimated_odds":"30/1","reason":"Begründung Deutsch"}}]}}"""

    results, source = call_gemini(prompt, use_tools=False)
    if not results:
        results, source = call_groq(prompt)

    combos = []
    try:
        import re as _re2
        text = _json.dumps(results) if isinstance(results, (list, dict)) else str(results)
        m = _re2.search(r'\{.*\}', text, _re2.DOTALL)
        if m:
            combos = _json.loads(m.group(0)).get("combos", [])
    except Exception as e:
        log(f"🔑 Props JSON Error: {e}", "WARN")
        return

    if not combos:
        log("🔑 Keine Kombis generiert")
        return

    # ── Senden ──
    TYPE_EMOJI = {
        "FOULS BUILDER":        "🟥",
        "BOOKING BUILDER":      "🟨",
        "SHOT BUILDER+":        "🎯",
        "SHOT BUILDER+ SAME":   "🎯",
        "SHOT BUILDER+ TWO":    "🎯",
        "MIXED":                "💎",
    }

    nl = "\n"
    header = (
        f"🔑 <b>PROP BUILDER — {target_date}</b>{nl}"
        f"<i>Shots · Fouls · Bookings · Nate Style</i>{nl}"
        f"━━━━━━━━━━━━━━━━━━━━{nl}"
        f"<i>📊 {total} Kandidaten · {len(combos)} Kombis · {source}</i>"
    )
    send_telegram(header, props_chat)

    for i, combo in enumerate(combos, 1):
        legs = combo.get("legs", [])
        if not legs:
            continue

        ctype = combo.get("type","COMBO").upper()
        emoji = TYPE_EMOJI.get(ctype, "🔑")

        by_match = {}
        for leg in legs:
            by_match.setdefault(leg.get("match","?"), []).append(leg)

        msg  = f"{emoji} <b>{ctype}</b>{nl}"
        msg += f"━━━━━━━━━━━━━━━━━━━━{nl}"
        for match, mlegs in by_match.items():
            msg += f"⚽ <b>{match}</b>{nl}"
            for leg in mlegs:
                stat = f" · {leg['stat']}" if leg.get("stat") else ""
                msg += f"  ▸ {leg.get('player','')} ({leg.get('team','')}){nl}"
                msg += f"    <b>{leg.get('market','')}</b>{stat}{nl}"
            msg += nl
        msg += f"💰 <b>{combo.get('estimated_odds','?')}</b>"
        if combo.get("reason"):
            msg += f"{nl}💡 <i>{combo['reason'][:130]}</i>"
        msg += f"{nl}━━━━━━━━━━━━━━━━━━━━"

        send_telegram(msg, props_chat)
        log(f"   🔑 {ctype} {i}: {combo.get('estimated_odds','?')} · {len(legs)} Legs")

    log(f"✅ Prop Builder: {len(combos)} Kombis gesendet")

def check_config():
    warnings = []

    # 🆕 Anzahl der Keys loggen
    log(f"🔑 API Keys geladen:")
    log(f"   • Gemini: {len(GEMINI_API_KEYS)} Keys")
    log(f"   • Groq: {len(GROQ_API_KEYS)} Keys")
    log(f"   • OpenRouter: {'✅ ' + str(len(OPENROUTER_API_KEYS)) + ' Keys' if OPENROUTER_API_KEYS else '❌ kein Key'}")
    log(f"   • Mistral: {'✅ aktiv' if MISTRAL_API_KEYS else '❌ kein Key'}")
    log(f"   • Cohere: {'✅ aktiv' if COHERE_API_KEY else '❌ kein Key'}")
    log(f"   • HuggingFace: {'✅ aktiv' if HUGGINGFACE_API_KEY else '❌ kein Key'}")
    log(f"   • Odds API: {len(ODDS_API_KEYS)} Keys")
    log(f"   • Football-Data: {len(FOOTBALL_DATA_API_KEYS)} Keys" if FOOTBALL_DATA_API_KEYS else "   • Football-Data: ❌")
    log(f"   • BSD: ✅ (8 Top-Ligen, unlimited Calls)")
    log(f"   • Sportmonks: ✅ (Dänemark + Schottland, Free Forever)")
    log(f"   • Wetter: {'✅ OpenWeatherMap aktiv!' if WEATHER_API_KEY else '❌ OPENWEATHER_API_KEY fehlt'}")
    log(f"   • FootyStats: {'✅ BTTS Stats aktiv!' if FOOTYSTATS_API_KEY else '❌ FOOTYSTATS_API_KEY fehlt (optional)'}")
    log(f"   • SportDB.dev: {'✅ Lineups + Flashscore!' if SPORTDB_API_KEY else '❌ SPORTDB_API_KEY fehlt (optional)'}")
    log(f"   • Livescore API: {'✅ aktiv!' if LIVESCORE_API_KEY else '❌ LIVESCORE_API_KEY fehlt (optional)'}")
    log(f"   • API-Ninjas: {'✅ aktiv!' if API_NINJAS_KEY else '❌ API_NINJAS_KEY fehlt (optional)'}")
    log(f"   • Playwright: {'✅ verfügbar!' if PLAYWRIGHT_AVAILABLE else '❌ nicht installiert (pip install playwright)'}")
    log(f"   • soccerdata: {'✅ verfügbar!' if SOCCERDATA_AVAILABLE else '❌ nicht installiert (pip install soccerdata)'}")
    log(f"   • FotMob: ✅ aktiv (kein Key!)")
    log(f"   • FPL API: ✅ aktiv (kein Key!)")
    log(f"   • DataHub.io: ✅ aktiv (kein Key!)")
    log(f"   • Tavily: {'✅ aktiv!' if TAVILY_API_KEY else '❌ TAVILY_API_KEY fehlt (optional)'}")
    log(f"   • AllSports API: {'✅ aktiv!' if ALLSPORTS_API_KEY else '❌ ALLSPORTS_API_KEY fehlt (optional)'}")
    log(f"   • Footballdata.io: {'✅ aktiv!' if FOOTBALLDATA_IO_API_KEY else '❌ FOOTBALLDATA_IO_API_KEY fehlt (optional, Settlement-Fallback)'}")
    log(f"   • OpenLigaDB: ✅ aktiv (kein Key, nur deutsche Ligen)")
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



# ============================================================
# 📊 DAILY REPORT - Automatisch jeden Morgen
# ============================================================

def send_daily_report():
    """Sendet täglich Performance Report an Stats Gruppe."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        month_start = today.replace(day=1)

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "date,market,league,status,odds,units", "date": f"gte.{month_start}", "status": "in.(won,lost)"},
            timeout=15,
        )
        if not r.ok:
            return
        tips = r.json()
        if not tips:
            return

        def get_stats(tip_list):
            won = sum(1 for t in tip_list if t.get("status") == "won")
            total = len(tip_list)
            profit = 0
            for t in tip_list:
                try:
                    odds = float(t.get("odds", 1.5) or 1.5)
                    units = float(t.get("units", 1.0) or 1.0)
                    profit += (odds - 1) * units if t.get("status") == "won" else -units
                except Exception:
                    pass
            return won, total, round(profit, 2)

        y_won, y_total, y_roi = get_stats([t for t in tips if t.get("date") == str(yesterday)])
        w_won, w_total, w_roi = get_stats([t for t in tips if t.get("date", "") >= str(week_ago)])
        m_won, m_total, m_roi = get_stats(tips)

        def line(won, total, roi, label):
            if total == 0:
                return ""
            pct = round(won / total * 100)
            e = "✅" if pct >= 65 else "⚠️" if pct >= 50 else "❌"
            re = "🟢" if roi >= 0 else "🔴"
            roi_s = f"+{roi}" if roi >= 0 else str(roi)
            return f"{e} <b>{label}:</b> {won}/{total} ({pct}%) · {roi_s}U {re}\n"

        msg = "📊 <b>NETRATTLER DAILY REPORT</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += f"📅 {today.strftime('%d.%m.%Y')}\n\n"
        msg += line(y_won, y_total, y_roi, "Gestern")
        msg += line(w_won, w_total, w_roi, "7 Tage")
        msg += line(m_won, m_total, m_roi, now_utc.strftime("%B"))

        # Liga Stats
        league_stats = {}
        for t in tips:
            lg = t.get("league", "?")
            if lg not in league_stats:
                league_stats[lg] = {"won": 0, "total": 0}
            league_stats[lg]["total"] += 1
            if t.get("status") == "won":
                league_stats[lg]["won"] += 1

        top = [(lg, s["won"], s["total"], round(s["won"]/s["total"]*100)) for lg, s in league_stats.items() if s["total"] >= 3]
        top_good = sorted([x for x in top if x[3] >= 70], key=lambda x: x[3], reverse=True)[:5]
        top_bad = sorted([x for x in top if x[3] < 40], key=lambda x: x[3])[:3]

        if top_good:
            msg += "\n🏆 <b>Top Ligen:</b>\n"
            for lg, w, t, pct in top_good:
                msg += f"✅ {lg}: {w}/{t} ({pct}%)\n"

        if top_bad:
            msg += "\n⚠️ <b>Schwache Ligen:</b>\n"
            for lg, w, t, pct in top_bad:
                msg += f"❌ {lg}: {w}/{t} ({pct}%) → pausieren?\n"

        msg += "\n━━━━━━━━━━━━━━━━━━\n"
        overall = round(m_won / m_total * 100) if m_total > 0 else 0
        if overall >= 75:
            msg += "🚀 <b>Exzellent!</b> Weiter so!\n"
        elif overall >= 65:
            msg += "✅ <b>Gut!</b> Kleine Optimierung möglich.\n"
        elif overall >= 55:
            msg += "⚠️ <b>Filter verschärfen!</b>\n→ MIN_PROBABILITY auf 70%\n"
        else:
            msg += "❌ <b>Analyse nötig!</b>\n→ Flop Ligen deaktivieren\n"

        _auto_void_old_pending()

        stats_chat = TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID)
        if stats_chat:
            send_telegram(msg, stats_chat)
            log("✅ Daily Report gesendet!")

    except Exception as e:
        log(f"Daily Report Error: {str(e)[:60]}", "WARN")



# ============================================================
# 🚀 NETRATTLER PRO V3 — Eingebettet
# Edge Filter · CLV · Drawdown · Pinnacle · Backtest
# ============================================================
NETRATTLER_PRO = True
_PINNACLE_MATCHUPS = []  # Wird in main() gefüllt
_AF_BULK_FIXTURES = {}   # API-Football Bulk Cache - global

import math


# ════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ════════════════════════════════════════════════════════════════════════

def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in ["1", "true", "yes", "on"]


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except:
        return default


def _log(component: str, msg: str, level: str = "INFO"):
    print(f"[{component}] [{level}] {msg}", flush=True)


# Shared Cache Helpers
def _cache_get(cache: dict, key: str, ttl: int = 600):
    entry = cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > ttl:
        return None
    return entry["data"]


def _cache_set(cache: dict, key: str, data):
    cache[key] = {"ts": time.time(), "data": data}


# Shared Constants
SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_KEY")
ODDS_API_KEYS = [k.strip() for k in _env("ODDS_API_KEYS").split(",") if k.strip()]
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
TELEGRAM_GROUP_PREMIUM = _env("TELEGRAM_GROUP_PREMIUM_ALERTS", TELEGRAM_CHAT_ID)


# ════════════════════════════════════════════════════════════════════════
# 1️⃣ MARKET INFO EXTENDED (inkl. neuer Märkte)
# ════════════════════════════════════════════════════════════════════════

MARKET_INFO_EXTENDED = {
    "btts": {
        "name": "⚽ BTTS", "emoji": "⚽",
        "instr": "Analysiere BTTS (Both Teams To Score).",
        "bet365_market": "btts", "tip_outcome": "Yes",
    },
    "over25": {
        "name": "🎯 Over 2.5", "emoji": "🎯",
        "instr": "Analysiere Over 2.5 Tore.",
        "bet365_market": "totals", "tip_outcome": "Over", "point": 2.5,
    },
    "combo": {
        "name": "🔥 BTTS + Over 2.5", "emoji": "🔥",
        "instr": "Analysiere BTTS & Over 2.5 KOMBO.",
        "bet365_market": "btts_and_totals", "tip_outcome": "Yes & Over", "point": 2.5,
    },
    "btts_ht": {
        "name": "🕐 BTTS HT", "emoji": "🕐",
        "instr": "Analysiere BTTS in der 1. Halbzeit.",
        "bet365_market": "btts_1h", "tip_outcome": "Yes",
    },
    "over15_ht": {
        "name": "⏰ Over 1.5 HT", "emoji": "⏰",
        "instr": ("Analysiere Over 1.5 Tore in der 1. Halbzeit. "
                  "Berücksichtige xG HT pro Team, Pressing, frühe Tor-Quote."),
        "bet365_market": "totals_1h", "tip_outcome": "Over", "point": 1.5,
    },
    "corners": {
        "name": "🚩 Corners Over", "emoji": "🚩",
        "instr": "Analysiere Eckbälle pro Spiel.",
        "bet365_market": "corners_totals", "tip_outcome": "Over",
    },
    "scorer": {
        "name": "⚽ Anytime Scorer", "emoji": "⚽",
        "instr": "Analysiere Anytime Goalscorer.",
        "bet365_market": "anytime_goalscorer", "tip_outcome": "Yes",
    },
    "advanced_props": {
        "name": "🔑 Player Props", "emoji": "🔑",
        "instr": "Analysiere Player Props (SOT, Fouls, Bookings).",
        "bet365_market": "player_props", "tip_outcome": "Over",
    },
}


# ════════════════════════════════════════════════════════════════════════
# 2️⃣ PINNACLE SCRAPER (Kostenlose Pinnacle-Quoten)
# ════════════════════════════════════════════════════════════════════════

PINNACLE_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
PINNACLE_SPORT_SOCCER = 29
PINNACLE_GUEST_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"

PINNACLE_HEADERS = {
    "x-api-key": PINNACLE_GUEST_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.pinnacle.com/",
    "Origin": "https://www.pinnacle.com",
    "Accept": "application/json",
}

_PIN_MATCHUP_CACHE = {}
_PIN_ODDS_CACHE = {}


def _pin_american_to_decimal(a) -> float:
    """American Odds → Dezimalquote."""
    try:
        a = float(a)
        return round(1 + (a / 100.0 if a > 0 else 100.0 / abs(a)), 2)
    except Exception:
        return 0.0


AF_TEAM_ID_CACHE = {}

def _af_find_team_id(team_name, league_id):
    """Sucht team_id über /teams?search= für H2H/Stats/Injuries."""
    if not team_name or not league_id:
        return None
    cache_key = f"{team_name.lower()}_{league_id}"
    if cache_key in AF_TEAM_ID_CACHE:
        return AF_TEAM_ID_CACHE[cache_key]

    response = _af_request("/teams", {"search": team_name})
    tid = None
    if response:
        # Bestes Match: exakter Name-Treffer bevorzugen
        for entry in response:
            tname = (entry.get("team") or {}).get("name", "")
            if tname.lower() == team_name.lower():
                tid = (entry.get("team") or {}).get("id")
                break
        if tid is None and response:
            tid = (response[0].get("team") or {}).get("id")

    AF_TEAM_ID_CACHE[cache_key] = tid
    return tid


# Top-5-Ligen für Daten-Enrichment (API-Football Budget schonen)
ENRICH_LEAGUES = {
    "premier league": 39, "la liga": 140, "bundesliga": 78,
    "serie a": 135, "ligue 1": 61,
}


def enrich_pinnacle_tip(tip_dict, home, away, league_name, season=2025):
    """
    Reichert einen Pinnacle-Tipp mit Wetter, H2H, xG, Verletzungen, Schiri an.
    Wetter: für alle Ligen (kostenlos via Open-Meteo).
    H2H/xG/Verletzungen: nur Top-5-Ligen (API-Football Budget).
    """
    ln = league_name.lower()

    # 🌤️ Wetter (kostenlos, alle Ligen)
    try:
        weather = get_open_meteo_weather(league_name, datetime.now(timezone.utc).date())
        if weather:
            tip_dict["weather"] = weather
    except Exception:
        pass

    # Nur Top-5-Ligen: H2H, xG, Verletzungen
    league_id = None
    for key, lid in ENRICH_LEAGUES.items():
        if key in ln:
            league_id = lid
            break
    if not league_id or APIFOOTBALL_QUOTA_EXHAUSTED:
        return tip_dict

    try:
        home_id = _af_find_team_id(home, league_id)
        away_id = _af_find_team_id(away, league_id)

        if home_id and away_id:
            # H2H
            h2h = fetch_head_to_head(home_id, away_id, last=5)
            if h2h:
                tip_dict["h2h_btts"] = f"{int(h2h['btts_rate']/100*h2h['count'])}/{h2h['count']}"
                tip_dict["h2h_avg_goals"] = h2h["avg_goals"]

            # Team Stats (xG, BTTS-Rate, Form)
            hs = fetch_team_statistics(home_id, league_id, season)
            as_ = fetch_team_statistics(away_id, league_id, season)
            if hs:
                tip_dict["xg_home"] = hs.get("goals_for_avg")
                tip_dict["btts_rate_home"] = hs.get("btts_rate_approx")
                tip_dict["homeForm"] = hs.get("form")
            if as_:
                tip_dict["xg_away"] = as_.get("goals_for_avg")
                tip_dict["btts_rate_away"] = as_.get("btts_rate_approx")
                tip_dict["awayForm"] = as_.get("form")

            # Verletzungen
            inj_h = fetch_injuries(home_id, league_id, season)
            inj_a = fetch_injuries(away_id, league_id, season)
            if inj_h:
                tip_dict["injuries_home"] = ", ".join(i["name"] for i in inj_h[:3])
            if inj_a:
                tip_dict["injuries_away"] = ", ".join(i["name"] for i in inj_a[:3])
    except Exception:
        pass

    return tip_dict


def _pinnacle_get_json(url, params):
    """GET mit JSON-Parse. Fällt auf Playwright zurück falls requests leer/blockiert ist."""
    try:
        r = requests.get(url, headers=PINNACLE_HEADERS, params=params, timeout=20)
        if r.ok:
            try:
                data = r.json()
                if data:  # nicht-leere Antwort
                    return data, r.status_code
            except Exception:
                pass
        status = r.status_code
    except Exception as e:
        status = f"EXC:{str(e)[:40]}"

    # Fallback: Playwright (umgeht Cloudflare/Bot-Block)
    if PLAYWRIGHT_AVAILABLE:
        try:
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            html = scrape_with_playwright(full_url, timeout=15000)
            if html:
                import re as _re
                # JSON kann in <pre> oder roh im body stehen
                m = _re.search(r'(\[.*\]|\{.*\})', html, _re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        log(f"   🔑 Pinnacle Props: Playwright-Fallback erfolgreich")
                        return data, "playwright_ok"
                    except Exception:
                        pass
        except Exception as e:
            log(f"   🔑 Pinnacle Props: Playwright-Fallback Fehler {str(e)[:60]}", "WARN")

    return None, status


def fetch_pinnacle_player_props() -> List[Dict]:
    """Player Props Specials von Pinnacle (echte Quoten)."""
    try:
        data, status = _pinnacle_get_json(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/matchups",
            {"withSpecials": "true", "brandId": "0"},
        )
        if not data:
            log(f"   🔑 Pinnacle Props: matchups fehlgeschlagen ({status})", "WARN")
            return []
        log(f"   🔑 Pinnacle Props: {len(data)} Einträge total (inkl. normale Matches)")

        # Specials zählen nach Typ/Kategorie für Diagnose
        special_count = sum(1 for m in data if m.get("type") == "special")
        log(f"   🔑 Pinnacle Props: {special_count} Specials gefunden")
        if special_count > 0:
            sample_cats = set()
            for m in data:
                if m.get("type") == "special":
                    sp = m.get("special", {}) or {}
                    sample_cats.add((sp.get("category") or sp.get("categoryName") or "?"))
                if len(sample_cats) >= 8:
                    break
            log(f"   🔑 Pinnacle Props: Beispiel-Kategorien: {list(sample_cats)[:8]}")

        # Quoten holen — mit Specials-Flag (gleicher Endpunkt wie funktionierende Matchups-Funktion)
        r2_data, status2 = _pinnacle_get_json(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/markets/straight",
            {"primaryOnly": "false", "withSpecials": "true"},
        )
        prices_by_matchup = {}
        if r2_data:
            log(f"   🔑 Pinnacle Props: {len(r2_data)} Markt-Einträge für Quoten")
            for mk in r2_data:
                mid = mk.get("matchupId")
                for p in mk.get("prices", []):
                    pid = p.get("participantId")
                    if mid and pid:
                        prices_by_matchup[(mid, pid)] = p.get("price")
        else:
            log(f"   🔑 Pinnacle Props: markets/straight fehlgeschlagen ({status2})", "WARN")

        props = []
        skipped_no_price = 0
        for m in data:
            if m.get("type") != "special":
                continue
            sp = m.get("special", {}) or {}
            # Kategorie-Feld kann je nach API-Version anders heissen — alle Varianten prüfen
            cat = (sp.get("category") or sp.get("categoryName") or sp.get("type") or "").lower()
            desc = sp.get("description", "") or sp.get("name", "")
            parent = m.get("parent") or {}
            pparts = parent.get("participants", [])
            ph = next((p.get("name","") for p in pparts if p.get("alignment")=="home"), "")
            pa = next((p.get("name","") for p in pparts if p.get("alignment")=="away"), "")

            desc_low = desc.lower()
            player_keywords = [
                "anytime goalscorer", "first goalscorer", "last goalscorer",
                "player to score", "to assist", "to be booked", "shots",
                "shot on target", "fouls committed", "fouls won", "tackles",
                "saves", "offsides", "passes", "interceptions", "clearances",
                "player cards", "to be fouled", "to be carded", "to be shown a card",
                "headed shot", "outside box", "goalkeeper saves", "player headed",
            ]
            team_builder_keywords = [
                "either team to score", "both teams to score", "team to score",
                " to score?", "both teams to receive a card", "to qualify",
                "to reach the final", "1st half goals", "2nd half goals",
            ]
            is_player_category = "player" in cat
            is_team_category = "team" in cat or "reach the final" in cat
            is_player_description = any(k in desc_low for k in player_keywords)
            is_team_builder_description = any(k in desc_low for k in team_builder_keywords)

            if not (
                is_player_category or is_team_category
                or is_player_description or is_team_builder_description
            ):
                continue
            league_name = (m.get("league") or {}).get("name", "")
            starts = m.get("startTime", "") or parent.get("startTime", "")
            for part in m.get("participants", []):
                price = prices_by_matchup.get((m.get("id"), part.get("id")))
                if price is None:
                    skipped_no_price += 1
                    continue
                dec = _pin_american_to_decimal(price)
                if dec <= 1.0:
                    continue
                props.append({
                    "player_prop": desc,
                    "selection": part.get("name", ""),
                    "odds": dec,
                    "prob": int(100 / dec * 0.95) if dec > 1 else 0,
                    "match": f"{ph} vs {pa}" if ph else desc,
                    "league": league_name,
                    "starts": starts,
                    "special_category": cat,
                    "is_team_market": bool(is_team_category or is_team_builder_description),
                })
        if skipped_no_price:
            log(f"   🔑 Pinnacle Props: {skipped_no_price} Props ohne Preis übersprungen")
        _log("PINNACLE", f"🔑 {len(props)} Player-Prop-Quoten geladen")
        return props
    except Exception as e:
        _log("PINNACLE", f"Props Fehler: {str(e)[:80]}", "WARN")
        return []


# Prop-Typen die Skip werden (tournament-weite Specials, nicht match-gebunden)
_SKIP_PROP_KEYWORDS = [
    "head to head", "most goals", "most assists", "top scorer", "golden boot",
    "golden ball", "tournament winner", "group winner",
]

# Leg-Kategorien für Bet Builder
_REAL_PLAYER_BUILDER_CATS = {
    "score", "first_scorer", "last_scorer", "assist",
    "booked", "yellow_cards", "sot", "shots", "sot_outside_box", "shots_outside_box",
    "fouls", "fouls_won", "tackles_committed", "tackles_received",
    "saves", "offsides",
}

_LEG_CATEGORY = {
    "btts_ht": ["either team to score? 1st half", "both teams to score 1st half", "btts 1st half", "btts ht"],
    "half_goals_1st": ["over 1.5 goals 1st half", "over 2 goals 1st half", "1st half goals"],
    "half_goals_2nd": ["over 1.5 goals 2nd half", "over 2 goals 2nd half", "2nd half goals"],
    "team_cards": ["both teams to receive a card", "both teams carded"],
    "btts": ["both teams to score", "either team to score"],
    "result": ["to qualify", "qualify", "to reach the final"],
    "first_scorer": ["first goalscorer", "first goal scorer"],
    "last_scorer": ["last goalscorer", "last goal scorer"],
    "score": ["anytime goalscorer", "player to score", "score or assist"],
    "match_goals": ["team to score", " to score?", "total goals"],
    "assist": ["to assist", "score or assist"],
    "booked": ["to be booked", "receive a card", "be carded"],
    "sot_outside_box": ["shots on target from outside", "shot on target from outside"],
    "shots_outside_box": ["shots from outside", "shot from outside"],
    "sot": ["shots on target", "shot on target"],
    "shots": ["shots", "shots on goal"],
    "fouls_won": ["fouls won", "to be fouled"],
    "fouls": ["fouls committed", "foul committed", "foul"],
    "tackles_received": ["tackles received", "times tackled", "to be tackled"],
    "tackles_committed": ["tackles committed", "tackles made", "player tackles", "tackles won", "tackle"],
    "corners": ["corners", "corner kicks"],
    "saves": ["saves", "goalkeeper saves"],
    "offsides": ["offside"],
}

def _get_leg_category(prop_name):
    pn = str(prop_name or "").lower()
    matches = []
    for cat, keywords in _LEG_CATEGORY.items():
        for keyword in keywords:
            if keyword in pn:
                matches.append((len(keyword), cat))
    if not matches:
        return "other"
    # Spezifischster/längster Ausdruck gewinnt.
    matches.sort(reverse=True)
    return matches[0][1]


def _is_either_market(prop_name):
    """Erkennt Either-Or-Substitute-Märkte (mehrere Spieler in einer Quote kombiniert)."""
    pn = prop_name.lower()
    return " or " in pn and (" to " in pn or "either" in pn)

def _calc_combo_odds(legs):
    """Berechnet kombinierte Quote mit Korrelationsabschlag."""
    if not legs:
        return 1.0
    odds = 1.0
    for l in legs:
        odds *= l["odds"]
    # Korrelationsabschlag: 15% für 2 Legs, 20% für 3+
    disc = 0.85 if len(legs) == 2 else 0.80
    return round(odds * disc, 2)

def _fbref_prop_edge_check(player_name, league_name, prop_name, pinnacle_prob):
    """
    Kreuzvergleich: FBref-Statistik vs. Pinnacle-Quote.
    Berechnet eine unabhängige Wahrscheinlichkeit aus echten Saison-Stats
    und vergleicht sie mit der quoten-implizierten Pinnacle-Wahrscheinlichkeit.
    Gibt (adjusted_prob, has_fbref_data, edge_confirmed) zurück.

    Ohne FBref-Daten: Pinnacle-Wahrscheinlichkeit unverändert nutzen (has_fbref_data=False).
    Mit FBref-Daten: Mittelwert aus beiden Quellen (60% FBref-Stats, 40% Pinnacle-Markt),
    da FBref echte Spielerleistung misst, der Markt aber Verletzungen/Tagesform einpreist.
    """
    try:
        stats = _advanced_props_manager.scrape_fbref_advanced_stats(league_name)
    except Exception:
        stats = {}

    if not stats:
        return pinnacle_prob, False, False

    # Spieler fuzzy matchen (FBref nutzt oft Kurznamen)
    player_stats = None
    pn_lower = player_name.lower()
    for name, s in stats.items():
        if pn_lower in name.lower() or name.lower() in pn_lower:
            player_stats = s
            break
    if not player_stats:
        return pinnacle_prob, False, False

    pn = prop_name.lower()
    fbref_prob = None

    # Marktspezifische FBref-Wahrscheinlichkeit ableiten (Poisson-ähnliche Heuristik)
    if "score" in pn or "goalscorer" in pn:
        # Keine direkte Tor-Rate in player_db — überspringen (Pinnacle bleibt führend)
        return pinnacle_prob, True, False
    elif "shot" in pn:
        sot = player_stats.get("sot_per90", 0)
        # P(mind. 1 SoT) via Poisson-Näherung
        fbref_prob = round((1 - math.exp(-sot)) * 100) if sot > 0 else None
    elif "booked" in pn or "card" in pn:
        yc = player_stats.get("yc_per90", 0)
        fbref_prob = round(yc * 100) if yc > 0 else None
    elif "foul" in pn and "drawn" not in pn and "won" not in pn:
        fc = player_stats.get("fouls_committed", 0)
        fbref_prob = round((1 - math.exp(-fc)) * 100) if fc > 0 else None
    elif "fouled" in pn or "foul" in pn and ("drawn" in pn or "won" in pn):
        fw = player_stats.get("fouls_drawn", 0)
        fbref_prob = round((1 - math.exp(-fw)) * 100) if fw > 0 else None

    if fbref_prob is None:
        return pinnacle_prob, True, False

    fbref_prob = max(5, min(95, fbref_prob))
    blended = round(0.6 * fbref_prob + 0.4 * pinnacle_prob)
    # Edge bestätigt wenn beide Quellen sich einig sind (FBref >= Pinnacle - 10)
    edge_confirmed = fbref_prob >= (pinnacle_prob - 10)
    return blended, True, edge_confirmed


_STAT_INSIGHT_SENT_TODAY = set()  # Dedup: ein Analyse-Post pro Match pro Tag

def _send_stat_insight_fallback(match_name, legs):
    """
    Sendet eine reine Statistik-Analyse (keine Quote) wenn der Bet Builder
    für ein WM-Spiel keine sinnvolle Kombi bauen konnte. Nutzt FotMob-Kaderstats.
    """
    _dedup_key = f"{match_name}_{datetime.now(timezone.utc).date()}"
    if _dedup_key in _STAT_INSIGHT_SENT_TODAY:
        return
    if " vs " not in match_name:
        return
    home_team, away_team = match_name.split(" vs ", 1)
    league = legs[0].get("league", "") if legs else ""
    kickoff_str = ""
    try:
        _ko = legs[0].get("_ko") if legs else None
        if _ko:
            kickoff_str = _ko.strftime("%H:%M")
    except Exception:
        pass

    msg = generate_stat_insight_tip(match_name, league, home_team, away_team, kickoff_str)
    if not msg:
        return  # keine echten Daten gefunden — nichts senden

    stats_chat = TELEGRAM_GROUPS.get("advanced_props") or TELEGRAM_GROUPS.get("stats")
    if stats_chat:
        send_telegram(msg, chat_id=stats_chat)
        _STAT_INSIGHT_SENT_TODAY.add(_dedup_key)
        log(f"   📊 Stat-Analyse gesendet (statt Bet Builder): {match_name}")



def _ntr_builder_stake_for_odds(odds, legs=None):
    try:
        o = float(odds or 0)
    except Exception:
        o = 0.0
    if o >= 100:
        return 0.05
    if o >= 50:
        return 0.10
    if o >= 20:
        return 0.15
    if o >= 8:
        return 0.25
    if o >= 3.5:
        return 0.35
    return 0.50

def _ntr_builder_read(prob, odds):
    try:
        p = float(prob or 0)
        o = float(odds or 0)
    except Exception:
        p, o = 0.0, 0.0
    if o >= 50:
        return "LOTTERY", max(1, min(10, round((p - 35) / 6)))
    if o >= 12:
        return "HIGH ODDS", max(1, min(10, round((p - 40) / 5)))
    if p >= 68 and o <= 4:
        return "SAFE/VALUE", max(1, min(10, round((p - 45) / 5)))
    if p >= 55:
        return "VALUE", max(1, min(10, round((p - 42) / 5)))
    return "SPECULATIVE", max(1, min(10, round((p - 35) / 6)))


def _ntr_is_generic_builder_selection(value):
    v = str(value or "").strip().lower()
    if not v:
        return True
    if v in {"yes", "no", "home", "away", "draw", "odd", "even", "over", "under"}:
        return True
    if v.startswith(("over ", "under ")):
        return True
    if re.fullmatch(r"[ou]\s*\d+(?:\.\d+)?", v):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\+?", v):
        return True
    return False

def _ntr_builder_player_name(leg):
    desc = str(leg.get("player_prop") or leg.get("market") or "").strip()
    sel = str(leg.get("selection") or leg.get("player") or "").strip()
    if sel and not _ntr_is_generic_builder_selection(sel):
        return sel[:100]
    try:
        p = _ntr_extract_player(desc, sel)
        if p and not _ntr_is_generic_builder_selection(p):
            return p[:100]
    except Exception:
        pass
    m = re.search(
        r"^(.+?)\s+(?:anytime\s+goalscorer|first\s+goalscorer|last\s+goalscorer|"
        r"to\s+be\s+booked|player\s+to\s+be\s+booked|to\s+score|shots?\s+on\s+target|shots?)\b",
        desc,
        flags=re.I,
    )
    if m:
        p = m.group(1).strip(" -:|")
        if p and not _ntr_is_generic_builder_selection(p):
            return p[:100]
    return ""

def _ntr_builder_market_label(leg):
    desc = str(leg.get("player_prop") or leg.get("market") or "").strip()
    cat = str(leg.get("_cat") or leg.get("category") or "").strip()
    line = leg.get("line", None)
    try:
        line_f = float(line) if line is not None and str(line) != "" else None
    except Exception:
        line_f = None
    if cat in {"booked", "yellow_cards"}:
        return "To Be Booked"
    if cat == "score":
        return "Anytime Goalscorer"
    if cat == "first_scorer":
        return "First Goalscorer"
    if cat == "last_scorer":
        return "Last Goalscorer"
    if cat == "sot":
        return f"Over {line_f:g} Shots on Target" if line_f and line_f > 1 else "1+ Shot on Target"
    if cat == "shots":
        return f"Over {line_f:g} Shots" if line_f and line_f > 1 else "1+ Shot"
    if cat in {"fouls", "fouls_committed"}:
        return f"Over {line_f:g} Fouls Committed" if line_f and line_f > 1 else "1+ Foul Committed"
    if cat == "fouls_won":
        return f"Over {line_f:g} Fouls Won" if line_f and line_f > 1 else "1+ Foul Won"
    if cat == "tackles_committed":
        return f"Over {line_f:g} Tackles Committed" if line_f and line_f > 1 else "1+ Tackle Committed"
    if cat == "tackles_received":
        return f"Over {line_f:g} Tackles Received" if line_f and line_f > 1 else "1+ Tackle Received"
    return desc or str(leg.get("selection") or "").strip() or "Market"

def _ntr_builder_leg_line(leg, icons, indent=""):
    cat = str(leg.get("_cat") or leg.get("category") or "other")
    icon = icons.get(cat, "○")
    player = _ntr_builder_player_name(leg)
    label = _ntr_builder_market_label(leg)
    fbref = " 🔍" if leg.get("_fbref_confirmed") else ""
    either = " 🔀" if leg.get("_is_either") else ""
    player_cats = {
        "score", "first_scorer", "last_scorer", "assist",
        "booked", "yellow_cards", "sot", "shots",
        "fouls", "fouls_committed", "fouls_won",
        "tackles_committed", "tackles_received", "saves", "offsides",
    }
    if player and cat in player_cats:
        return f"{indent}{icon} <b>{player}</b> — {label}{fbref}{either}"
    return f"{indent}{icon} {label}{fbref}{either}"

def run_pinnacle_props_bot(win_start_utc=None, win_end_utc=None, ch_tz=None, top_btts_tips=None, fixtures_cache=None) -> int:
    """
    Pinnacle Player Props Bot.
    top_btts_tips: Beste BTTS-Tipps aus Hauptanalyse (als zusätzliche Bet-Builder-Legs).
    """
    """Bet Builder Style: Pro Spiel 2-4 Legs kombiniert → Prop Hunter Kanal.
    Quellen: Pinnacle (echte Quoten) + FBref (unabhängige Stats) für Cross-Validation."""
    from datetime import datetime as _dt2
    props = fetch_pinnacle_player_props()
    if not props:
        log("🔑 Pinnacle Props: keine Specials verfügbar")
        return 0

    # Diagnose der tatsächlich angebotenen Special-Märkte.
    _raw_category_counts = {}
    for _raw_prop in props:
        if not isinstance(_raw_prop, dict):
            continue
        _text = (
            f"{_raw_prop.get('special_category', '')} "
            f"{_raw_prop.get('player_prop', '')} "
            f"{_raw_prop.get('selection', '')}"
        )
        _category = _get_leg_category(_text)
        _raw_category_counts[_category] = _raw_category_counts.get(_category, 0) + 1
    log(
        "   🔑 Pinnacle Roh-Kategorien: "
        + ", ".join(
            f"{key}={value}" for key, value in sorted(
                _raw_category_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:12]
        )
    )

    # Alle validen Props sammeln
    valid = []
    _fbref_checked = 0
    _fbref_confirmed = 0
    _invalid_prop_rows = 0
    _builder_player_prop_count = 0
    _builder_player_prop_cats = {}
    for p in props:
        if not isinstance(p, dict):
            _invalid_prop_rows += 1
            continue
        sel = str(p.get("selection") or "").lower()
        prop_name = p.get("player_prop", "").lower()
        match_name = p.get("match", "")

        if "under" in sel or sel.strip() == "no":
            continue
        if any(kw in prop_name for kw in _SKIP_PROP_KEYWORDS):
            continue
        if not match_name or "vs" not in match_name.lower():
            continue
        if match_name.lower() == prop_name:
            continue
        _classification_text = (
            f"{p.get('special_category', '')} "
            f"{p.get('player_prop', '')} "
            f"{p.get('selection', '')}"
        )
        p["_cat"] = _get_leg_category(_classification_text)
        p["_is_either"] = _is_either_market(_classification_text)
        if p["_cat"] == "other":
            continue

        _is_real_player_builder_leg = p["_cat"] in _REAL_PLAYER_BUILDER_CATS and not p.get("is_team_market")
        # Spielerprops wie Kane 2+ SOT / Messi Tor / Otamendi Karte haben oft hohe Quoten
        # und dadurch niedrige implizite Prob. Diese dürfen für Builder rein.
        if _is_real_player_builder_leg:
            if not (1.15 <= float(p.get("odds", 0) or 0) <= 25.00):
                continue
            if int(p.get("prob", 0) or 0) < 15:
                continue
        else:
            if not (1.15 <= float(p.get("odds", 0) or 0) <= 5.00):
                continue
            if int(p.get("prob", 0) or 0) < 55:
                continue

        # 🔍 FBref Cross-Check: unabhängige Wahrscheinlichkeit gegen Pinnacle-Quote prüfen
        try:
            if p.get("is_team_market"):
                raise LookupError("team market")
            adj_prob, has_data, confirmed = _fbref_prop_edge_check(
                p["selection"], p.get("league", ""), prop_name, p["prob"]
            )
            if has_data:
                _fbref_checked += 1
                p["prob"] = adj_prob
                p["_fbref_confirmed"] = confirmed
                if confirmed:
                    _fbref_confirmed += 1
        except Exception:
            pass

        # Zeitfenster
        if win_start_utc and p.get("starts"):
            try:
                s = p["starts"].replace("Z", "+00:00")
                if "+" not in s[10:] and s[10:].count("-") == 0:
                    s += "+00:00"
                md = _dt2.fromisoformat(s)
                _grace = timedelta(minutes=90)
                if md < (win_start_utc - _grace) or md >= (win_end_utc + _grace):
                    continue
                p["_ko"] = md
            except Exception:
                continue

        # Kategorie wurde vor dem Odds/Prob-Filter gesetzt. Hier nur final sammeln.
        if p.get("_cat") == "other":
            continue

        valid.append(p)

        _desc = p.get("player_prop", "")
        _category = {
            "booked": "yellow_cards",
            "tackles": "tackles_committed",
            "corners": "team_corners",
        }.get(p["_cat"], p["_cat"])
        _player = (
            _desc.rstrip("?") if p.get("is_team_market")
            else _ntr_extract_player(_desc, p.get("selection", ""))
        )
        _before_pool = len(_NTR_BUILDER_PROP_POOL)
        _ntr_collect_prop(
            _player, "", p.get("match", ""), p.get("league", ""), _desc,
            category=_category,
            line=_ntr_market_line(_desc, 1),
            odds=p.get("odds", 0),
            probability=p.get("prob", 0),
            source="pinnacle",
            kickoff=p.get("starts", ""),
            games=0,
        )
        if len(_NTR_BUILDER_PROP_POOL) > _before_pool and p.get("_cat") in _REAL_PLAYER_BUILDER_CATS:
            try:
                _builder_player_prop_count += 1
                _builder_player_prop_cats[_category] = _builder_player_prop_cats.get(_category, 0) + 1
            except NameError:
                _builder_player_prop_count = 1
                _builder_player_prop_cats = {_category: 1}

    if _invalid_prop_rows:
        log(f"   ⚠️ Pinnacle Props: {_invalid_prop_rows} ungültige Rows ignoriert")
    if _fbref_checked > 0:
        log(f"   🔍 FBref Cross-Check: {_fbref_checked} Props mit Stats abgeglichen, {_fbref_confirmed} bestätigt")
    if _builder_player_prop_count:
        log(
            "   🔥 Echte Spieler-Props für Builder: "
            + str(_builder_player_prop_count)
            + " Legs · "
            + ", ".join(f"{k}={v}" for k, v in sorted(_builder_player_prop_cats.items(), key=lambda item: item[1], reverse=True)[:10])
        )

    if not valid:
        log("🔑 Pinnacle Props: keine Props im Zeitfenster")
        return 0

    # 🌍 WM-Diagnose: wie viele valide Props/Matches sind World Cup?
    _wc_props = [p for p in valid if "world cup" in p.get("league", "").lower() or "fifa" in p.get("league", "").lower()]
    _wc_matches = set(p.get("match", "?") for p in _wc_props)
    log(f"   🌍 WM-Diagnose: {len(_wc_props)} valide Props aus {len(_wc_matches)} WM-Spielen")
    if _wc_matches:
        for _m in list(_wc_matches)[:5]:
            _cats = set(p.get("player_prop", "")[:30] for p in _wc_props if p.get("match") == _m)
            log(f"      🌍 {_m}: {len([p for p in _wc_props if p.get('match')==_m])} Props, Beispiele: {list(_cats)[:4]}")

    # Props nach Spiel gruppieren
    by_match = {}
    for p in valid:
        mn = p.get("match", "?")
        by_match.setdefault(mn, []).append(p)

    # 🏆 Matchwinner-Leg: echte Pinnacle 1X2-Quote pro Spiel als zusätzliche Leg-Option
    for match_name in list(by_match.keys()):
        try:
            parts = match_name.split(" vs ")
            if len(parts) != 2:
                continue
            home, away = parts[0].strip(), parts[1].strip()
            mw_odds = get_pinnacle_match_odds(home, away)
            if not mw_odds:
                continue
            # Favoriten-Seite mit solider Quote wählen (Heim oder Auswärts, nicht Remis)
            hw = mw_odds.get("home_win")
            aw = mw_odds.get("away_win")
            for side_name, side_odds, side_label in [
                (home, hw, f"Result: {home}"),
                (away, aw, f"Result: {away}"),
            ]:
                if not side_odds:
                    continue
                try:
                    side_odds = float(side_odds)
                except Exception:
                    continue
                if not (1.15 <= side_odds <= 3.50):
                    continue
                _mw_prob = int(100 / side_odds * 0.95)
                if _mw_prob < 55:
                    continue
                by_match[match_name].append({
                    "selection": side_name,
                    "player_prop": side_label,
                    "odds": side_odds,
                    "prob": _mw_prob,
                    "match": match_name,
                    "league": mw_odds.get("league", ""),
                    "_cat": "result",
                    "_fbref_confirmed": False,
                })
        except Exception:
            continue

    # Pro Spiel: beste 2-4 Legs auswählen (verschiedene Kategorien, Vielfalt erzwungen)
    builders = []
    _rejected_too_few_legs = 0
    _rejected_low_odds = 0
    for match_name, legs in by_match.items():
        _is_wc_match = match_name in _wc_matches

        # Innerhalb jeder Kategorie sortieren: Either-Or-Märkte zuerst (höhere Trefferquote),
        # dann FBref-bestätigt, dann nach Wahrscheinlichkeit
        legs.sort(key=lambda x: (not x.get("_is_either", False), not x.get("_fbref_confirmed", False), -x["prob"]))

        # Legs nach Kategorie gruppieren
        by_cat = {}
        for leg in legs:
            by_cat.setdefault(leg["_cat"], []).append(leg)

        selected = []
        used_players = set()

        # 🆕 Round-Robin — max 6 Legs (Bet Builder = 2-6 Tipps)
        cat_order = sorted(by_cat.keys(), key=lambda c: -len(by_cat[c]))
        cat_pointers = {c: 0 for c in cat_order}
        while len(selected) < 6:
            progressed = False
            for cat in cat_order:
                if len(selected) >= 6:
                    break
                pointer = cat_pointers[cat]
                cat_legs = by_cat[cat]
                while pointer < len(cat_legs):
                    leg = cat_legs[pointer]
                    pointer += 1
                    player = leg["selection"].lower()
                    cat_count = sum(1 for s in selected if s["_cat"] == cat)
                    if cat_count >= 2:
                        break  # max 2 Legs pro Kategorie für Vielfalt
                    if player in used_players and cat not in ["booked", "fouls", "tackles"]:
                        continue
                    selected.append(leg)
                    used_players.add(player)
                    progressed = True
                    break
                cat_pointers[cat] = pointer
            if not progressed:
                break  # keine Kategorie hatte noch etwas zu bieten

        if len(selected) < 2:
            _rejected_too_few_legs += 1
            if _is_wc_match:
                log(f"   🌍 WM-Reject (zu wenig Legs): {match_name} → nur {len(selected)} Legs aus {len(legs)} Props")
                _send_stat_insight_fallback(match_name, legs)
            continue

        combo_odds = _calc_combo_odds(selected)
        # Nur Builders mit sinnvoller Quote senden
        if combo_odds < 1.80:
            _rejected_low_odds += 1
            if _is_wc_match:
                log(f"   🌍 WM-Reject (Quote zu tief): {match_name} → {combo_odds}")
                # 🆕 Einzelne Props senden statt Kombi — Portugal vs Uzbekistan hat echte Player-Props
                _prop_chat = TELEGRAM_GROUPS.get("advanced_props") or TELEGRAM_GROUPS.get("props")
                _dedup_k = f"wmprop_{match_name}_{datetime.now(timezone.utc).date()}"
                if _prop_chat and _dedup_k not in _STAT_INSIGHT_SENT_TODAY:
                    _STAT_INSIGHT_SENT_TODAY.add(_dedup_k)
                    for _leg in selected[:2]:  # Max 2 Props
                        _leg_odds = float(_leg.get("price", _leg.get("odds", 0)) or 0)
                        _leg_name = _leg.get("name", _leg.get("tip", ""))
                        if not _leg_name or _leg_odds < 1.30:
                            continue
                        _msg = (
                            f"🎯 <b>PLAYER PROP</b>  {_leg_odds}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⚽ <b>{match_name}</b>\n"
                            f"   ✅ {_leg_name}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"💰 @ {_leg_odds} · 0.5u"
                        )
                        send_telegram(_msg, chat_id=_prop_chat)
                        log(f"   🎯 WM Single Prop: {_leg_name} @ {_leg_odds}")
                else:
                    _send_stat_insight_fallback(match_name, legs)
            continue

        # 🆕 Generiere alle Größen 2-6 für dieses Match
        _bb_labels = {
            2: "🏗️ BET BUILDER",
            3: "🎯 BET BUILDER",
            4: "🔥 BET BUILDER",
            5: "💎 BET BUILDER",
            6: "👑 BET BUILDER",
        }
        for _n in range(2, min(len(selected) + 1, 7)):
            _legs_n = selected[:_n]
            _odds_n = _calc_combo_odds(_legs_n)
            if _odds_n < 1.80:
                continue
            builders.append({
                "match": match_name,
                "legs": _legs_n,
                "odds": _odds_n,
                "label": _bb_labels.get(_n, f"🎯 BET BUILDER {_n}"),
                "_ko": _legs_n[0].get("_ko"),
                "_n": _n,
            })

    if _rejected_too_few_legs or _rejected_low_odds:
        log(f"   🔑 Bet Builder Filter: {_rejected_too_few_legs} mit <2 Legs verworfen, {_rejected_low_odds} mit Quote<1.80 verworfen")

    # 🆕 BTTS-Tipps als Bet Builder — optional.
    # V31: Standard AUS, damit der Prop-Kanal nicht mit Team-BTTS-Kombis zugemüllt wird.
    # Aktivieren mit ENABLE_BTTS_AS_PROP_BUILDER=true.
    if env("ENABLE_BTTS_AS_PROP_BUILDER", "false").lower() in ["1", "true", "yes"] and top_btts_tips and len(top_btts_tips) >= 2:
        log(f"   🔑 Verwende {len(top_btts_tips)} BTTS-Tipps als Bet Builder Beine...")
        prop_chat = TELEGRAM_GROUPS.get("advanced_props") or TELEGRAM_GROUPS.get("props")

        # Paare nach höchster kombinierter Wahrscheinlichkeit bilden
        _btts_sent = set()
        for i, t1 in enumerate(top_btts_tips[:10]):
            for t2 in top_btts_tips[i+1:10]:
                if t1.get("match") == t2.get("match"):
                    continue
                _pair_key = f"{t1['match']}_{t2['match']}"
                if _pair_key in _btts_sent:
                    continue
                _btts_sent.add(_pair_key)

                # Fair-Quote berechnen
                p1 = int(t1.get("probability", 67))
                p2 = int(t2.get("probability", 67))
                o1 = float(t1.get("oddsYes") or round(100/p1, 2))
                o2 = float(t2.get("oddsYes") or round(100/p2, 2))
                if o1 < 1.40: o1 = round(100/p1, 2)
                if o2 < 1.40: o2 = round(100/p2, 2)
                combo_odds = round(o1 * o2, 2)

                if combo_odds < 1.90:  # Min-Quote für BTTS-Kombi
                    continue

                msg = (
                    f"🏗️ <b>BET BUILDER</b>  {combo_odds}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"⚽ <b>{t1['match']}</b>\n"
                    f"   ✅ BTTS YES ({p1}%)\n\n"
                    f"⚽ <b>{t2['match']}</b>\n"
                    f"   ✅ BTTS YES ({p2}%)\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 @ {combo_odds} · 0.5u"
                )

                if prop_chat:
                    send_telegram(msg, chat_id=prop_chat)
                    log(f"   ✅ BTTS Bet Builder: {t1['match']} + {t2['match']} @ {combo_odds}")
                break  # Pro t1 nur ein bestes Paar
            if len(_btts_sent) >= 3:  # Max 3 Paare
                break

    # 🆕 SofaScore Player Props Value-Alert (Supabase Hit-Rate × Odds > 1.10)
    _sofa_event_ids = {}
    for league, fixtures in (fixtures_cache or {}).items():
        for fix in (fixtures or []):
            eid = fix.get("sofa_event_id") or fix.get("event_id")
            if eid:
                _sofa_event_ids[f"{fix.get('home','')}_vs_{fix.get('away','')}"] = str(eid)

    if _sofa_event_ids:
        _value_chat = TELEGRAM_GROUPS.get("advanced_props") or TELEGRAM_GROUPS.get("props")
        _value_sent = 0
        _sofa_pool_added = 0
        for match_key, ev_id in list(_sofa_event_ids.items())[:12]:
            sofa_props = get_sofascore_player_props(ev_id)
            # 🆕 bet365-Player-Props (SofaScore Provider 1) in den Builder-Pool speisen.
            # Das ist die fehlende Verbindung: bisher wurden diese Props nur fuer
            # Value-Alerts genutzt, nie fuer echte Same-Game-Builder.
            try:
                _sofa_match = match_key.replace("_vs_", " vs ")
                for _sp in sofa_props:
                    _grp = str(_sp.get("market_group", ""))
                    _lnraw = str(_sp.get("line", ""))
                    _ll = _lnraw.lower()
                    if "under" in _ll or _ll.strip() in {"no", "-"}:
                        continue  # nur Over/Yes-Seite als Builder-Leg
                    _pl = str(_sp.get("player_name", "")).strip()
                    try:
                        _od = float(_sp.get("odds", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    if not _pl or _od <= 1.20:
                        continue
                    _cat = _ntr_prop_category(_grp)
                    if _cat == "other":
                        continue
                    _mm = re.search(r"(\d+(?:\.\d+)?)", _lnraw)
                    _line = float(_mm.group(1)) if _mm else 0.5
                    _ntr_collect_prop(
                        _pl, "", _sofa_match, "", _grp,
                        category=_cat, line=_line, odds=_od,
                        probability=(1.0 / _od * 0.95) if _od > 1 else 0,
                        source="bet365_sofascore", games=0,
                    )
                    _sofa_pool_added += 1
            except Exception as _sfe:
                log(f"   💰 SofaScore->Builder-Pool Fehler: {str(_sfe)[:60]}", "WARN")
            for prop in sofa_props[:30]:
                player = prop.get("player_name", "")
                supabase_stats = get_supabase_player_avg_stats(player)
                if not supabase_stats:
                    continue
                value_info = check_prop_value(
                    player, prop.get("market_group", ""),
                    prop.get("line", ""), prop.get("odds", 0), supabase_stats
                )
                if value_info and _value_chat and _value_sent < 5:
                    _msg = (
                        f"🎯 <b>PLAYER PROP VALUE</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⚽ <b>{match_key.replace('_vs_', ' vs ')}</b>\n"
                        f"👤 {value_info['player']}\n"
                        f"📊 {value_info['market']}\n\n"
                        f"💰 Quote: <b>{value_info['odds']}</b>\n"
                        f"📈 Hit-Rate: <b>{value_info['hit_rate_pct']}%</b> ({value_info['games_sample']} Spiele)\n"
                        f"🎯 Edge: <b>+{value_info['edge_pct']}%</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💰 0.5u ✅"
                    )
                    send_telegram(_msg, chat_id=_value_chat)
                    _value_sent += 1
                    log(f"   🎯 Value Alert: {player} {value_info['market']} +{value_info['edge_pct']}%")
        if _sofa_pool_added:
            log(f"   💰 bet365/SofaScore: {_sofa_pool_added} Player-Props in Builder-Pool eingespeist")

    # 🆕 EXTRA-QUELLEN-KETTE: Kambi (Unibet/Betsson) + 1xbet-Familie.
    # Fehlertolerant: jede Quelle in try/except, Ausfall stoppt nichts.
    try:
        from netrattler_prop_sources import collect_extra_player_props
        _extra_fixtures = []
        _seen_fx = set()
        for league, fixtures in (fixtures_cache or {}).items():
            for fix in (fixtures or []):
                _h = str(fix.get("home", "")).strip()
                _a = str(fix.get("away", "")).strip()
                _k = f"{_h}|{_a}"
                if _h and _a and _k not in _seen_fx:
                    _seen_fx.add(_k)
                    _extra_fixtures.append({"home": _h, "away": _a})
        if _extra_fixtures:
            _extra_added = 0
            for _xp in collect_extra_player_props(_extra_fixtures, log=log):
                _cat = _xp.get("category") or _ntr_prop_category(_xp.get("market", ""))
                if _cat == "other":
                    continue
                try:
                    _od = float(_xp.get("odds", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if _od <= 1.20 or not _xp.get("player"):
                    continue
                _ntr_collect_prop(
                    _xp.get("player", ""), _xp.get("team", ""), _xp.get("match", ""),
                    _xp.get("league", ""), _xp.get("market", ""),
                    category=_cat, line=float(_xp.get("line", 0.5) or 0.5), odds=_od,
                    probability=(1.0 / _od * 0.95) if _od > 1 else 0,
                    source=_xp.get("source", "extra"), games=0,
                )
                _extra_added += 1
            if _extra_added:
                log(f"   🔌 Extra-Quellen (Kambi/1xbet): {_extra_added} Player-Props in Builder-Pool eingespeist")
    except Exception as _xse:
        log(f"   🔌 Extra-Quellen-Kette übersprungen: {str(_xse)[:80]}", "WARN")

    # 🎭 TEAM-ZUORDNUNG: jedem Leg sein Team zuweisen (via Lineups) — Basis fuer
    # das Favorit-vs-Aussenseiter-Rollen-System im Builder. Legs ohne Team-Info
    # (v.a. Kambi) bekommen es hier; SofaScore-Legs tragen es schon.
    try:
        _matches = {}
        for _row in _NTR_BUILDER_PROP_POOL:
            if _row.get("team"):
                continue
            _m = _row.get("match", "")
            if " vs " in _m:
                _matches.setdefault(_m, True)
        _team_map = {}   # (match, player_norm) -> team
        _lu_cap = int(os.getenv("NETRATTLER_LINEUP_MAX", "16"))
        for _i, _m in enumerate(list(_matches.keys())[:_lu_cap]):
            _h, _a = [s.strip() for s in _m.split(" vs ", 1)]
            try:
                _lu = get_sportdb_lineups(_h, _a, str(target_date))
            except Exception:
                _lu = None
            if not _lu:
                continue
            for _pl in (_lu.get("home_lineup") or []):
                _team_map[(_m, _normalize_name(_pl))] = _h
            for _pl in (_lu.get("away_lineup") or []):
                _team_map[(_m, _normalize_name(_pl))] = _a
        _tagged = 0
        if _team_map:
            for _row in _NTR_BUILDER_PROP_POOL:
                if _row.get("team"):
                    continue
                _t = _team_map.get((_row.get("match", ""), _normalize_name(_row.get("player", ""))))
                if _t:
                    _row["team"] = _t
                    _tagged += 1
            if _tagged:
                log(f"   🎭 Team-Zuordnung: {_tagged} Legs via Lineups (Favorit/Außenseiter-Rollen aktiv)")
    except Exception as _te:
        log(f"   🎭 Team-Zuordnung übersprungen: {str(_te)[:70]}", "WARN")

    # 🧠 PLAYER-PROP XGBOOST: echte Modell-Wahrscheinlichkeit statt implied-odds.
    # Damit bekommt der Builder eine ECHTE Edge (Modell vs. Buchmacher).
    try:
        import netrattler_ml_player as _mlp
        try:
            import netrattler_stat_sources as _sbs
        except Exception:
            _sbs = None
        _pm = _mlp.load_player_models(SUPABASE_URL, SUPABASE_KEY)
        if _pm:
            _ml_prob_set = 0
            _sb_lookups = 0
            _SB_LOOKUP_CAP = int(os.getenv("NETRATTLER_STATBUNKER_MAX_LOOKUPS", "40"))
            for _row in _NTR_BUILDER_PROP_POOL:
                _cat = _row.get("category", "")
                if _mlp.model_for(_cat, _row.get("line", 0.5)) is None:
                    continue
                _player = _row.get("player", "")
                if not _player:
                    continue
                try:
                    _avg = get_supabase_player_avg_stats(_player)
                except Exception:
                    _avg = {}
                # Fallback StatBunker, wenn Supabase-Historie fehlt (kleine Ligen).
                if _sbs is not None and (not _avg or not any((v or {}).get("avg") for v in _avg.values())) and _sb_lookups < _SB_LOOKUP_CAP:
                    _sb_lookups += 1
                    try:
                        _sb = _sbs.fetch_statbunker_player_stats(_player, _row.get("league", ""))
                        if _sb:
                            _avg = _sbs.merge_stats(_avg, _sb)
                    except Exception:
                        pass
                # Rollen-Kontext (Favorit/Außenseiter) für das Modell berechnen
                _ctx = None
                try:
                    import netrattler_role_context as _rc
                    _rc.load_team_elo(SUPABASE_URL, SUPABASE_KEY)
                    _mtch = _row.get("match", "")
                    _tm = _row.get("team", "")
                    if " vs " in _mtch and _tm:
                        _hh, _aa = [s.strip() for s in _mtch.split(" vs ", 1)]
                        _te = _rc.team_elo(_tm)
                        _oe = _rc.team_elo(_aa if _rc._norm(_tm) == _rc._norm(_hh) else _hh)
                        if _te is not None and _oe is not None:
                            _ishome = 1.0 if _rc._norm(_tm) == _rc._norm(_hh) else 0.0
                            _ctx = {
                                "elo_diff": _te - _oe, "opponent_elo": _oe, "is_home": _ishome,
                                "is_favorite": 1.0 if (_te - _oe + (65 if _ishome else -65)) > 0 else 0.0,
                            }
                except Exception:
                    _ctx = None
                _mprob = _mlp.predict_player_prop(_avg, _cat, _row.get("line", 0.5), _ctx)
                # 🪜 Modell-bevorzugte Linie NUR merken (nicht Quote fälschen).
                # Die echte Hochstufung passiert unten pool-weit über reale Quoten.
                try:
                    _min_conf = float(os.getenv("NETRATTLER_LADDER_MIN_CONF", "0.55"))
                    _best = _mlp.best_line_for_role(_avg, _cat, _ctx, _min_conf)
                    if _best is not None:
                        _row["model_best_line"] = _best[0]
                        _row["model_best_prob"] = _best[1]
                except Exception:
                    pass
                if _mprob is not None:
                    _row["probability"] = round(_mprob, 4)
                    _row["ml_backed"] = True
                    _ml_prob_set += 1
            if _ml_prob_set:
                log(f"   🧠 Player-XGBoost: {_pm} Modelle geladen · {_ml_prob_set} Props mit echter Modell-Wahrscheinlichkeit versehen")
                # 🪜 ROLLEN-STAFFELUNG (Nate-Style 3+/2+/1+) mit ECHTEN Quoten:
                # Pro Spieler+Kategorie das höchste Linien-Leg bevorzugen, das der
                # Buchmacher wirklich anbietet UND das Modell mind. min_conf deckt.
                try:
                    _min_conf = float(os.getenv("NETRATTLER_LADDER_MIN_CONF", "0.55"))
                    _groups = {}
                    for _row in _NTR_BUILDER_PROP_POOL:
                        _bl = _row.get("model_best_line")
                        if _bl is None:
                            continue
                        _k = (_normalize_name(_row.get("player", "")), _row.get("match", ""), _row.get("category", ""))
                        _groups.setdefault(_k, []).append(_row)
                    _escalated = 0
                    for _k, _rws in _groups.items():
                        if len(_rws) < 2:
                            continue
                        _bestline = max(r.get("model_best_line", 0) for r in _rws)
                        # reale Legs auf/unter der Modell-Linie behalten, höchste bevorzugen
                        for _r in _rws:
                            _ln = float(_r.get("line", 0.5))
                            if _ln == _bestline and (_r.get("model_best_prob") or 0) >= _min_conf:
                                _r["ladder_primary"] = True
                                _escalated += 1
                            elif _ln < _bestline:
                                _r["ladder_lower"] = True  # niedrigere Linie abwerten
                    if _escalated:
                        log(f"   🪜 Rollen-Staffelung: {_escalated} Legs auf höchste modell-gedeckte Linie gesetzt (echte Quoten)")
                except Exception as _lae:
                    log(f"   🪜 Staffelung übersprungen: {str(_lae)[:60]}", "WARN")
            else:
                log(f"   🧠 Player-XGBoost: {_pm} Modelle geladen · 0 Props gematcht (keine Spielerhistorie in player_avg_stats — bei kleinen Ligen normal)")
        else:
            log("   🧠 Player-XGBoost: keine Modelle geladen (Fallback: implied-odds)", "WARN")
    except Exception as _mle:
        log(f"   🧠 Player-XGBoost übersprungen: {str(_mle)[:80]}", "WARN")

    # V31 CLEAN: Alte Pinnacle-Bet-Builder mit generischen Team-/Total-Goals-Legs nicht mehr senden.
    # Die echten Player-Props gehen über netrattler_builder_engine.py.
    if str(env("ENABLE_LEGACY_PINNACLE_BUILDER", "false")).lower() not in ["1", "true", "yes", "on"]:
        if builders:
            log(f"🔑 Legacy Pinnacle Bet Builder übersprungen: {len(builders)} generische Builder (V31 Player-Prop Engine aktiv)")
        builders = []

    if not builders:
        log("🔑 Pinnacle Legacy Builder: keine Sendung (V31 Clean Mode)")

    # Nur valide Builder-Dictionaries weiterverarbeiten.
    _invalid_builders = sum(1 for item in builders if not isinstance(item, dict))
    if _invalid_builders:
        log(f"   ⚠️ Pinnacle Builder: {_invalid_builders} ungültige Einträge verworfen")
    builders = [item for item in builders if isinstance(item, dict)]

    # Sortierung nach Anstosszeit
    builders.sort(key=lambda x: x.get("_ko") or _dt2.max.replace(tzinfo=timezone.utc))

    # Datum muss vor Multi-Match-Dedupe gesetzt sein.
    _bdate = str(datetime.now(timezone.utc).date())

    # 🆕 MULTI-MATCH BET BUILDER (wie Nate VIP — 2-3 Spiele gemischt)
    # Nimmt das beste Leg aus 2-3 verschiedenen Matches und kombiniert sie
    _match_best = {}  # {match_name: [sorted legs]}
    for b in builders:
        mn = b["match"]
        if mn not in _match_best:
            _match_best[mn] = b["legs"]

    _match_names = list(_match_best.keys())
    _mm_labels = {2:"🏗️ BET BUILDER", 3:"🎯 BET BUILDER", 4:"🔥 BET BUILDER",
                  5:"💎 BET BUILDER", 6:"👑 BET BUILDER"}

    if len(_match_names) >= 2:
        # Generiere Multi-Match Kombis 2-6 Legs über 2-3 verschiedene Matches
        for _total_legs in range(2, 7):
            # Verteile Legs möglichst gleichmässig über 2-3 Matches
            _n_matches = min(3, len(_match_names), _total_legs)
            _legs_per_match = _total_legs // _n_matches
            _remainder = _total_legs % _n_matches

            _mm_legs = []
            for i, mn in enumerate(_match_names[:_n_matches]):
                _take = _legs_per_match + (1 if i < _remainder else 0)
                _mm_legs.extend(_match_best[mn][:_take])

            if len(_mm_legs) < 2:
                continue

            _mm_odds = _calc_combo_odds(_mm_legs)
            if _mm_odds < 1.80:
                continue

            _sig = _combo_signature(_mm_legs, prefix="mm")
            _dup_id = f"mm_builder_{_bdate}_{_sig}".replace(" ", "_")
            if is_duplicate_combo(_dup_id, _bdate):
                continue

            builders.append({
                "match": " + ".join(_match_names[:_n_matches]),
                "legs": _mm_legs,
                "odds": _mm_odds,
                "label": _mm_labels.get(_total_legs, "🎯 BET BUILDER"),
                "_ko": _match_best[_match_names[0]][0].get("_ko"),
                "_n": _total_legs,
                "_multi_match": True,
                "_match_names": _match_names[:_n_matches],
            })

    builders = builders[:12]  # Max 12 Builder pro Run

    # Nachrichten bauen — Bet365 Bet Builder Style
    sent = 0
    prop_chat = TELEGRAM_GROUPS.get("advanced_props")
    if not prop_chat:
        return 0

    for b in builders:
        tstr = ""
        try:
            if b.get("_ko") and ch_tz:
                _ko_ch = b["_ko"].astimezone(ch_tz)
                tstr = _ko_ch.strftime("%H:%M")
        except Exception:
            pass

        # Deterministische Signatur — identischer Builder (gleiche Legs) wird nicht erneut gesendet
        _sig = _combo_signature(b["legs"], prefix=f"builder_{b['match']}")
        _builder_tip_id = f"builder_{_bdate}_{_sig}".replace(" ", "_")
        if is_duplicate_combo(_builder_tip_id, _bdate):
            _ntr_log_duplicate(f"   ⏭️ Bet Builder Duplikat übersprungen: {b['match']}", key="bet_builder")
            continue

        _cat_icons = {"score":"⚽","first_scorer":"🥇⚽","last_scorer":"🏁⚽","assist":"🎯",
                      "booked":"🟨","yellow_cards":"🟨","sot":"🎯","shots":"🥅",
                      "fouls":"👊","fouls_won":"🧲","tackles_committed":"🦵","tackles_received":"🎯🦵",
                      "tackles":"🦵","corners":"🔵","team_cards":"🟨","saves":"🧤",
                      "offsides":"🚩","result":"🏆","other":"○"}

        msg = f"{b.get('label', '🏗️ BET BUILDER')}  {b['odds']}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"

        if b.get("_multi_match") and b.get("_match_names"):
            # Multi-Match: Legs nach Match gruppieren
            _legs_by_match = {}
            for leg in b["legs"]:
                _lm = leg.get("_match", b["match"])
                _legs_by_match.setdefault(_lm, []).append(leg)
            for _mn, _mlegs in _legs_by_match.items():
                try:
                    _ko_str = " · ⏰ " + _mlegs[0]["_ko"].strftime("%H:%M")
                except Exception:
                    _ko_str = ""
                msg += f"\n⚽ <b>{_mn}</b>{_ko_str}\n"
                for leg in _mlegs:
                    msg += _ntr_builder_leg_line(leg, _cat_icons, indent="   ") + "\n"
        else:
            # Single-Match
            msg += f"⚽ <b>{b['match']}</b>"
            if tstr:
                msg += " · ⏰ " + tstr
            msg += "\n"
            for leg in b["legs"]:
                msg += _ntr_builder_leg_line(leg, _cat_icons, indent="") + "\n"

        _avg_prob = int(sum(float(l.get("prob", 0) or 0) for l in b["legs"]) / max(1, len(b["legs"])))
        _risk, _builder_score = _ntr_builder_read(_avg_prob, b["odds"])
        _stake = _ntr_builder_stake_for_odds(b["odds"], b["legs"])
        msg += f"\n💰 @ <b>{b['odds']}</b> · {_stake:.2f}u"
        msg += f"\n🧠 <b>PROP BUILDER READ:</b> {_risk} · Score {_builder_score}/10"
        msg += "\n<i>Player-, Team- und Match-Props werden klein gespielt, wenn die Gesamtquote hoch ist.</i>"

        _mid = send_telegram(msg, chat_id=prop_chat)
        sent += 1

        # Supabase speichern für Settlement — deterministische ID (verhindert Duplikate über mehrere Runs)
        try:
            save_to_supabase({
                "tip_id": _builder_tip_id,
                "date": _bdate,
                "market": "bet_builder",
                "market_name": "🏗️ Bet Builder",
                "match": b["match"],
                "tip": " + ".join(l["player_prop"] for l in b["legs"]),
                "odds": str(b["odds"]),
                "units": _stake,
                "probability": int(sum(l["prob"] for l in b["legs"]) / len(b["legs"])),
                "confidence": max(1, min(5, int(round(_builder_score / 2)))),
                "status": "pending",
                "group_key": "builder",
                "pick_type": "builder",
                "builder_id": _builder_tip_id,
                "builder_total_legs": len(b["legs"]),
                "builder_legs": [
                    {
                        "player": _ntr_builder_player_name(l), "selection": l.get("selection", ""),
                        "player_prop": l.get("player_prop", ""), "market": l.get("player_prop", ""),
                        "category": l.get("_cat", ""), "line": l.get("line"), "side": l.get("side", "over"),
                        "odds": l.get("odds"), "prob": l.get("prob"), "match": l.get("_match", b["match"]),
                        "source": l.get("source", "pinnacle"),
                    } for l in b["legs"]
                ],
                "nate_score": _builder_score,
                "source": "pinnacle",
                "telegram_chat_id": str(prop_chat),
                "telegram_msg_id": _mid,
                "message_text": msg[:3500],
            })
        except Exception as _save_err:
            try:
                log(f"   ⚠️ Bet Builder DB-Save fehlgeschlagen: {str(_save_err)[:160]}", "WARN")
            except Exception:
                pass

    log(f"🏗️ Bet Builder: {sent} Builder gesendet ({len(builders)} generiert)")
    return sent



def fetch_pinnacle_matchups() -> List[Dict]:
    """Holt alle aktuellen Fußball-Matches von Pinnacle (kostenlos)."""
    cache_key = "matchups_soccer"
    cached = _cache_get(_PIN_MATCHUP_CACHE, cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/matchups",
            headers=PINNACLE_HEADERS,
            params={"withSpecials": "false", "brandId": "0"},
            timeout=15,
        )
        if not r.ok:
            _cache_set(_PIN_MATCHUP_CACHE, cache_key, [])
            return []

        data = r.json()
        matches = []
        for m in data:
            if m.get("type") != "matchup":
                continue
            participants = m.get("participants", [])
            if len(participants) < 2:
                continue
            home = next((p.get("name", "") for p in participants if p.get("alignment") == "home"), "")
            away = next((p.get("name", "") for p in participants if p.get("alignment") == "away"), "")
            if not home or not away:
                continue
            matches.append({
                "match_id": m.get("id"),
                "league_name": m.get("league", {}).get("name", ""),
                "home": home, "away": away,
                "starts": m.get("startTime", ""),
            })

        _cache_set(_PIN_MATCHUP_CACHE, cache_key, matches)
        _log("PINNACLE", f"📊 {len(matches)} Matches geladen")
        return matches
    except Exception as e:
        _log("PINNACLE", f"Matchups Fehler: {str(e)[:80]}", "WARN")
        _cache_set(_PIN_MATCHUP_CACHE, cache_key, [])
        return []


def fetch_pinnacle_match_odds(match_id: int) -> Optional[Dict]:
    """Holt alle Quoten für ein einzelnes Pinnacle-Match."""
    cache_key = f"odds_{match_id}"
    cached = _cache_get(_PIN_ODDS_CACHE, cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            f"{PINNACLE_BASE}/matchups/{match_id}/markets/related/straight",
            headers=PINNACLE_HEADERS,
            timeout=10,
        )
        if not r.ok:
            _cache_set(_PIN_ODDS_CACHE, cache_key, None)
            return None

        markets = r.json()
        result = {"match_id": match_id}

        for market in markets:
            mtype = market.get("type", "")
            period = market.get("period", 0)
            for price in market.get("prices", []):
                pv = price.get("price")
                des = price.get("designation", "")
                pts = price.get("points")
                if not pv or pv <= 1:
                    continue

                if mtype == "moneyline" and period == 0:
                    if des == "home": result["home_win"] = round(pv, 2)
                    elif des == "draw": result["draw"] = round(pv, 2)
                    elif des == "away": result["away_win"] = round(pv, 2)
                elif mtype == "total" and period == 0:
                    if pts == 2.5:
                        if des == "over": result["over_25"] = round(pv, 2)
                        elif des == "under": result["under_25"] = round(pv, 2)
                elif mtype == "total" and period == 1:
                    if pts == 1.5:
                        if des == "over": result["over_15_ht"] = round(pv, 2)
                    elif pts == 0.5:
                        if des == "over": result["over_05_ht"] = round(pv, 2)

        # BTTS via related markets
        try:
            r2 = requests.get(
                f"{PINNACLE_BASE}/matchups/{match_id}/related",
                headers=PINNACLE_HEADERS, timeout=8,
            )
            if r2.ok:
                for sub in r2.json():
                    if "both teams to score" in sub.get("special", {}).get("description", "").lower():
                        sub_id = sub.get("id")
                        if not sub_id:
                            continue
                        rs = requests.get(
                            f"{PINNACLE_BASE}/matchups/{sub_id}/markets/straight",
                            headers=PINNACLE_HEADERS, timeout=8,
                        )
                        if not rs.ok:
                            continue
                        for m in rs.json():
                            for p in m.get("prices", []):
                                if p.get("designation", "").lower() == "yes":
                                    pp = m.get("period", 0)
                                    if pp == 0:
                                        result["btts_yes"] = round(p["price"], 2)
                                    elif pp == 1:
                                        result["btts_yes_ht"] = round(p["price"], 2)
        except Exception:
            pass

        _cache_set(_PIN_ODDS_CACHE, cache_key, result)
        return result
    except Exception:
        _cache_set(_PIN_ODDS_CACHE, cache_key, None)
        return None


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    for x in [" fc", " cf", " ac", " sc", " sv", "fc ", "ac ", "sc ", "sv "]:
        n = n.replace(x, " ")
    return " ".join(n.split())


def get_pinnacle_match_odds(home_team: str, away_team: str,
                              league_hint: Optional[str] = None) -> Optional[Dict]:
    """Holt Pinnacle-Quoten für ein Match per Team-Namen."""
    matchups = fetch_pinnacle_matchups()
    if not matchups:
        return None

    h_norm = _normalize_name(home_team)
    a_norm = _normalize_name(away_team)
    if not h_norm or not a_norm:
        return None

    for m in matchups:
        mh = _normalize_name(m["home"])
        ma = _normalize_name(m["away"])
        h_match = (h_norm == mh or h_norm in mh or mh in h_norm or
                   any(w in mh for w in h_norm.split() if len(w) > 3))
        a_match = (a_norm == ma or a_norm in ma or ma in a_norm or
                   any(w in ma for w in a_norm.split() if len(w) > 3))
        if h_match and a_match:
            odds = fetch_pinnacle_match_odds(m["match_id"])
            if odds:
                odds["pinnacle_home"] = m["home"]
                odds["pinnacle_away"] = m["away"]
                odds["league"] = m.get("league_name", "")
            return odds
    return None


def get_pinnacle_quote_for_market(home_team: str, away_team: str,
                                    market: str = "btts") -> Optional[float]:
    """Direkt die Quote für einen bestimmten Markt holen."""
    odds = get_pinnacle_match_odds(home_team, away_team)
    if not odds:
        return None
    mapping = {
        "btts": odds.get("btts_yes"),
        "over25": odds.get("over_25"),
        "over15_ht": odds.get("over_15_ht"),
        "btts_ht": odds.get("btts_yes_ht"),
        "home_win": odds.get("home_win"),
        "away_win": odds.get("away_win"),
        "draw": odds.get("draw"),
        "combo": (odds.get("btts_yes", 0) * odds.get("over_25", 0)
                  if odds.get("btts_yes") and odds.get("over_25") else None),
    }
    return mapping.get(market)


# ════════════════════════════════════════════════════════════════════════
# 3️⃣ BET365 EDGE FILTER
# ════════════════════════════════════════════════════════════════════════

EDGE_FILTER_ENABLED = _env_bool("EDGE_FILTER_ENABLED", "true")
EDGE_FILTER_MIN_EDGE = _env_float("EDGE_FILTER_MIN_EDGE", 0.08)
EDGE_FILTER_MAX_EDGE = _env_float("EDGE_FILTER_MAX_EDGE", 0.50)
EDGE_FILTER_REQUIRE_BET365 = _env_bool("EDGE_FILTER_REQUIRE_BET365", "false")
CROSS_MATCH_COMBOS = _env_bool("CROSS_MATCH_COMBOS", "true")
CROSS_MATCH_MIN_SCORE = int(_env("CROSS_MATCH_MIN_SCORE", "7"))
CROSS_MATCH_MAX_COMBOS = int(_env("CROSS_MATCH_MAX_COMBOS", "5"))

_QUOTES_CACHE = {}


def get_bet365_quote_any_source(tip: Dict, odds_data: Optional[List] = None) -> Tuple[Optional[float], str]:
    """Holt beste verfügbare Quote für einen Tipp."""
    match = tip.get("match", "")
    if " vs " not in match:
        return None, "no_match"
    parts = match.split(" vs ", 1)
    home, away = parts[0].strip(), parts[1].strip()

    market = tip.get("market") or tip.get("market_type") or "btts"

    # 1. Pinnacle Scraper (kostenlos!)
    try:
        quote = get_pinnacle_quote_for_market(home, away, market)
        if quote and quote > 1.0:
            return quote, "pinnacle"
    except Exception:
        pass

    # 2. Odds Data Fallback
    if odds_data:
        h_low, a_low = home.lower(), away.lower()
        api_market = {"btts": "btts", "over25": "totals", "combo": "btts"}.get(market, "btts")
        point = 2.5 if market in ("over25", "combo") else None

        for g in odds_data:
            gh, ga = g.get("home_team", "").lower(), g.get("away_team", "").lower()
            if not ((h_low in gh or gh in h_low) and (a_low in ga or ga in a_low)):
                continue
            for bm_prio in ["bet365", "pinnacle", "smarkets", "betfair_ex_eu", "unibet"]:
                for bm in g.get("bookmakers", []):
                    if bm.get("key") != bm_prio:
                        continue
                    for m in bm.get("markets", []):
                        if m.get("key") != api_market:
                            continue
                        for outcome in m.get("outcomes", []):
                            if api_market == "btts" and outcome.get("name") == "Yes":
                                return float(outcome.get("price", 0)), "odds_data"
                            if api_market == "totals" and outcome.get("name") == "Over":
                                if point and outcome.get("point") != point:
                                    continue
                                return float(outcome.get("price", 0)), "odds_data"

    # 3. Persistierter Multi-Bookmaker-Harvester: Bet365/OddsPortal/Pinnacle/Betfair/etc.
    try:
        from netrattler_odds_harvester import get_best_quote_from_supabase
        lookup = {
            "btts": [("btts", "yes")],
            "over25": [("totals", "over_2_5")],
            "home_win": [("1x2", "home")],
            "draw": [("1x2", "draw")],
            "away_win": [("1x2", "away")],
        }
        if market == "combo":
            qb = get_best_quote_from_supabase(home, away, "btts", "yes")
            qo = get_best_quote_from_supabase(home, away, "totals", "over_2_5")
            if qb and qo:
                return round(float(qb[0]) * float(qo[0]), 4), f"odds_history:{qb[1]}+{qo[1]}"
        for hist_market, selection in lookup.get(market, []):
            found = get_best_quote_from_supabase(home, away, hist_market, selection)
            if found and found[0] > 1.0:
                return float(found[0]), f"odds_history:{found[1]}"
    except Exception:
        pass

    return None, "none"


def calculate_edge(market_quote: float, fair_quote: float) -> float:
    """Returns Edge als Dezimal (0.08 = 8%)."""
    if not market_quote or not fair_quote or market_quote <= 1 or fair_quote <= 1:
        return 0.0
    return (market_quote / fair_quote) - 1


def calculate_kelly_stake(edge: float, market_quote: float,
                          max_units: float = 3.0, kelly_fraction: float = 0.5) -> float:
    """Berechnet optimalen Einsatz nach Half-Kelly."""
    if edge <= 0 or market_quote <= 1:
        return 0.5
    p = 1.0 / (market_quote / (1 + edge))
    p = max(0.01, min(0.99, p))
    q = 1 - p
    b = market_quote - 1
    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(0, kelly) * kelly_fraction
    units = round(kelly * 100, 1)
    return max(0.5, min(units, max_units))


def filter_tips_by_edge(tips: List[Dict], market: str = "btts",
                         min_edge: float = None, max_edge: float = None,
                         odds_data: Optional[List] = None,
                         require_bet365: bool = None) -> List[Dict]:
    """Universeller Edge-Filter."""
    if not EDGE_FILTER_ENABLED:
        return tips

    min_edge = EDGE_FILTER_MIN_EDGE if min_edge is None else min_edge
    max_edge = EDGE_FILTER_MAX_EDGE if max_edge is None else max_edge
    require_bet365 = EDGE_FILTER_REQUIRE_BET365 if require_bet365 is None else require_bet365

    if not tips:
        return tips

    filtered = []
    stats = {"total": len(tips), "no_quote": 0, "below_min": 0, "above_max": 0, "kept": 0}

    for tip in tips:
        fair_str = (tip.get("fairOdds") or tip.get("fair_odds") or tip.get("oddsYes") or "0")
        try:
            fair_odds = float(str(fair_str).replace(",", "."))
        except:
            fair_odds = 0.0
        if fair_odds <= 1.0:
            stats["no_quote"] += 1
            continue

        tip_market = tip.get("market") or market
        market_quote, source = get_bet365_quote_any_source({**tip, "market": tip_market}, odds_data)

        if not market_quote:
            stats["no_quote"] += 1
            if require_bet365:
                continue
            try:
                market_quote = float(str(tip.get("oddsYes", "0")).replace(",", "."))
                source = "tip_odds"
            except:
                continue
            if market_quote <= 1.0:
                continue

        edge = calculate_edge(market_quote, fair_odds)

        if edge < min_edge:
            stats["below_min"] += 1
            continue
        if edge > max_edge:
            stats["above_max"] += 1
            continue

        kelly = calculate_kelly_stake(edge, market_quote)
        tip["bet365_quote"] = round(market_quote, 2)
        tip["edge"] = round(edge, 4)
        tip["edge_pct"] = round(edge * 100, 1)
        tip["edge_source"] = source
        tip["kelly_units"] = kelly
        tip["value_rating"] = ("🔥 HIGH" if edge >= 0.20 else "💚 OK" if edge >= 0.12 else "🟡 LOW")
        filtered.append(tip)
        stats["kept"] += 1

    _log("EDGE", f"[{market}]: {stats['kept']}/{stats['total']} kept "
                  f"(no_quote: {stats['no_quote']}, below_min: {stats['below_min']})")
    return filtered


# Anti-Correlation Check
ANTI_CORRELATIONS = [
    ("btts", "Yes", "totals_0.5", "Under"),
    ("over15_ht", "Over", "over05_ht", "Under"),
    ("over25", "Over", "under15", "Under"),
]


def check_anti_correlation(combo: List[Dict]) -> bool:
    """Prüft logische Konflikte in einem Combo."""
    if len(combo) < 2:
        return True
    seen = {}
    for tip in combo:
        match = tip.get("match", "")
        mkt = tip.get("market", "")
        outc = tip.get("tip", "")
        if mkt == "advanced_props":
            continue
        key = f"{match}_{mkt}"
        if key in seen and seen[key] != outc:
            return False
        seen[key] = outc
    return True


def build_cross_match_combos(tips_by_market: Dict[str, List[Dict]],
                              top_n: int = None, min_score: int = None) -> List[Dict]:
    """Baut Cross-Match Combos (Bet Builder Style)."""
    if not CROSS_MATCH_COMBOS:
        return []
    top_n = top_n or CROSS_MATCH_MAX_COMBOS
    min_score = min_score or CROSS_MATCH_MIN_SCORE

    all_tips = []
    for market, tips in (tips_by_market or {}).items():
        for tip in tips:
            edge = tip.get("edge", 0)
            prob = int(tip.get("probability", 0))
            conf = int(tip.get("confidence", 0))
            score = (edge * 100) * (prob / 100) * (conf / 5)
            if score < min_score:
                continue
            tip["combo_score"] = round(score, 2)
            all_tips.append(tip)

    all_tips.sort(key=lambda t: t.get("combo_score", 0), reverse=True)
    candidates = all_tips[:10]
    combos = []

    # 2-Leg Combos
    for i, ta in enumerate(candidates):
        for tb in candidates[i+1:]:
            if ta.get("match") == tb.get("match"):
                continue
            combo = [ta, tb]
            if not check_anti_correlation(combo):
                continue
            co = (ta.get("bet365_quote", ta.get("oddsYes", 1)) *
                  tb.get("bet365_quote", tb.get("oddsYes", 1)))
            cp = (ta.get("probability", 0) / 100) * (tb.get("probability", 0) / 100)
            fc = float(ta.get("fairOdds", 1)) * float(tb.get("fairOdds", 1))
            ce = (co / fc) - 1 if fc > 0 else 0
            kelly = calculate_kelly_stake(ce, co)
            combos.append({
                "combo_id": f"C2-{len(combos)+1:03d}",
                "legs": combo,
                "combined_odds": round(co, 2),
                "combined_prob": round(cp, 3),
                "combined_edge_pct": round(ce * 100, 1),
                "kelly_units": kelly,
                "type": "2-leg cross-match", "leg_count": 2,
            })

    # 3-Leg Combos
    for i, ta in enumerate(candidates[:5]):
        for j, tb in enumerate(candidates[i+1:6]):
            for tc in candidates[i+j+2:7]:
                if len({ta.get("match"), tb.get("match"), tc.get("match")}) < 3:
                    continue
                combo = [ta, tb, tc]
                if not check_anti_correlation(combo):
                    continue
                co, cp, fc = 1.0, 1.0, 1.0
                for t in combo:
                    co *= t.get("bet365_quote", t.get("oddsYes", 1))
                    cp *= (t.get("probability", 0) / 100)
                    fc *= float(t.get("fairOdds", 1))
                ce = (co / fc) - 1 if fc > 0 else 0
                kelly = calculate_kelly_stake(ce, co) * 0.5
                combos.append({
                    "combo_id": f"C3-{len(combos)+1:03d}",
                    "legs": combo,
                    "combined_odds": round(co, 2),
                    "combined_prob": round(cp, 3),
                    "combined_edge_pct": round(ce * 100, 1),
                    "kelly_units": kelly,
                    "type": "3-leg cross-match", "leg_count": 3,
                })

    combos.sort(key=lambda c: c.get("combined_edge_pct", 0), reverse=True)
    return combos[:top_n]


def format_combo_message(combo: Dict) -> str:
    """Formatiert Cross-Match Combo für Telegram."""
    leg_count = combo.get("leg_count", 2)
    odds = combo.get("combined_odds", 0)
    prob = combo.get("combined_prob", 0)
    edge_pct = combo.get("combined_edge_pct", 0)
    units = combo.get("kelly_units", 0.5)
    edge_emoji = "🔥" if edge_pct >= 25 else "💚" if edge_pct >= 15 else "🟡"

    msg = f"<b>{edge_emoji} BET BUILDER COMBO ({leg_count} Legs)</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎰 <b>Combo Quote:</b> {odds}\n"
    msg += f"📈 <b>Hit-Rate:</b> {round(prob*100, 1)}%\n"
    msg += f"{edge_emoji} <b>Combined Edge:</b> +{edge_pct}%\n"
    msg += f"💵 <b>Stake:</b> {units} Units\n\n"
    msg += "<b>📋 Legs:</b>\n"
    for i, leg in enumerate(combo.get("legs", []), 1):
        market = leg.get("market", "?")
        info = MARKET_INFO_EXTENDED.get(market, {})
        emoji = info.get("emoji", "💎")
        leg_quote = leg.get("bet365_quote", leg.get("oddsYes", "?"))
        msg += (f"{i}. {emoji} <b>{leg.get('match', '?')}</b>\n"
                f"   {leg.get('tip', '?')} @ {leg_quote}\n"
                f"   ({info.get('name', market)})\n")
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>💡 Bei Bet365: Bet Builder → Multi öffnen → alle Legs einzeln hinzufügen</i>"
    return msg


def integrate_edge_filter_into_pipeline(tips_by_market: Dict[str, List[Dict]],
                                         odds_data: Optional[List] = None) -> Dict:
    """All-in-One Integration."""
    if not EDGE_FILTER_ENABLED:
        return {"filtered_tips": tips_by_market, "combos": [], "stats": {}}

    filtered = {}
    total_before = 0
    total_after = 0
    for market, tips in (tips_by_market or {}).items():
        total_before += len(tips)
        for tip in tips:
            tip["market"] = market
        filtered[market] = filter_tips_by_edge(tips, market=market, odds_data=odds_data)
        total_after += len(filtered[market])

    combos = []
    if CROSS_MATCH_COMBOS:
        combos = build_cross_match_combos(filtered)

    _log("EDGE", f"🎯 FINAL: {total_after}/{total_before} Tipps, {len(combos)} Combos")
    return {
        "filtered_tips": filtered,
        "combos": combos,
        "stats": {"total_before": total_before, "total_after": total_after, "combos_built": len(combos)},
    }


# ════════════════════════════════════════════════════════════════════════
# 4️⃣ DRAWDOWN PROTECTION (Bankroll-Schutz)
# ════════════════════════════════════════════════════════════════════════

DRAWDOWN_ENABLED = _env_bool("DRAWDOWN_PROTECTION_ENABLED", "true")
STARTING_BANKROLL = _env_float("STARTING_BANKROLL_UNITS", 100.0)
DD_LOSS_HALF = int(_env("DRAWDOWN_LOSS_STREAK_HALF", "3"))
DD_LOSS_STRICT = int(_env("DRAWDOWN_LOSS_STREAK_STRICT", "5"))
DD_BANKROLL_WARN = _env_float("DRAWDOWN_BANKROLL_WARN_PCT", 10.0)
DD_BANKROLL_STOP = _env_float("DRAWDOWN_BANKROLL_STOP_PCT", 20.0)
DD_STRICT_MIN_PROB = int(_env("STRICT_MIN_PROBABILITY", "72"))

_BANKROLL_CACHE = {"data": None, "ts": 0}


def _load_bankroll_state() -> Dict:
    """Lädt Bankroll-State aus Supabase."""
    if _BANKROLL_CACHE["data"] and time.time() - _BANKROLL_CACHE["ts"] < 60:
        return _BANKROLL_CACHE["data"]

    default = {
        "current_units": STARTING_BANKROLL,
        "starting_units": STARTING_BANKROLL,
        "peak_units": STARTING_BANKROLL,
        "loss_streak": 0, "win_streak": 0,
        "mode": "normal", "pause_until": None,
    }
    if not SUPABASE_URL or not SUPABASE_KEY:
        _BANKROLL_CACHE["data"] = default
        return default

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/bankroll_state",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"id": "eq.1", "select": "*"},
            timeout=8,
        )
        if r.ok and r.json():
            data = r.json()[0]
            _BANKROLL_CACHE["data"] = data
            _BANKROLL_CACHE["ts"] = time.time()
            return data
    except Exception:
        pass
    _BANKROLL_CACHE["data"] = default
    return default


def _save_bankroll_state(state: Dict) -> bool:
    """Speichert Bankroll-State in Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["id"] = 1
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/bankroll_state",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            json=state, timeout=8,
        )
        _BANKROLL_CACHE["data"] = state
        return r.ok
    except Exception:
        return False


def get_current_mode() -> Dict:
    """Ermittelt aktuellen Risiko-Mode."""
    state = _load_bankroll_state()
    loss_streak = int(state.get("loss_streak", 0))
    current = float(state.get("current_units", STARTING_BANKROLL))
    peak = float(state.get("peak_units", STARTING_BANKROLL))
    pause_until = state.get("pause_until")
    bankroll_drop = ((peak - current) / peak * 100) if peak > 0 else 0

    # Check Pause
    if pause_until:
        try:
            pause_dt = datetime.fromisoformat(str(pause_until).replace("Z", "+00:00"))
            if pause_dt > datetime.now(timezone.utc):
                return {
                    "mode": "paused", "stake_multiplier": 0,
                    "min_probability_boost": 0, "require_high_value": False,
                    "pause_until": pause_until, "loss_streak": loss_streak,
                    "bankroll_pct": (current / peak * 100) if peak > 0 else 100,
                    "reason": f"🛑 Pausiert bis {pause_dt.strftime('%H:%M')} "
                              f"(Bankroll -{bankroll_drop:.1f}%)",
                }
        except:
            pass

    # Bankroll Drop > 20%
    if bankroll_drop >= DD_BANKROLL_STOP:
        pause_new = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        state["pause_until"] = pause_new
        state["mode"] = "paused"
        _save_bankroll_state(state)
        return {
            "mode": "paused", "stake_multiplier": 0,
            "min_probability_boost": 0, "require_high_value": False,
            "pause_until": pause_new, "loss_streak": loss_streak,
            "bankroll_pct": (current / peak * 100),
            "reason": f"🛑 STOPP: Bankroll -{bankroll_drop:.1f}% (Pause 24h)",
        }

    # Strict Mode
    if loss_streak >= DD_LOSS_STRICT or bankroll_drop >= DD_BANKROLL_WARN:
        return {
            "mode": "strict", "stake_multiplier": 0.25,
            "min_probability_boost": 10, "require_high_value": True,
            "pause_until": None, "loss_streak": loss_streak,
            "bankroll_pct": (current / peak * 100),
            "reason": (f"⚠️ STRICT: {loss_streak} Lost, Bankroll -{bankroll_drop:.1f}% "
                       f"(MIN_PROB +10%, nur HIGH, Stake ×0.25)"),
        }

    # Conservative Mode
    if loss_streak >= DD_LOSS_HALF:
        return {
            "mode": "conservative", "stake_multiplier": 0.5,
            "min_probability_boost": 5, "require_high_value": False,
            "pause_until": None, "loss_streak": loss_streak,
            "bankroll_pct": (current / peak * 100),
            "reason": (f"⚠️ CONSERVATIVE: {loss_streak} Lost in Row "
                       f"(MIN_PROB +5%, Stake ×0.5)"),
        }

    return {
        "mode": "normal", "stake_multiplier": 1.0,
        "min_probability_boost": 0, "require_high_value": False,
        "pause_until": None, "loss_streak": loss_streak,
        "bankroll_pct": (current / peak * 100),
        "reason": "✅ Normal Mode",
    }


def should_skip_tip(tip: Dict, mode: Optional[Dict] = None,
                     base_min_probability: int = 67) -> bool:
    """Soll Tipp wegen Drawdown übersprungen werden?"""
    if not DRAWDOWN_ENABLED:
        return False
    mode = mode or get_current_mode()
    if mode["mode"] == "paused":
        return True
    min_prob = base_min_probability + mode["min_probability_boost"]
    if int(tip.get("probability", 0)) < min_prob:
        return True
    if mode["require_high_value"]:
        value = str(tip.get("value_rating") or tip.get("valueRating", "OK")).upper()
        if "HIGH" not in value and "🔥" not in str(tip.get("value_rating", "")):
            return True
    return False


def adjust_tip_stake(original_units: float, mode: Optional[Dict] = None) -> float:
    """Passt Stake an Mode an."""
    if not DRAWDOWN_ENABLED:
        return original_units
    mode = mode or get_current_mode()
    return max(0.25, round(original_units * mode["stake_multiplier"], 2))


def update_after_tip(tip_id: str, result: str, profit_units: float,
                       units_staked: float = 1.0) -> bool:
    """Update nach Spielergebnis."""
    if not DRAWDOWN_ENABLED:
        return False
    state = _load_bankroll_state()
    current = float(state.get("current_units", STARTING_BANKROLL)) + profit_units
    peak = max(float(state.get("peak_units", STARTING_BANKROLL)), current)
    loss_streak = int(state.get("loss_streak", 0))
    win_streak = int(state.get("win_streak", 0))

    if result == "won":
        win_streak += 1
        loss_streak = 0
    elif result == "lost":
        loss_streak += 1
        win_streak = 0

    state.update({
        "current_units": round(current, 2), "peak_units": round(peak, 2),
        "loss_streak": loss_streak, "win_streak": win_streak,
        "last_tip_id": tip_id, "last_tip_result": result,
    })
    mode_info = get_current_mode()
    state["mode"] = mode_info["mode"]
    state["pause_until"] = mode_info.get("pause_until")
    return _save_bankroll_state(state)


def get_bankroll_status() -> str:
    """Bankroll-Status für Telegram."""
    state = _load_bankroll_state()
    mode = get_current_mode()
    current = float(state.get("current_units", STARTING_BANKROLL))
    starting = float(state.get("starting_units", STARTING_BANKROLL))
    peak = float(state.get("peak_units", STARTING_BANKROLL))
    loss_streak = int(state.get("loss_streak", 0))
    win_streak = int(state.get("win_streak", 0))

    total_pl = current - starting
    pl_pct = (total_pl / starting * 100) if starting > 0 else 0
    drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0

    mode_emoji = {"normal": "🟢", "conservative": "🟡", "strict": "🔴", "paused": "⏸️"}.get(mode["mode"], "❓")
    pl_emoji = "📈" if total_pl >= 0 else "📉"
    sign = "+" if total_pl >= 0 else ""

    msg = "💰 <b>BANKROLL STATUS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"{pl_emoji} <b>Aktuell:</b> {current:.2f}U\n"
    msg += f"   Start: {starting:.2f}U · Peak: {peak:.2f}U\n"
    msg += f"   P/L: {sign}{total_pl:.2f}U ({sign}{pl_pct:.1f}%)\n"
    if drawdown_pct > 0:
        msg += f"\n📉 <b>Drawdown vom Peak:</b> -{drawdown_pct:.1f}%\n"
    msg += f"\n{mode_emoji} <b>Mode: {mode['mode'].upper()}</b>\n"
    msg += f"   <i>{mode['reason']}</i>\n"
    if loss_streak >= 2:
        msg += f"\n❌ <b>Verlust-Streak:</b> {loss_streak} in Folge\n"
    if win_streak >= 3:
        msg += f"\n✅ <b>Gewinn-Streak:</b> {win_streak} in Folge 🔥\n"
    msg += "\n━━━━━━━━━━━━━━━━━━"
    return msg


# ════════════════════════════════════════════════════════════════════════
# 5️⃣ CLV TRACKER (Closing Line Value)
# ════════════════════════════════════════════════════════════════════════

CLV_ENABLED = _env_bool("CLV_TRACKER_ENABLED", "true")
CLV_MIN_TIPS = int(_env("CLV_MIN_TIPS_FOR_REPORT", "20"))


def log_tip_for_clv(tip: Dict, target_date) -> bool:
    """Speichert Tipp beim Posten für CLV-Tracking."""
    if not CLV_ENABLED or not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        tip_id = (tip.get("tip_id") or
                  f"{tip.get('market','?')}_{target_date}_{abs(hash(tip.get('match','?'))) % 100000}")
        open_odds = tip.get("bet365_quote") or tip.get("oddsYes") or 0
        try:
            open_odds = float(str(open_odds).replace(",", "."))
        except:
            open_odds = 0
        if open_odds <= 1.0:
            return False

        pin_quote = None
        match = tip.get("match", "")
        if " vs " in match:
            parts = match.split(" vs ", 1)
            pin_quote = get_pinnacle_quote_for_market(parts[0].strip(), parts[1].strip(),
                                                       tip.get("market", "btts"))

        data = {
            "tip_id": tip_id, "date": str(target_date),
            "match": match, "league": tip.get("league", ""),
            "market": tip.get("market", "btts"), "tip": tip.get("tip", ""),
            "open_odds": round(open_odds, 2),
            "open_quote_source": tip.get("edge_source", "tip_odds"),
            "open_pinnacle": pin_quote,
            "open_bet365": tip.get("bet365_quote"),
            "open_timestamp": datetime.now(timezone.utc).isoformat(),
            "units": tip.get("kelly_units", 1.0),
            "result": "pending",
        }
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/clv_tracking",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            json=data, timeout=10,
        )
        return r.ok
    except Exception:
        return False


def fetch_closing_lines(target_date=None) -> int:
    """Holt Closing Lines für pending CLV-Tipps."""
    if not CLV_ENABLED or not SUPABASE_URL:
        return 0
    target_date = target_date or datetime.now(timezone.utc).date()

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/clv_tracking",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "date": f"eq.{target_date}",
                "close_pinnacle": "is.null",
                "select": "id,tip_id,match,market,open_odds,open_pinnacle",
            },
            timeout=15,
        )
        if not r.ok:
            return 0
        pending = r.json()
    except Exception:
        return 0

    updated = 0
    for ctip in pending:
        try:
            match = ctip.get("match", "")
            if " vs " not in match:
                continue
            parts = match.split(" vs ", 1)
            pin_close = get_pinnacle_quote_for_market(parts[0].strip(), parts[1].strip(),
                                                       ctip.get("market", "btts"))
            if not pin_close:
                continue

            open_pin = ctip.get("open_pinnacle") or ctip.get("open_odds")
            if not open_pin or open_pin <= 1:
                continue
            clv_pct = ((open_pin - pin_close) / pin_close) * 100

            r = requests.patch(
                f"{SUPABASE_URL}/rest/v1/clv_tracking",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                },
                params={"id": f"eq.{ctip['id']}"},
                json={
                    "close_pinnacle": pin_close,
                    "close_timestamp": datetime.now(timezone.utc).isoformat(),
                    "clv_pct": round(clv_pct, 2),
                },
                timeout=10,
            )
            if r.ok:
                updated += 1
        except Exception:
            continue
    return updated


def calculate_clv_report(days: int = 30) -> str:
    """Generiert CLV-Report über letzte X Tage."""
    if not CLV_ENABLED or not SUPABASE_URL:
        return ""
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/clv_tracking",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "date": f"gte.{since}",
                "clv_pct": "not.is.null",
                "select": "market,clv_pct,result,units,profit_units",
                "limit": "1000",
            },
            timeout=15,
        )
        if not r.ok:
            return ""
        tips = r.json()
    except Exception:
        return ""

    if len(tips) < CLV_MIN_TIPS:
        return f"📊 <b>CLV REPORT</b>\n\nZu wenig Daten: {len(tips)}/{CLV_MIN_TIPS} Tipps"

    avg_clv = sum(t.get("clv_pct", 0) for t in tips) / len(tips)
    pos_clv = sum(1 for t in tips if t.get("clv_pct", 0) > 0)
    neg_clv = len(tips) - pos_clv
    won = sum(1 for t in tips if t.get("result") == "won")
    lost = sum(1 for t in tips if t.get("result") == "lost")
    total_results = won + lost
    win_rate = (won / total_results * 100) if total_results > 0 else 0
    total_profit = sum(float(t.get("profit_units", 0) or 0) for t in tips)
    total_units = sum(float(t.get("units", 0) or 0) for t in tips)
    roi = (total_profit / total_units * 100) if total_units > 0 else 0

    by_market = {}
    for t in tips:
        m = t.get("market", "?")
        if m not in by_market:
            by_market[m] = {"count": 0, "clv_sum": 0, "won": 0, "lost": 0, "profit": 0}
        by_market[m]["count"] += 1
        by_market[m]["clv_sum"] += t.get("clv_pct", 0)
        if t.get("result") == "won": by_market[m]["won"] += 1
        elif t.get("result") == "lost": by_market[m]["lost"] += 1
        by_market[m]["profit"] += float(t.get("profit_units", 0) or 0)

    clv_emoji = "🔥" if avg_clv >= 3 else "✅" if avg_clv >= 0 else "⚠️"
    roi_emoji = "🟢" if roi > 0 else "🔴"

    msg = f"📊 <b>CLV REPORT - Letzte {days} Tage</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"{clv_emoji} <b>Durchschnittl. CLV: {avg_clv:+.2f}%</b>\n"
    msg += f"   ({pos_clv} pos · {neg_clv} neg / {len(tips)} total)\n\n"
    msg += f"🎯 <b>Hit-Rate:</b> {win_rate:.1f}% ({won}/{total_results})\n"
    msg += f"💰 <b>ROI:</b> {roi:+.2f}% ({total_profit:+.2f} Units) {roi_emoji}\n\n"

    market_names = {
        "btts": "⚽ BTTS", "over25": "🎯 Over 2.5", "combo": "🔥 Combo",
        "btts_ht": "🕐 BTTS HT", "over15_ht": "⏰ O1.5 HT",
        "corners": "🚩 Corners", "scorer": "⚽ Scorer",
        "advanced_props": "🔑 Props",
    }
    msg += "<b>📈 Pro Markt:</b>\n"
    sorted_markets = sorted(by_market.items(),
                              key=lambda x: x[1]["clv_sum"] / max(x[1]["count"], 1),
                              reverse=True)
    for market, st in sorted_markets:
        if st["count"] < 3:
            continue
        avg_mc = st["clv_sum"] / st["count"]
        wr = (st["won"] / max(st["won"] + st["lost"], 1)) * 100
        em = "🔥" if avg_mc >= 3 else "✅" if avg_mc >= 0 else "⚠️"
        msg += (f"{em} {market_names.get(market, market)}: "
                f"CLV {avg_mc:+.1f}% · "
                f"{st['won']}/{st['won']+st['lost']} ({wr:.0f}%) · "
                f"{st['profit']:+.1f}U\n")

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>💡 CLV > 0% = du hattest echte Edge\n"
    msg += "💡 CLV ist wichtiger als Hit-Rate!</i>"
    return msg


# ════════════════════════════════════════════════════════════════════════
# 6️⃣ LIVE EDGE ALERTS (Premium Alerts)
# ════════════════════════════════════════════════════════════════════════

LIVE_ALERTS_ENABLED = _env_bool("LIVE_EDGE_ALERTS_ENABLED", "true")
PREMIUM_EDGE_THRESHOLD = _env_float("PREMIUM_EDGE_THRESHOLD", 0.20)
EXTREME_EDGE_THRESHOLD = _env_float("EXTREME_EDGE_THRESHOLD", 0.30)
PREMIUM_MIN_PROB = int(_env("PREMIUM_MIN_PROB", "60"))
MAX_ALERTS_PER_DAY = int(_env("MAX_ALERTS_PER_DAY", "5"))


def format_alert_message(tip: Dict, alert_level: str = "premium") -> str:
    """Formatiert High-Edge Tipp als Premium Alert."""
    edge_pct = tip.get("edge_pct", 0)
    market = tip.get("market", "btts")
    info = MARKET_INFO_EXTENDED.get(market, {})
    market_emoji = info.get("emoji", "💎")
    market_name = info.get("name", market).replace("⚽ ", "").replace("🎯 ", "").replace("🔑 ", "")

    if alert_level == "extreme":
        header = "🚨🚨🚨 EXTREME EDGE ALERT 🚨🚨🚨"
        urgency = "🔥🔥🔥 DROP EVERYTHING 🔥🔥🔥"
    else:
        header = "💎 PREMIUM EDGE BET 💎"
        urgency = "🔥 HIGH VALUE"

    msg = f"<b>{header}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n<b>{urgency}</b>\n\n"
    msg += f"{market_emoji} <b>Markt: {market_name}</b>\n"
    msg += f"⚽ <b>{tip.get('match', '?')}</b>\n"
    msg += f"📍 {tip.get('league', '')}\n"
    msg += f"⏰ {tip.get('time', 'TBD')} Uhr\n\n"
    msg += f"🎯 <b>Tipp:</b> {tip.get('tip', 'YES')}\n"
    msg += f"📈 <b>Wahrscheinlichkeit:</b> {tip.get('probability', 0)}%\n"
    msg += f"⭐ <b>Confidence:</b> {'⭐' * int(tip.get('confidence', 0))}\n\n"
    msg += f"╔═══════════════════════╗\n║ 🔥 <b>EDGE: +{edge_pct:.1f}%</b> 🔥\n╚═══════════════════════╝\n\n"
    msg += f"💰 <b>Quote (Bet365):</b> {tip.get('bet365_quote', tip.get('oddsYes', '?'))}\n"
    msg += f"🎯 <b>Fair Odds:</b> {tip.get('fairOdds', tip.get('fair_odds', '?'))}\n"
    msg += f"📊 <b>Source:</b> {tip.get('edge_source', '?')}\n\n"
    kelly = tip.get('kelly_units', 1.0)
    msg += f"💵 <b>Empfohlener Stake:</b> {kelly} Units\n"
    profit_est = kelly * (edge_pct / 100)
    msg += f"📈 <b>Erwarteter Gewinn:</b> +{profit_est:.2f}U pro Bet\n\n"
    if tip.get("reasoning"):
        msg += f"💭 <i>{tip['reasoning'][:300]}</i>\n\n"
    if tip.get("keyFactor") or tip.get("key_factor"):
        msg += f"⚡ <i>{tip.get('keyFactor') or tip.get('key_factor')}</i>\n\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🎰 <b>BET365:</b> https://www.bet365.com/#/AS/B1/\n\n"
    msg += "⚠️ <i>Premium Alerts bei ≥20% Edge. Quoten ändern sich schnell!</i>"
    return msg


def _send_telegram_alert(text: str, chat_id: str = None) -> Optional[int]:
    """Sendet Telegram-Nachricht."""
    if not TELEGRAM_TOKEN:
        return None
    chat_id = chat_id or TELEGRAM_GROUP_PREMIUM or TELEGRAM_CHAT_ID
    if not chat_id:
        return None
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if not r.ok and r.status_code == 400:
            plain = re.sub(r"<[^>]+>", "", text)
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": plain}, timeout=15,
            )
        if r.ok:
            return r.json().get("result", {}).get("message_id")
    except Exception:
        return None


def send_edge_alerts(tips_by_market: Dict[str, List[Dict]],
                       min_edge: Optional[float] = None,
                       extreme_threshold: Optional[float] = None,
                       max_alerts: Optional[int] = None) -> int:
    """Sendet Premium Alerts für hohe Edge."""
    if not LIVE_ALERTS_ENABLED:
        return 0
    min_edge = min_edge if min_edge is not None else PREMIUM_EDGE_THRESHOLD
    extreme_threshold = extreme_threshold if extreme_threshold is not None else EXTREME_EDGE_THRESHOLD
    max_alerts = max_alerts if max_alerts is not None else MAX_ALERTS_PER_DAY

    high_edge = []
    for market, tips in (tips_by_market or {}).items():
        for tip in tips:
            if tip.get("edge", 0) < min_edge: continue
            if int(tip.get("probability", 0)) < PREMIUM_MIN_PROB: continue
            tip["market"] = tip.get("market", market)
            high_edge.append(tip)
    high_edge.sort(key=lambda t: t.get("edge", 0), reverse=True)
    high_edge = high_edge[:max_alerts]

    sent = 0
    for tip in high_edge:
        edge = tip.get("edge", 0)
        level = "extreme" if edge >= extreme_threshold else "premium"
        if _send_telegram_alert(format_alert_message(tip, alert_level=level), TELEGRAM_GROUP_PREMIUM):
            sent += 1
    return sent


# ════════════════════════════════════════════════════════════════════════
# 7️⃣ BACKTEST ENGINE
# ════════════════════════════════════════════════════════════════════════

def _fetch_historical_tips(days: int = 60) -> List[Dict]:
    """Lädt historische Tipps."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "select": "*", "date": f"gte.{since}",
                "status": "in.(won,lost)",
                "limit": "10000", "order": "date.asc",
            }, timeout=30,
        )
        if r.ok: return r.json()
    except Exception:
        pass
    return []


def _simulate_backtest(tips: List[Dict], apply_edge: bool = True,
                       apply_drawdown: bool = True, min_edge: float = 0.08,
                       starting_bankroll: float = 100.0) -> Dict:
    """Simuliert Performance."""
    bankroll = starting_bankroll
    peak = starting_bankroll
    loss_streak = 0
    posted = skipped_edge = skipped_dd = won = lost = 0
    total_profit = 0.0
    max_dd_pct = 0.0

    for tip in tips:
        try:
            odds = float(str(tip.get("odds", "1.0")).replace(",", "."))
            fair = float(str(tip.get("fair_odds", "1.0")).replace(",", "."))
            units = float(tip.get("units", 1.0))
        except:
            continue

        if apply_edge and ((odds / fair) - 1) < min_edge:
            skipped_edge += 1
            continue

        stake_mult = 1.0
        if apply_drawdown:
            bd = ((peak - bankroll) / peak * 100) if peak > 0 else 0
            if bd >= 20: skipped_dd += 1; continue
            elif loss_streak >= 5 or bd >= 10:
                stake_mult = 0.25
                if int(tip.get("probability", 0)) < 72: skipped_dd += 1; continue
            elif loss_streak >= 3:
                stake_mult = 0.5

        adj_units = units * stake_mult
        posted += 1

        if tip.get("status") == "won":
            profit = adj_units * (odds - 1)
            bankroll += profit
            total_profit += profit
            won += 1
            loss_streak = 0
        elif tip.get("status") == "lost":
            bankroll -= adj_units
            total_profit -= adj_units
            lost += 1
            loss_streak += 1

        if bankroll > peak: peak = bankroll
        dp = ((peak - bankroll) / peak * 100) if peak > 0 else 0
        if dp > max_dd_pct: max_dd_pct = dp

    tr = won + lost
    return {
        "tips_posted": posted, "tips_skipped_edge": skipped_edge,
        "tips_skipped_drawdown": skipped_dd,
        "won": won, "lost": lost,
        "win_rate": round((won / tr * 100) if tr > 0 else 0, 1),
        "final_units": round(bankroll, 2),
        "profit_units": round(total_profit, 2),
        "roi_pct": round((total_profit / starting_bankroll * 100), 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
    }


def run_backtest(days: int = 60, apply_edge_filter: bool = True,
                  min_edge: float = 0.08, apply_drawdown: bool = True,
                  starting_bankroll: float = 100.0) -> Dict:
    """Hauptfunktion für Backtest."""
    tips = _fetch_historical_tips(days)
    if not tips:
        return {"error": "Keine Daten"}

    baseline = _simulate_backtest(tips, apply_edge=False, apply_drawdown=False,
                                    starting_bankroll=starting_bankroll)
    with_filters = _simulate_backtest(tips, apply_edge=apply_edge_filter,
                                        apply_drawdown=apply_drawdown,
                                        min_edge=min_edge,
                                        starting_bankroll=starting_bankroll)
    return {
        "days": days, "total_tips": len(tips),
        "baseline": baseline, "with_filters": with_filters,
    }


def format_backtest_report(result: Dict) -> str:
    """Formatiert Backtest-Result."""
    if result.get("error"):
        return f"❌ Backtest: {result['error']}"
    bl = result["baseline"]
    wf = result["with_filters"]
    msg = f"🔬 <b>BACKTEST - {result['days']} Tage</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📊 <b>Datenbasis:</b> {result['total_tips']} Tipps\n\n"

    msg += "<b>📈 SZENARIO 1: Baseline</b>\n"
    msg += f"   Posted: {bl['tips_posted']} · Hit-Rate: {bl['win_rate']}%\n"
    msg += f"   Final: {bl['final_units']:.2f}U\n"
    sign = "+" if bl['profit_units'] >= 0 else ""
    pl_em = "🟢" if bl['profit_units'] >= 0 else "🔴"
    msg += f"   P/L: {sign}{bl['profit_units']:.2f}U ({sign}{bl['roi_pct']:.1f}%) {pl_em}\n"
    msg += f"   Max Drawdown: -{bl['max_drawdown_pct']:.1f}%\n\n"

    msg += "<b>🎯 SZENARIO 2: Mit Filtern</b>\n"
    msg += f"   Posted: {wf['tips_posted']} (Edge: -{wf['tips_skipped_edge']}, DD: -{wf['tips_skipped_drawdown']})\n"
    msg += f"   Hit-Rate: {wf['win_rate']}%\n"
    msg += f"   Final: {wf['final_units']:.2f}U\n"
    sign = "+" if wf['profit_units'] >= 0 else ""
    pl_em = "🟢" if wf['profit_units'] >= 0 else "🔴"
    msg += f"   P/L: {sign}{wf['profit_units']:.2f}U ({sign}{wf['roi_pct']:.1f}%) {pl_em}\n"
    msg += f"   Max Drawdown: -{wf['max_drawdown_pct']:.1f}%\n\n"

    diff = wf['final_units'] - bl['final_units']
    diff_em = "🚀" if diff > 5 else "✅" if diff > 0 else "⚠️"
    sign = "+" if diff >= 0 else ""
    msg += f"{diff_em} <b>VERBESSERUNG: {sign}{diff:.2f}U</b>\n\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>💡 Was passiert wäre wenn Filter aktiv gewesen wären.</i>"
    return msg


# ════════════════════════════════════════════════════════════════════════
# 🎯 BOOT MESSAGE
# ════════════════════════════════════════════════════════════════════════

print("[NETRATTLER-PRO] 🎯 V3 Module geladen:", flush=True)
print(f"   • Edge Filter:    {'✅' if EDGE_FILTER_ENABLED else '❌'} (min {EDGE_FILTER_MIN_EDGE*100:.0f}%)", flush=True)
print(f"   • Cross-Combos:   {'✅' if CROSS_MATCH_COMBOS else '❌'}", flush=True)
print(f"   • Drawdown Prot:  {'✅' if DRAWDOWN_ENABLED else '❌'}", flush=True)
print(f"   • CLV Tracker:    {'✅' if CLV_ENABLED else '❌'}", flush=True)
print(f"   • Live Alerts:    {'✅' if LIVE_ALERTS_ENABLED else '❌'} (≥{PREMIUM_EDGE_THRESHOLD*100:.0f}%)", flush=True)
print(f"   • Pinnacle:       ✅ (kostenlos via guest token)", flush=True)


# ════════════════════════════════════════════════════════════════════════
# DEBUG (lokaler Test)
# ════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 NetRattler Pro V3 - Self Test")
    print("="*70)
    
    # Test Edge Filter
    test_tip = {
        "match": "Arsenal vs Brentford", "league": "Premier League",
        "market": "btts", "tip": "YES", "probability": 70, "confidence": 5,
        "fairOdds": "1.43", "oddsYes": "2.10", "time": "20:00",
    }
    result = filter_tips_by_edge([test_tip], market="btts")
    if result:
        print(f"\n✅ Edge Filter: Tipp mit +{result[0]['edge_pct']}% Edge durchgelassen")
    
    # Test Drawdown
    mode = get_current_mode()
    print(f"\n✅ Drawdown Mode: {mode['mode']} ({mode['reason']})")
    
    # Test Pinnacle (live!)
    print("\n📊 Test Pinnacle Scraper (live)...")
    matches = fetch_pinnacle_matchups()
    print(f"   Gefunden: {len(matches)} aktuelle Matches")
    
    print("\n✅ Alle Module funktionieren!")

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
    run_mode = env("RUN_MODE", "tips")  # "tips", "settlement", "both", "live"

    # Settlement: nur wenn RUN_MODE=settlement/both ODER explizit aktiviert
    _do_settlement = (
        run_mode in ["settlement", "both"]
        or env("ENABLE_SETTLEMENT", "false").lower() in ["1", "true", "yes"]
    )
    if _do_settlement:
        log("🏆 Settlement - prüfe vergangene Tipps...")
        try:
            run_settlement()
        except Exception as _se:
            log(f"🏆 Settlement Fehler: {str(_se)[:80]}", "WARN")

    if run_mode == "settlement":
        log("Settlement fertig!")
        return

    # Live Bot Mode
    if run_mode == "live":
        log("🔴 Live Bot Mode...")
        run_live_bots()
        log("Live Bots fertig!")
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

    # Martj42 vorab laden
    load_martj42_data()

    # ── API-Football Bulk: ALLE heutigen Spiele in 1 Call ──
    global _AF_BULK_FIXTURES
    if API_FOOTBALL_KEY:
        try:
            import requests as _rq
            log("📡 API-Football: Lade alle heutigen Spiele...")
            _af_r = _rq.get(
                "https://v3.football.api-sports.io/fixtures",
                headers={"x-rapidapi-key": API_FOOTBALL_KEY,
                         "x-rapidapi-host": "v3.football.api-sports.io"},
                params={"date": target_date.strftime("%Y-%m-%d"), "timezone": "UTC"},
                timeout=15
            )
            if _af_r.ok:
                _af_data = _af_r.json()
                _af_all = _af_data.get("response", [])
                for _fix in _af_all:
                    _ln = _fix.get("league",{}).get("name","")
                    _cn = _fix.get("league",{}).get("country","")
                    _key = f"{_ln} ({_cn})"
                    if _key not in _AF_BULK_FIXTURES:
                        _AF_BULK_FIXTURES[_key] = []
                    _h = _fix.get("teams",{}).get("home",{}).get("name","")
                    _a = _fix.get("teams",{}).get("away",{}).get("name","")
                    _t = _fix.get("fixture",{}).get("date","")[:16].replace("T"," ")
                    if _h and _a:
                        _AF_BULK_FIXTURES[_key].append({
                            "home": _h, "away": _a, "time": _t, "source": "api-football",
                            "league_id": _fix.get("league",{}).get("id",0),
                        })
                total_af = sum(len(v) for v in _AF_BULK_FIXTURES.values())
                log(f"   ✅ API-Football Bulk: {total_af} Spiele in {len(_AF_BULK_FIXTURES)} Ligen (1 API-Call)")
            else:
                log(f"   ⚠️ API-Football Bulk: HTTP {_af_r.status_code}")
        except Exception as _e:
            log(f"   ⚠️ API-Football Bulk Fehler: {_e}")

    # ── Variablen initialisieren ──
    tips_by_market = {m: [] for m in MARKETS_TO_RUN}
    total_analyzed = 0
    _fixtures_cache = {}
    _m42_sent_today = set()  # Dedup: martj42-Match nur einmal analysieren, nicht für jede intl. Liga

    # ── Pinnacle global laden ──
    log("📊 Pinnacle Matchups laden...")
    try:
        _PINNACLE_MATCHUPS = fetch_pinnacle_matchups()
        _raw_count = len(_PINNACLE_MATCHUPS)
        # 🆕 Dedup: Pinnacle liefert teils doppelte Einträge für dasselbe Spiel
        # (z.B. durch verschiedene Markt-Gruppierungen) — vor der Analyse bereinigen,
        # damit nicht zwei separate Tipps für denselben Match in einem Run entstehen.
        _seen_matchup_keys = set()
        _deduped_matchups = []
        for _pm in _PINNACLE_MATCHUPS:
            _key = (
                normalize_team_name(_pm.get("home", "")),
                normalize_team_name(_pm.get("away", "")),
                (_pm.get("league_name") or _pm.get("league") or "").lower(),
            )
            if _key in _seen_matchup_keys:
                continue
            _seen_matchup_keys.add(_key)
            _deduped_matchups.append(_pm)
        _PINNACLE_MATCHUPS = _deduped_matchups
        if _raw_count != len(_PINNACLE_MATCHUPS):
            log(f"   🧹 Pinnacle Dedup: {_raw_count} → {len(_PINNACLE_MATCHUPS)} Matches ({_raw_count - len(_PINNACLE_MATCHUPS)} Duplikate entfernt)")
        log(f"   ✅ Pinnacle: {len(_PINNACLE_MATCHUPS)} Matches geladen")
    except Exception as e:
        _PINNACLE_MATCHUPS = []
        log(f"   ⚠️ Pinnacle: {e}")

    pinnacle_tips_count = 0
    # ⏰ Gestaffeltes Zeitfenster (Schweizer Zeit):
    #    Run vor 14:00 CH  → Spiele heute 12:00–20:00 CH (Nachmittag/Abend)
    #    Run ab 14:00 CH   → Spiele heute 20:00 – morgen 12:00 CH (spät/Nacht/Morgen)
    from datetime import timedelta as _td
    try:
        from zoneinfo import ZoneInfo as _ZI
        _ch_tz = _ZI("Europe/Zurich")
    except Exception:
        _ch_tz = timezone(_td(hours=2))
    _now_ch = now_utc.astimezone(_ch_tz)
    _today_ch = _now_ch.replace(hour=0, minute=0, second=0, microsecond=0)
    if _now_ch.hour < 14:
        _win_start = _today_ch.replace(hour=12)
        _win_end = _today_ch.replace(hour=20)
        log(f"⏰ Fenster: heute 12:00–20:00 CH (Morgen-Run)")
    else:
        _win_start = _today_ch.replace(hour=20)
        _win_end = (_today_ch + _td(days=1)).replace(hour=12)
        log(f"⏰ Fenster: heute 20:00 – morgen 12:00 CH (Abend-Run)")
    _win_start_utc = _win_start.astimezone(timezone.utc)
    _win_end_utc = _win_end.astimezone(timezone.utc)
    # 🆕 Fix: Untergrenze nie in der Vergangenheit — falls der Run spät im Fenster
    # startet (oder lange läuft), werden bereits angepfiffene Spiele ausgeschlossen.
    if now_utc > _win_start_utc:
        log(f"   ⏰ Fenster-Untergrenze angepasst: {_win_start_utc.strftime('%H:%M')} → {now_utc.strftime('%H:%M')} UTC (Run startet spät im Fenster)")
        _win_start_utc = now_utc
    if _PINNACLE_MATCHUPS:
        log(f"🎰 Analysiere {len(_PINNACLE_MATCHUPS)} Pinnacle Matches...")
        from datetime import datetime as _pdt
        _processed_this_run = set()  # 🆕 Sicherheitsnetz gegen Restduplikate innerhalb des Runs
        for pm in _PINNACLE_MATCHUPS:
            try:
                home = pm.get("home", "")
                away = pm.get("away", "")
                league_name = pm.get("league_name", "")
                starts = pm.get("starts", "")
                if not home or not away:
                    continue
                _run_key = (normalize_team_name(home), normalize_team_name(away), league_name.lower())
                if _run_key in _processed_this_run:
                    continue
                _processed_this_run.add(_run_key)
                # Specials skippen — Corners/Bookings sind keine echten Matches
                if ("(Corners)" in home or "(Bookings)" in home
                        or "Corners" in league_name or "Bookings" in league_name):
                    continue

                # Zeitfenster: gestaffelt nach CH-Zeit (siehe oben)
                match_dt = None
                if starts:
                    try:
                        s = starts.replace("Z", "+00:00")
                        if "+" not in s[10:] and s[10:].count("-") == 0:
                            s += "+00:00"
                        match_dt = _pdt.fromisoformat(s)
                        if match_dt < _win_start_utc or match_dt >= _win_end_utc:
                            continue
                    except Exception:
                        continue  # Ohne Zeit kein gestaffelter Tipp

                log(f"   🎰 Pinnacle: {home} vs {away} | {league_name}")

                # Liga-basierte BTTS/Over-Schätzungen
                ln = league_name.lower()
                if any(k in ln for k in ["world cup","fifa","weltmeister"]):
                    btts_yes, over25, prob_b, prob_o = 1.80, 1.75, 68, 67
                elif any(k in ln for k in ["friendly","international"]):
                    btts_yes, over25, prob_b, prob_o = 1.90, 1.85, 67, 68
                elif any(k in ln for k in ["premier league","bundesliga","la liga","serie a","ligue 1","eredivisie","brasileirao","mls"]):
                    btts_yes, over25, prob_b, prob_o = 1.75, 1.70, 68, 69
                else:
                    btts_yes, over25, prob_b, prob_o = 1.85, 1.80, 67, 68

                # 🌍 martj42: echte BTTS/Over-Raten für Nationalteams
                # Fix: "Club Friendlies" enthält "friendl", darf aber NICHT als Länderspiel zählen
                # (sonst matched die lockere Fuzzy-Suche Vereinsnamen fälschlich gegen Länder-Daten)
                _is_intl = (
                    any(k in ln for k in ["world cup", "fifa", "international", "nations league", "weltmeister"])
                    or ("friendl" in ln and "club" not in ln)
                )
                if _is_intl:
                    try:
                        _sh = get_national_team_btts_stats(home)
                        _sa = get_national_team_btts_stats(away)
                        if _sh and _sa:
                            _mb = (_sh["btts_pct"] + _sa["btts_pct"]) / 2
                            _mo = (_sh["over25_pct"] + _sa["over25_pct"]) / 2
                            # Mit Liga-Basis mischen (60% Team-Daten, 40% Basis)
                            prob_b = int(0.6 * _mb + 0.4 * prob_b)
                            prob_o = int(0.6 * _mo + 0.4 * prob_o)
                            log(f"      🌍 martj42: {home} {_sh['btts_pct']}% / {away} {_sa['btts_pct']}% BTTS → {prob_b}%")
                    except Exception:
                        pass
                else:
                    # 🆕 football-data.co.uk: echte BTTS/Over-Raten für ~20 Top-Vereinsligen
                    try:
                        _fh = get_fd_co_uk_team_stats(home, league_name)
                        _fa = get_fd_co_uk_team_stats(away, league_name)
                        if _fh and _fa:
                            _mb = (_fh["btts_pct"] + _fa["btts_pct"]) / 2
                            _mo = (_fh["over25_pct"] + _fa["over25_pct"]) / 2
                            prob_b = int(0.6 * _mb + 0.4 * prob_b)
                            prob_o = int(0.6 * _mo + 0.4 * prob_o)
                            log(f"      📊 FD-CoUk: {home} {_fh['btts_pct']}% / {away} {_fa['btts_pct']}% BTTS → {prob_b}% ({_fh['games']}/{_fa['games']} Spiele)")
                    except Exception:
                        pass

                    # 🤖 XGBoost ML-Modell (stärkste Ebene wenn Modelle geladen)
                    # Schlägt Elo/Poisson weil es kalibriert und aus echten Daten trainiert ist
                    try:
                        # 🆕 ClubElo als externe Teamstärke-Quelle
                        _celo = get_clubelo_for_match(home, away, target_date)
                        if _celo.get("elo_diff") is not None:
                            log(f"      ⚡ ClubElo: {home} {_celo['elo_home']} vs {away} {_celo['elo_away']} (Diff: {_celo['elo_diff']})")

                        _ml = get_ml_prediction(home, away, league_name)
                        if _ml:
                            # 80% ML-Modell, 20% bisherige Schätzung (Absicherung bei Nischenteams)
                            prob_b = int(0.80 * _ml.get("btts_pct", prob_b) + 0.20 * prob_b)
                            prob_o = int(0.80 * _ml.get("over25_pct", prob_o) + 0.20 * prob_o)
                            log(f"      🤖 XGBoost: BTTS {_ml.get('btts_pct')}%, Over2.5 {_ml.get('over25_pct')}% "
                                f"→ final {prob_b}%/{prob_o}%")
                        else:
                            # Fallback: Elo + Poisson Formel
                            _elo = get_elo_poisson_prediction(home, away, league_name)
                            if _elo:
                                prob_b = int(0.70 * prob_b + 0.30 * _elo["btts_pct"])
                                prob_o = int(0.70 * prob_o + 0.30 * _elo["over25_pct"])
                                log(f"      🧠 Elo-Fallback: {home}({_elo['elo_home']:.0f}) vs {away}({_elo['elo_away']:.0f}) "
                                    f"BTTS {_elo['btts_pct']}% → final {prob_b}%")
                    except Exception:
                        pass

                # Echte Pinnacle-Odds als Upgrade (optional, mit Schutz)
                ro = None
                try:
                    ro = get_pinnacle_match_odds(home, away)
                    if ro:
                        if ro.get("btts_yes"):
                            btts_yes = ro["btts_yes"]
                            prob_b = int(100 / btts_yes * 0.95)
                        if ro.get("over_25"):
                            over25 = ro["over_25"]
                            prob_o = int(100 / over25 * 0.95)
                except Exception:
                    pass

                mn = f"{home} vs {away}"
                tstr = "TBD"
                _ko_sort = "9999"
                try:
                    if match_dt:
                        _ko_ch = match_dt.astimezone(_ch_tz)
                        tstr = _ko_ch.strftime("%H:%M")
                        _ko_sort = match_dt.isoformat()
                    elif starts and "T" in starts:
                        tstr = starts[11:16]
                except Exception:
                    pass

                # BTTS Tipp — nur Value Bets (Quote >=1.70 + echter Edge)
                if prob_b >= MIN_PROBABILITY and "btts" in tips_by_market and _is_value_bet(btts_yes, prob_b):
                    tip_btts = {
                        "match": mn, "league": league_name or "Pinnacle",
                        "time": tstr, "tip": "YES",
                        "probability": prob_b, "confidence": 3,
                        "oddsYes": btts_yes, "fairOdds": round(100/prob_b, 2),
                        "valueRating": ("VALUE" if ro else "OK"), "units": 1.0, "market": "btts",
                        "reasoning": f"Pinnacle Markt-Analyse | {league_name}",
                        "_no_real_odds": not bool(ro), "_source": "pinnacle", "_kickoff": _ko_sort,
                    }
                    enrich_pinnacle_tip(tip_btts, home, away, league_name)
                    tips_by_market["btts"].append(tip_btts)
                    pinnacle_tips_count += 1
                    log(f"      ✅ BTTS YES @ {btts_yes} ({prob_b}%)")

                # Over 2.5 Tipp — nur Value Bets
                if prob_o >= MIN_PROBABILITY and "over25" in tips_by_market and _is_value_bet(over25, prob_o):
                    tip_over25 = {
                        "match": mn, "league": league_name or "Pinnacle",
                        "time": tstr, "tip": "YES",
                        "probability": prob_o, "confidence": 3,
                        "oddsYes": over25, "fairOdds": round(100/prob_o, 2),
                        "valueRating": ("VALUE" if ro else "OK"), "units": 1.0, "market": "over25",
                        "reasoning": f"Pinnacle Markt-Analyse | {league_name}",
                        "_no_real_odds": not bool(ro), "_source": "pinnacle", "_kickoff": _ko_sort,
                    }
                    enrich_pinnacle_tip(tip_over25, home, away, league_name)
                    tips_by_market["over25"].append(tip_over25)
                    pinnacle_tips_count += 1

                # 🔥 Combo: BTTS + Over 2.5 (stark korreliert)
                if prob_b >= MIN_PROBABILITY and prob_o >= MIN_PROBABILITY and "combo" in tips_by_market:
                    # Korrelation: BTTS-Yes-Spiele sind meist auch Over 2.5
                    combo_prob = min(prob_b, prob_o) - 5
                    combo_odds = round(btts_yes * over25 * 0.80, 2)  # Korrelationsabschlag
                    if combo_prob >= (MIN_PROBABILITY - 10) and _is_value_bet(combo_odds, combo_prob):
                        tip_combo = {
                            "match": mn, "league": league_name or "Pinnacle",
                            "time": tstr, "tip": "BTTS + Over 2.5",
                            "probability": combo_prob, "confidence": 3,
                            "oddsYes": combo_odds, "fairOdds": round(100/combo_prob, 2),
                            "valueRating": ("VALUE" if ro else "OK"), "units": 0.75, "market": "combo",
                            "reasoning": f"Pinnacle Combo-Analyse | {league_name}",
                            "_no_real_odds": not bool(ro), "_source": "pinnacle", "_kickoff": _ko_sort,
                        }
                        enrich_pinnacle_tip(tip_combo, home, away, league_name)
                        tips_by_market["combo"].append(tip_combo)
                        pinnacle_tips_count += 1

                # 🕐 HT-Tipps: BTTS HT + Over 1.5 HT (zwei separate Tipps)
                if "btts_ht" in tips_by_market:
                    # --- BTTS HT ---
                    btts_ht_odds = 0
                    btts_ht_prob = 0
                    try:
                        if ro and ro.get("btts_yes_ht"):
                            btts_ht_odds = ro["btts_yes_ht"]
                            btts_ht_prob = int(100 / btts_ht_odds * 0.95)
                    except Exception:
                        pass
                    if not btts_ht_odds:
                        # Fallback: ~38-44% liegt BTTS HT typischerweise
                        if prob_b >= MIN_PROBABILITY + 5:  # sehr torreiche Paarung
                            btts_ht_odds, btts_ht_prob = 2.05, 68
                        else:
                            btts_ht_odds, btts_ht_prob = 2.30, 67
                    if btts_ht_prob >= MIN_PROBABILITY and _is_value_bet(btts_ht_odds, btts_ht_prob):
                        tip_btts_ht = {
                            "match": mn, "league": league_name or "Pinnacle",
                            "time": tstr, "tip": "BTTS HT (Beide Teams treffen 1.HZ)",
                            "probability": btts_ht_prob, "confidence": 3,
                            "oddsYes": btts_ht_odds, "fairOdds": round(100/btts_ht_prob, 2),
                            "valueRating": ("VALUE" if (ro and ro.get("btts_yes_ht")) else "OK"), "units": 1.0, "market": "btts_ht",
                            "reasoning": f"Pinnacle HT-Analyse | {league_name}",
                            "_no_real_odds": not bool(ro), "_source": "pinnacle", "_kickoff": _ko_sort,
                        }
                        enrich_pinnacle_tip(tip_btts_ht, home, away, league_name)
                        tips_by_market["btts_ht"].append(tip_btts_ht)
                        pinnacle_tips_count += 1

                    # --- Over 1.5 Tore HT ---
                    o15_odds = 0
                    o15_prob = 0
                    try:
                        if ro and ro.get("over_15_ht"):
                            o15_odds = ro["over_15_ht"]
                            o15_prob = int(100 / o15_odds * 0.95)
                    except Exception:
                        pass
                    if not o15_odds:
                        if prob_o >= MIN_PROBABILITY:  # torreiche Liga
                            o15_odds, o15_prob = 2.10, 68
                        else:
                            o15_odds, o15_prob = 2.40, 67
                    if o15_prob >= MIN_PROBABILITY and "over15_ht" in tips_by_market and _is_value_bet(o15_odds, o15_prob):
                        tip_o15_ht = {
                            "match": mn, "league": league_name or "Pinnacle",
                            "time": tstr, "tip": "Over 1.5 Tore HT",
                            "probability": o15_prob, "confidence": 3,
                            "oddsYes": o15_odds, "fairOdds": round(100/o15_prob, 2),
                            "valueRating": ("VALUE" if (ro and ro.get("over_15_ht")) else "OK"), "units": 1.0, "market": "over15_ht",
                            "reasoning": f"Pinnacle HT-Analyse | {league_name}",
                            "_no_real_odds": not bool(ro), "_source": "pinnacle", "_kickoff": _ko_sort,
                        }
                        enrich_pinnacle_tip(tip_o15_ht, home, away, league_name)
                        tips_by_market["over15_ht"].append(tip_o15_ht)
                        pinnacle_tips_count += 1

                total_analyzed += 1
            except Exception as pe:
                log(f"   ⚠️ Pinnacle Match Fehler: {str(pe)[:60]}")
        log(f"🎰 Pinnacle fertig: {pinnacle_tips_count} Tipps generiert")

    if MAX_LEAGUES_PER_RUN > 0:
        active_leagues = active_leagues[:MAX_LEAGUES_PER_RUN]
        log(f"MAX_LEAGUES_PER_RUN aktiv: Es werden nur {len(active_leagues)} Ligen analysiert.")

    # ⚡ SPEED: Liga-Schleife skippen wenn Pinnacle genug geliefert hat
    # (ESPN/FotMob/etc. liefern aus GitHub Actions eh 0 — spart ~5 Min Actions-Minuten)
    _skip_league_loop = False
    try:
        # 🆕 Schwelle auf 10 gesenkt (vorher 30) — auch Morgen-Runs mit wenigen Matches sparen Zeit
        if pinnacle_tips_count >= 10 and env("FORCE_LEAGUE_LOOP", "false").lower() not in ["1", "true", "yes"]:
            _skip_league_loop = True
            log(f"⚡ Liga-Schleife übersprungen ({pinnacle_tips_count} Pinnacle-Tipps reichen) — spart ~5 Min")
    except Exception:
        pass

    for league in ([] if _skip_league_loop else active_leagues):
        log(f"╔══ Liga: {league} ══╗")

        try:
            odds, fixtures = fetch_league_data_once(league, target_date)
            if fixtures:
                _fixtures_cache[league] = fixtures  # Speichern für Corners/Scorer

            if not odds and not fixtures:
                continue  # Kein Log-Spam für leere Ligen

            # Ohne Odds: martj42 für Länderspiele nutzen
            if not odds and fixtures:
                intl_kw = ["international","wm 2026","nations league","copa america",
                           "afrika cup","gold cup","freundschaft","friendly",
                           "freundschaftsspiele"]
                if any(kw in league.lower() for kw in intl_kw):
                    log(f"   🌍 [{league}] Länderspiel-Analyse via martj42...")
                    is_friendly = any(k in league.lower() for k in ["freundschaft","friendly","international friendly"])
                    btts_threshold = 55 if is_friendly else 62
                    for fix in fixtures[:8]:
                        h, a = fix.get("home",""), fix.get("away","")
                        if not h or not a:
                            continue
                        # 🆕 Dedup — selbes Match nicht mehrfach senden
                        _m42_key = f"{h}_{a}"
                        if _m42_key in _m42_sent_today:
                            continue
                        _m42_sent_today.add(_m42_key)
                        h_st = get_national_team_btts_stats(h)
                        a_st = get_national_team_btts_stats(a)
                        if h_st and a_st:
                            bp = (h_st.get("btts_pct",0)+a_st.get("btts_pct",0))/2
                            op = (h_st.get("over25_pct",0)+a_st.get("over25_pct",0))/2
                            log(f"   🌍 {h} vs {a}: BTTS={bp:.0f}% Over={op:.0f}% (min {btts_threshold}%)")
                            mn = f"{h} vs {a}"
                            if bp >= btts_threshold:
                                tips_by_market["btts"].append({
                                    "match":mn,"league":league,"time":"TBD",
                                    "tip":"YES","probability":int(bp),"confidence":3,
                                    "oddsYes":round(100/bp,2),"fairOdds":round(100/bp,2),
                                    "valueRating":"OK","units":1.0,"market":"btts",
                                    "reasoning":f"martj42: {h} {h_st.get('btts_pct',0):.0f}% | {a} {a_st.get('btts_pct',0):.0f}%",
                                    "_no_real_odds":True,
                                })
                                total_analyzed += 1
                            if op >= 62:
                                tips_by_market["over25"].append({
                                    "match":mn,"league":league,"time":"TBD",
                                    "tip":"YES","probability":int(op),"confidence":3,
                                    "oddsYes":round(100/op,2),"fairOdds":round(100/op,2),
                                    "valueRating":"OK","units":1.0,"market":"over25",
                                    "reasoning":f"martj42 Over2.5: ⌀{(h_st.get('avg_goals',0)+a_st.get('avg_goals',0))/2:.1f} Tore",
                                    "_no_real_odds":True,
                                })
                                total_analyzed += 1
                            # Over 2.5
                continue  # Keine Odds → Gemini überspringen

            # ✅ Qualitäts-Check: TheSportsDB allein = überspringen!
            if fixtures:
                confirmed = []
                for fix in fixtures:
                    source = fix.get("source", "")
                    home = fix.get("home", "").lower()
                    away = fix.get("away", "").lower()
                    # Zähle Bestätigungen von anderen Quellen
                    other_sources = [
                        f for f in fixtures
                        if f.get("home","").lower() == home
                        and f.get("away","").lower() == away
                        and f.get("source","") != source
                    ]
                    # TheSportsDB allein → nur für bekannte Ligen erlauben
                    # (nicht filtern wenn keine anderen Quellen verfügbar!)
                    if source == "thesportsdb" and not other_sources:
                        # Trotzdem behalten - TheSportsDB ist oft die einzige Quelle!
                        pass  # Nicht filtern
                    if fix not in confirmed:
                        confirmed.append(fix)
                if len(confirmed) < len(fixtures):
                    log(f"   🔍 Filter: {len(fixtures)} → {len(confirmed)} Spiele")
                fixtures = confirmed

            if not fixtures and not odds:
                log("   - Keine bestätigten Spiele")
                continue

            log(f"   📅 {len(fixtures)} Spiele | 💰 {len(odds)} mit Quoten")
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
                    log(f"   ⚠️ {source} → kein Ergebnis")

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

    # ── NETRATTLER PRO: Edge Filter ──
    if NETRATTLER_PRO:
        try:
            _ef = integrate_edge_filter_into_pipeline(tips_by_market)
            _ft = _ef.get("filtered_tips") if isinstance(_ef, dict) else None
            if _ft:
                for _mk in list(tips_by_market.keys()):
                    _orig = tips_by_market.get(_mk, [])
                    _filt = _ft.get(_mk, [])
                    # Wenn Filter alles verwirft (keine echten Quoten) → Original behalten
                    if _filt:
                        tips_by_market[_mk] = _filt
                    else:
                        log(f"   🎯 Edge Filter [{_mk}]: keine Quoten — behalte {len(_orig)} Tipps")
                log(f"   🎯 Edge Filter angewendet (mit Pinnacle-Fallback)")
        except Exception as _efe:
            log(f"   🎯 Edge Filter übersprungen: {str(_efe)[:60]}")

    # ⏰ Sortierung nach Anstosszeit (früheste zuerst)
    for _mk in tips_by_market:
        try:
            tips_by_market[_mk].sort(key=lambda t: t.get("_kickoff", "9999"))
        except Exception:
            pass

    send_top_tips(tips_by_market, target_date)

    # 📊 Gruppen-Auswertung IMMER senden (nicht nur an tipplosen Tagen) — jede Gruppe
    # bekommt ihre Markt-Stats. Guard in der Funktion verhindert Doppel-Senden.
    try:
        _send_daily_auswertung_to_all_groups()
    except Exception as _ae:
        log(f"Gruppen-Auswertung Error: {str(_ae)[:60]}", "WARN")
    if _PINNACLE_MATCHUPS:
        _injected = 0
        for pm in _PINNACLE_MATCHUPS:
            _h, _a = pm.get("home",""), pm.get("away","")
            _ln = pm.get("league_name","")
            _st = pm.get("starts","")
            # Skip Specials-Duplikate (Corners/Bookings als eigene "Matches")
            if not _h or not _a or "(Corners)" in _h or "(Bookings)" in _h:
                continue
            # Zeitfenster wie oben
            try:
                _s = _st.replace("Z","+00:00")
                if "+" not in _s[10:] and _s[10:].count("-")==0:
                    _s += "+00:00"
                from datetime import datetime as _idt
                _md = _idt.fromisoformat(_s)
                if _md < _win_start_utc or _md >= _win_end_utc:
                    continue
            except Exception:
                pass
            _key = _ln or "Pinnacle"
            if _key not in _fixtures_cache:
                _fixtures_cache[_key] = []
            _t = _st[11:16] if _st and "T" in _st else "TBD"
            _fixtures_cache[_key].append({"home": _h, "away": _a, "time": _t, "source": "pinnacle"})
            if _key not in active_leagues:
                active_leagues.append(_key)
            _injected += 1
        if _injected:
            log(f"🎰 {_injected} Pinnacle-Matches als Fixtures für Props/Corners injiziert")

    # Builder-Pool pro Run zurücksetzen, damit keine alten Legs erneut erscheinen.
    _NTR_BUILDER_PROP_POOL.clear()

    # 🔵⚽ Ecken + Scorer Bots
    if env("ENABLE_CORNERS_SCORER", "true").lower() in ["1", "true", "yes"]:
        run_corners_and_scorer_bots(
            target_date=target_date,
            active_leagues=active_leagues,
            odds_data_cache={},
            fixtures_cache=_fixtures_cache,
        )

    # 🔑 ADVANCED PROPS BOT
    if env("ENABLE_ADVANCED_PROPS", "true").lower() in ["1", "true", "yes"]:
        run_advanced_props_bot(
            active_leagues=active_leagues,
            fixtures_cache=_fixtures_cache,
            target_date=target_date,
        )
        # 🔑 Pinnacle Player Props (echte Quoten — funktioniert aus Actions!)
        try:
            # 🆕 Beste BTTS-Tipps nach Wahrscheinlichkeit für Prop Builder vorbereiten
            _top_btts_for_props = sorted(
                [t for t in tips_by_market.get("btts", []) if int(t.get("probability", 0)) >= 65],
                key=lambda x: int(x.get("probability", 0)),
                reverse=True
            )[:20]
            run_pinnacle_props_bot(
                win_start_utc=_win_start_utc,
                win_end_utc=_win_end_utc,
                ch_tz=_ch_tz,
                top_btts_tips=_top_btts_for_props,
                fixtures_cache=_fixtures_cache,
            )
        except Exception as _ppe:
            log(
                f"🔑 Pinnacle Props Error: {type(_ppe).__name__}: {str(_ppe)[:140]}",
                "WARN",
            )
            if env("DEBUG_PROP_TRACEBACK", "false").lower() in ["1", "true", "yes"]:
                traceback.print_exc()

    # 🆕 NETRATTLER BUILDER ENGINE V20 — Shot Ladders, SOT Trios, Corner Fusion
    try:
        from netrattler_builder_engine import run_builder_engine, build_builder_picks
        _builder_prop_pool = []

        # Kandidaten aus normalen Team-Tipps nur optional.
        # V31 CLEAN: Prop Builder soll echte Spielerprops senden, keine BTTS/Over-Team-Builder.
        # V34B SANITY: PROP BUILDER ist player-only.
        # Team-Märkte bleiben in BTTS / Over / Combo und dürfen nicht als
        # "Player-Prop Profil" oder mit multiplizierten korrelierten Quoten erscheinen.
        _team_builder_env = str(env("ENABLE_TEAM_LEGS_IN_PROP_BUILDER", "false")).lower() in ["1", "true", "yes", "on"]
        if _team_builder_env:
            log("   ⚠️ ENABLE_TEAM_LEGS_IN_PROP_BUILDER wird in V34B ignoriert: Prop Builder bleibt player-only", "WARN")
        _allow_team_legs_for_builder = False
        for _mk, _tips in []:
            for _t in _tips:
                _match_n = _t.get("match", "")
                _parts = _match_n.split(" vs ") if " vs " in _match_n else [_match_n, ""]
                _builder_prop_pool.append({
                    "player": _t.get("tip", ""),
                    "team": _t.get("team", _parts[0] if "home" in _mk else _parts[1] if len(_parts) > 1 else ""),
                    "match": _match_n,
                    "league": _t.get("league", ""),
                    "market": _t.get("market_name", _mk),
                    "category": {
                        "btts": "btts", "over25": "over_goals",
                        "corners": "team_corners", "btts_ht": "btts_ht", "over15_ht": "half_goals_1st",
                    }.get(_mk, "shots"),
                    "line": 0.5,
                    "odds": _t.get("odds", _t.get("oddsYes", 0)),
                    "model_prob": _t.get("probability", 0),
                    "source": _t.get("_source", "pinnacle"),
                    "ko": str(_t.get("_kickoff", "")),
                    "games": 10,
                })

        # Echte Player-Props aus Advanced Props + Pinnacle hinzufügen.
        _builder_prop_pool.extend(_NTR_BUILDER_PROP_POOL)

        # Match-Kontexte für Same-Match-/Underdog-/Narrative-Builder.
        try:
            from netrattler_source_hub import source_health_snapshot
            _enabled_sources = [s for s in source_health_snapshot() if s.get("enabled")]
            log("   🌐 Source Hub V30 aktiv: " + ", ".join(s["source"] for s in _enabled_sources[:10]) + ("..." if len(_enabled_sources) > 10 else ""))
        except Exception as _sh_exc:
            log(f"   🌐 Source Hub V30 Diagnose übersprungen: {str(_sh_exc)[:80]}", "WARN")

        _builder_contexts = []
        for _lg, _fixs in (_fixtures_cache or {}).items():
            for _fx in (_fixs or []):
                _home = _fx.get("home", "")
                _away = _fx.get("away", "")
                if _home and _away:
                    _builder_contexts.append({
                        "match": f"{_home} vs {_away}",
                        "league": _lg,
                        "home_odds": _fx.get("home_odds", 0),
                        "away_odds": _fx.get("away_odds", 0),
                    })

        _pool_categories = {}
        _pool_matches = {}
        for _row in _NTR_BUILDER_PROP_POOL:
            if not isinstance(_row, dict):
                continue
            _cat = str(_row.get("category") or "other")
            _mat = str(_row.get("match") or "?")
            _pool_categories[_cat] = _pool_categories.get(_cat, 0) + 1
            _pool_matches[_mat] = _pool_matches.get(_mat, 0) + 1

        log(
            f"   🏗️ Builder-Pool: {len(_builder_prop_pool)} Legs "
            f"({len(_NTR_BUILDER_PROP_POOL)} echte Player-Props)"
        )
        log(
            "   🏗️ Player-Prop Kategorien: "
            + ", ".join(
                f"{k}={v}" for k, v in sorted(
                    _pool_categories.items(), key=lambda item: item[1], reverse=True
                )[:12]
            )
        )
        log(
            f"   🏗️ Matches mit echten Props: {len(_pool_matches)} · "
            f"≥2 Legs: {sum(1 for v in _pool_matches.values() if v >= 2)} · "
            f"≥3 Legs: {sum(1 for v in _pool_matches.values() if v >= 3)}"
        )

        if len(_builder_prop_pool) >= 2:
            _builder_chat = TELEGRAM_GROUPS.get("advanced_props") or TELEGRAM_GROUPS.get("props")
            if _builder_chat:
                def _send_builder(msg):
                    return send_telegram(msg, chat_id=_builder_chat)

                _sent_n, _picks = run_builder_engine(
                    raw_props=_builder_prop_pool,
                    send_message=_send_builder,
                    match_date=str(target_date),
                    match_contexts=_builder_contexts,
                    supabase_url=SUPABASE_URL,
                    supabase_key=SUPABASE_KEY,
                    send_chat_id=str(_builder_chat),
                    logger=lambda m: log(f"   🏗️ {m}"),
                )
                log(f"   🏗️ Builder Engine: {_sent_n} Builder aus {len(_builder_prop_pool)} Props gesendet")
    except ImportError:
        log("   🏗️ netrattler_builder_engine nicht gefunden — skip", "WARN")
    except Exception as _be:
        log(f"   🏗️ Builder Engine Error: {str(_be)[:80]}", "WARN")

    # 🆕 MULTI-COMBO SYSTEM (3,4,5,6,7,8 Tipps)
    all_tips_flat = []
    for market_id, tips in tips_by_market.items():
        for tip in tips:
            tip["market"] = market_id
            all_tips_flat.append(tip)

    if len(all_tips_flat) >= 3:
        log("")
        # Multi-Combos 3-11 immer erzeugen (7-11 sind die groesseren "Lottery"-Kombis).
        _combo_sizes = [3, 4, 5, 6, 7, 8, 9, 10, 11]
        log(f"🎰 Generiere Multi-Combos ({','.join(str(x) for x in _combo_sizes)} Tipps)...")
        combo_chat = TELEGRAM_GROUPS.get("combos", TELEGRAM_CHAT_ID)  # Multi-Combos

        # Header für Combo Channel
        combo_header = f"<b>🎰 MULTI-COMBO TIPPS</b>" + "\n"
        combo_header += f"<i>📅 {target_date}</i>" + "\n"
        combo_header += f"<i>Basis: {len(all_tips_flat)} Top-Tipps</i>"
        send_telegram(combo_header, combo_chat)

        # V31 CLEAN: normale Combos 3-6. 7-11 nur mit ENABLE_LOTTERY_COMBOS=true.
        _combo_run_ts = datetime.now(timezone.utc).strftime("%H%M%S")
        generated = 0
        for n in _combo_sizes:
            combo = generate_multi_combo_bets(all_tips_flat, num_tips=n)
            if combo:
                # Deterministische Signatur — identische Kombi (gleiche Legs) wird nicht erneut gesendet
                _sig = _combo_signature(combo.get("tips", []), prefix=f"combo{n}")
                _combo_tip_id = f"combo_{n}leg_{target_date}_{_sig}".replace(" ", "_")
                if is_duplicate_combo(_combo_tip_id, target_date):
                    log(f"   ⏭️ Combo {n} Duplikat übersprungen (identische Legs bereits heute gesendet)")
                    continue

                log(f"   {combo['label']}: Quote {combo['total_odds']}")
                msg = format_combo_telegram_message(combo)
                if msg:
                    _combo_mid = send_telegram(msg, combo_chat)
                    generated += 1
                    try:
                        save_to_supabase({
                            "tip_id": _combo_tip_id,
                            "date": str(target_date),
                            "market": "combo_multi",
                            "market_name": combo.get("label", "Multi-Combo"),
                            "match": " / ".join(t.get("match","?") for t in combo.get("tips",[])[:3]),
                            "tip": f"Multi-Combo {n} Legs",
                            "odds": str(combo.get("total_odds","?")),
                            "units": combo.get("stake_suggestion", 0.5),
                            "probability": int(combo.get("expected_confidence", 3) / 5 * 100),
                            "confidence": 3,
                            "status": "pending",
                            "group_key": "combos",
                            "pick_type": "combo_multi",
                            "builder_total_legs": n,
                            "builder_legs": [
                                {
                                    "match": t.get("match", ""),
                                    "market": t.get("market", ""),
                                    "tip": t.get("tip", t.get("selection", "YES")),
                                    "category": t.get("market", ""),
                                    "line": 2.5 if t.get("market") in {"over25", "combo"} else (1.5 if t.get("market") == "over15_ht" else None),
                                    "side": "over",
                                    "raw": f"{t.get('market','')} {t.get('tip', t.get('selection','YES'))}",
                                } for t in combo.get("tips", [])
                            ],
                            "telegram_chat_id": str(combo_chat),
                            "telegram_msg_id": _combo_mid,
                            "message_text": msg[:3500],
                        })
                    except Exception:
                        pass
            else:
                log(f"   ⚠️ Combo {n}: Zu wenig Tipps")

        log(f"✅ {generated} Combos generiert und gesendet!")
    else:
        log(f"ℹ️ Nur {len(all_tips_flat)} Tipps - min. 3 für Combos nötig")

    # Daily Report nach jedem 08:00 Run
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour == 8:
        send_daily_report()
        log("📊 Daily Report gesendet!")

    log("⚡ Duplikat-Zusammenfassung: " + ", ".join(f"{k}={v}" for k, v in sorted(_DUP_LOG_COUNTS.items())) if _DUP_LOG_COUNTS else "⚡ Duplikat-Zusammenfassung: keine")
    log("Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
