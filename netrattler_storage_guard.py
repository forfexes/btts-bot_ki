"""Storage guard for the main Supabase project (limit 500 MB).
Reads db_size_mb() RPC. Read-only diagnostics and optional alerting only.
No automatic snapshot deletion, REINDEX, or other database maintenance."""
import os
import json
from datetime import datetime, timedelta, timezone

import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
WARN_MB = float(os.getenv("STORAGE_WARN_MB", "400"))
TRIM_MB = float(os.getenv("STORAGE_TRIM_MB", "415"))
TRIM_KEEP_DAYS = int(os.getenv("STORAGE_TRIM_KEEP_DAYS", "2"))


def decide(mb: float) -> str:
    if mb >= TRIM_MB:
        return "trim"
    if mb >= WARN_MB:
        return "warn"
    return "ok"


def trim_keep_days(mb: float) -> int:
    """Gestaffelt: je voller die DB, desto kuerzer bleiben die (regenerierbaren) x1-Snapshots erhalten."""
    if mb >= TRIM_MB + 10:  # 425+ MiB: only retain one day (430 MB reached with 2 days kept)
        return 1
    return TRIM_KEEP_DAYS


def alert(text: str) -> None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat = os.getenv("TELEGRAM_GROUP_ALERTS") or os.getenv("TELEGRAM_GROUP_STATS")
    if tok and chat and os.getenv("NETRATTLER_STORAGE_TELEGRAM","0")=="1":
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text}, timeout=15)
        except Exception:
            pass


def run() -> dict:
    if not SB or not KEY:
        raise RuntimeError("Storage guard configuration missing")
    r = requests.post(f"{SB}/rest/v1/rpc/db_size_mb", headers=H, json={}, timeout=30)
    info = {"probe": "storage_guard"}
    if not r.ok:
        raise RuntimeError(f"Storage measurement failed: HTTP {r.status_code}")
    else:
        d = r.json()
        if not isinstance(d, dict) or d.get("mb") is None:
            raise RuntimeError("Storage measurement missing mb")
        mb = float(d["mb"])
        if not (0 < mb < float("inf")):
            raise RuntimeError("Storage measurement invalid")
        action = decide(mb)
        info.update(mb=mb, action=action, tables=d.get("tables"))
        if action != "ok":
            info["maintenance"] = "manual_review_required_no_destructive_operations"
            alert(f"⚠️ Supabase Hauptdatenbank {mb:.0f} MB (Limit 500). Aktion: {action}")
    if SB and KEY:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, json={"info": info}, timeout=20)
    print(json.dumps(info)[:400])
    return info


if __name__ == "__main__":
    run()
