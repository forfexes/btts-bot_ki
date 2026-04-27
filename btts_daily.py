"""
═══════════════════════════════════════════════════════════════
  AI TIPP BOT - ULTIMATE EDITION (Multi-Source)
═══════════════════════════════════════════════════════════════
  ⚽ BTTS · 🎯 Over 2.5 · 🔥 Combo · 🏆 1X2
  
  Datenquellen (8 Stück, alle gratis):
   1. Odds API (13 Keys)
   2. football-data.org
   3. API-Football
   4. football.json (GitHub openfootball)
   5. OpenLigaDB (Bundesliga + andere, KEIN Key)
   6. football-data.co.uk (CSV, KEIN Key)
   7. Understat (xG-Daten, scraping)
   8. Gemini Web-Suche
  
  Anti-Halluzination · Multi-Validierung · Supabase
═══════════════════════════════════════════════════════════════
"""

import requests
import json
import re
import os
import sys
import csv
from io import StringIO
from datetime import date, datetime, timedelta, timezone

# ═══ KONFIGURATION ═══════════════════════════════════════════

GEMINI_API_KEYS = [
    "AIzaSyAhp4Cc-RaycmRWkvMcgBLkOOPSs1sMXgI",
    "AIzaSyAqwbGf-lBX6h6vdp1u1CQ5IrLYC0bL8hw",
    "AIzaSyDcPfgl-eeRKzpODhVqoy3uNYtEiL4r8-U",
    "AIzaSyBDsDmhE8CmHQk0q7ct-dHFydk5nLe_n7c",
    "AIzaSyDFSB5eUdcP_aDidtRs7gEP7uvHF4XZb-M",
    "AIzaSyB-V_ZzMRNnkde_PKUgc45zpOJQQMcyr-M",
    "AIzaSyC6cJlQ2UhAhyfeQH70XV1OYXYCeY-9It8",
    "AIzaSyAV1a7K2pnh9lvmHSgT9y1nl9pn5x_B0fI",
    "AIzaSyC0KefvlyGE7x3ptav9GEAUVTcIYvLLhpw",
    "AIzaSyBIXxe6ngVZpaNpbwVO-8LSI0zpOPnfeO0",
]
GEMINI_MODEL = "gemini-2.5-flash"

GROQ_API_KEYS = [
    "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",
    "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",
    "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",
    "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",
]
GROQ_MODEL = "llama-3.3-70b-versatile"

ODDS_API_KEYS = [
    "4b66fb8339b88da06e6bf49fec19efdf",
    "6e8ca3f1e2b866da469d0c240fda544f",
    "3a74c3b0568e27304018f9e22fa90c6f",
    "a3d647a6a454741a4645dea0a64c362f",
    "aa82164fb332ca1413c0c91a2110b4d7",
    "2d3e697d1268d870bdb1b59f1264ed51",
    "4af53d2e241ee2555c4f47cb577eb792",
    "58b5f642893b59f006c6b928ed6a2842",
    "1e27f0920c85f958a94c7839f8ecfb85",
    "15a179b24f7f471fc9ef70e371197611",
    "203ff23da1fd1982bf829fabeed6b39a",
    "6edbff55f6e4aeb6b8e8875930534bca",
    "de3e3d946e73a66bb57750d59f284dc4",
]

FOOTBALL_DATA_API_KEY = "bfd46775e9df45e98b5ace754fd6c2b1"
API_FOOTBALL_KEY = "3eb2bd4e228aac07fdbaf1964304b6cf"
WEATHER_API_KEY = "26b0619037f07eea9194d4ef9fea53e1"

TELEGRAM_TOKEN = "8613868656:AAFHN_zpWerWXYjL4o5gb4Jy9aTo_7yITts"
TELEGRAM_CHAT_ID = "558164451"

TELEGRAM_GROUPS = {
    "btts": "-5255652174",
    "over25": "-5113758598",
    "combo": "-5046003943",
    "1x2": "-1003959046551",
    "stats": "-1003755614684",
}

SUPABASE_URL = "https://sugycqnjncgfheueqaee.supabase.co"
SUPABASE_KEY = "sb_secret_SuIolwQOeMa1mekoyhrnbQ_N36pUi4-"

# ═══ FILTER ═════════════════════════════════════════════════
MIN_PROBABILITY = 65
MIN_ODDS = 1.6
MAX_ODDS = 3.0
MIN_CONFIDENCE = 3

MARKETS_TO_RUN = ["btts", "over25", "combo", "1x2"]

