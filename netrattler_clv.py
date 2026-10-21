"""Closing-line value for single tips (idea taken from Prop Hunter's CLV engine).

For over25 / btts / 1x2 singles: closing odds = median of the last pre-match
quotes of independent sources in odds_history (captured on the match day) for
the same teams/market/selection. clv = taken/closing - 1 (positive = we beat the
close). Writes tips.odds_taken, odds_closing, clv only where empty. Read-only on
odds_history; never touches status/result/profit. Diag probe 'clv'.
"""
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from netrattler_pending_result_backfill import team_match, tip_day, tip_pair

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
SOURCES = ("bwin", "1xbet_platform", "altenar_platform", "matchbook", "smarkets", "gamdom_platform", "kambi")
LOOKBACK_DAYS = int(os.getenv("CLV_LOOKBACK_DAYS", "4"))


def tip_selection(row: Dict[str, Any]) -> Optional[tuple]:
    """(history market, selection) for a single tip, else None."""
    m, t = str(row.get("market") or "").lower(), str(row.get("tip") or "").strip().lower()
    if m == "over25" and t in ("yes", "over 2.5", "over"):
        return "totals_2_5", "over_2_5"
    if m == "btts":
        return ("btts", "yes") if t == "yes" else ("btts", "no") if t == "no" else None
    if m == "1x2":
        return ("1x2", {"1": "home", "x": "draw", "2": "away"}[t]) if t in ("1", "x", "2") else None
    return None


def closing_odds(tip: Dict[str, Any], history: List[Dict[str, Any]]) -> Optional[float]:
    sel = tip_selection(tip)
    pair = tip_pair(tip)
    day = tip_day(tip)
    if not sel or not pair:
        return None
    quotes = []
    for r in history:
        if r.get("market") != sel[0] or r.get("selection") != sel[1]:
            continue
        if r.get("source") not in SOURCES or str(r.get("match_date") or "") != str(tip.get("date") or day):
            continue
        try:
            o = float(r.get("odds"))
        except (TypeError, ValueError):
            continue
        if not 1.01 < o < 50:
            continue
        if team_match(r.get("home_team"), pair[0]) and team_match(r.get("away_team"), pair[1]):
            quotes.append(o)
    return round(statistics.median(quotes), 3) if len(quotes) >= 1 else None


def clv_value(taken: Any, closing: Optional[float]) -> Optional[float]:
    try:
        t = float(taken)
    except (TypeError, ValueError):
        return None
    if not closing or t <= 1:
        return None
    return round(t / closing - 1.0, 4)


def run() -> Dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    tips = requests.get(f"{SB}/rest/v1/tips", headers=H, timeout=40, params={
        "select": "tip_id,market,tip,odds,date,message_text,created_at,odds_closing",
        "created_at": f"gte.{since}", "odds_closing": "is.null", "builder_id": "is.null",
        "market": "in.(over25,btts,1x2)", "limit": "2000"}).json()
    stats = {"probe": "clv", "tips": len(tips), "written": 0, "no_close": 0, "avg_clv": None}
    vals = []
    days = sorted({str(t.get("date") or "") for t in tips if t.get("date")})
    history: List[Dict[str, Any]] = []
    for d in days:
        for off in range(0, 20000, 1000):
            r = requests.get(f"{SB}/rest/v1/odds_history", headers=H, timeout=60, params={
                "select": "source,market,selection,odds,home_team,away_team,match_date",
                "match_date": f"eq.{d}", "market": "in.(1x2,btts,totals_2_5)",
                "source": "in.(" + ",".join(SOURCES) + ")", "limit": "1000", "offset": str(off)})
            part = r.json() if r.ok else []
            history.extend(part if isinstance(part, list) else [])
            if len(part) < 1000:
                break
    for t in tips:
        c = closing_odds(t, history)
        v = clv_value(t.get("odds"), c)
        if v is None:
            stats["no_close"] += 1
            continue
        body = {"odds_taken": float(t["odds"]), "odds_closing": c, "clv": v}
        r = requests.patch(f"{SB}/rest/v1/tips", headers=H, params={"tip_id": f"eq.{t['tip_id']}"}, json=body, timeout=30)
        if r.ok:
            stats["written"] += 1
            vals.append(v)
    if vals:
        stats["avg_clv"] = round(sum(vals) / len(vals), 4)
    if SB and KEY:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", headers=H, json={"info": stats}, timeout=20)
    print(stats)
    return stats


if __name__ == "__main__":
    run()
