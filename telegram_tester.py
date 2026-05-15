"""
🤖 NETRATTLER - Telegram Tester
"""
import os
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

def send_test(chat_id, group_name):
    if not chat_id:
        return False, "Kein Chat ID"
    
    msg = (
        f"🧪 <b>TELEGRAM TEST</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Gruppe: <b>{group_name}</b>\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🤖 Netrattler Bot aktiv!\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.ok:
            return True, r.json().get("result", {}).get("message_id", "?")
        else:
            return False, r.json().get("description", "Fehler")
    except Exception as e:
        return False, str(e)

def get_bot_info():
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=10)
        if r.ok:
            data = r.json().get("result", {})
            print(f"\n🤖 Bot: @{data.get('username')} ({data.get('first_name')})")
            return True
        print(f"❌ Token ungültig!")
        return False
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return False

def get_updates():
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", timeout=10)
        if r.ok:
            updates = r.json().get("result", [])
            if not updates:
                print("\n⚠️  Keine Updates - schreib dem Bot eine Nachricht!")
                return
            seen = set()
            print("\n📋 Gefundene Chats:")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            for update in reversed(updates[-30:]):
                msg = update.get("message") or update.get("channel_post") or update.get("my_chat_member", {}).get("chat", {})
                if isinstance(msg, dict) and "chat" in msg:
                    chat = msg.get("chat", {})
                elif isinstance(msg, dict) and "id" in msg:
                    chat = msg
                else:
                    continue
                chat_id = chat.get("id")
                chat_title = chat.get("title") or chat.get("username") or chat.get("first_name", "")
                chat_type = chat.get("type", "")
                if chat_id and chat_id not in seen:
                    seen.add(chat_id)
                    print(f"  📱 {chat_title}")
                    print(f"     ID: {chat_id}")
                    print(f"     Typ: {chat_type}")
                    print()
    except Exception as e:
        print(f"❌ Updates Error: {e}")

print("=" * 50)
print("🧪 NETRATTLER TELEGRAM TESTER")
print("=" * 50)

if not get_bot_info():
    exit(1)

# Alle Gruppen inkl. BTTS+2.5
groups = {
    "BTTS Gruppe":    os.getenv("TELEGRAM_GROUP_BTTS", ""),
    "Over 2.5":       os.getenv("TELEGRAM_GROUP_OVER25", ""),
    "BTTS +2.5":      os.getenv("TELEGRAM_GROUP_COMBO", "") or os.getenv("TELEGRAM_GROUP_COMBOS", ""),
    "Combos":         os.getenv("TELEGRAM_GROUP_COMBOS", ""),
    "BTTS HT":        os.getenv("TELEGRAM_GROUP_BTTS_HT", ""),
    "Stats":          os.getenv("TELEGRAM_GROUP_STATS", ""),
    "Corner Sniper":  os.getenv("TELEGRAM_GROUP_HZ_LIVE", ""),
    "Goal Hunter":    os.getenv("TELEGRAM_GROUP_LATE_GOALS", ""),
    "Main Chat":      os.getenv("TELEGRAM_CHAT_ID", ""),
}

print("\n📤 Teste alle Gruppen:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

ok = 0
fail = 0
for name, chat_id in groups.items():
    if not chat_id:
        print(f"  ⚠️  {name}: KEIN ID! (Secret fehlt)")
        fail += 1
        continue
    success, result = send_test(chat_id, name)
    if success:
        print(f"  ✅ {name}: OK (ID: {chat_id}, msg: {result})")
        ok += 1
    else:
        print(f"  ❌ {name}: FEHLER - {result}")
        print(f"     Chat ID war: {chat_id}")
        fail += 1

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  ✅ {ok} OK | ❌ {fail} Fehler")

get_updates()
print("\n✅ Test abgeschlossen!")