LEAGUES_TO_RUN = [
    "Champions League", "Europa League", "Conference League",
    "Bundesliga", "2. Bundesliga", "Premier League", "Championship",
    "La Liga", "La Liga 2", "Serie A", "Serie B",
    "Ligue 1", "Ligue 2",
    "Eredivisie", "Primeira Liga", "Pro League Belgien",
    "Süper Lig", "Bundesliga Österreich", "Super League Schweiz",
    "Slovak Super Liga", "Ekstraklasa", "Scottish Premiership",
    "MLS", "Brasileirao Serie A", "Liga Argentinien",
    "J1 League Japan", "Saudi Pro League",
]

# ═════════════════════════════════════════════════════════════

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
    "Slovak Super Liga": "soccer_slovakia_super_liga",
    "Ekstraklasa": "soccer_poland_ekstraklasa",
    "Scottish Premiership": "soccer_spl",
    "MLS": "soccer_usa_mls",
    "Brasileirao Serie A": "soccer_brazil_campeonato",
    "Liga Argentinien": "soccer_argentina_primera_division",
    "J1 League Japan": "soccer_japan_j_league",
    "Saudi Pro League": "soccer_saudi_arabia_league",
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
    "Champions League": 2, "Europa League": 3, "Conference League": 848,
    "Bundesliga": 78, "2. Bundesliga": 79,
    "Premier League": 39, "Championship": 40,
    "La Liga": 140, "La Liga 2": 141,
    "Serie A": 135, "Serie B": 136,
    "Ligue 1": 61, "Ligue 2": 62,
    "Eredivisie": 88, "Primeira Liga": 94, "Pro League Belgien": 144,
    "Süper Lig": 203, "Bundesliga Österreich": 218,
    "Super League Schweiz": 207, "Slovak Super Liga": 332,
    "Ekstraklasa": 106, "Scottish Premiership": 179,
    "MLS": 253, "Brasileirao Serie A": 71, "Liga Argentinien": 128,
    "J1 League Japan": 98, "Saudi Pro League": 307,
}

FOOTBALL_JSON_LEAGUES = {
    "Bundesliga": "de.1", "2. Bundesliga": "de.2",
    "Premier League": "en.1", "Championship": "en.2",
    "La Liga": "es.1", "La Liga 2": "es.2",
    "Serie A": "it.1", "Serie B": "it.2",
    "Ligue 1": "fr.1", "Ligue 2": "fr.2",
    "Eredivisie": "nl.1", "Primeira Liga": "pt.1",
    "Champions League": "uefa.cl", "Europa League": "uefa.el",
}

# OpenLigaDB Liga-Codes
OPENLIGADB_LEAGUES = {
    "Bundesliga": "bl1",
    "2. Bundesliga": "bl2",
    "Bundesliga Österreich": "bl-at",
    "Süper Lig": "tr1",
    "Champions League": "ucl",
    "Europa League": "uel",
}

# football-data.co.uk Liga-Codes
FOOTBALL_DATA_CO_UK = {
    "Bundesliga": "D1",
    "2. Bundesliga": "D2",
    "Premier League": "E0",
    "Championship": "E1",
    "La Liga": "SP1",
    "La Liga 2": "SP2",
    "Serie A": "I1",
    "Serie B": "I2",
    "Ligue 1": "F1",
    "Ligue 2": "F2",
    "Eredivisie": "N1",
    "Primeira Liga": "P1",
    "Pro League Belgien": "B1",
    "Süper Lig": "T1",
    "Scottish Premiership": "SC0",
}

UNDERSTAT_LEAGUES = {
    "Premier League": "EPL",
    "La Liga": "La_liga",
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie_A",
    "Ligue 1": "Ligue_1",
}

MARKET_INFO = {
    "btts": {"name": "⚽ BTTS", "instr": "Analysiere BTTS (Both Teams To Score - beide Teams treffen)."},
    "over25": {"name": "🎯 Over 2.5", "instr": "Analysiere Over 2.5 Tore."},
    "combo": {"name": "🔥 BTTS + Over 2.5", "instr": "Analysiere BTTS & Over 2.5 KOMBO."},
    "1x2": {"name": "🏆 1X2 Sieger", "instr": "Analysiere den Sieger des Spiels (1=Heim, X=Unentschieden, 2=Auswärts)."},
}


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
    except:
        return "TBD"


# ═══ DATEN-QUELLEN ═══════════════════════════════════════════

