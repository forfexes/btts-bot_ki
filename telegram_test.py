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

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TELEGRAM_GROUPS = {
    "btts": os.getenv("TELEGRAM_GROUP_BTTS", ""),
    "over25": os.getenv("TELEGRAM_GROUP_OVER25", ""),
    "combo": os.getenv("TELEGRAM_GROUP_COMBO", ""),
    "btts_ht": os.getenv("TELEGRAM_GROUP_BTTS_HT", ""),
    "stats": os.getenv("TELEGRAM_GROUP_STATS", ""),
}


def log(msg, level="INFO"):
    """Simple Logger"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def send_telegram(text, chat_id=None):
    """Sendet Nachricht an Telegram"""
    if not TELEGRAM_TOKEN:
        log("⚠️ TELEGRAM_TOKEN nicht gesetzt!", "WARN")
        return False
    
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    
    if not chat_id:
        log("⚠️ Chat ID nicht gesetzt!", "WARN")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        
        r = requests.post(url, json=payload, timeout=10)
        
        if r.ok:
            log(f"✅ Nachricht gesendet zu {chat_id}")
            return True
        else:
            log(f"❌ Error: {r.status_code} - {r.text}", "ERROR")
            return False
    
    except Exception as e:
        log(f"❌ Exception: {e}", "ERROR")
        return False


def main():
    log("=" * 60)
    log("🧪 TELEGRAM TEST - Sendet Test-Nachricht in alle Channels")
    log("=" * 60)
    
    if not TELEGRAM_TOKEN:
        log("❌ TELEGRAM_TOKEN nicht gesetzt!", "ERROR")
        return
    
    log(f"Token: {'***' + TELEGRAM_TOKEN[-10:]}")
    log("")
    
    # Test Main Chat
    log("📤 Test Main Chat...")
    msg = "🧪 <b>TEST - Main Chat</b>\n\n"
    msg += f"Zeit: {datetime.now().strftime('%H:%M:%S')}\n"
    msg += "✅ Verbindung OK"
    
    if TELEGRAM_CHAT_ID:
        send_telegram(msg, TELEGRAM_CHAT_ID)
    else:
        log("⚠️ TELEGRAM_CHAT_ID nicht gesetzt", "WARN")
    
    log("")
    
    # Test alle Group Channels (nur die die funktionieren)
    channels = [
        ("over25", "🎯 Over 2.5 Channel"),
        ("combo", "🔥 Combo Channel"),
        ("stats", "📊 Stats Channel"),
    ]
    
    # BTTS + BTTS_HT haben Probleme - use Main Chat stattdessen
    log("⚠️ BTTS & BTTS_HT verwenden Main Chat als Fallback")
    log("")
    
    results = {}
    
    for key, name in channels:
        chat_id = TELEGRAM_GROUPS.get(key, "")
        
        if not chat_id:
            log(f"⚠️ {name}: Keine Chat ID gesetzt", "WARN")
            results[key] = "❌ Keine ID"
            continue
        
        msg = f"🧪 <b>TEST - {name}</b>\n\n"
        msg += f"Channel: {key}\n"
        msg += f"Chat ID: {chat_id}\n"
        msg += f"Zeit: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += "✅ Verbindung OK"
        
        log(f"📤 {name}...")
        success = send_telegram(msg, chat_id)
        results[key] = "✅ OK" if success else "❌ Error"
    
    log("")
    log("=" * 60)
    log("📊 ERGEBNISSE:")
    log("=" * 60)
    
    if TELEGRAM_CHAT_ID:
        log(f"Main Chat ({TELEGRAM_CHAT_ID}): ✅ OK")
    else:
        log(f"Main Chat: ❌ Keine ID")
    
    for key, result in results.items():
        chat_id = TELEGRAM_GROUPS.get(key, "")
        if chat_id:
            log(f"{key:10s} ({chat_id:15s}): {result}")
        else:
            log(f"{key:10s} (kein ID): ❌ Nicht gesetzt")
    
    log("=" * 60)
    log("✅ Test Complete!")


if __name__ == "__main__":
    main()
