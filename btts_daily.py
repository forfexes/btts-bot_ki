"""
AI TIPP BOT - FINAL FREE VALUE VERSION
======================================

Datei-Name in GitHub: btts_daily.py

Features:
- GitHub Secrets only
- keine .env nötig
- Auto League Switch
- weniger API Calls
- Groq optional, standard AUS
- Duplikat-Schutz
- keine alten Tipps erneut
- 1X2 raus
- 1H BTTS rein
- Youth/Goal-Ligen
- Free Value Engine
"""

import os
import re
import sys
import json
import time
import traceback
from datetime import date, datetime, timedelta, timezone

import requests


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

GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = env("GROQ_MODEL", "llama-3.3-70b-versatile")

MARKETS_TO_RUN = [
    x.strip()
    for x in env("MARKETS_TO_RUN", "btts,over25,combo,btts_ht").split(",")
    if x.strip()
]

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "62"))
MIN_ODDS = float(env("MIN_ODDS", "1.60"))
MAX_ODDS = float(env("MAX_ODDS", "3.20"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "4"))

MIN_PROBABILITY_BTTS_HT = int(env("MIN_PROBABILITY_BTTS_HT", "60"))
MIN_ODDS_BTTS_HT = float(env("MIN_ODDS_BTTS_HT", "1.80"))
MAX_ODDS_BTTS_HT = float(env("MAX_ODDS_BTTS_HT", "3.80"))

MIN_VALUE_EDGE_PCT = float(env("MIN_VALUE_EDGE_PCT", "6.0"))
REQUIRE_HIGH_VALUE = env("REQUIRE_HIGH_VALUE", "true").lower() in ["1", "true", "yes", "on"]
VALUE_SCORE_MIN = float(env("VALUE_SCORE_MIN", "65"))

AUTO_LEAGUE_SWITCH = env("AUTO_LEAGUE_SWITCH", "true").lower() in ["1", "true", "yes", "on"]
AUTO_LEAGUE_MIN_TIPS = int(env("AUTO_LEAGUE_MIN_TIPS", "10"))
AUTO_LEAGUE_MIN_WINRATE = float(env("AUTO_LEAGUE_MIN_WINRATE", "48"))
AUTO_LEAGUE_MIN_ROI = float(env("AUTO_LEAGUE_MIN_ROI", "-2.0"))
AUTO_LEAGUE_LOOKBACK_DAYS = int(env("AUTO_LEAGUE_LOOKBACK_DAYS", "120"))

MAX_LEAGUES_PER_RUN = int(env("MAX_LEAGUES_PER_RUN", "20"))
AI_SLEEP_SECONDS = float(env("AI_SLEEP_SECONDS", "1.5"))
GROQ_SLEEP_SECONDS = float(env("GROQ_SLEEP_SECONDS", "2.5"))
USE_GROQ_FALLBACK = env("USE_GROQ_FALLBACK", "false").lower() in ["1", "true", "yes", "on"]

ALWAYS_ON_LEAGUES = [
    x.strip()
    for x in env(
        "ALWAYS_ON_LEAGUES",
        "Premier League,Bundesliga,2. Bundesliga,Eredivisie,Serie A,La Liga,Ligue 1"
    ).split(",")
    if x.strip()
]

ALWAYS_OFF_LEAGUES = [
    x.strip()
    for x in env("ALWAYS_OFF_LEAGUES", "").split(",")
    if x.strip()
]


# ============================================================
# LIGEN
# ============================================================