def fetch_odds_api(league_name, target_date):
    """Quelle 1: Odds API (13 Keys)"""
    sport_key = LEAGUE_KEYS.get(league_name)
    if not sport_key:
        return []
    for key in ODDS_API_KEYS:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                params={"apiKey": key, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"},
                timeout=15
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
                    game_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                    if game_time > now_utc:
                        filtered.append(g)
                except:
                    continue
            return filtered
        except:
            continue
    return []


def fetch_football_data(league_name, target_date):
    """Quelle 2: football-data.org"""
    code = FOOTBALL_DATA_CODES.get(league_name)
    if not code:
        return []
    try:
        r = requests.get(
            f"https://api.football-data.org/v4/competitions/{code}/matches",
            params={"dateFrom": target_date.isoformat(), "dateTo": target_date.isoformat()},
            headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY},
            timeout=15
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
            except:
                continue
        return fixtures
    except:
        return []


def fetch_api_football(league_name, target_date):
    """Quelle 3: API-Football"""
    league_id = API_FOOTBALL_LEAGUES.get(league_name)
    if not league_id or not API_FOOTBALL_KEY:
        return []
    try:
        season = target_date.year if target_date.month > 6 else target_date.year - 1
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"},
            params={"date": target_date.isoformat(), "league": league_id, "season": season, "status": "NS"},
            timeout=15
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
            except:
                continue
        return fixtures
    except:
        return []


def fetch_football_json(league_name, target_date):
    """Quelle 4: football.json (GitHub openfootball)"""
    league_code = FOOTBALL_JSON_LEAGUES.get(league_name)
    if not league_code:
        return []
    try:
        year = target_date.year
        if target_date.month >= 7:
            season = f"{year}-{(year+1) % 100:02d}"
        else:
            season = f"{year-1}-{year % 100:02d}"
        url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league_code}.json"
        r = requests.get(url, timeout=10)
        if not r.ok:
            return []
        data = r.json()
        target_str = target_date.isoformat()
        fixtures = []
        for m in data.get("matches", []):
            if m.get("date") == target_str:
                fixtures.append({
                    "home": m.get("team1", ""),
                    "away": m.get("team2", ""),
                    "time_local": "TBD",
                    "source": "football.json",
                })
        return fixtures
    except:
        return []


def fetch_openligadb(league_name, target_date):
    """Quelle 5: OpenLigaDB - KEIN Key, KEIN Limit!"""
    code = OPENLIGADB_LEAGUES.get(league_name)
    if not code:
        return []
    try:
        # Saison ermitteln
        year = target_date.year
        season = year if target_date.month >= 7 else year - 1
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
                if not kickoff_str:
                    continue
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff_str.startswith(target_str) and kickoff > now_utc:
                    teams = m.get("team1", {}), m.get("team2", {})
                    fixtures.append({
                        "home": teams[0].get("teamName", ""),
                        "away": teams[1].get("teamName", ""),
                        "match_id": m.get("matchID"),
                        "time_utc": kickoff_str,
                        "time_local": get_local_time(kickoff_str),
                        "source": "openligadb",
                    })
            except:
                continue
        return fixtures
    except:
        return []


