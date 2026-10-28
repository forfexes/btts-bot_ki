"""Storage guard for the main Supabase project (limit 500 MB).
Reads db_size_mb() RPC. >= WARN: diag + Telegram alert (group alerts only). >= TRIM: delete old
x1_player_snapshots (regenerable shadow data) down to TRIM_KEEP_DAYS. Never touches tips/results/models."""
import os
import json
from datetime import datetime, timedelta, timezone

import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
WARN_MB = float(os.getenv("STORAGE_WARN_MB", "420"))
TRIM_MB = float(os.getenv("STORAGE_TRIM_MB", "450"))
TRIM_KEEP_DAYS = int(os.getenv("STORAGE_TRIM_KEEP_DAYS", "2"))


def decide(mb: float) -> str:
    if mb >= TRIM_MB:
        return "trim"
    if mb >= WARN_MB:
        return "warn"
    return "ok"


def trim_keep_days(mb: float) -> int:
    """Gestaffelt: je voller die DB, desto kuerzer bleiben die (regenerierbaren) x1-Snapshots erhalten."""
    if mb >= TRIM_MB + 30:  # 480+ MB (Limit 500): nur noch 1 Tag behalten
        return 1
    return TRIM_KEEP_DAYS


def alert(text: str) -> None:
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_GROUP_ALERTS")
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text}, timeout=15)
        except Exception:
            pass


def run() -> dict:
    r = requests.post(f"{SB}/rest/v1/rpc/db_size_mb", headers=H, json={}, timeout=30)
    info = {"probe": "storage_guard"}
    if not r.ok:
        info["error"] = r.text[:160]
    else:
        d = r.json()
        mb = float(d.get("mb") or 0)
        action = decide(mb)
        info.update(mb=mb, action=action, tables=d.get("tables"))
        if action == "trim":
            cut = (datetime.now(timezone.utc) - timedelta(days=trim_keep_days(mb))).isoformat()
            dr = requests.delete(f"{SB}/rest/v1/x1_player_snapshots", headers={**H, "Prefer": "return=minimal"},
                                 params={"captured_at": f"lt.{cut}"}, timeout=120)
            info["trim_status"] = dr.status_code
        if action != "ok":
            alert(f"⚠️ Supabase Hauptdatenbank {mb:.0f} MB (Limit 500). Aktion: {action}")
    if SB and KEY:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, json={"info": info}, timeout=20)
    print(json.dumps(info)[:400])
    return info


if __name__ == "__main__":
    run()
