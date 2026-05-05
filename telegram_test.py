#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST SCRIPT - Sendet Test-Nachricht in alle Telegram Channels
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TELEGRAM_GROUPS = {
    "btts":    os.getenv("TELEGRAM_GROUP_BTTS", ""),
    "over25":  os.getenv("TELEGRAM_GROUP_OVER25", ""),
    "combo":   os.getenv("TELEGRAM_GROUP_COMBO", os.getenv("TELEGRAM_GROUP_COMBOS", "")),
    "btts_ht": os.getenv("TELEGRAM_GROUP_BTTS_HT", ""),
    "stats":   os.getenv("TELEGRAM_GROUP_STATS", ""),
}


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def send_telegram(text, chat_id=None):
    if not TELEGRAM_TOKEN:
        log("TELEGRAM_TOKEN fehlt!", "WARN")
        return False
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    if not chat_id:
        log("Chat ID fehlt!", "WARN")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.ok:
            log(f"Nachricht gesendet zu {chat_id}")
            return True
        else:
            log(f"Error: {r.status_code} - {r.text}", "ERROR")
            return False
    except Exception as e:
        log(f"Exception: {e}", "ERROR")
        return False


def main():
    log("=" * 60)
    log("TELEGRAM TEST - Alle Channels")
    log("=" * 60)

    if not TELEGRAM_TOKEN:
        log("TELEGRAM_TOKEN fehlt!", "ERROR")
        return

    log(f"Token: ***{TELEGRAM_TOKEN[-10:]}")
    log("")

    # Test Main Chat
    log("Test Main Chat...")
    send_telegram(
        f"TEST - Main Chat\nZeit: {datetime.now().strftime('%H:%M:%S')}\nVerbindung OK",
        TELEGRAM_CHAT_ID
    )
    log("")

    # Test ALLE 5 Channels
    channels = [
        ("btts",    "BTTS Channel"),
        ("over25",  "Over 2.5 Channel"),
        ("combo",   "Combo Channel"),
        ("btts_ht", "BTTS HT Channel"),
        ("stats",   "Stats Channel"),
    ]

    results = {}

    for key, name in channels:
        chat_id = TELEGRAM_GROUPS.get(key, "")
        if not chat_id:
            log(f"{name}: Keine Chat ID!", "WARN")
            results[key] = "Keine ID"
            continue

        msg = f"TEST - {name}\nChannel: {key}\nChat ID: {chat_id}\nZeit: {datetime.now().strftime('%H:%M:%S')}\nVerbindung OK"
        log(f"Test {name}...")
        success = send_telegram(msg, chat_id)
        results[key] = "OK" if success else "Error"
        log("")

    log("=" * 60)
    log("ERGEBNISSE:")
    log("=" * 60)
    log(f"Main Chat (***): OK")
    for key, result in results.items():
        chat_id = TELEGRAM_GROUPS.get(key, "***")
        log(f"{key:10s} (***): {result}")
    log("=" * 60)
    log("Test Complete!")


if __name__ == "__main__":
    main()