def fetch_understat_xg(team_name, league_name):
    """Quelle 6: Understat (xG-Daten)"""
    league_code = UNDERSTAT_LEAGUES.get(league_name)
    if not league_code:
        return None
    try:
        url = f"https://understat.com/league/{league_code}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if not r.ok:
            return None
        m = re.search(r"var teamsData\s*=\s*JSON\.parse\('([^']+)'\)", r.text)
        if not m:
            return None
        encoded = m.group(1).encode().decode('unicode_escape')
        teams_data = json.loads(encoded)
        team_lower = team_name.lower()
        for team_id, info in teams_data.items():
            title = info.get("title", "").lower()
            if team_lower in title or title in team_lower:
                history = info.get("history", [])
                if history:
                    last5 = history[-5:]
                    avg_xg = sum(float(h.get("xG", 0)) for h in last5) / len(last5)
                    avg_xga = sum(float(h.get("xGA", 0)) for h in last5) / len(last5)
                    return {"xG": round(avg_xg, 2), "xGA": round(avg_xga, 2)}
        return None
    except:
        return None


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
        ctx += f"\n📅 ECHTER SPIELPLAN für {league} HEUTE (MESZ):\n"
        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f['time_local']} Uhr [{f.get('source','?')}]"
            
            # xG-Daten anhängen wenn verfügbar (nur Top-5-Ligen)
            if league in UNDERSTAT_LEAGUES:
                home_xg = fetch_understat_xg(f['home'], league)
                away_xg = fetch_understat_xg(f['away'], league)
                if home_xg:
                    line += f"\n   📊 {f['home']}: xG {home_xg['xG']}/Spiel, xGA {home_xg['xGA']}"
                if away_xg:
                    line += f"\n   📊 {f['away']}: xG {away_xg['xG']}/Spiel, xGA {away_xg['xGA']}"
            
            ctx += line + "\n"
    
    if odds_data:
        ctx += f"\n💰 LIVE-QUOTEN:\n"
        for g in odds_data[:10]:
            try:
                t = get_local_time(g["commence_time"])
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}\n"
                for bm in g.get("bookmakers", [])[:3]:
                    for m in bm.get("markets", []):
                        if m["key"] == "totals":
                            ov = next((o["price"] for o in m["outcomes"] if o["name"] == "Over" and o.get("point") == 2.5), None)
                            un = next((o["price"] for o in m["outcomes"] if o["name"] == "Under" and o.get("point") == 2.5), None)
                            if ov:
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}\n"
                        if m["key"] == "h2h":
                            home_o = next((o["price"] for o in m["outcomes"] if o["name"] == g['home_team']), None)
                            draw_o = next((o["price"] for o in m["outcomes"] if o["name"] == "Draw"), None)
                            away_o = next((o["price"] for o in m["outcomes"] if o["name"] == g['away_team']), None)
                            if home_o:
                                ctx += f"  [{bm['title']}] 1: {home_o} / X: {draw_o} / 2: {away_o}\n"
            except:
                continue
    return ctx


def extract_json_array(text):
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        s = cleaned.find("[")
        e = cleaned.rfind("]")
        if s != -1 and e > s:
            return json.loads(cleaned[s:e+1])
    except:
        pass
    objects = []
    depth = 0
    start_idx = -1
    for i, c in enumerate(cleaned):
        if c == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    obj = json.loads(cleaned[start_idx:i+1])
                    if "match" in obj:
                        objects.append(obj)
                except:
                    pass
                start_idx = -1
    return objects


def build_prompt(market, league, target_date, context):
    info = MARKET_INFO[market]
    if market == "1x2":
        json_format = '[{"match":"A vs B","league":"' + league + '","time":"HH:MM","tip":"1","probability":55,"confidence":4,"fairOdds":"1.85","oddsYes":"1.95","oddsNo":"-","bookie":"Bet365","homeForm":"WWDLW","awayForm":"LWWDD","valueRating":"HIGH","keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        tip_help = 'tip: "1" (Heimsieg) / "X" (Unentschieden) / "2" (Auswärtssieg)'
    else:
        json_format = '[{"match":"A vs B","league":"' + league + '","time":"HH:MM","tip":"YES","probability":72,"confidence":4,"fairOdds":"1.65","oddsYes":"1.72","oddsNo":"2.10","bookie":"Bet365","homeForm":"WWDLW","awayForm":"LWWDD","valueRating":"HIGH","keyFactor":"Faktor","reasoning":"2 Sätze."}]'
        tip_help = 'tip: "YES" / "NO" / "MAYBE"'
    
    return f"""Du bist Fußball-Wettanalyst. {info['instr']}

Liga: "{league}" · Datum: {target_date}

{context}

🚨 KRITISCH:
1. Analysiere AUSSCHLIESSLICH die oben aufgeführten Spiele!
2. ERFINDE KEINE Spiele die NICHT in der Liste stehen!
3. Verwende die ECHTEN Anstoßzeiten!
4. Berücksichtige xG-Daten (xG hoch + xGA hoch = mehr Tore)
5. Wenn Liste leer: gib [] zurück!

Antworte mit JSON-Array:
{json_format}

{tip_help}
Falls keine echten Spiele: []"""


def call_gemini(prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 32000}
    }
    for idx, key in enumerate(GEMINI_API_KEYS):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload, timeout=240
            )
            data = r.json()
            if "error" in data:
                continue
            candidates = data.get("candidates", [])
            if not candidates:
                continue
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
            results = extract_json_array(text)
            if results is not None:
                return results, f"Gemini #{idx+1}"
        except:
            continue
    return None, "Gemini erschöpft"


def call_groq(prompt):
    for idx, key in enumerate(GROQ_API_KEYS):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": 8000},
                timeout=120
            )
            data = r.json()
            if "error" in data:
                continue
            choices = data.get("choices", [])
            if not choices:
                continue
            text = choices[0].get("message", {}).get("content", "")
            results = extract_json_array(text)
            if results is not None:
                return results, f"Groq #{idx+1}"
        except:
            continue
    return None, "Groq erschöpft"


