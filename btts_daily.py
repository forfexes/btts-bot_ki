import os
import json
import time
import requests
from datetime import datetime, timezone

def env(name, default=""):
    return os.getenv(name, default).strip()

def env_list(name):
    return [x.strip() for x in env(name).split(",") if x.strip()]

GEMINI_API_KEYS = env_list("GEMINI_API_KEYS")
API_FOOTBALL_KEY = env("API_FOOTBALL_KEY")
TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

MIN_PROBABILITY = int(env("MIN_PROBABILITY", "55"))
MIN_CONFIDENCE = int(env("MIN_CONFIDENCE", "3"))
MAX_MATCHES = int(env("MAX_MATCHES", "25"))
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")
MARKETS_TO_RUN = [x.strip() for x in env("MARKETS_TO_RUN", "btts,over25,combo,btts_ht").split(",") if x.strip()]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM_TOKEN oder TELEGRAM_CHAT_ID fehlt")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=20,
        )
        if not r.ok:
            log(f"Telegram Fehler: {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as e:
        log(f"Telegram Exception: {e}")
        return False

def fetch_today_fixtures():
    if not API_FOOTBALL_KEY:
        log("API_FOOTBALL_KEY fehlt")
        return []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"},
            params={"date": today},
            timeout=25,
        )
        if not r.ok:
            log(f"API-Football Fehler: {r.status_code} {r.text[:200]}")
            return []
        now = datetime.now(timezone.utc)
        fixtures = []
        for item in r.json().get("response", []):
            fixture = item.get("fixture", {})
            status = fixture.get("status", {}).get("short", "")
            kickoff_raw = fixture.get("date", "")
            if status not in ["NS", "TBD"]:
                continue
            try:
                kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
                if kickoff < now:
                    continue
            except Exception:
                pass
            league = item.get("league", {})
            teams = item.get("teams", {})
            home = teams.get("home", {}).get("name", "")
            away = teams.get("away", {}).get("name", "")
            if home and away:
                fixtures.append({
                    "league": league.get("name", ""),
                    "country": league.get("country", ""),
                    "home": home,
                    "away": away,
                    "time": kickoff_raw,
                })
        return fixtures[:MAX_MATCHES]
    except Exception as e:
        log(f"API-Football Exception: {e}")
        return []

def call_gemini(prompt):
    if not GEMINI_API_KEYS:
        log("GEMINI_API_KEYS fehlt")
        return ""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4000},
    }
    for idx, key in enumerate(GEMINI_API_KEYS, start=1):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload,
                timeout=60,
            )
            data = r.json()
            if "error" in data:
                log(f"Gemini #{idx} Fehler: {data['error'].get('message','')[:120]}")
                continue
            text = ""
            for c in data.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    text += p.get("text", "")
            if text.strip():
                return text.strip()
        except Exception as e:
            log(f"Gemini #{idx} Exception: {e}")
    return ""

def extract_json_array(text):
    if not text:
        return []
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    except Exception as e:
        log(f"JSON Fehler: {e}")
    return []

def market_name(market):
    return {
        "btts": "BTTS - beide Teams treffen im Spiel",
        "over25": "Over 2.5 Tore",
        "combo": "BTTS + Over 2.5 Combo",
        "btts_ht": "1. Halbzeit BTTS - beide Teams treffen in Halbzeit 1",
    }.get(market, market)

def build_prompt(match, market):
    return f"""
Du bist Fußball-Wettanalyst.

Analysiere NUR dieses Spiel:
Liga: {match['league']}
Land: {match['country']}
Spiel: {match['home']} vs {match['away']}
Markt: {market_name(market)}

WICHTIG:
- Erfinde keine Teams.
- Antworte NUR als JSON Array.
- Wenn kein guter Tipp: [].
- tip muss YES sein, wenn du den Tipp empfiehlst.
- probability realistisch 50-80.
- confidence 1-5.
- valueRating HIGH nur bei gutem Value.

Format:
[
  {{
    "match": "{match['home']} vs {match['away']}",
    "league": "{match['league']}",
    "time": "TBD",
    "tip": "YES",
    "probability": 62,
    "confidence": 4,
    "oddsYes": "1.80",
    "fairOdds": "1.65",
    "bookie": "N/A",
    "valueRating": "HIGH",
    "keyFactor": "Warum dieser Tipp gut ist",
    "reasoning": "Kurze Begründung."
  }}
]
"""

def is_good_tip(tip):
    if not isinstance(tip, dict):
        return False
    if tip.get("tip") != "YES":
        return False
    try:
        prob = int(tip.get("probability", 0))
    except Exception:
        prob = 0
    try:
        conf = int(tip.get("confidence", 0))
    except Exception:
        conf = 0
    if prob < MIN_PROBABILITY:
        return False
    if conf < MIN_CONFIDENCE:
        return False
    if str(tip.get("valueRating", "")).upper() != "HIGH":
        return False
    return True

def format_tip(tip, market):
    icons = {"btts": "⚽ BTTS", "over25": "🎯 Over 2.5", "combo": "🔥 Combo", "btts_ht": "⏱️ 1H BTTS"}
    return f"""<b>{icons.get(market, market)} VALUE TIPP</b>
━━━━━━━━━━━━━━━━━━
<b>{tip.get('match','?')}</b>
📍 {tip.get('league','?')}

✅ Tipp: <b>{tip.get('tip')}</b>
📈 Wahrscheinlichkeit: <b>{tip.get('probability')}%</b>
⭐ Confidence: <b>{tip.get('confidence')}</b>

💰 Quote: <b>{tip.get('oddsYes','-')}</b>
🎯 Fair Odds: <b>{tip.get('fairOdds','-')}</b>
🔥 Value: <b>{tip.get('valueRating','HIGH')}</b>

⚡ <i>{tip.get('keyFactor','')}</i>
💭 <i>{tip.get('reasoning','')}</i>

⏳ <b>Status: PENDING</b>"""

def main():
    log("AI TIPP BOT START")
    send_telegram("✅ <b>Bot gestartet</b>\nIch suche jetzt Value Tipps...")
    fixtures = fetch_today_fixtures()
    log(f"Fixtures gefunden: {len(fixtures)}")
    if not fixtures:
        send_telegram("ℹ️ Keine kommenden Spiele gefunden oder API-Football liefert keine Daten.")
        return
    posted = 0
    checked = 0
    for match in fixtures:
        for market in MARKETS_TO_RUN:
            checked += 1
            ai_text = call_gemini(build_prompt(match, market))
            tips = extract_json_array(ai_text)
            if not tips:
                log(f"Kein Tipp: {market} {match['home']} vs {match['away']}")
                continue
            for tip in tips:
                tip["match"] = f"{match['home']} vs {match['away']}"
                tip["league"] = match["league"]
                if not is_good_tip(tip):
                    continue
                send_telegram(format_tip(tip, market))
                posted += 1
                log(f"POSTED: {market} {tip['match']}")
                time.sleep(1)
            time.sleep(1)
    send_telegram(f"📊 <b>Bot fertig</b>\nGeprüft: <b>{checked}</b>\nNeue Tipps: <b>{posted}</b>")
    log(f"FERTIG checked={checked} posted={posted}")

if __name__ == "__main__":
    main()
