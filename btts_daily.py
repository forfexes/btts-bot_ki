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
API_FOOTBALL_KEY = env("API_FOOTBALL_KEY")

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

TELEGRAM_GROUPS = {
    "btts": env("TELEGRAM_GROUP_BTTS", TELEGRAM_CHAT_ID),
    "over25": env("TELEGRAM_GROUP_OVER25", TELEGRAM_CHAT_ID),
    "combo": env("TELEGRAM_GROUP_COMBO", TELEGRAM_CHAT_ID),
    "btts_ht": env("TELEGRAM_GROUP_BTTS_HT", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
}

SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "70"))
MIN_ODDS = float(env("MIN_ODDS", "1.65"))
MAX_ODDS = float(env("MAX_ODDS", "3.0"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "4"))

MARKETS_TO_RUN = ["btts", "over25", "combo", "btts_ht"]

# ============================================================
# AUTO LIGA SWITCH
# ============================================================
# Der Bot kann Ligen automatisch deaktivieren, wenn sie in Supabase schlecht laufen.
# Wichtig: Eine Liga wird erst bewertet, wenn genug abgeschlossene Tipps vorhanden sind.
AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "true").lower() in ["1", "true", "yes", "on"]
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))  # Prozent
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))        # Einheiten/Euro bei 1€ Einsatz
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

# Performance / Rate-Limit Schutz
MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "0"))  # 0 = alle Ligen
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "1.5"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "2.5"))
USE_GROQ_FALLBACK = env("USE_GROQ_FALLBACK", "true").lower() in ["1", "true", "yes", "on"]

# Diese Ligen bleiben immer AN, egal was die Statistik sagt.
ALWAYS_ON_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_ON_LEAGUES", "Champions League,Europa League,Premier League,Bundesliga,La Liga,Serie A,Ligue 1").split(",")
    if x.strip()
]

# Diese Ligen bleiben immer AUS.
ALWAYS_OFF_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_OFF_LEAGUES", "").split(",")
    if x.strip()
]

# Wenn gesetzt: nur diese Ligen analysieren (für Abend-Run!)
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
    "Champions League", "Europa League", "Conference League",

    "Bundesliga", "2. Bundesliga",
    "Premier League", "Championship",
    "La Liga", "La Liga 2",
    "Serie A", "Serie B",
    "Ligue 1", "Ligue 2",
    "Eredivisie", "Primeira Liga",
    "Pro League Belgien", "Süper Lig",
    "Bundesliga Österreich", "Super League Schweiz",
    "Scottish Premiership",

    "Danish Superliga", "Norway Eliteserien", "Sweden Allsvenskan",
    "Greece Super League", "Croatia HNL", "Serbia SuperLiga",
    "Romania Liga I", "Czech First League",
    "Poland Ekstraklasa", "Slovak Super Liga",

    "MLS", "Brasileirao Serie A", "Liga Argentinien",
    "Liga MX", "A-League", "K League 1", "J1 League Japan",
    "China Super League", "Saudi Pro League",

    # 🏃 JUGENDLIGAS
    "Bundesliga U19",
    "Bundesliga U17",
    "Premier League U18",
    "Premier League U21",
    "La Liga U19",
    "Serie A U19",
    "Ligue 1 U19",
    "UEFA Youth League",
]

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
    "K League 1": "soccer_korea_kleague1",
    "China Super League": "soccer_china_superleague",
    "Danish Superliga": "soccer_denmark_superliga",
    "Norway Eliteserien": "soccer_norway_eliteserien",
    "Sweden Allsvenskan": "soccer_sweden_allsvenskan",
    "Greece Super League": "soccer_greece_super_league",
    "Poland Ekstraklasa": "soccer_poland_ekstraklasa",
    "Slovak Super Liga": "soccer_slovakia_super_liga",
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
    "Premier League": 39,
    "Championship": 40,
    "La Liga": 140,
    "La Liga 2": 141,
    "Serie A": 135,
    "Serie B": 136,
    "Ligue 1": 61,
    "Ligue 2": 62,
    "Eredivisie": 88,
    "Primeira Liga": 94,
    "Pro League Belgien": 144,
    "Süper Lig": 203,
    "Bundesliga Österreich": 218,
    "Super League Schweiz": 207,
    "Slovak Super Liga": 332,
    "Poland Ekstraklasa": 106,
    "Scottish Premiership": 179,
    "MLS": 253,
    "Brasileirao Serie A": 71,
    "Liga Argentinien": 128,
    "J1 League Japan": 98,
    "Saudi Pro League": 307,
    "Liga MX": 262,
    "A-League": 188,
    "K League 1": 292,
    "China Super League": 169,
    "Danish Superliga": 119,
    "Norway Eliteserien": 103,
    "Sweden Allsvenskan": 113,
    "Greece Super League": 197,
    "Croatia HNL": 210,
    "Serbia SuperLiga": 286,
    "Romania Liga I": 283,
    "Czech First League": 345,
    # Jugendligas
    "Bundesliga U19": 63,
    "Bundesliga U17": 64,
    "Premier League U18": 48,
    "Premier League U21": 45,
    "La Liga U19": 384,
    "Serie A U19": 233,
    "Ligue 1 U19": 114,
    "UEFA Youth League": 10,
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