def normalize_team_name(name):
    if not name:
        return ""
    n = name.lower().strip()
    for x in [" fc", " cf", " ac", " sc", " sv", " 1.", "fc ", "ac ", "sc ", "sv ", "1. ", " e.v.", " ev"]:
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


def validate_tips(tips, real_fixtures, real_odds):
    if not tips:
        return []
    real_matches = []
    for f in real_fixtures:
        real_matches.append((f.get("home", ""), f.get("away", ""), f.get("time_local", "")))
    for g in real_odds:
        try:
            t = get_local_time(g.get("commence_time", ""))
            real_matches.append((g.get("home_team", ""), g.get("away_team", ""), t))
        except:
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


def parse_odds(val):
    try:
        return float(str(val).replace(",", "."))
    except:
        return 0.0


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
        game_local = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        game_utc = (game_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        return game_utc > now_utc - timedelta(minutes=15)
    except:
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
        if r.get("probability", 0) < MIN_PROBABILITY:
            continue
        if r.get("confidence", 0) < MIN_CONFIDENCE:
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
    
    unique.sort(key=lambda r: (0 if r.get("valueRating") == "HIGH" else 1, -r.get("probability", 0)))
    return unique


def analyze_market(market, league, target_date):
    """Analysiert einen Markt - probiert ALLE 6 Datenquellen!"""
    odds = fetch_odds_api(league, target_date)
    fd_fix = fetch_football_data(league, target_date)
    af_fix = fetch_api_football(league, target_date)
    fj_fix = fetch_football_json(league, target_date)
    ol_fix = fetch_openligadb(league, target_date)
    
    fixtures = merge_fixtures(fd_fix, af_fix, fj_fix, ol_fix)
    
    if not odds and not fixtures:
        return [], "Keine echten Spiele heute", []
    
    ctx = build_context(odds, fixtures, league)
    prompt = build_prompt(market, league, target_date, ctx)
    
    results, source = call_gemini(prompt)
    if not results:
        results, source = call_groq(prompt)
    if not results:
        return [], source, fixtures
    
    validated = validate_tips(results, fixtures, odds)
    return validated, source, fixtures


def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
        if not r.ok:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": re.sub(r'<[^>]+>', '', text)},
                timeout=15
            )
        if r.ok:
            return r.json().get("result", {}).get("message_id")
    except:
        pass
    return None


def save_to_supabase(tip):
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=tip, timeout=10
        )
        return r.ok
    except:
        return False


