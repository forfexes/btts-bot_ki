"""Einmaliges Aufraeumen: Telegram-Nachrichten fehlerhafter Tipps loeschen und die Tipps als ungueltig (void) markieren.
Auswahl per Umgebungsvariablen (Zeitfenster, Maerkte, Wahrscheinlichkeitsbereich, reasoning-Muster). DRY_RUN=1 zaehlt nur.
Tipp-Zeilen bleiben in der Datenbank (status/result = void), damit sie nicht in die Statistik einfliessen."""
import json
import os
import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}
FROM, TO = os.getenv("CLEAN_FROM"), os.getenv("CLEAN_TO")
MARKETS = os.getenv("CLEAN_MARKETS", "over25,btts")
PMIN, PMAX = os.getenv("CLEAN_PROB_MIN", "67"), os.getenv("CLEAN_PROB_MAX", "69")
REASON = os.getenv("CLEAN_REASONING", "Markt-Analyse*")
DRY = os.getenv("DRY_RUN", "1") == "1"


def main():
    if not (SB and SK and FROM and TO):
        print("missing config")
        return
    rows = []
    off = 0
    while True:
        r = requests.get(f"{SB}/rest/v1/tips", headers={**H, "Range": f"{off}-{off + 999}"}, timeout=40, params=[
            ("select", "id,telegram_chat_id,telegram_msg_id,status,market"),
            ("created_at", f"gte.{FROM}"), ("created_at", f"lte.{TO}"),
            ("market", f"in.({MARKETS})"), ("probability", f"gte.{PMIN}"), ("probability", f"lte.{PMAX}"),
            ("reasoning", f"like.{REASON}"), ("status", "eq.pending")])
        if not r.ok:
            print("select failed", r.status_code)
            return
        part = r.json()
        rows += part
        if len(part) < 1000:
            break
        off += 1000
    info = {"probe": "tg_cleanup", "selected": len(rows), "dry_run": DRY, "deleted": 0, "failed": 0, "voided": 0, "db_failed": 0}
    if not DRY:
        for t in rows:
            ok = False
            if TOKEN and t.get("telegram_chat_id") and t.get("telegram_msg_id"):
                try:
                    d = requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteMessage", timeout=20,
                                      json={"chat_id": t["telegram_chat_id"], "message_id": t["telegram_msg_id"]})
                    ok = d.ok and d.json().get("ok") is True
                except (requests.RequestException, ValueError):
                    ok = False
            if not ok:
                # Keep the DB row pending if the published Telegram tip still exists.
                info["failed"] += 1
                continue
            info["deleted"] += 1
            try:
                u = requests.patch(f"{SB}/rest/v1/tips", headers=H, timeout=20, params={"id": f"eq.{t['id']}"},
                                   data=json.dumps({"status": "void", "result": "void"}))
                if u.ok:
                    info["voided"] += 1
                else:
                    info["db_failed"] += 1
            except requests.RequestException:
                info["db_failed"] += 1
    print(json.dumps(info))
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, timeout=20, data=json.dumps({"info": info}))


if __name__ == "__main__":
    main()
