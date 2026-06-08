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
    "over15_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),  # Gleiche Gruppe wie BTTS HT
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
    "hz_live": env("TELEGRAM_GROUP_HZ_LIVE", TELEGRAM_CHAT_ID),
    "late_goals": env("TELEGRAM_GROUP_LATE_GOALS", TELEGRAM_CHAT_ID),
    "advanced_props": env("TELEGRAM_GROUP_ADVANCED_PROPS", env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID)),  # Fallback auf STATS Gruppe
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


# ============================================================
# 🗄️ SUPABASE DAILY CACHE — Fixtures, Stats, Odds
# Spart API Calls: Run 1 scrapt, Run 2+3 lesen aus Supabase
# ============================================================

def cache_get(cache_key: str, target_date) -> dict | None:
    """Holt gecachte Daten aus Supabase daily_cache Tabelle."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/daily_cache",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "cache_date": f"eq.{target_date}",
                "cache_key": f"eq.{cache_key}",
                "select": "data",
                "limit": "1",
            },
            timeout=8,
        )
        if r.ok and r.json():
            return r.json()[0].get("data")
    except Exception:
        pass
    return None


def cache_set(cache_key: str, target_date, data: dict) -> bool:
    """Speichert Daten in Supabase daily_cache (upsert)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        import json as _cj
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/daily_cache",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json={
                "cache_date": str(target_date),
                "cache_key": cache_key,
                "data": data,
            },
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def cache_get_fixtures(target_date) -> dict | None:
    """Holt gecachte Fixtures für heute (alle Ligen)."""
    cached = cache_get("fixtures_all", target_date)
    if cached:
        log(f"   🗄️ Fixtures aus Supabase Cache geladen ({sum(len(v) for v in cached.values())} Spiele)")
    return cached


def cache_set_fixtures(target_date, fixtures_by_league: dict) -> bool:
    """Speichert alle heutigen Fixtures in Supabase."""
    if not fixtures_by_league:
        return False
    # Nur nicht-leere Ligen speichern
    to_save = {lg: fixes for lg, fixes in fixtures_by_league.items() if fixes}
    if not to_save:
        return False
    result = cache_set("fixtures_all", target_date, to_save)
    if result:
        total = sum(len(v) for v in to_save.values())
        log(f"   🗄️ {total} Spiele in {len(to_save)} Ligen in Supabase gecacht")
    return result


def cache_get_player_stats(league_name: str, target_date) -> dict | None:
    """Holt gecachte FBref Player Stats."""
    return cache_get(f"fbref_{league_name.replace(' ', '_')}", target_date)


def cache_set_player_stats(league_name: str, target_date, stats: dict) -> bool:
    """Speichert FBref Player Stats in Supabase."""
    if not stats:
        return False
    return cache_set(f"fbref_{league_name.replace(' ', '_')}", target_date, stats)


def cache_get_odds(league_name: str, target_date) -> list | None:
    """Holt gecachte Odds API Daten."""
    cached = cache_get(f"odds_{league_name.replace(' ', '_')}", target_date)
    return cached.get("odds") if cached else None


def cache_set_odds(league_name: str, target_date, odds: list) -> bool:
    """Speichert Odds in Supabase."""
    if not odds:
        return False
    return cache_set(f"odds_{league_name.replace(' ', '_')}", target_date, {"odds": odds})


MIN_PROBABILITY = int(env("MIN_PROBABILITY", "67"))  # 🆕 Hybrid: 67% (zwischen 65-69)
MIN_ODDS = float(env("MIN_ODDS", "1.65"))
MAX_ODDS = float(env("MAX_ODDS", "3.0"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))
# 🆕 Nur HIGH + OK Value (LOW fliegt raus)
MIN_VALUE_RATING = env("MIN_VALUE_RATING", "OK")  # HIGH, OK, oder LOW

