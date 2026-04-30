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
TELEGRAM_GROUP_1X2=...
TELEGRAM_GROUP_STATS=...
SUPABASE_URL=...
SUPABASE_KEY=...
"""

import os
import re
import sys
import json
import traceback
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
    "1x2": env("TELEGRAM_GROUP_1X2", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
}

SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "60"))
MIN_ODDS = float(env("MIN_ODDS", "1.5"))
MAX_ODDS = float(env("MAX_ODDS", "3.5"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))

MARKETS_TO_RUN = ["btts", "over25", "combo", "1x2"]

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
    "1x2": {
        "name": "🏆 1X2 Sieger",
        "instr": "Analysiere den Sieger des Spiels (1=Heim, X=Unentschieden, 2=Auswärts).",
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
                continue

            choices = data.get("choices", [])

            if not choices:
                last_error = "no choices"
                continue

            text = choices[0].get("message", {}).get("content", "")
            results = extract_json_array(text)

            if results is not None:
                return results, f"Groq #{idx + 1}"

        except Exception as e:
            last_error = str(e)[:120]
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


def build_context(odds_data, fixtures, league):
    ctx = ""

    if fixtures:
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE:\n"

        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f.get('time_local', 'TBD')} Uhr [{f.get('source', '?')}]"

            if league in UNDERSTAT_LEAGUES:
                home_xg = get_team_xg(f["home"], league)
                away_xg = get_team_xg(f["away"], league)

                if home_xg:
                    line += f"\n   📊 {f['home']}: xG {home_xg['xG']}/Spiel, xGA {home_xg['xGA']}"

                if away_xg:
                    line += f"\n   📊 {f['away']}: xG {away_xg['xG']}/Spiel, xGA {away_xg['xGA']}"

            ctx += line + "\n"

    if odds_data:
        ctx += "\n💰 LIVE-QUOTEN:\n"

        for g in odds_data[:10]:
            try:
                t = get_local_time(g["commence_time"])
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}\n"

                for bm in g.get("bookmakers", [])[:3]:
                    for m in bm.get("markets", []):
                        if m["key"] == "totals":
                            ov = next(
                                (
                                    o["price"]
                                    for o in m["outcomes"]
                                    if o["name"] == "Over" and o.get("point") == 2.5
                                ),
                                None,
                            )
                            un = next(
                                (
                                    o["price"]
                                    for o in m["outcomes"]
                                    if o["name"] == "Under" and o.get("point") == 2.5
                                ),
                                None,
                            )

                            if ov:
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}\n"

                        if m["key"] == "h2h":
                            home_o = next(
                                (
                                    o["price"]
                                    for o in m["outcomes"]
                                    if o["name"] == g["home_team"]
                                ),
                                None,
                            )
                            draw_o = next(
                                (
                                    o["price"]
                                    for o in m["outcomes"]
                                    if o["name"] == "Draw"
                                ),
                                None,
                            )
                            away_o = next(
                                (
                                    o["price"]
                                    for o in m["outcomes"]
                                    if o["name"] == g["away_team"]
                                ),
                                None,
                            )

                            if home_o:
                                ctx += f"  [{bm['title']}] 1: {home_o} / X: {draw_o} / 2: {away_o}\n"

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

    for r in tips:
        if not is_future_game(r.get("time", ""), target_date):
            continue

        if market == "1x2":
            if r.get("tip") not in ["1", "X", "2"]:
                continue
        else:
            if r.get("tip") != "YES":
                continue

        if int(r.get("probability", 0)) < MIN_PROBABILITY:
            continue

        if int(r.get("confidence", 0)) < MIN_CONFIDENCE:
            continue

        odds = parse_odds(r.get("oddsYes", 0))

        if odds < MIN_ODDS or odds > MAX_ODDS:
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

    results, source = call_gemini(prompt, use_tools=True)

    if not results:
        results, source = call_gemini(prompt, use_tools=False)

    if not results:
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
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "select": "*",
                "order": "date.desc,id.desc",
            },
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

        roi = 0

        for t in won:
            try:
                roi += float(str(t.get("odds", "1")).replace(",", ".")) - 1
            except Exception:
                pass

        roi -= len(lost)

        by_market = {
            "btts": {"w": 0, "l": 0, "roi": 0},
            "over25": {"w": 0, "l": 0, "roi": 0},
            "combo": {"w": 0, "l": 0, "roi": 0},
            "1x2": {"w": 0, "l": 0, "roi": 0},
        }

        for t in won + lost:
            m = t.get("market", "")

            if m not in by_market:
                continue

            if t.get("status") == "won":
                by_market[m]["w"] += 1
                try:
                    by_market[m]["roi"] += float(str(t.get("odds", "1")).replace(",", ".")) - 1
                except Exception:
                    pass
            else:
                by_market[m]["l"] += 1
                by_market[m]["roi"] -= 1

        return {
            "won": len(won),
            "lost": len(lost),
            "pending": len(pending),
            "quote_pct": quote_pct,
            "roi": round(roi, 2),
            "by_market": by_market,
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

        roi_emoji = "🟢" if stats["roi"] >= 0 else "🔴"
        stats_header += f"💰 ROI: <b>{'+' if stats['roi'] >= 0 else ''}{stats['roi']}</b> € {roi_emoji}\n"

        stats_header += "\n<b>📊 Pro Markt:</b>\n"

        for m_id in MARKETS_TO_RUN:
            mb = stats["by_market"].get(m_id, {"w": 0, "l": 0, "roi": 0})
            tot = mb["w"] + mb["l"]

            if tot > 0:
                pct = round(mb["w"] / tot * 100)
                emoji = "🟢" if pct >= 60 else "🟡" if pct >= 40 else "🔴"
                roi_str = f"+{round(mb['roi'], 2)}" if mb["roi"] >= 0 else f"{round(mb['roi'], 2)}"
                stats_header += f"{MARKET_INFO[m_id]['name']}: {mb['w']}/{tot} ({pct}%) · {roi_str}€ {emoji}\n"

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

            msg = f"<b>💎 Tipp {i}/{len(tips)}</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"
            msg += f"<b>{r.get('match', '?')}</b>\n"
            msg += f"📍 {r.get('league', '')}\n"
            msg += f"⏰ {r.get('time', 'TBD')} Uhr\n\n"
            msg += f"{icons.get(r.get('tip', '?'), '')} <b>Tipp: {r.get('tip', '?')}</b>\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability', 0)}%</b>\n"
            msg += f"⭐ Confidence: {'⭐' * confidence}\n\n"
            msg += f"💰 <b>Quote: {r.get('oddsYes', '-')}</b>\n"
            msg += f"🎯 Fair Odds: {r.get('fairOdds', '-')}\n"
            msg += f"{val_icons.get(r.get('valueRating', 'OK'), '🟡')} Value: <b>{r.get('valueRating', 'OK')}</b>\n"

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

            tip_id = f"{market_id}_{target_date}_{i}_{abs(hash(r.get('match', ''))) % 100000}"

            tip_data = {
                "tip_id": tip_id,
                "date": str(target_date),
                "market": market_id,
                "market_name": market_name,
                "match": r.get("match", ""),
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
    - Winrate
    - ROI bei 1 Einheit Einsatz pro Tipp
    """
    stats = {}

    for t in tips:
        league = t.get("league") or "Unknown"
        status = t.get("status")

        if league not in stats:
            stats[league] = {
                "won": 0,
                "lost": 0,
                "total": 0,
                "roi": 0.0,
                "winrate": 0.0,
            }

        if status == "won":
            stats[league]["won"] += 1
            try:
                odds = float(str(t.get("odds", "1")).replace(",", "."))
                stats[league]["roi"] += odds - 1
            except Exception:
                stats[league]["roi"] += 0
        elif status == "lost":
            stats[league]["lost"] += 1
            stats[league]["roi"] -= 1
        else:
            continue

        stats[league]["total"] += 1

    for league, s in stats.items():
        if s["total"] > 0:
            s["winrate"] = round((s["won"] / s["total"]) * 100, 1)
            s["roi"] = round(s["roi"], 2)

    return stats