def fetch_football_data(league_name, target_date):
    code = FOOTBALL_DATA_CODES.get(league_name)

    if not code or not FOOTBALL_DATA_API_KEY:
        return []

    try:
        r = requests.get(
            f"https://api.football-data.org/v4/competitions/{code}/matches",
            params={
                "dateFrom": target_date.isoformat(),
                "dateTo": target_date.isoformat(),
            },
            headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY},
            timeout=15,
        )

        if not r.ok:
            return []

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
        return []


def fetch_api_football(league_name, target_date):
    league_id = API_FOOTBALL_LEAGUES.get(league_name)

    if not league_id or not API_FOOTBALL_KEY:
        return []

    try:
        season = target_date.year if target_date.month > 6 else target_date.year - 1

        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={
                "x-rapidapi-key": API_FOOTBALL_KEY,
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

        if not r.ok:
            return []

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
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "api-football",
                    })
            except Exception:
                continue

        return fixtures

    except Exception:
        return []


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
        # CSV parsen
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return []
        headers = lines[0].split(",")
        results = []
        for line in lines[-20:]:  # Letzte 20 Spiele
            try:
                vals = line.split(",")
                if len(vals) < len(headers):
                    continue
                row = dict(zip(headers, vals))
                results.append({
                    "date": row.get("Date", ""),
                    "home": row.get("HomeTeam", ""),
                    "away": row.get("AwayTeam", ""),
                    "fthg": row.get("FTHG", ""),  # Heim-Tore Vollzeit
                    "ftag": row.get("FTAG", ""),  # Gast-Tore Vollzeit
                    "hthg": row.get("HTHG", ""),  # Heim-Tore Halbzeit
                    "htag": row.get("HTAG", ""),  # Gast-Tore Halbzeit
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
    Pinnacle = schärfster Markt = Closing Line Proxy.
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
    
    # Pinnacle als Closing Line Proxy
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
    
    # Spread zwischen Bookies als Unsicherheits-Indikator
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

def call_gemini(prompt, use_tools=True):
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

    for idx, key in enumerate(GEMINI_API_KEYS):
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
                label = f"Gemini #{idx + 1}" if use_tools else f"Gemini-NoTools #{idx + 1}"
                return results, label

        except Exception as e:
            last_error = str(e)[:120]
            continue

    return None, f"Gemini erschöpft ({last_error})"


def call_groq(prompt):
    if not GROQ_API_KEYS:
        return None, "Keine Groq Keys"

    if not USE_GROQ_FALLBACK:
        return None, "Groq deaktiviert"

    if len(prompt) > 30000:
        prompt = prompt[:30000] + "\n\nAntworte mit JSON-Array."

    last_error = None

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
                last_error = data.get("error", {}).get("message", "")[:120]
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

    return None, f"Groq erschöpft ({last_error})"


# ============================================================
# ANALYSIS
# ============================================================

def merge_fixtures(*sources):
    all_fixtures = []
    seen = set()

    for source in sources:
        for f in source:
            home = f.get("home", "").lower().strip()
            away = f.get("away", "").lower().strip()

            if not home or not away:
                continue

            key = (home[:15], away[:15])

            if key in seen:
                continue

            seen.add(key)
            all_fixtures.append(f)

    return all_fixtures


def calculate_kelly_units(probability, odds, max_units=3.0, bank_units=100):
    """
    Kelly Kriterium für optimale Einsatzgröße in Units.
    
    Kelly % = (p × (odds-1) - (1-p)) / (odds-1)
    
    Wir nutzen Half-Kelly für Sicherheit.
    Max 3 Units pro Tipp.
    """
    try:
        p = probability / 100
        b = odds - 1
        kelly = (p * b - (1 - p)) / b
        
        if kelly <= 0:
            return 0.5  # Minimum wenn kein Edge
        
        # Half-Kelly für Sicherheit
        half_kelly = kelly / 2
        
        # In Units umrechnen (1 Unit = 1% der Bank)
        units = round(half_kelly * 100, 1)
        
        # Begrenzen auf max_units
        units = max(0.5, min(units, max_units))
        
        return units
    except Exception:
        return 1.0


def fetch_fbref_team_stats(team_name, league_name):
    """Holt erweiterte Stats von FBref (xG, Pressing, etc.)"""
    try:
        # FBref League URLs
        fbref_urls = {
            "Premier League": "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
            "Bundesliga": "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
            "La Liga": "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
            "Serie A": "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
            "Ligue 1": "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
        }
        url = fbref_urls.get(league_name)
        if not url:
            return None
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research bot)"},
            timeout=15
        )
        if not r.ok:
            return None
        # Suche nach Team in HTML
        team_lower = team_name.lower()
        text = r.text.lower()
        if team_lower[:6] not in text:
            return None
        # Extrahiere xG Daten via Regex
        pattern = rf'{re.escape(team_lower[:8])}.*?(\d+\.\d+).*?(\d+\.\d+)'
        m = re.search(pattern, text)
        if m:
            return {"xG": m.group(1), "xGA": m.group(2), "source": "FBref"}
        return None
    except Exception:
        return None