MARKETS_TO_RUN = ["btts", "over25", "combo", "btts_ht", "over15_ht"]

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
    # ── Österreich komplett ──
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
    # ── Deutschland Regional komplett ──
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
    "Germany Verbandsliga Bayern",
    "Germany Bayernliga Nord",
    "Germany Bayernliga Süd",
    "DFB Pokal",
    "Germany Frauen Bundesliga",
    "Germany 2. Frauen Bundesliga",
    # ── Schweiz komplett ──
    "Switzerland Promotion League",
    "Switzerland 1. Liga Classic",
    "Switzerland 1. Liga",
    "Switzerland Frauen Super League",
    "Switzerland Cup",
    # ── Frankreich Regional ──
    "France National",
    "France National 2",
    "France National 3",
    "France Coupe de France",
    "France Frauen Division 1",
    # ── Spanien Regional ──
    "Spain Primera Federación",
    "Spain Segunda Federación",
    "Spain Tercera Federación",
    "Copa del Rey",
    "Spain Frauen Primera División",
    # ── Italien Regional ──
    "Italy Serie D",
    "Italy Coppa Italia",
    "Italy Frauen Serie A",
    # ── England Regional ──
    "England National League North",
    "England National League South",
    "England FA Cup",
    "England EFL Trophy",
    "England Premier League Women",
    "England Championship Women",
    # ── Niederlande ──
    "Netherlands Keuken Kampioen Divisie",
    "Netherlands Eerste Divisie",
    "Netherlands 3. Divisie",
    "Netherlands KNVB Beker",
    # ── Belgien ──
    "Belgium First Amateur",
    "Belgium Cup",
    # ── Portugal ──
    "Portugal Liga 3",
    "Portugal Campeonato de Portugal",
    "Portugal Taça de Portugal",
    # ── Griechenland ──
    "Greece Super League 2",
    "Greece Football League",
    "Greece Cup",
    # ── Türkei ──
    "Turkey 2. Lig",
    "Turkey 3. Lig",
    "Turkey Cup",
    # ── Russland ──
    "Russia FNL2 Division B Group 4",
    "Russia FNL2 Division B Group 5",
    "Russia FNL2 Division B Group 6",
    "Russia FNL2 Division B Group 7",
    "Russia FNL2 Division B Group 8",
    "Russia Cup",
    # ── Ukraine ──
    "Ukraine First League",
    "Ukraine Second League",
    # ── Polen ──
    "Poland III Liga Group 1",
    "Poland III Liga Group 2",
    "Poland III Liga Group 3",
    "Poland III Liga Group 4",
    "Poland Cup",
    # ── Tschechien ──
    "Czech Cup",
    # ── Rumänien ──
    "Romania Liga 4",
    "Romania Cup",
    # ── Ungarn ──
    "Hungary NB III",
    "Hungary Cup",
    # ── Skandinavien ──
    "Sweden Division 2 Norra",
    "Sweden Division 2 Södra",
    "Norway Division 2 Group 1",
    "Norway Division 2 Group 2",
    "Denmark 3. Division",
    "Finland Kolmonen",
    "Finland Cup",
    "Iceland Cup",
    # ── Baltikum ──
    "Latvia First League",
    "Lithuania Division 1",
    "Estonia Esiliiga",
    # ── Südosteuropa ──
    "Romania Liga IV",
    "Bulgaria Third League",
    "Serbia Srpska Liga South",
    "Croatia Cup",
    "Bosnia Cup",
    "Albania First Division",
    "North Macedonia Cup",
    "Kosovo First League",
    "Moldova Second Division",


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
    # ── Tschechien Regional (aktiv während Europa-Pause) ──
    "Czech 3. CFL Group A",
    "Czech 3. CFL Group B",
    "Czech 3. MSFL",
    "Czech 4. Liga Group A",
    "Czech 4. Liga Group B",
    "Czech 4. Liga Group C",
    "Czech 4. Liga Group D",
    "Czech 4. Liga Group E",
    "Czech 4. Liga Group F",
    "Czech Jihocesky KP",
    "Czech Jihomoravsky KP",
    "Czech Karlovarsky KP",
    "Czech Kralovehradecky KP",
    "Czech Liberecky KP",
    "Czech Moravskoslezsky KP",
    "Czech Olomoucky KP",
    "Czech Pardubicky KP",
    "Czech Plzensky KP",
    "Czech Prazsky Prebor",
    "Czech Stredocesky KP",
    "Czech Ustecky KP",
    "Czech Vysocina KP",
    # ── China (aktiv während Europa-Pause) ──
    "China League Two",
    "China League Three",
    "China FA Cup",
    # ── Australien (früh morgens aktiv) ──
    "Australia NPL Queensland",
    "Australia NPL Victoria",
    "Australia NPL NSW",
    "Australia NPL South Australia",
    "Australia NPL Western Australia",
    "Australia NPL Capital Territory",
    "Australia NPL Northern NSW",
    "Australia NPL Tasmania",
    "Australia FFA Cup",
    "Australia Capital Football",
    "Australia Queensland NPL2",
    "Australia Victoria NPL2",
    # ── Weitere aktive Ligen während Pausen ──
    "Slovakia 2. Liga",
    "Slovakia 3. Liga",
    "Poland I Liga",
    "Poland II Liga",
    "Romania Liga II",
    "Romania Liga III",
    "Hungary NB II",
    "Bulgaria First League",
    "Bulgaria Second League",
    "Serbia First League",
    "Croatia 2. HNL",
    "Slovenia 2. SNL",
    "Bosnia 2. Liga",
    "Greece Football League",
    "Greece Gamma Ethniki",
    "Cyprus First Division",
    "Cyprus Second Division",
    "Israel National League",
    "Finland Ykkönen",
    "Sweden Division 1",
    "Norway Division 1",
    "Denmark 2. Division",
    "Iceland 2. Deild",
    "Latvia First League",
    "Lithuania A Lyga 2",
    "Estonia Meistriliiga",
    "Belarus First League",
    "Ukraine First League",
    "Russia First League",
    "Russia Second League",

    # ── Europa Youth/Cups ──
    "Euro U19 Qualification League A",
    "Euro U19 Qualification League B",
    "Europe Baltic Cup",
    "Europe Premier League Crimea",
    # ── Finnland ──
    "Finland Ykkosliiga",
    "Finland Ykkönen",
    # ── Island ──
    "Iceland Division 1",
    "Iceland Division 2",
    # ── Norwegen Regional ──
    "Norway Division 3 Group 1",
    "Norway Division 3 Group 6",
    # ── Paraguay ──
    "Paraguay Division Intermedia",
    # ── Polen Play-Offs ──
    "Poland Division 2 Promotion Play-Offs",
    "Poland Division 2 Relegation Play-Offs",
    # ── Rumänien ──
    "Romania Liga 3 Promotion Play-Offs",
    # ── Russland FNL2 ──
    "Russia FNL2 Division A Silver",
    "Russia FNL2 Division B Group 1",
    "Russia FNL2 Division B Group 2",
    "Russia FNL2 Division B Group 3",
    # ── Serbien Regional ──
    "Serbia Srpska Liga Belgrade",
    "Serbia Srpska Liga Vojvodina",
    "Serbia Srpska Liga East",
    "Serbia Srpska Liga West",
    # ── Japan Frauen ──
    "Japan L1 League Women",
    "Japan L2 League Women",
    # ── Afrika Frauen + Cups ──
    "Cameroon Liga Women",
    "Nigeria FA Cup",
    "South Africa Premier Play-Offs",
    # ── Myanmar Youth ──
    "Myanmar U20 League",
    # ── Südkorea alle ──
    "K3 League",
    "K4 League",
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
    # ══ UEFA Cups ══
    "Champions League": 2, "Europa League": 3, "Conference League": 848,
    "UEFA Nations League": 5, "UEFA Youth League": 14,
    # ══ Deutschland ══
    "Bundesliga": 78, "2. Bundesliga": 79, "3. Liga Deutschland": 82,
    "DFB Pokal": 81, "Bundesliga Reserve": 80,
    "German Regionalliga Bayern": 83, "German Regionalliga Nord": 84,
    "German Regionalliga Nordost": 85, "German Regionalliga West": 86,
    "German Regionalliga Südwest": 87,
    # ══ England ══
    "Premier League": 39, "Championship": 40, "EFL League 1": 41,
    "EFL League 2": 42, "National League": 43, "FA Cup": 45,
    "EFL Cup": 48, "Premier League 2": 46, "Premier League U18": 47,
    # ══ Spanien ══
    "La Liga": 140, "La Liga 2": 141, "Copa del Rey": 143,
    "LaLiga Youth": 142,
    # ══ Italien ══
    "Serie A": 135, "Serie B": 136, "Serie C": 137,
    "Coppa Italia": 139, "Serie A Primavera": 138,
    # ══ Frankreich ══
    "Ligue 1": 61, "Ligue 2": 62, "Ligue National": 63,
    "Coupe de France": 66,
    # ══ Niederlande ══
    "Eredivisie": 88, "Eerste Divisie": 89,
    # ══ Portugal ══
    "Primeira Liga": 94, "Segunda Liga": 95, "Taca de Portugal": 96,
    # ══ Belgien ══
    "Pro League Belgien": 144, "Belgium Challenger": 296,
    # ══ Türkei ══
    "Süper Lig": 203, "Turkish 1. Lig": 200, "Turkish 2. Lig": 201,
    # ══ Österreich ══
    "Bundesliga Österreich": 218, "Austria 2. Liga": 293,
    "Austrian Regional Liga": 219,
    # ══ Schweiz ══
    "Super League Schweiz": 207, "Swiss Challenge League": 265,
    # ══ Schottland ══
    "Scottish Premiership": 179, "Scottish Championship": 181,
    "Scottish League One": 182, "Scottish League Two": 183,
    # ══ Dänemark ══
    "Danish Superliga": 119, "Danish 1. Division": 120,
    "Danish 2. Division": 121,
    # ══ Norwegen ══
    "Norway Eliteserien": 103, "Norwegian 1. Division": 104,
    "Norway Division 1": 104, "Norway Division 3 Group 1": 1055,
    # ══ Schweden ══
    "Sweden Allsvenskan": 113, "Swedish Superettan": 114,
    "Swedish Division 1": 115,
    # ══ Finnland ══
    "Finland Veikkausliiga": 244, "Finland Ykkosliiga": 245,
    "Finland Ykkönen": 245,
    # ══ Island ══
    "Iceland Premier": 271, "Iceland 1. Deild": 272,
    "Iceland Division 1": 272, "Iceland Division 2": 1118,
    # ══ Griechenland ══
    "Greece Super League": 197, "Greece Football League": 198,
    "Greece Gamma Ethniki": 199,
    # ══ Kroatien ══
    "Croatia HNL": 210, "Croatia 2. HNL": 211,
    # ══ Serbien ══
    "Serbia SuperLiga": 286, "Serbia First League": 287,
    "Serbia Srpska Liga Belgrade": 1350, "Serbia Srpska Liga Vojvodina": 1351,
    "Serbia Srpska Liga East": 1352, "Serbia Srpska Liga West": 1353,
    # ══ Rumänien ══
    "Romania Liga I": 283, "Romania Liga II": 284, "Romania Liga III": 285,
    "Romania Liga 3 Promotion Play-Offs": 285,
    # ══ Tschechien ══
    "Czech First League": 345, "Czech 2. Liga": 346,
    "Czech 3. CFL Group A": 347, "Czech 3. CFL Group B": 347,
    "Czech 3. MSFL": 349,
    # ══ Polen ══
    "Poland Ekstraklasa": 106, "Poland I Liga": 107, "Poland II Liga": 108,
    "Poland Division 2 Promotion Play-Offs": 107,
    # ══ Slowakei ══
    "Slovak Super Liga": 332, "Slovakia 2. Liga": 333,
    # ══ Ungarn ══
    "Hungarian NB I": 325, "Hungary NB II": 326,
    # ══ Bulgarien ══
    "Bulgarian First": 348, "Bulgaria Second League": 349,
    # ══ Israel ══
    "Israeli Premier": 288, "Israeli Liga Leumit": 289,
    # ══ Ukraine ══
    "Ukrainian Premier": 333,
    # ══ Russland ══
    "Russian Premier": 235, "Russia First League": 236,
    "Russia Second League": 237, "Russia FNL2 Division A Silver": 238,
    "Russia FNL2 Division B Group 1": 239,
    # ══ Belarus ══
    "Belarus Premier": 116,
    # ══ Baltikum ══
    "Latvian Higher League": 180, "Lithuanian A Lyga": 186,
    "Estonian Premium": 117,
    # ══ Kasachstan ══
    "Kazakh Premier": 121, "Kazakhstan Premier League": 121,
    # ══ Kaukasus ══
    "Georgia Erovnuli Liga": 189, "Armenia Premier League": 191,
    "Azerbaijan Premier League": 195,
    # ══ Balkan ══
    "Slovenia Prva Liga": 212, "Bosnia Premier League": 213,
    "North Macedonia First League": 215, "Kosovo Superliga": 219,
    "Montenegro First League": 217, "Albania Superliga": 220,
    # ══ Kleine EU ══
    "Cyprus First Division": 278, "Malta Premier League": 303,
    "Luxembourg BGL Ligue": 316, "Faroe Islands Premier League": 270,
    "Northern Ireland Premiership": 183,
    "Republic of Ireland Premier Division": 357,
    "Wales Premier League": 361,
    # ══ MLS / Nordamerika ══
    "MLS": 253, "USL Championship": 255, "Canada Premier League": 256,
    "USL League One": 257, "CONCACAF Champions": 37,
    "CONCACAF Nations League": 38, "Gold Cup": 40,
    "Costa Rica Primera": 321, "Guatemala Liga": 327,
    "Honduras Liga": 329, "Liga MX": 262, "Liga MX Expansion": 263,
    "Panama LPF": 330,
    # ══ Südamerika ══
    "Brasileirao Serie A": 71, "Brasileirao Serie B": 72,
    "Brazil Serie C": 75, "Brazil Serie D": 76,
    "Liga Argentinien": 128, "Argentina Primera B": 130,
    "Copa Argentina": 131, "Campeonato Paulista": 73,
    "Campeonato Carioca": 74, "Copa Libertadores": 13,
    "Copa Sudamericana": 11, "Recopa Sudamericana": 12,
    "Chile Primera": 265, "Chile Primera B": 266,
    "Colombia Primera": 239, "Colombia Primera B": 240,
    "Ecuador Serie A": 256, "Peru Primera": 281,
    "Venezuela Primera": 293, "Bolivia Division Profesional": 236,
    "Paraguay Division": 260, "Paraguay Division Intermedia": 261,
    "Uruguay Primera": 268,
    # ══ Saudi / Naher Osten ══
    "Saudi Pro League": 307, "Saudi Division 1": 308,
    "Qatar Stars League": 304, "UAE Pro League": 299,
    "UAE Division 1": 300, "Kuwait Premier League": 285,
    "Bahrain Premier League": 276, "Jordan Pro League": 286,
    "Iraq Premier League": 290, "Oman Professional League": 303,
    # ══ Afrika ══
    "Egypt Premier": 233, "Morocco Botola": 200, "Morocco Botola 2": 201,
    "Tunisia Ligue 1": 202, "Algeria Ligue 1": 197, "Algeria Ligue 2": 198,
    "Nigeria Premier": 206, "Ghana Premier League": 208,
    "South Africa PSL": 288, "Kenya Premier": 357,
    "CAF Champions League": 20, "CAF Confederation Cup": 21,
    # ══ Asien ══
    "J1 League Japan": 98, "J2 League Japan": 99, "J3 League Japan": 100,
    "K League 1": 292, "K League 2": 293, "K3 League": 294,
    "China Super League": 169, "China League 1": 170,
    "India Super League": 323, "India I-League": 324,
    "Vietnam V-League": 340, "Thailand League 1": 296,
    "Malaysia Super League": 302, "Indonesia Liga 1": 310,
    "Singapore Premier League": 306,
    "Iran Pro League": 290, "ACL Elite": 17,
    "A-League Australia": 188, "Australia NPL NSW": 513,
    "Australia NPL Victoria": 514, "Australia NPL Queensland": 515,
    "New Zealand NZFC": 270,
    # ══ International ══
    "WM 2026": 1, "WM 2026 Qualifikation Europa": 32,
    "WM 2026 Qualifikation Südamerika": 9,
    "WM 2026 Qualifikation Asien": 30,
    "WM 2026 Qualifikation Afrika": 29,
    "WM 2026 Qualifikation CONCACAF": 31,
    "Copa America": 7, "Afrika Cup": 6,
    "Freundschaftsspiele International": 10,
    "Euro U19 Qualification League A": 39,
    "Europe Baltic Cup": 192,
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

    # ═══ EUROPA KOMPLETT ═══
    # Deutschland
    "German Regionalliga Bayern": 90,
    "German Regionalliga Nord": 91,
    "German Regionalliga Nordost": 92,
    "German Regionalliga West": 93,
    "German Regionalliga Südwest": 94,
    # Österreich
    "Austrian Regional Liga": 221,
    "Austria Regionalliga Mitte": 222,
    "Austria Regionalliga Ost": 223,
    "Austria Regionalliga Salzburg": 224,
    "Austria Regionalliga Tirol": 225,
    "Austria Regionalliga West": 226,
    "ÖFB Cup": 552,
    # ── Deutschland Regional ──
    "Germany Oberliga Baden-Württemberg": 96,
    "Germany Oberliga Hessen": 97,
    "Germany Oberliga Niedersachsen": 98,
    "Germany Oberliga Nordost Nord": 99,
    "Germany Oberliga Nordost Süd": 100,
    "Germany Oberliga Rheinland-Pfalz/Saar": 101,
    "Germany Oberliga Westfalen": 102,
    "Germany Oberliga NOFV Nord": 103,
    "Germany Oberliga NOFV Süd": 104,
    "Germany 2. Frauen Bundesliga": 846,
    # ── Frankreich ──
    "France Frauen Division 1": 846,
    # ── Spanien ──
    "Spain Tercera Federación": 544,
    # ── Russland ──
    "Russia FNL2 Division B Group 4": 237,
    "Russia FNL2 Division B Group 5": 237,
    "Russia FNL2 Division B Group 6": 237,
    "Russia FNL2 Division B Group 7": 237,
    "Russia FNL2 Division B Group 8": 237,
    "Russia Cup": 560,
    # ── Ukraine ──
    "Ukraine Second League": 335,
    # ── Polen ──
    "Poland III Liga Group 1": 109,
    "Poland III Liga Group 2": 109,
    "Poland III Liga Group 3": 109,
    "Poland III Liga Group 4": 109,
    # ── Tschechien ──
    "Czech Cup": 553,
    # ── Rumänien ──
    "Romania Liga 4": 286,
    "Romania Cup": 561,
    "Romania Liga IV": 286,
    # ── Bulgarien ──
    "Bulgaria Third League": 350,
    # ── Serbien ──
    "Serbia Srpska Liga South": 288,
    "Serbia Srpska Liga West": 289,
    # ── Albanien ──
    "Albania First Division": 388,
    # ── Kosovo ──
    "Kosovo First League": 542,
    # ── Moldova ──
    "Moldova Second Division": 520,
    # ── Estland ──
    "Estonia Esiliiga": 331,
    # ── Lettland ──
    "Latvia First League": 347,
    # ── Litauen ──
    "Lithuania Division 1": 370,
    # ── Schweden ──
    "Sweden Division 2 Norra": 116,
    "Sweden Division 2 Södra": 117,
    # ── Norwegen ──
    "Norway Division 2 Group 1": 105,
    "Norway Division 2 Group 2": 105,
    # ── Dänemark ──
    "Denmark 3. Division": 121,
    # ── Finnland ──
    "Finland Kolmonen": 246,
    # ── Island ──
    "Iceland Cup": 1120,
    # ── Niederlande ──
    "Netherlands Eerste Divisie": 89,
    # ── Belgien ──
    "Belgium First Amateur": 297,
    # ── Griechenland ──
    "Greece Football League": 199,
    "Greece Gamma Ethniki": 549,
    # ── Ungarn ──
    "Hungary NB III": 326,
    # ── Kroatien ──
    "Croatia Cup": 538,
    # ── Bosnien ──
    "Bosnia Cup": 562,
    # ── England ──
    "England Premier League Women": 848,
    "England Championship Women": 849,
    "England EFL Trophy": 47,
    # ── Australien ──
    "Australia NPL NSW": 513,
    "Australia NPL Victoria": 514,
    "Australia NPL Queensland": 515,
    "Australia NPL South Australia": 516,
    "Australia NPL Western Australia": 517,
    "Australia FFA Cup": 185,
    # ── Asien weitere ──
    "China League Two": 171,
    "China FA Cup": 549,
    "India I-League 2": 325,
    "Indonesia Liga 2": 275,
    "Vietnam V-League 2": 341,
    "Thailand Division 1": 297,
    "Uzbekistan Division 1": 438,
    "Lebanon Division 2": 460,
    "Saudi Division 1": 308,
    "UAE Division 1": 436,
    # ── Afrika weitere ──
    "Botswana Premier League": 469,
    "Burkina Faso Premier League": 470,
    "Guinea Ligue Professionnelle": 473,
    "Ivory Coast Ligue 1": 399,
    "Malawi Super League": 474,
    "Mali Premiere Division": 475,
    "Mauritania Ligue 1": 476,
    "Namibia Premier League": 477,
    "Rwanda Premier League": 515,
    "Sierra Leone Premier League": 518,
    "Togo Championnat National": 524,
    # ── Americas weitere ──
    "Campeonato Paulista": 73,
    "Campeonato Carioca": 74,
    "Campeonato Mineiro": 476,
    "Copa Argentina": 130,
    "Ecuador Liga Pro 2": 259,
    "Peru Liga 2": 281,
    "Venezuela Segunda Division": 274,
    "Paraguay Division Intermedia": 242,
    "Bolivia Division Profesional": 232,
    "Costa Rica Segunda": 315,
    "El Salvador Primera Division": 318,
    "Panama LPF": 344,
    "Jamaica Premier League": 428,
    "Trinidad and Tobago Pro League": 346,
    "Haiti Ligue Haïtienne": 351,
    "Nicaragua Primera Division": 352,
    "Dominican Republic LDF": 353,
    "Canada Premier League": 256,
    "USL League One": 255,
    "USL League Two": 257,
    # ── Internationale Cups weitere ──
    "COSAFA Cup": 721,
    "CECAFA Cup": 722,
    "Pacific Games Football": 723,
    "Gold Cup": 10,
    "Euro U19 Qualification League A": 849,
    "Euro U19 Qualification League B": 849,
    "Europe Baltic Cup": 850,
    "CONCACAF Nations League": 875,

    # Deutschland Regional
    "DFB Pokal": 529,
    "Germany Frauen Bundesliga": 845,
    "Germany Oberliga Bayern": 95,
    "Germany Bayernliga Nord": 95,
    "Germany Bayernliga Süd": 95,
    # Schweiz
    "Switzerland Promotion League": 266,
    "Switzerland 1. Liga Classic": 267,
    "Switzerland Cup": 554,
    # Frankreich
    "France National": 63,
    "France National 2": 64,
    "France National 3": 65,
    "France Coupe de France": 558,
    # Spanien
    "Spain Primera Federación": 142,
    "Spain Segunda Federación": 143,
    "Copa del Rey": 556,
    # Italien
    "Italy Serie D": 138,
    "Italy Coppa Italia": 557,
    # England
    "England National League North": 44,
    "England National League South": 45,
    "England FA Cup": 534,
    # Niederlande
    "Netherlands Keuken Kampioen Divisie": 89,
    "Netherlands 3. Divisie": 90,
    "Netherlands KNVB Beker": 545,
    # Belgien
    "Belgium Cup": 549,
    # Portugal
    "Portugal Liga 3": 95,
    "Portugal Taça de Portugal": 555,
    # Griechenland
    "Greece Super League 2": 198,
    "Greece Cup": 536,
    # Türkei
    "Turkey 2. Lig": 203,
    "Turkey 3. Lig": 204,
    "Turkey Cup": 559,
    # Polen
    "Poland Cup": 1065,
    # Ungarn
    "Hungary NB III": 326,
    "Hungary Cup": 537,
    # Skandinavien
    "Sweden Division 2 Norra": 116,
    "Sweden Division 2 Södra": 117,
    "Norway Division 2 Group 1": 105,
    "Denmark 3. Division": 121,
    "Finland Cup": 540,
    # Baltikum
    "Estonia Esiliiga": 331,
    "Lithuania Division 1": 370,

    # Schweiz
    "Swiss Challenge League": 265,
    # UK
    "National League": 43,
    "Northern Ireland Premiership": 415,
    "Republic of Ireland Premier Division": 357,
    "Republic of Ireland First Division": 358,
    "Wales Premier League": 410,
    # Skandinavien
    "Finland Ykkosliiga": 244,
    "Finland Ykkönen": 245,
    "Iceland Division 1": 272,
    "Iceland Division 2": 1118,
    "Norway Division 1": 104,
    "Norway Division 3 Group 1": 1055,
    "Sweden Division 1": 115,
    # Osteuropa
    "Czech 3. CFL Group A": 347,
    "Czech 3. CFL Group B": 347,
    "Czech 3. MSFL": 349,
    "Slovakia 2. Liga": 333,
    "Hungary NB II": 329,
    "Poland I Liga": 107,
    "Poland II Liga": 108,
    "Romania Liga II": 284,
    "Romania Liga III": 285,
    "Bulgaria Second League": 349,
    "Serbia First League": 287,
    "Croatia 2. HNL": 211,
    "Slovenia Prva Liga": 336,
    "Slovenia 2. SNL": 337,
    "Bosnia Premier League": 308,
    "Bosnia 2. Liga": 309,
    "North Macedonia First League": 385,
    "Albania Superliga": 387,
    "Kosovo Superliga": 541,
    "Montenegro First League": 556,
    "Moldova National Division": 519,
    "Armenia Premier League": 382,
    "Azerbaijan Premier League": 373,
    "Georgia Erovnuli Liga": 526,
    "Cyprus First Division": 337,
    "Malta Premier League": 482,
    "Luxembourg BGL Ligue": 444,
    "Gibraltar National League": 555,
    "Faroe Islands Premier League": 546,
    "Latvia Higher League": 347,
    "Lithuania A Lyga": 369,
    "Estonia Meistriliiga": 330,
    "Belarus Premier League": 370,
    "Belarus First League": 371,
    "Ukraine First League": 334,
    "Russia First League": 236,
    "Russia Second League": 237,
    "Russia FNL2 Division A Silver": 237,
    "Kazakh Premier": 360,
    "Uzbekistan Super League": 437,
    # ═══ AFRIKA KOMPLETT ═══
    "Egypt Premier": 233,
    "Morocco Botola": 200,
    "Morocco Botola 2": 547,
    "Tunisia Ligue 1": 201,
    "Algeria Ligue 1": 207,
    "Algeria Ligue 2": 208,
    "South Africa PSL": 288,
    "Ghana Premier League": 342,
    "Nigeria Premier": 332,
    "Kenya Premier": 374,
    "Tanzania Premier League": 523,
    "Uganda Premier League": 500,
    "Zimbabwe Premier Soccer League": 543,
    "Zambia Super League": 542,
    "Senegal Ligue 1": 517,
    "Ivory Coast Ligue 1": 399,
    "Cameroon Elite One": 385,
    "Ethiopia Premier League": 525,
    "Rwanda Premier League": 515,
    "Angola Girabola": 471,
    "Mozambique Mocambola": 472,
    "Libya Premier League": 470,
    "CAF Champions League": 12,
    "CAF Confederation Cup": 13,
    # ═══ ASIEN KOMPLETT ═══
    "J1 League Japan": 98,
    "J2 League Japan": 99,
    "J3 League Japan": 100,
    "K League 1": 292,
    "K League 2": 293,
    "K3 League": 294,
    "China Super League": 169,
    "China League 1": 170,
    "Saudi Pro League": 307,
    "Qatar Stars League": 267,
    "UAE Pro League": 435,
    "Kuwait Premier League": 479,
    "Bahrain Premier League": 462,
    "Oman Professional League": 503,
    "Iraq Premier League": 400,
    "Jordan Pro League": 459,
    "Iran Pro League": 290,
    "Kazakhstan Premier League": 360,
    "Uzbekistan Super League": 437,
    "India Super League": 323,
    "India I-League": 324,
    "Vietnam V-League": 340,
    "Thailand League 1": 296,
    "Malaysia Super League": 274,
    "Indonesia Liga 1": 274,
    "Singapore Premier League": 441,
    "Myanmar National League": 531,
    "Philippines United Football League": 551,
    "Hong Kong Premier League": 471,
    "AFC Champions League": 17,
    "ACL Elite": 17,
    # ═══ AMERICAS KOMPLETT ═══
    "MLS": 253,
    "USL Championship": 254,
    "Canada Premier League": 256,
    "USL League One": 255,
    "Brasileirao Serie A": 71,
    "Brasileirao Serie B": 72,
    "Brazil Serie C": 75,
    "Brazil Serie D": 76,
    "Liga Argentinien": 128,
    "Argentina Primera B": 131,
    "Uruguay Primera": 268,
    "Chile Primera": 265,
    "Colombia Primera": 239,
    "Colombia Primera B": 240,
    "Ecuador Serie A": 258,
    "Peru Primera": 280,
    "Venezuela Primera": 273,
    "Paraguay Division": 241,
    "Bolivia Division Profesional": 232,
    "Costa Rica Primera": 314,
    "Guatemala Liga": 343,
    "Honduras Liga": 345,
    "Mexico Liga MX": 262,
    "Mexico Expansion": 278,
    "Copa Libertadores": 11,
    "Copa Sudamericana": 13,
    "CONCACAF Champions": 16,
    # ═══ OZEANIEN ═══
    "A-League Australia": 188,
    "A-League Women": 189,
    "New Zealand NZFC": 415,
    # ═══ INTERNATIONALE CUPS ═══
    "WM 2026": 1,
    "UEFA Nations League": 5,
    "Copa America": 9,
    "Gold Cup": 10,
    "Afrika Cup": 6,
    "Arab Cup": 7,
    # ── Tschechien ──
    "Czech 3. CFL Group A": 347,
    "Czech 3. CFL Group B": 347,
    "Czech 3. MSFL": 349,
    "Czech 4. Liga Group A": 350,
    "Czech 4. Liga Group B": 350,
    # ── Island ──
    "Iceland Division 1": 272,
    "Iceland Division 2": 1118,
    # ── Norwegen ──
    "Norway Division 1": 104,
    "Norway Division 3 Group 1": 1055,
    # ── Polen ──
    "Poland I Liga": 107,
    "Poland II Liga": 108,
    # ── Rumänien ──
    "Romania Liga II": 284,
    "Romania Liga III": 285,
    # ── Finnland ──
    "Finland Ykkosliiga": 245,
    "Finland Ykkönen": 245,
    # ── Serbien ──
    "Serbia First League": 287,
    # ── Kroatien ──
    "Croatia 2. HNL": 211,
    # ── Bulgarien ──
    "Bulgaria Second League": 349,
    # ── Schweiz ──
    "Swiss Challenge League": 265,
    # ── Australien ──
    "A-League Australia": 188,
    "Australia NPL NSW": 513,
    "Australia NPL Victoria": 514,
    "Australia NPL Queensland": 515,
    # ── Russland ──
    "Russia First League": 236,
    "Russia FNL2 Division A Silver": 237,
    # ── Korea ──
    "K League 2": 293,
    "K3 League": 294,
    # ── Lateinamerika ──
    "Brazil Serie C": 75,
    "Brazil Serie D": 76,
    "Chile Primera B": 265,
    "Colombia Primera B": 240,
    "Paraguay Division Intermedia": 241,
    "Uruguay Primera": 268,
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
        "name": "⚡ Over 1.5 HT",
        "instr": "Analysiere Over 1.5 Tore in der 1. Halbzeit. Prüfe: xG erste Hälfte, Tore in HZ1 der letzten 10 Spiele, pressing-intensive Teams, frühe Führungstreffer Tendenz. Mindest-Wahrscheinlichkeit 67%.",
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

    cache_key = f"scout_{target_date}"  # Pro Tag cachen
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
            f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
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



