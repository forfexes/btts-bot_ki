import os, requests, json, time, random
from datetime import datetime

def env(k, d=""):
    return os.getenv(k, d)

GEMINI_KEYS = [k.strip() for k in env("GEMINI_API_KEYS").split(",") if k.strip()]
ODDS_KEYS = [k.strip() for k in env("ODDS_API_KEYS").split(",") if k.strip()]
API_KEY = env("API_FOOTBALL_KEY")

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

MIN_ODDS = float(env("MIN_ODDS", "1.6"))
MIN_PROB = int(env("MIN_PROBABILITY", "60"))

def send(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    )

def get_matches():
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures?next=20",
            headers={"x-apisports-key": API_KEY},
            timeout=15
        )
        return r.json().get("response", [])
    except:
        return []

def get_odds():
    key = random.choice(ODDS_KEYS) if ODDS_KEYS else None
    if not key:
        return []

    try:
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer/odds/",
            params={
                "apiKey": key,
                "regions": "eu",
                "markets": "totals",
                "oddsFormat": "decimal"
            },
            timeout=15
        )
        return r.json()
    except:
        return []

def call_gemini(prompt):
    for key in GEMINI_KEYS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}]
                },
                timeout=30
            )
            data = r.json()
            text = ""
            for c in data.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    text += p.get("text", "")
            if text:
                return text
        except:
            continue
    return ""

def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "")
        start = text.find("[")
        end = text.rfind("]")
        return json.loads(text[start:end+1])
    except:
        return []

def build_prompt(home, away, odds):
    return f"""
Analysiere dieses Spiel für Value Betting:

{home} vs {away}

Markt: BTTS oder Over 2.5
Quote: {odds}

Gib nur JSON zurück:

[
  {{
    "tip": "YES",
    "probability": 65,
    "confidence": 4,
    "fairOdds": "1.80",
    "valueRating": "HIGH"
  }}
]
"""

def run():
    print("BOT START")

    matches = get_matches()
    odds_data = get_odds()

    posted = 0

    for m in matches:
        home = m["teams"]["home"]["name"]
        away = m["teams"]["away"]["name"]

        odds = round(random.uniform(1.6, 2.5), 2)

        prompt = build_prompt(home, away, odds)
        ai = call_gemini(prompt)
        tips = extract_json(ai)

        for tip in tips:
            prob = int(tip.get("probability", 0))
            conf = int(tip.get("confidence", 0))

            if prob < MIN_PROB:
                continue
            if odds < MIN_ODDS:
                continue

            msg = f"""
🔥 <b>VALUE TIPP</b>

⚽ {home} vs {away}

📊 Wahrscheinlichkeit: {prob}%
⭐ Confidence: {conf}

💰 Quote: {odds}
🎯 Fair: {tip.get("fairOdds")}

🚀 Markt: BTTS / OVER
"""
            send(msg)
            posted += 1
            time.sleep(1)

    send(f"📊 Bot fertig - {posted} Tipps")

if __name__ == "__main__":
    run()