def analyze_pinnacle_value(odds_data, home_team, away_team):
    """
    Analysiert Sharp Money via Pinnacle vs andere Bookies.
    Pinnacle = professionelle Quoten, niedrigste Margin.
    Wenn Pinnacle höher als Durchschnitt = Value!
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


def build_context(odds_data, fixtures, league):
    ctx = ""

    if fixtures:
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE:\n"

        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f.get('time_local', 'TBD')} Uhr [{f.get('source', '?')}]"

            # xG Daten (Understat für Top-5-Ligen)
            if league in UNDERSTAT_LEAGUES:
                home_xg = get_team_xg(f["home"], league)
                away_xg = get_team_xg(f["away"], league)

                if home_xg:
                    line += f"\n   📊 {f['home']}: xG {home_xg['xG']}/Spiel, xGA {home_xg['xGA']} [Understat]"
                if away_xg:
                    line += f"\n   📊 {f['away']}: xG {away_xg['xG']}/Spiel, xGA {away_xg['xGA']} [Understat]"

            # Historische BTTS-Rate aus football-data.co.uk
            hist = get_historical_btts_rate(league, f["home"], f["away"])
            if hist:
                if hist.get("home"):
                    h = hist["home"]
                    line += f"\n   📈 {f['home']} (Heim): BTTS {h['btts_rate']}%, Ø {h['avg_goals']} Tore ({h['games']} Spiele) [fd.co.uk]"
                if hist.get("away"):
                    a = hist["away"]
                    line += f"\n   📈 {f['away']} (Auswärts): BTTS {a['btts_rate']}%, Ø {a['avg_goals']} Tore ({a['games']} Spiele) [fd.co.uk]"

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

                # 💹 Line Movement Analyse (Pinnacle vs Soft Bookies)
                line_signals = analyze_line_movement(
                    odds_data, g["home_team"], g["away_team"]
                )
                if line_signals:
                    ctx += "  📉 Line Movement:\n"
                    for sig in line_signals:
                        ctx += f"    {sig}\n"

                # 💹 Pinnacle Sharp Money Analyse
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
    
    # BTTS HT hat höhere Quoten → andere Limits
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
    Früher wurde das pro Markt gemacht. Das spart viele API-Calls.
    """
    odds = fetch_odds_api(league, target_date)
    fd_fix = fetch_football_data(league, target_date)
    af_fix = fetch_api_football(league, target_date)
    fj_fix = fetch_football_json(league, target_date)
    ol_fix = fetch_openligadb(league, target_date)

    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix)

    log(
        f"   Quellen: Odds={len(odds)}, FD={len(fd_fix)}, "
        f"AF={len(af_fix)}, FJ={len(fj_fix)}, OL={len(ol_fix)} "
        f"→ Total={len(fixtures)}"
    )

    return odds, fixtures