def send_top_tips(tips_by_market, target_date):
    icons = {"YES": "✅", "NO": "❌", "MAYBE": "⚠️", "1": "🏠", "X": "🤝", "2": "✈️"}
    val_icons = {"HIGH": "🔥", "OK": "🟡", "LOW": "🔴"}
    market_emoji = {"btts": "⚽", "over25": "🎯", "combo": "🔥", "1x2": "🏆"}
    
    total_tips = sum(len(t) for t in tips_by_market.values())
    
    # Stats-Übersicht
    stats_header = f"<b>🤖 AI TIPP BOT - DAILY</b>\n<i>{target_date}</i>\n\n"
    stats_header += f"📊 <b>Übersicht heute:</b>\n"
    for m_id in MARKETS_TO_RUN:
        count = len(tips_by_market.get(m_id, []))
        stats_header += f"• {MARKET_INFO[m_id]['name']}: <b>{count}</b> Tipps\n"
    stats_header += f"\n💎 <b>Total: {total_tips} Top-Tipps</b>"
    send_telegram(stats_header, TELEGRAM_GROUPS["stats"])
    
    if total_tips == 0:
        send_telegram(
            f"ℹ Heute keine Top-Tipps.\nFilter:\n"
            f"• Wahrsch. ≥ {MIN_PROBABILITY}%\n"
            f"• Quote {MIN_ODDS}-{MAX_ODDS}\n"
            f"• Confidence ≥ {MIN_CONFIDENCE}⭐",
            chat_id=TELEGRAM_GROUPS["stats"]
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
        header += f"<i>📅 {target_date}</i>\n<i>{len(tips)} Top-Tipps · validiert ✓</i>"
        send_telegram(header, target_chat)
        
        for i, r in enumerate(tips, 1):
            msg = f"<b>💎 Tipp {i}/{len(tips)}</b>\n━━━━━━━━━━━━━━━━━━\n"
            msg += f"<b>{r.get('match','?')}</b>\n📍 {r.get('league','')}\n⏰ {r.get('time','TBD')} Uhr\n\n"
            msg += f"{icons.get(r.get('tip','?'),'')} <b>Tipp: {r.get('tip','?')}</b>\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability',0)}%</b>\n"
            msg += f"⭐ Confidence: {'⭐'*r.get('confidence',0)}\n\n"
            msg += f"💰 <b>Quote: {r.get('oddsYes','-')}</b>\n"
            msg += f"🎯 Fair Odds: {r.get('fairOdds','-')}\n"
            msg += f"{val_icons.get(r.get('valueRating','OK'),'')} Value: <b>{r.get('valueRating','OK')}</b>\n"
            if r.get('bookie'):
                msg += f"🏦 Bookie: {r.get('bookie')}\n"
            msg += f"\n📊 <b>Form</b>\n🏠 Heim: {r.get('homeForm','-')}\n✈️ Auswärts: {r.get('awayForm','-')}\n"
            if r.get('keyFactor'):
                msg += f"\n⚡ <i>{r.get('keyFactor')}</i>\n"
            reasoning = r.get('reasoning', '')[:300]
            if reasoning:
                msg += f"\n💭 <i>{reasoning}</i>"
            
            msg_id = send_telegram(msg, target_chat)
            
            tip_id = f"{market_id}_{target_date}_{i}_{abs(hash(r.get('match','')))%100000}"
            tip_data = {
                "tip_id": tip_id, "date": str(target_date),
                "market": market_id, "market_name": market_name,
                "match": r.get("match", ""), "league": r.get("league", ""),
                "time": r.get("time", ""), "tip": r.get("tip", ""),
                "probability": r.get("probability", 0), "confidence": r.get("confidence", 0),
                "odds": str(r.get("oddsYes", "0")), "fair_odds": str(r.get("fairOdds", "0")),
                "bookie": r.get("bookie", ""), "value_rating": r.get("valueRating", "OK"),
                "home_form": r.get("homeForm", ""), "away_form": r.get("awayForm", ""),
                "reasoning": r.get("reasoning", "")[:500], "key_factor": r.get("keyFactor", "")[:200],
                "telegram_chat_id": str(target_chat), "telegram_msg_id": msg_id,
                "status": "pending",
            }
            if save_to_supabase(tip_data):
                saved += 1
        
        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")
        footer = "━━━━━━━━━━━━━━━━━━\n"
        footer += f"📊 <b>Zusammenfassung</b>\n"
        footer += f"• {len(tips)} Tipps · 🔥 {value_count} Value-Bets\n"
        footer += f"<i>Viel Erfolg! 🍀</i>"
        send_telegram(footer, target_chat)
    
    log(f"💾 {saved} Tipps in Supabase gespeichert")


def main():
    log("=" * 60)
    log("AI TIPP BOT - ULTIMATE EDITION (Multi-Source)")
    log("=" * 60)
    target_date = date.today()
    log(f"Datum: {target_date}")
    log(f"Märkte: {[MARKET_INFO[m]['name'] for m in MARKETS_TO_RUN]}")
    log(f"Ligen: {len(LEAGUES_TO_RUN)}")
    log(f"Filter: ≥{MIN_PROBABILITY}% · Quote {MIN_ODDS}-{MAX_ODDS} · Conf ≥{MIN_CONFIDENCE}⭐")
    log(f"Quellen: 13×Odds + football-data + API-Football + football.json + OpenLigaDB + Understat")
    log(f"KIs: 10×Gemini + 4×Groq Fallback")
    log("")
    
    tips_by_market = {m: [] for m in MARKETS_TO_RUN}
    total_analyzed = 0
    
    for market in MARKETS_TO_RUN:
        log(f"╔══ {MARKET_INFO[market]['name']} ══╗")
        for league in LEAGUES_TO_RUN:
            log(f" → {league}")
            try:
                results, source, fixtures = analyze_market(market, league, target_date)
                if "Keine echten Spiele" in source:
                    log(f"   - Keine Spiele heute")
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
    log(f"💎 Top-Tipps: {total_top}")
    for m, tips in tips_by_market.items():
        log(f"   • {MARKET_INFO[m]['name']}: {len(tips)}")
    log("════════════════════════════════════════")
    log("Sende an Telegram + Supabase...")
    send_top_tips(tips_by_market, target_date)
    log("✓ Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        import traceback
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