def fetch_espn_all_today(target_date) -> dict:
    """
    ESPN All Soccer Scoreboard — holt ALLE Fussball Spiele weltweit an einem Tag.
    Kein Key nötig, funktioniert von GitHub Actions.
    Endpoint: site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard
    """
    try:
        date_str = str(target_date).replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=500"
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.espn.com/",
        }, timeout=20)
        
        if not r.ok:
            log(f"   ⚠️ ESPN All: HTTP {r.status_code}")
            return {}
        
        data = r.json()
        events = data.get("events", [])
        
        if not events:
            return {}
        
        result = {}
        for ev in events:
            try:
                competition = ev.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])
                if len(competitors) < 2:
                    continue
                
                home = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "home"), "")
                away = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "away"), "")
                
                if not home or not away:
                    continue
                
                # Liga aus ESPN
                league_raw = ev.get("league", {}).get("name", "")
                if not league_raw:
                    league_raw = ev.get("season", {}).get("slug", "Unknown")
                
                # Zeit
                start_time = ev.get("date", "")
                kickoff = "TBD"
                if start_time:
                    try:
                        from datetime import timezone as _tz_e
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        kickoff = dt.astimezone(_tz_e.utc).strftime("%H:%M")
                    except Exception:
                        pass
                
                fixture = {
                    "home": home,
                    "away": away,
                    "time": kickoff,
                    "time_local": kickoff,
                    "source": "espn_bulk",
                    "match_id": str(ev.get("id", "")),
                    "league": league_raw,
                }
                
                # ESPN Slug → Liga-Name Mapping
                # ESPN gibt Slugs wie "2026-brasileiro-serie-b" → mappe auf "Brasileirao Serie B"
                ESPN_SLUG_MAP = {
                    "2026-brasileiro-serie-b": "Brasileirao Serie B",
                    "2026-brasileiro-serie-a": "Brasileirao Serie A",
                    "2026-brasileiro-serie-c": "Brazil Serie C",
                    "2026-bolivian-liga-profesional": "Bolivia Division Profesional",
                    "2026-international-friendly": "Freundschaftsspiele International",
                    "2026-womens-international-friendly": "Freundschaftsspiele International",
                    "2026-argentine-primera-division": "Liga Argentinien",
                    "2026-primera-nacional": "Argentina Primera B",
                    "2026-torneo-federal-a": "Argentina Primera B",
                    "2026-uruguayan-primera-division": "Uruguay Primera",
                    "2026-chilean-primera-division": "Chile Primera",
                    "2026-colombian-primera-a": "Colombia Primera",
                    "2026-ecuadorian-liga-pro": "Ecuador Serie A",
                    "2026-peruvian-primera-division": "Peru Primera",
                    "2026-venezuelan-primera": "Venezuela Primera",
                    "2026-paraguayan-primera-division": "Paraguay Division",
                    "2026-mls": "MLS",
                    "2026-usl-championship": "USL Championship",
                    "2026-canadian-premier-league": "Canada Premier League",
                    "2026-liga-mx": "Liga Argentinien",
                    "group-stage": "WM 2026",
                    "round-of-32": "Copa Libertadores",
                    "regular-season": "MLS",
                    "apertura-final": "Liga Argentinien",
                    "torneo-intermedio": "Liga Argentinien",
                    "promotion-semifinals": "Argentina Primera B",
                }
                
                # Direkte Slug-Map prüfen
                league_slug = ev.get("league", {}).get("slug", "").lower()
                mapped_league = ESPN_SLUG_MAP.get(league_slug) or ESPN_SLUG_MAP.get(league_raw.lower())
                
                if not mapped_league:
                    # Fuzzy: ESPN Slug enthält oft Liga-Keywords
                    slug_clean = league_slug.replace("-", " ").replace("2026", "").strip()
                    for our_league in LEAGUES_TO_RUN:
                        our_words = set(w for w in our_league.lower().split() if len(w) > 4)
                        slug_words = set(w for w in slug_clean.split() if len(w) > 4)
                        if len(our_words & slug_words) >= 1 and our_words & slug_words:
                            mapped_league = our_league
                            break
                
                if not mapped_league:
                    mapped_league = league_raw  # Fallback
                
                league_key = mapped_league
                if league_key not in result:
                    result[league_key] = []
                result[league_key].append(fixture)
                
            except Exception:
                continue
        
        log(f"   ✅ ESPN All: {sum(len(v) for v in result.values())} Spiele in {len(result)} Ligen")
        return result
        
    except Exception as e:
        log(f"   ⚠️ ESPN All Fehler: {e}")
        return {}