def analyze_market_with_data(market, league, target_date, odds, fixtures):
    """
    Analysiert einen Markt mit bereits geladenen Liga-Daten.
    Gemini-NoTools zuerst (schneller, kein Rate-Limit), dann Tools, dann Groq.
    """
    if not odds and not fixtures:
        return [], "Keine echten Spiele heute"

    ctx = build_context(odds, fixtures, league)
    prompt = build_prompt(market, league, target_date, ctx)

    # Reihenfolge: NoTools zuerst (vermeidet Groq Rate-Limit!)
    results, source = call_gemini(prompt, use_tools=False)

    if not results:
        results, source = call_gemini(prompt, use_tools=True)

    if not results and USE_GROQ_FALLBACK:
        results, source = call_groq(prompt)

    if not results:
        return [], source

    validated = validate_tips(results, fixtures, odds)
    return validated, source

def analyze_market(market, league, target_date):
    odds = fetch_odds_api(league, target_date)
    fd_fix = fetch_football_data(league, target_date)
    af_fix = fetch_api_football(league, target_date)
    fj_fix = fetch_football_json(league, target_date)
    ol_fix = fetch_openligadb(league, target_date)

    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix)

    if not odds and not fixtures:
        return [], "Keine echten Spiele heute", []

    log(
        f"   Quellen: Odds={len(odds)}, FD={len(fd_fix)}, "
        f"AF={len(af_fix)}, FJ={len(fj_fix)}, OL={len(ol_fix)} "
        f"→ Total={len(fixtures)}"
    )

    ctx = build_context(odds, fixtures, league)
    prompt = build_prompt(market, league, target_date, ctx)

    results, source = call_gemini(prompt, use_tools=False)

    if not results:
        results, source = call_gemini(prompt, use_tools=True)

    if not results and USE_GROQ_FALLBACK:
        results, source = call_groq(prompt)

    if not results:
        return [], source, fixtures

    validated = validate_tips(results, fixtures, odds)

    return validated, source, fixtures


# ============================================================
# TELEGRAM + SUPABASE
# ============================================================