LEAGUES_TO_RUN = [
    "Champions League",
    "Europa League",
    "Conference League",

    "Bundesliga",
    "2. Bundesliga",
    "Premier League",
    "Championship",
    "La Liga",
    "La Liga 2",
    "Serie A",
    "Serie B",
    "Ligue 1",
    "Ligue 2",
    "Eredivisie",
    "Primeira Liga",
    "Pro League Belgien",
    "Süper Lig",
    "Bundesliga Österreich",
    "Super League Schweiz",
    "Scottish Premiership",

    "Danish Superliga",
    "Norway Eliteserien",
    "Sweden Allsvenskan",
    "Greece Super League",
    "Croatia HNL",
    "Serbia SuperLiga",
    "Romania Liga I",
    "Czech First League",
    "Poland Ekstraklasa",
    "Slovak Super Liga",

    "MLS",
    "Brasileirao Serie A",
    "Liga Argentinien",
    "Liga MX",
    "A-League",
    "K League 1",
    "J1 League Japan",
    "China Super League",
    "Saudi Pro League",

    # Youth / Reserve / Goal Leagues
    "England Premier League 2",
    "England Professional Development League",
    "Italy Campionato Primavera - 1",
    "Italy Campionato Primavera - 2",
    "Poland Central Youth League",
    "Ukraine U19 League",
    "Ukraine U21 League",
    "Mexico Liga MX U23",
    "Mexico Liga MX U21",
    "Mexico U20 League",
    "Algeria U21 League 1",
    "UAE Pro League U23",

    # Extra Goal Leagues
    "England League One",
    "England League Two",
    "England National League",
    "Netherlands Eerste Divisie",
    "Germany 3. Liga",
    "Austria 2. Liga",
    "Switzerland Challenge League",
    "Belgium Challenger Pro League",
    "Denmark 1st Division",
    "Norway 1st Division",
    "Sweden Superettan",
    "Finland Veikkausliiga",
    "Ireland Premier Division",
    "Iceland Urvalsdeild",
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
}# ============================================================
# UTILS
# ============================================================

def log(msg: str, level: str = "INFO"):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{level}] {msg}")


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def parse_odds(value):
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return 0.0


# ============================================================
# VALUE ENGINE (WICHTIG)
# ============================================================

def calculate_value_edge_pct(odds_yes, fair_odds):
    odds = parse_odds(odds_yes)
    fair = parse_odds(fair_odds)

    if odds <= 1.0 or fair <= 1.0:
        return 0.0

    return round(((odds / fair) - 1.0) * 100, 1)


def calculate_value_score(tip):
    probability = safe_int(tip.get("probability", 0))
    confidence = safe_int(tip.get("confidence", 0))
    edge = calculate_value_edge_pct(tip.get("oddsYes"), tip.get("fairOdds"))

    high_bonus = 8 if str(tip.get("valueRating", "")).upper() == "HIGH" else 0

    score = probability * 0.65 + confidence * 6 + edge * 1.4 + high_bonus
    return round(score, 1)


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str, chat_id: str):
    if not TELEGRAM_TOKEN or not chat_id:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
    except Exception as e:
        log(f"Telegram Fehler: {e}", "WARN")


# ============================================================
# API FOOTBALL (SPIELE)
# ============================================================

def fetch_matches_today():
    if not API_FOOTBALL_KEY:
        return []

    today = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={
                "x-rapidapi-key": API_FOOTBALL_KEY,
                "x-rapidapi-host": "v3.football.api-sports.io",
            },
            params={"date": today},
            timeout=20,
        )

        if not r.ok:
            return []

        data = r.json().get("response", [])

        matches = []

        for m in data:
            league = m.get("league", {}).get("name", "")
            home = m.get("teams", {}).get("home", {}).get("name", "")
            away = m.get("teams", {}).get("away", {}).get("name", "")
            time_str = m.get("fixture", {}).get("date", "")

            matches.append({
                "league": league,
                "home": home,
                "away": away,
                "time": time_str,
            })

        return matches

    except Exception as e:
        log(f"API Football Fehler: {e}", "WARN")
        return []# ============================================================
# THE ODDS API
# ============================================================

def get_odds_key():
    for key in ODDS_API_KEYS:
        if key.strip():
            return key.strip()
    return None


def fetch_odds_for_soccer():
    key = get_odds_key()
    if not key:
        return []

    all_odds = []

    sports = [
        "soccer_epl",
        "soccer_germany_bundesliga",
        "soccer_germany_bundesliga2",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_netherlands_eredivisie",
        "soccer_sweden_allsvenskan",
        "soccer_norway_eliteserien",
        "soccer_denmark_superliga",
    ]

    for sport in sports:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h,totals",
                    "oddsFormat": "decimal",
                },
                timeout=20,
            )

            if not r.ok:
                continue

            all_odds.extend(r.json())
            time.sleep(0.4)

        except Exception as e:
            log(f"Odds Fehler {sport}: {e}", "WARN")

    return all_odds