def fetch_fotmob_all_today(target_date) -> dict:
    """
    FotMob All Matches Today — alle Spiele eines Tages.
    Sehr gute Daten inkl. xG, weniger aggressiv geblockt als SofaScore.
    """
    try:
        date_str = str(target_date).replace("-", "")
        url = f"https://www.fotmob.com/api/matches?date={date_str}"
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0",
            "Accept": "application/json",
            "Referer": "https://www.fotmob.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }, timeout=20)
        
        if not r.ok:
            log(f"   ⚠️ FotMob All: HTTP {r.status_code}")
            return {}
        
        data = r.json()
        leagues_data = data.get("leagues", [])
        
        if not leagues_data:
            return {}
        
        result = {}
        for league_data in leagues_data:
            league_raw = league_data.get("name", "")
            matches = league_data.get("matches", [])
            
            if not matches:
                continue
            
            # Liga mappen — mindestens 2 Wörter müssen übereinstimmen
            mapped_league = None
            raw_lower = league_raw.lower()
            raw_words = set(w for w in raw_lower.split() if len(w) > 3)
            
            for our_league in LEAGUES_TO_RUN:
                our_words = set(w for w in our_league.lower().split() if len(w) > 3)
                if len(raw_words & our_words) >= 2:
                    mapped_league = our_league
                    break
            
            league_key = mapped_league or league_raw
            
            for match in matches:
                try:
                    home = match.get("home", {}).get("name", "")
                    away = match.get("away", {}).get("name", "")
                    if not home or not away:
                        continue
                    
                    status = match.get("status", {})
                    kickoff = status.get("utcTime", "")
                    if kickoff:
                        try:
                            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                            kickoff = dt.strftime("%H:%M")
                        except Exception:
                            kickoff = "TBD"
                    
                    fixture = {
                        "home": home,
                        "away": away,
                        "time": kickoff,
                        "time_local": kickoff,
                        "source": "fotmob_bulk",
                        "match_id": str(match.get("id", "")),
                        "xg_home": match.get("xg", {}).get("home", 0),
                        "xg_away": match.get("xg", {}).get("away", 0),
                    }
                    
                    if league_key not in result:
                        result[league_key] = []
                    result[league_key].append(fixture)
                except Exception:
                    continue
        
        log(f"   ✅ FotMob All: {sum(len(v) for v in result.values())} Spiele in {len(result)} Ligen")
        return result
        
    except Exception as e:
        log(f"   ⚠️ FotMob All Fehler: {e}")
        return {}

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
                if status in ["inprogress", "finished"]