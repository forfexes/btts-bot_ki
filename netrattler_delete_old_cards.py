#!/usr/bin/env python3
"""Loescht alte Builder-Telegram-Nachrichten (builder_id endet auf _v1), nachdem die Neuauflage gesendet wurde."""
import os, requests
U = (os.getenv("SUPABASE_URL") or "").rstrip("/")
K = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json"}
TOK = os.getenv("TELEGRAM_TOKEN") or ""
rows = requests.get(f"{U}/rest/v1/netrattler_builder_picks", headers=H, timeout=30, params={
    "select": "builder_id,telegram_msg_id,telegram_chat_id", "builder_id": "like.%_v1", "telegram_msg_id": "not.is.null",
    "limit": "200"}).json()
ok = bad = 0
for r in rows:
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TOK}/deleteMessage", timeout=15,
                             json={"chat_id": r["telegram_chat_id"], "message_id": int(r["telegram_msg_id"])})
        good = resp.ok and resp.json().get("ok")
    except Exception:
        good = False
    if good:
        ok += 1
        requests.patch(f"{U}/rest/v1/netrattler_builder_picks", headers=H, timeout=15,
                       params={"builder_id": "eq." + r["builder_id"]}, json={"telegram_msg_id": None})
    else:
        bad += 1
print(f"deleted={ok} failed={bad} total={len(rows)}")