def find_match_odds(home, away, odds_data):
    home_n = home.lower()
    away_n = away.lower()

    for game in odds_data:
        gh = game.get("home_team", "").lower()
        ga = game.get("away_team", "").lower()

        if home_n in gh or gh in home_n:
            if away_n in ga or ga in away_n:
                return game

    return None


def extract_best_over25_odds(game):
    best = 0.0
    bookie = ""

    if not game:
        return best, bookie

    for bm in game.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != "totals":
                continue

            for outcome in market.get("outcomes", []):
                if outcome.get("name") == "Over" and outcome.get("point") == 2.5:
                    price = parse_odds(outcome.get("price"))
                    if price > best:
                        best = price
                        bookie = bm.get("title", "")

    return best, bookie


def extract_h2h_odds(game):
    if not game:
        return {}

    result = {}

    for bm in game.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):
                result[outcome.get("name")] = outcome.get("price")

    return result


# ============================================================
# GEMINI AI
# ============================================================

def call_gemini(prompt):
    if not GEMINI_API_KEYS:
        return None

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 6000,
        }
    }

    for key in GEMINI_API_KEYS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload,
                timeout=60,
            )

            data = r.json()

            if "error" in data:
                continue

            text = ""
            for c in data.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    text += p.get("text", "")

            if text.strip():
                return text

        except Exception as e:
            log(f"Gemini Fehler: {e}", "WARN")
            continue

    return None


def extract_json(text):
    if not text:
        return []

    text = text.replace("```json", "").replace("```", "").strip()

    try:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
    except Exception:
        return []

    return []


