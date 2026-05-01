import os
import requests
from datetime import datetime

def env(k):
    return os.getenv(k)

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except:
        pass

def run():
    now = datetime.now().strftime("%d.%m %H:%M")
    send(f"📊 <b>Checker läuft</b>\n⏱ {now}\n\n(Ergebnisse folgen später automatisch)")

if __name__ == "__main__":
    run()
