#!/usr/bin/env python3
"""NETRATTLER täglicher Health-Check: GitHub-Runs + Supabase-Frische + Quellen-Gesundheit.

Schickt eine kurze Telegram-Meldung (OK oder Problemliste) und beendet sich mit
Exit-Code 0 (Alarm ist die Telegram-Nachricht, nicht ein roter Workflow).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY") or "forfexes/btts-bot_ki"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN") or ""
TG_CHAT = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID") or ""
DB_WARN_MB = float(os.getenv("DB_WARN_MB", "470"))


def _sb(path: str, params: Optional[dict] = None, method: str = "GET", json_body: Any = None):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.request(method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers,
                         params=params or {}, json=json_body, timeout=30)
    return r


def _newest(table: str, column: str) -> Optional[str]:
    r = _sb(table, {"select": column, "order": f"{column}.desc.nullslast", "limit": "1"})
    if r.ok and r.json():
        return str(r.json()[0].get(column) or "") or None
    return None


def _count(table: str, extra: Optional[dict] = None) -> Optional[int]:
    params = {"select": "*", "limit": "1"}
    params.update(extra or {})
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "count=exact"}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, timeout=30)
    cr = r.headers.get("Content-Range", "")
    if r.ok and "/" in cr:
        try:
            return int(cr.rsplit("/", 1)[1])
        except ValueError:
            return None
    return None


def _age_hours(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        t = ts.replace(" ", "T").replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def check_github() -> List[str]:
    issues: List[str] = []
    if not GITHUB_TOKEN:
        return ["GitHub-Token fehlt (Runs nicht geprüft)"]
    since = (datetime.now(timezone.utc) - timedelta(hours=26)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        params={"created": f">={since}", "per_page": 100}, timeout=30)
    if not r.ok:
        return [f"GitHub Runs HTTP {r.status_code}"]
    by_wf: Dict[str, Dict[str, int]] = {}
    for run in r.json().get("workflow_runs", []):
        name = run.get("name") or "?"
        if "Health" in name:
            continue
        d = by_wf.setdefault(name, {"ok": 0, "fail": 0, "other": 0})
        c = run.get("conclusion")
        if c == "success":
            d["ok"] += 1
        elif c in ("failure", "timed_out", "startup_failure"):
            d["fail"] += 1
        else:
            d["other"] += 1
    for name, d in sorted(by_wf.items()):
        if d["fail"] and not d["ok"]:
            issues.append(f"Workflow '{name}': {d['fail']} Fehlschläge, kein Erfolg in 26h")
        elif d["fail"] > 2:
            issues.append(f"Workflow '{name}': {d['fail']} Fehlschläge (+{d['ok']} ok)")
    return issues


def check_supabase() -> List[str]:
    issues: List[str] = []
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ["Supabase-Zugang fehlt"]

    # Frische
    for table, col, max_h, label in (
        ("match_results", "created_at", 36, "match_results"),
        ("odds_history", "imported_at", 14, "odds_history"),
        ("player_game_log", "updated_at", 36, "player_game_log"),
    ):
        age = _age_hours(_newest(table, col))
        if age is None:
            issues.append(f"{label}: keine Daten / nicht lesbar")
        elif age > max_h:
            issues.append(f"{label}: letzte Daten vor {age:.0f}h (Limit {max_h}h)")

    # Datenqualität player_game_log
    total = _count("player_game_log")
    cards = _count("player_game_log", {"yellow_cards": "not.is.null"})
    if total is not None and total > 0 and cards is not None and cards == 0:
        issues.append("player_game_log: keine Karten-Daten")

    # Größe
    r = _sb("rpc/netrattler_db_size_mb", method="POST", json_body={})
    size = None
    if r.ok:
        try:
            size = float(r.json())
        except Exception:
            size = None
    if size is not None and size > DB_WARN_MB:
        issues.append(f"DB-Größe {size:.0f} MB (Warnschwelle {DB_WARN_MB:.0f} MB)")

    # Quellen-Gesundheit der letzten 26h: pro Quelle letzter Eintrag
    since = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()
    r = _sb("source_health", {"select": "workflow,source,rows_found,ok,note,run_at",
                              "run_at": f"gte.{since}", "order": "run_at.desc", "limit": "300"})
    latest: Dict[str, Dict[str, Any]] = {}
    if r.ok:
        for row in r.json():
            latest.setdefault(f"{row['workflow']}/{row['source']}", row)
    for key, row in sorted(latest.items()):
        if not row.get("ok"):
            note = str(row.get("note") or "")[:110]
            issues.append(f"Quelle {key}: 0 Zeilen — {note}")
    return issues, size, total, len(latest)  # type: ignore[return-value]


def send(text: str) -> None:
    print(text)
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT, "text": text[:3900], "parse_mode": "HTML"}, timeout=15)
        except Exception as exc:
            print("Telegram Fehler:", str(exc)[:100])


def main() -> int:
    issues = check_github()
    sb = check_supabase()
    size = total = n_sources = None
    if isinstance(sb, tuple):
        sb_issues, size, total, n_sources = sb
    else:
        sb_issues = sb
    issues += sb_issues
    head = f"🩺 <b>NETRATTLER Health {date.today().isoformat()}</b>"
    stats = f"DB {size:.0f} MB · player_game_log {total} Zeilen · {n_sources} Quellen geprüft" if size is not None and total is not None else ""
    if issues:
        body = "\n".join(f"• {i}" for i in issues[:15])
        send(f"{head}\n⚠️ {len(issues)} Auffälligkeiten\n{body}\n{stats}")
    else:
        send(f"{head}\n✅ Alles ok\n{stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