def build_prompt(match, market, odds, bookie):
    league = match.get("league", "")
    home = match.get("home", "")
    away = match.get("away", "")

    if market == "btts_ht":
        market_text = "1. Halbzeit BTTS: beide Teams treffen in der ersten Halbzeit."
    elif market == "btts":
        market_text = "BTTS: beide Teams treffen im Spiel."
    elif market == "over25":
        market_text = "Over 2.5 Tore im Spiel."
    else:
        market_text = "BTTS + Over 2.5 Combo."

    return f"""
Du bist professioneller Fußball Value-Betting Analyst.

Analysiere NUR dieses Spiel:

Liga: {league}
Spiel: {home} vs {away}
Markt: {market_text}
Beste Quote: {odds}
Bookie: {bookie}

Regeln:
- Antworte NUR als JSON Array.
- Keine erfundenen Spiele.
- Tip nur YES wenn wirklich Value.
- valueRating nur HIGH wenn echte Value-Chance besteht.
- fairOdds muss realistisch sein.
- probability muss realistisch sein.
- reasoning maximal 2 Sätze.

Format:
[
  {{
    "match": "{home} vs {away}",
    "league": "{league}",
    "time": "TBD",
    "tip": "YES",
    "probability": 64,
    "confidence": 4,
    "fairOdds": "1.80",
    "oddsYes": "{odds}",
    "oddsNo": "-",
    "bookie": "{bookie}",
    "homeForm": "-",
    "awayForm": "-",
    "valueRating": "HIGH",
    "keyFactor": "Kurzer Faktor",
    "reasoning": "Kurze Begründung."
  }}
]
# ============================================================
# SUPABASE
# ============================================================

def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def tip_exists_today(match_name, market, tip):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    today = date.today().isoformat()

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers=supabase_headers(),
            params={
                "select": "tip_id",
                "date": f"eq.{today}",
                "match": f"eq.{match_name}",
                "market": f"eq.{market}",
                "tip": f"eq.{tip}",
                "limit": "1",
            },
            timeout=10,
        )

        if not r.ok:
            return False

        return len(r.json()) > 0

    except Exception:
        return False


def save_tip(tip_data):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers=supabase_headers(),
            json=tip_data,
            timeout=10,
        )
        return r.ok

    except Exception as e:
        log(f"Supabase Save Fehler: {e}", "WARN")
        return False


# ============================================================
# FILTER
# ============================================================

def is_good_value_tip(tip, market):
    if not tip:
        return False

    if tip.get("tip") != "YES":
        return False

    probability = safe_int(tip.get("probability", 0))
    confidence = safe_int(tip.get("confidence", 0))
    odds = parse_odds(tip.get("oddsYes", 0))
    fair = parse_odds(tip.get("fairOdds", 0))

    if market == "btts_ht":
        if probability < MIN_PROBABILITY_BTTS_HT:
            return False
        if odds < MIN_ODDS_BTTS_HT or odds > MAX_ODDS_BTTS_HT:
            return False
    else:
        if probability < MIN_PROBABILITY:
            return False
        if odds < MIN_ODDS or odds > MAX_ODDS:
            return False

    if confidence < MIN_CONFIDENCE:
        return False

    edge = calculate_value_edge_pct(odds, fair)
    score = calculate_value_score(tip)

    tip["valueEdgePct"] = edge
    tip["valueScore"] = score

    if edge < MIN_VALUE_EDGE_PCT:
        return False

    if REQUIRE_HIGH_VALUE and str(tip.get("valueRating", "")).upper() != "HIGH":
        return False

    if score < VALUE_SCORE_MIN:
        return False

    return True


# ============================================================
# POSTING
# ============================================================

def format_tip_message(tip, market):
    market_names = {
        "btts": "⚽ BTTS",
        "over25": "🎯 Over 2.5",
        "combo": "🔥 Combo",
        "btts_ht": "⏱️ 1H BTTS",
    }

    msg = f"<b>{market_names.get(market, market)} VALUE TIPP</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>{tip.get('match')}</b>\n"
    msg += f"📍 {tip.get('league')}\n\n"
    msg += f"✅ Tipp: <b>{tip.get('tip')}</b>\n"
    msg += f"📈 Wahrscheinlichkeit: <b>{tip.get('probability')}%</b>\n"
    msg += f"⭐ Confidence: <b>{tip.get('confidence')}</b>\n\n"
    msg += f"💰 Quote: <b>{tip.get('oddsYes')}</b>\n"
    msg += f"🎯 Fair Odds: <b>{tip.get('fairOdds')}</b>\n"
    msg += f"📊 Edge: <b>{tip.get('valueEdgePct')}%</b>\n"
    msg += f"🔥 Value Score: <b>{tip.get('valueScore')}</b>\n"
    msg += f"🏦 Bookie: {tip.get('bookie', '-')}\n\n"
    msg += f"⚡ <i>{tip.get('keyFactor', '')}</i>\n"
    msg += f"💭 <i>{tip.get('reasoning', '')}</i>\n\n"
    msg += "⏳ <b>Status: PENDING</b>"

    return msg


def post_and_save_tip(tip, market):
    match_name = tip.get("match")
    tip_value = tip.get("tip")

    if tip_exists_today(match_name, market, tip_value):
        log(f"Duplikat übersprungen: {market} {match_name}")
        return False

    chat_id = TELEGRAM_GROUPS.get(market, TELEGRAM_CHAT_ID)

    message = format_tip_message(tip, market)

    msg_id = None

    if TELEGRAM_TOKEN and chat_id:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )

            if r.ok:
                msg_id = r.json().get("result", {}).get("message_id")

        except Exception as e:
            log(f"Telegram Post Fehler: {e}", "WARN")

    tip_id = f"{market}_{date.today()}_{abs(hash(match_name + tip_value)) % 100000000}"

    tip_data = {
        "tip_id": tip_id,
        "date": date.today().isoformat(),
        "market": market,
        "market_name": market,
        "match": match_name,
        "league": tip.get("league", ""),
        "time": tip.get("time", ""),
        "tip": tip_value,
        "probability": tip.get("probability", 0),
        "confidence": tip.get("confidence", 0),
        "odds": str(tip.get("oddsYes", "0")),
        "fair_odds": str(tip.get("fairOdds", "0")),
        "bookie": tip.get("bookie", ""),
        "value_rating": tip.get("valueRating", "HIGH"),
        "home_form": tip.get("homeForm", ""),
        "away_form": tip.get("awayForm", ""),
        "reasoning": tip.get("reasoning", "")[:500],
        "key_factor": tip.get("keyFactor", "")[:200],
        "telegram_chat_id": str(chat_id),
        "telegram_msg_id": msg_id,
        "status": "pending",
    }

    save_tip(tip_data)


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 60)
    log("AI TIPP BOT - FINAL FREE VALUE VERSION")
    log("=" * 60)

    if not GEMINI_API_KEYS:
        log("GEMINI_API_KEYS fehlt", "WARN")
    if not API_FOOTBALL_KEY:
        log("API_FOOTBALL_KEY fehlt", "WARN")
    if not ODDS_API_KEYS:
        log("ODDS_API_KEYS fehlt", "WARN")
    if not TELEGRAM_TOKEN:
        log("TELEGRAM_TOKEN fehlt", "WARN")
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("SUPABASE fehlt", "WARN")

    matches = fetch_matches_today()
    odds_data = fetch_odds_for_soccer()

    log(f"Spiele gefunden: {len(matches)}")
    log(f"Odds Spiele gefunden: {len(odds_data)}")

    if not matches:
        send_telegram("ℹ️ Heute keine Spiele gefunden.", TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID))
        return

    posted = 0
    checked = 0

    allowed_markets = MARKETS_TO_RUN

    for match in matches:
        league = match.get("league", "")
        home = match.get("home", "")
        away = match.get("away", "")

        if not home or not away:
            continue

        match_name = f"{home} vs {away}"

        # Nur interessante Ligen checken, aber Youth/Goal Ligen nicht hart blocken
        if MAX_LEAGUES_PER_RUN > 0 and checked > MAX_LEAGUES_PER_RUN * 10:
            break

        game_odds = find_match_odds(home, away, odds_data)
        over25_odds, bookie = extract_best_over25_odds(game_odds)

        # Wenn keine Quote vorhanden ist, überspringen
        # Ausnahme: Youth Ligen dürfen trotzdem via AI geschätzt werden, aber mit Standardquote
        is_youth_or_goal = any(x in league.lower() for x in [
            "u19", "u20", "u21", "u23", "youth", "primavera",
            "development", "reserve", "2. liga", "3. liga",
            "eerste", "superettan", "1st division"
        ])

        if over25_odds <= 0 and not is_youth_or_goal:
            continue

        if over25_odds <= 0:
            over25_odds = 2.05
            bookie = "AI/No Odds"

        for market in allowed_markets:
            checked += 1

            # Market-spezifische Quote
            if market == "btts_ht":
                market_odds = max(over25_odds + 0.25, MIN_ODDS_BTTS_HT)
            elif market == "combo":
                market_odds = max(over25_odds + 0.15, MIN_ODDS)
            else:
                market_odds = max(over25_odds, MIN_ODDS)

            prompt = build_prompt(match, market, market_odds, bookie)
            ai_text = call_gemini(prompt)
            tips = extract_json(ai_text)

            if not tips:
                log(f"Keine AI Tipps: {market} {match_name}")
                continue

            for tip in tips:
                if not isinstance(tip, dict):
                    continue

                # Sicherheit: Match korrekt setzen
                tip["match"] = match_name
                tip["league"] = league
                tip["oddsYes"] = str(tip.get("oddsYes", market_odds))
                tip["bookie"] = tip.get("bookie", bookie)

                if not is_good_value_tip(tip, market):
                    continue

                if post_and_save_tip(tip, market):
                    posted += 1
                    log(f"POSTED: {market} {match_name}")

            time.sleep(AI_SLEEP_SECONDS)

    summary = (
        f"<b>🤖 Bot Run fertig</b>\n\n"
        f"Geprüfte Spiele/Märkte: <b>{checked}</b>\n"
        f"Neue Value Tipps: <b>{posted}</b>\n"
        f"Filter: HIGH Value · Edge ≥ {MIN_VALUE_EDGE_PCT}% · Score ≥ {VALUE_SCORE_MIN}"
    )

    send_telegram(summary, TELEGRAM_GROUPS.get("stats", TELEGRAM_CHAT_ID))

    log("=" * 60)
    log(f"Fertig. Posted={posted}, Checked={checked}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