def should_run_league(league, league_stats):
    """
    Entscheidung:
    - ALWAYS_OFF = immer aus
    - ALWAYS_ON = immer an
    - zu wenig Daten = anlassen
    - genug Daten:
        aktiv, wenn Winrate und ROI über Schwelle liegen
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

    if s["winrate"] < AUTO_LEAGUE_MIN_WINRATE:
        return False, f"Winrate zu niedrig ({s['winrate']}% < {AUTO_LEAGUE_MIN_WINRATE}%)"

    if s["roi"] < AUTO_LEAGUE_MIN_ROI:
        return False, f"ROI zu niedrig ({s['roi']} < {AUTO_LEAGUE_MIN_ROI})"

    return True, f"OK ({s['winrate']}%, ROI {s['roi']})"


def get_active_leagues():
    """
    Gibt die Ligen zurück, die heute analysiert werden.
    """
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

    for market in MARKETS_TO_RUN:
        log(f"╔══ {MARKET_INFO[market]['name']} ══╗")

        for league in active_leagues:
            log(f" → {league}")

            try:
                results, source, fixtures = analyze_market(market, league, target_date)

                if "Keine echten Spiele" in source:
                    log("   - Keine Spiele heute")
                    continue

                if results:
                    log(f"   ✓ {len(results)} via {source}")
                    total_analyzed += len(results)

                    top = filter_top_tips(results, target_date, market)

                    if top:
                        log(f"   💎 {len(top)} TOP!", "TOP")
                        tips_by_market[market].extend(top)
                else:
                    log(f"   - {source}")

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