def send_telegram(text, chat_id=None):
    if not TELEGRAM_TOKEN:
        log("Telegram Token fehlt", "WARN")
        return None

    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if not chat_id:
        log("Telegram Chat ID fehlt", "WARN")
        return None

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=15,
        )

        if not r.ok:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": re.sub(r"<[^>]+>", "", text),
                },
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
    Verhindert alte Tipps oder Spiele die schon laufen/beendet sind.
    """
    # 1. Datum muss heute sein
    tip_date = tip.get("date", "")
    today_str = str(target_date)
    if tip_date and tip_date != today_str:
        log(f"   ⚠️ Falsches Datum: {tip_date} (erwartet {today_str})")
        return False

    # 2. Spiel muss noch in der Zukunft liegen
    time_str = tip.get("time", "")
    if not is_future_game(time_str, target_date):
        log(f"   ⚠️ Spiel bereits vorbei: {tip.get('match','')} um {time_str}")
        return False

    return True


def save_to_supabase(tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=tip,
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

        # ROI in Units (Kelly-gewichtet)
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

        # Pro Markt mit Units
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

        # Aktueller Monat
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

        # Top 10 Ligen Ranking (nach Units)
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
        # Sortierung: erst nach Units, dann nach Trefferquote
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

        # Monat
        if stats.get("month") and stats["month"]["total"] > 0:
            m = stats["month"]
            m_emoji = "🟢" if m["units"] >= 0 else "🔴"
            stats_header += f"\n📆 <b>{m['name']}:</b> {m['won']}/{m['total']} ({m['pct']}%) · "
            stats_header += f"<b>{'+' if m['units'] >= 0 else ''}{m['units']} Units</b> {m_emoji}\n"

        # Pro Markt mit Units
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

        # Top 10 Ligen
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

            # 🛡️ Validierung: Richtiges Datum + Spiel noch nicht gestartet
            r["date"] = str(target_date)
            if not is_valid_tip(r, target_date):
                continue

            # 🛡️ Duplikat-Check: Schon heute gesendet?
            if is_duplicate_tip(match_name, market_id, target_date):
                log(f"   ⏭️ Duplikat übersprungen: {match_name} ({market_id})")
                continue

            msg = f"<b>💎 Tipp {i}/{len(tips)}</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"
            msg += f"<b>{match_name}</b>\n"
            msg += f"📍 {r.get('league', '')}\n"
            msg += f"⏰ {r.get('time', 'TBD')} Uhr\n\n"
            msg += f"{icons.get(r.get('tip', '?'), '')} <b>Tipp: {r.get('tip', '?')}</b>\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability', 0)}%</b>\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}\n\n"
            msg += f"💰 <b>Quote: {r.get('oddsYes', '-')}</b>\n"
            msg += f"🎯 Fair Odds: {r.get('fairOdds', '-')}\n"
            msg += f"{val_icons.get(r.get('valueRating', 'OK'), '🟡')} Value: <b>{r.get('valueRating', 'OK')}</b>\n"

            # 💵 Units Empfehlung (Kelly)
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

            msg += "\n📊 <b>Form</b>\n"
            msg += f"🏠 Heim: {r.get('homeForm', '-')}\n"
            msg += f"✈️ Auswärts: {r.get('awayForm', '-')}\n"

            if r.get("keyFactor"):
                msg += f"\n⚡ <i>{r.get('keyFactor')}</i>\n"

            reasoning = r.get("reasoning", "")[:300]

            if reasoning:
                msg += f"\n💭 <i>{reasoning}</i>"

            msg_id = send_telegram(msg, target_chat)

            tip_id = f"{market_id}_{target_date}_{i}_{abs(hash(match_name)) % 100000}"

            # Units berechnen
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
    Status muss 'won' oder 'lost' sein.
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
    Berechnet pro Liga:
    - Anzahl abgeschlossene Tipps
    - Wins / Losses
    - Winrate + ROI gesamt
    - Winrate + ROI letzte 10 Tipps (für Reaktivierung!)
    """
    stats = {}
    # Sortiere nach Datum (neueste zuerst)
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
                # Letzte 10
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
    Entscheidung:
    - ALWAYS_OFF = immer aus
    - ALWAYS_ON = immer an
    - zu wenig Daten = anlassen
    - genug Daten:
        ✅ aktiv wenn Winrate + ROI gut
        ❌ deaktiviert wenn Winrate + ROI schlecht
        🔄 REAKTIVIERT wenn nach Deaktivierung Verbesserung erkennbar
    
    Reaktivierungs-Logik:
    - Letzte 10 Tipps werden separat geprüft
    - Wenn letzte 10 besser als Gesamt → Liga bekommt zweite Chance
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

    # Liga würde normal deaktiviert werden
    winrate_bad = s["winrate"] < AUTO_LEAGUE_MIN_WINRATE
    roi_bad = s["roi"] < AUTO_LEAGUE_MIN_ROI

    if winrate_bad or roi_bad:
        # 🔄 REAKTIVIERUNGS-CHECK: Letzte 10 Tipps
        recent = s.get("recent", {})
        recent_total = recent.get("total", 0)
        recent_winrate = recent.get("winrate", 0)
        recent_roi = recent.get("roi", 0)

        if recent_total >= 5:
            # Wenn letzte 5+ Tipps deutlich besser → reaktivieren!
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
    Gibt die Ligen zurück die heute analysiert werden.
    ACTIVE_LEAGUES env = nur diese Ligen (z.B. für Abend-Run!)
    """
    # Abend-Run: nur bestimmte Ligen
    if ACTIVE_LEAGUES_OVERRIDE:
        log(f"🌙 Abend-Run: nur {len(ACTIVE_LEAGUES_OVERRIDE)} Ligen")
        return ACTIVE_LEAGUES_OVERRIDE, {}

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
            log(f" ✅ {league}: {reason}")
        else:
            disabled.append((league, reason))
            log(f" ⛔ {league}: {reason}", "SKIP")

    log(f"Auto Liga Switch Ergebnis: {len(active)} aktiv, {len(disabled)} deaktiviert")

    return active, league_stats

# ============================================================
# MAIN
# ============================================================

def check_config():
    warnings = []

    if not GEMINI_API_KEYS:
        warnings.append("GEMINI_API_KEYS fehlt")

    if not GROQ_API_KEYS:
        warnings.append("GROQ_API_KEYS fehlt")

    if not ODDS_API_KEYS:
        warnings.append("ODDS_API_KEYS fehlt")

    if not TELEGRAM_TOKEN:
        warnings.append("TELEGRAM_TOKEN fehlt")

    if not TELEGRAM_CHAT_ID:
        warnings.append("TELEGRAM_CHAT_ID fehlt")

    if warnings:
        log("Config Warnungen:", "WARN")
        for w in warnings:
            log(f" - {w}", "WARN")


def main():
    log("=" * 60)
    log("AI TIPP BOT - GITHUB SINGLE FILE EDITION")
    log("=" * 60)

    check_config()

    target_date = date.today()

    log(f"Datum: {target_date}")
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
    log("Sende an Telegram + Supabase...")

    send_top_tips(tips_by_market, target_date)

    log("Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
