import os
import requests
import json
import time
from datetime import datetime

def env(k, d=""):
    return os.getenv(k, d)

API_KEY = env("API_FOOTBALL_KEY")
GEMINI_KEYS = env("GEMINI_API_KEYS").split(",")
TOKEN = env("TELEGRAM_TOKEN")
CHAT_ID = env("TELEGRAM_CHAT_ID")

MIN_PROB = int(env("MIN_PROBABILITY", "55"))

def log(x):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {x}", flush=True)

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except:
        pass

# ================= API =================

def get_matches():
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": API_KEY},
            params={"next": 30},
            timeout=20
        )
        return r.json().get("response", [])
    except:
        return []

# ================= AI =================

def ask_ai(home, away):
    prompt = f"""
Analysiere dieses Spiel:

{home} vs {away}

Gib NUR JSON:

[
  {{
    "tip": "YES",
    "probability": 60,
    "confidence": 4
  }}
]
"""

    for key in GEMINI_KEYS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
                json={"contents":[{"parts":[{"text":prompt}]}]},
                timeout=20
            )
            text = str(r.json())
            if "[" in text:
                start = text.find("[")
                end = text.rfind("]")
                return json.loads(text[start:end+1])
        except:
            continue
    return []

# ================= MAIN =================

def main():
    log("BOT START")

    matches = get_matches()
    log(f"Matches: {len(matches)}")

    if not matches:
        send("❌ Keine Spiele gefunden")
        return

    sent = 0

    for m in matches:
        home = m["teams"]["home"]["name"]
        away = m["teams"]["away"]["name"]

        tips = ask_ai(home, away)

        for t in tips:
            if t["tip"] != "YES":
                continue
            if int(t["probability"]) < MIN_PROB:
                continue

            msg = f"""🔥 <b>TIPP</b>

⚽ {home} vs {away}
📊 {t["probability"]}%
⭐ {t["confidence"]}/5
🎯 BTTS / OVER"""

            send(msg)
            sent += 1
            time.sleep(1)

    send(f"📊 Fertig: {sent} Tipps")

if __name__ == "__main__":
    main()
