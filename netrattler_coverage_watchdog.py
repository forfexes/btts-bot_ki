"""Coverage watchdog (idea from Prop Hunter): detect silent loss of sources/markets.
Read-only. Writes diag probe 'coverage_watchdog'; Telegram alert only to TELEGRAM_GROUP_ALERTS and only
when something expected is missing."""
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
EXPECTED_SOURCES = {"kambi": 6, "bwin": 6, "1xbet_platform": 6, "altenar_platform": 6, "matchbook": 12, "smarkets": 12}  # max age h
EXPECTED_MARKETS = ("1x2", "btts", "totals_2_5")


def stale_sources(latest: Dict[str, str], now: datetime) -> List[str]:
    bad = []
    for src, max_h in EXPECTED_SOURCES.items():
        ts = latest.get(src)
        if not ts:
            bad.append(f"{src}: no rows")
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            bad.append(f"{src}: bad timestamp")
            continue
        age = (now - dt).total_seconds() / 3600
        if age > max_h:
            bad.append(f"{src}: {age:.0f}h old (>{max_h}h)")
    return bad


def missing_markets(counts: Dict[str, int]) -> List[str]:
    return [m for m in EXPECTED_MARKETS if counts.get(m, 0) == 0]


def _get(path: str, **params) -> Any:
    r = requests.get(f"{SB}/rest/v1/{path}", headers=H, params=params, timeout=40)
    return r.json() if r.ok else []


def run() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    latest = {}
    for src in EXPECTED_SOURCES:
        rows = _get("odds_history", select="imported_at", source=f"eq.{src}", order="imported_at.desc", limit="1")
        if rows:
            latest[src] = rows[0].get("imported_at")
    today = now.date().isoformat()
    counts = {}
    for m in EXPECTED_MARKETS:
        r = requests.get(f"{SB}/rest/v1/odds_history", timeout=40,
                         headers={**H, "Prefer": "count=exact", "Range": "0-0"},
                         params={"select": "source", "market": f"eq.{m}", "captured_date": f"eq.{today}"})
        counts[m] = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else 0
    issues = stale_sources(latest, now) + [f"market {m}: 0 rows today" for m in missing_markets(counts)]
    info = {"probe": "coverage_watchdog", "issues": issues, "market_rows_today": counts}
    if issues:
        tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_GROUP_ALERTS")
        if tok and chat:
            try:
                requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                              json={"chat_id": chat, "text": "⚠️ Datenabdeckung: " + "; ".join(issues)[:600]})
            except Exception:
                pass
    requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, json={"info": info}, timeout=20)
    print(json.dumps(info)[:500])
    return info


if __name__ == "__main__":
    run()
