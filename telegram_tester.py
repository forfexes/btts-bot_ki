"""
🤖 NETRATTLER - Telegram Tester
Testet alle Telegram Gruppen und zeigt Chat IDs
"""
import os
import requests
from datetime import datetime

# Keys aus Environment oder direkt eingeben
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = input("Telegram Bot Token eingeben: ").strip()

def send_test(chat_id, group_name):
    """Sendet Testnachricht an eine Gruppe"""
    if not chat_id:
        return False, "Kein Chat ID"
    
    msg = (
        f"🧪 <b>TELEGRAM TEST</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Gruppe: <b>{group_name}</b>\n"
        f"📅 Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🤖 Netrattler Bot aktiv!\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        if r.ok:
            return True, r.json().get("result", {}).get("message_id", "?")
        else:
            return False, r.json().get("description", "Fehler")
    except Exception as e:
        return False, str(e)

def get_bot_info():
    """Holt Bot Info"""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe",
            timeout=10,
        )
        if r.ok:
            data = r.json().get("result", {})
            print(f"\n🤖 Bot: @{data.get('username')} ({data.get('first_name')})")
            return True
        else:
            print(f"❌ Token ungültig: {r.json().get('description')}")
            return False
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return False

def get_updates():
    """Zeigt letzte Updates (Chat IDs finden)"""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            timeout=10,
        )
        if r.ok:
            updates = r.json().get("result", [])
            if not updates:
                print("\n⚠️  Keine Updates - schreib dem Bot eine Nachricht in der Gruppe!")
                return
            
            seen_chats = set()
            print("\n📋 Gefundene Chats:")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            for update in reversed(updates[-20:]):
                msg = update.get("message") or update.get("channel_post") or {}
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                chat_type = chat.get("type", "")
                chat_title = chat.get("title") or chat.get("username") or chat.get("first_name", "")
                
                if chat_id and chat_id not in seen_chats:
                    seen_chats.add(chat_id)
                    print(f"  📱 {chat_title}")
                    print(f"     ID: {chat_id}")
                    print(f"     Typ: {chat_type}")
                    print()
    except Exception as e:
        print(f"❌ Updates Error: {e}")

# ============================================================
# HAUPT TESTER
# ============================================================

print("=" * 50)
print("🧪 NETRATTLER TELEGRAM TESTER")
print("=" * 50)

# Bot Info
if not get_bot_info():
    exit(1)

# Chat IDs aus Environment
groups = {
    "BTTS Gruppe": os.getenv("TELEGRAM_GROUP_BTTS", ""),
    "Over 2.5": os.getenv("TELEGRAM_GROUP_OVER25", ""),
    "Combos": os.getenv("TELEGRAM_GROUP_COMBOS", ""),
    "BTTS HT": os.getenv("TELEGRAM_GROUP_BTTS_HT", ""),
    "Stats": os.getenv("TELEGRAM_GROUP_STATS", ""),
    "Corner Sniper": os.getenv("TELEGRAM_GROUP_HZ_LIVE", ""),
    "Goal Hunter": os.getenv("TELEGRAM_GROUP_LATE_GOALS", ""),
    "Main Chat": os.getenv("TELEGRAM_CHAT_ID", ""),
}

print("\n📤 Teste alle Gruppen:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

ok_count = 0
fail_count = 0

for name, chat_id in groups.items():
    if not chat_id:
        print(f"  ⚠️  {name}: KEIN ID in Secrets!")
        fail_count += 1
        continue
    
    success, result = send_test(chat_id, name)
    if success:
        print(f"  ✅ {name}: OK (msg_id: {result})")
        ok_count += 1
    else:
        print(f"  ❌ {name}: FEHLER - {result}")
        fail_count += 1

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  ✅ {ok_count} OK | ❌ {fail_count} Fehler")

# Chat IDs finden
print("\n🔍 Suche Chat IDs aus Updates...")
get_updates()

print("\n✅ Test abgeschlossen!")
