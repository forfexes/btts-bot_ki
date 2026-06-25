#!/usr/bin/env python3
"""
NETRATTLER Settlement V2
=======================

Ziele:
- wertet offene Tipps aus Supabase aus
- unterstützt BTTS, Over 2.5, Combos, HT, Ecken, Builder/Props soweit Daten vorhanden
- nutzt mehrere Ergebnisquellen als Fallback
- speichert Status sauber zurück
- sendet kompakte Gruppen-Auswertung

Benötigte Secrets:
SUPABASE_URL
SUPABASE_KEY
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID / Gruppen
FOOTBALL_DATA_API_KEYS optional
THESTATSAPI_KEY optional
"""

import os
import re
import json
import time
import math
import traceback
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional, Tuple

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

TELEGRAM_GROUPS = {
    "btts": os.getenv("TELEGRAM_GROUP_BTTS") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "over25": os.getenv("TELEGRAM_GROUP_OVER25") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "combo": os.getenv("TELEGRAM_GROUP_COMBO") or os.getenv("TELEGRAM_GROUP_COMBOS") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "btts_ht": os.getenv("TELEGRAM_GROUP_BTTS_HT") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "over15_ht": os.getenv("TELEGRAM_GROUP_OVER15_HT") or os.getenv("TELEGRAM_GROUP_HZ_LIVE") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "corners": os.getenv("TELEGRAM_GROUP_HZ_LIVE") or os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "props": os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", ""),
    "stats": os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", ""),
}

FOOTBALL_DATA_KEYS = []
for name in ("FOOTBALL_DATA_API_KEYS", "FOOTBALL_DATA_API_KEY"):
    raw = os.getenv(name, "")
    for x in raw.replace("\n", ",").split(","):
        x = x.strip()
        if x and x not in FOOTBALL_DATA_KEYS:
            FOOTBALL_DATA_KEYS.append(x)

THESTATSAPI_KEYS = []
for name in ("THESTATSAPI_KEYS", "THESTATSAPI_KEY"):
    raw = os.getenv(name, "")
    for x in raw.replace("\n", ",").split(","):
        x = x.strip()
        if x and x not in THESTATSAPI_KEYS:
            THESTATSAPI_KEYS.append(x)

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

RESULT_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


def log(msg: str, level: str = "INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def norm(s: Any) -> str:
    s = str(s or "").lower()
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def send_telegram(text: str, chat_id: str = "") -> bool:
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        return r.ok
    except Exception as e:
        log(f"Telegram Fehler: {e}", "WARN")
        return False


def sb_get(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY fehlt")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS_SB, params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Supabase GET {table} {r.status_code}: {r.text[:500]}")
    return r.json()


def sb_patch(table: str, filters: Dict[str, str], data: Dict[str, Any]) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    params = dict(filters)
    headers = dict(HEADERS_SB)
    headers["Prefer"] = "return=minimal"
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, json=data, timeout=30)
    if not r.ok:
        log(f"Supabase PATCH {table} {r.status_code}: {r.text[:250]}", "WARN")
    return r.ok


def sb_upsert(table: str, rows: List[Dict[str, Any]], on_conflict: str = "") -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    headers = dict(HEADERS_SB)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"
    r = requests.post(url, headers=headers, json=rows, timeout=40)
    if not r.ok:
        log(f"Supabase UPSERT {table} {r.status_code}: {r.text[:300]}", "WARN")
        return 0
    return len(rows)


def get_pending_tips(days_back: int = 3, limit: int = 500) -> List[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
    queries = [
        {
            "select": "*",
            "status": "eq.pending",
            "date": f"gte.{since}",
            "limit": str(limit),
            "order": "date.asc",
        },
        {
            "select": "*",
            "result": "is.null",
            "date": f"gte.{since}",
            "limit": str(limit),
            "order": "date.asc",
        },
    ]
    seen = set()
    rows = []
    for q in queries:
        try:
            for r in sb_get("tips", q):
                key = r.get("id") or r.get("tip_id") or json.dumps(r, sort_keys=True)[:120]
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        except Exception as e:
            log(f"Pending query skip: {e}", "WARN")
    return rows


def parse_match(tip: Dict[str, Any]) -> Tuple[str, str]:
    m = tip.get("match") or tip.get("fixture") or tip.get("game") or ""
    if " vs " in m:
        a, b = m.split(" vs ", 1)
        return a.strip(), b.strip()
    if " v " in m:
        a, b = m.split(" v ", 1)
        return a.strip(), b.strip()
    home = tip.get("home_team") or tip.get("home") or ""
    away = tip.get("away_team") or tip.get("away") or ""
    return str(home).strip(), str(away).strip()


def parse_tip_date(tip: Dict[str, Any]) -> str:
    for k in ("date", "match_date", "kickoff_date"):
        if tip.get(k):
            return str(tip[k])[:10]
    for k in ("kickoff", "kickoff_at", "time"):
        v = str(tip.get(k) or "")
        m = re.search(r"\d{4}-\d{2}-\d{2}", v)
        if m:
            return m.group(0)
    return today_iso()


def football_data_result(home: str, away: str, d: str) -> Optional[Dict[str, Any]]:
    if not FOOTBALL_DATA_KEYS:
        return None
    # Free API works best by competition, but this broad endpoint can work on some plans.
    # If it fails, return None quickly.
    key = f"fd::{norm(home)}::{norm(away)}::{d}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]
    for api_key in FOOTBALL_DATA_KEYS[:4]:
        try:
            url = "https://api.football-data.org/v4/matches"
            r = requests.get(url, headers={"X-Auth-Token": api_key}, params={"dateFrom": d, "dateTo": d}, timeout=15)
            if r.status_code in (401, 403, 429):
                continue
            if not r.ok:
                continue
            data = r.json()
            for m in data.get("matches", []):
                h = (m.get("homeTeam") or {}).get("name", "")
                a = (m.get("awayTeam") or {}).get("name", "")
                if norm(home) in norm(h) or norm(h) in norm(home):
                    h_ok = True
                else:
                    h_ok = False
                if norm(away) in norm(a) or norm(a) in norm(away):
                    a_ok = True
                else:
                    a_ok = False
                if h_ok and a_ok:
                    ft = m.get("score", {}).get("fullTime", {})
                    ht = m.get("score", {}).get("halfTime", {})
                    if ft.get("home") is None or ft.get("away") is None:
                        continue
                    res = {
                        "home": h, "away": a,
                        "home_goals": int(ft.get("home") or 0),
                        "away_goals": int(ft.get("away") or 0),
                        "ht_home_goals": int(ht.get("home") or 0) if ht.get("home") is not None else None,
                        "ht_away_goals": int(ht.get("away") or 0) if ht.get("away") is not None else None,
                        "source": "football-data",
                    }
                    RESULT_CACHE[key] = res
                    return res
        except Exception:
            continue
    RESULT_CACHE[key] = None
    return None


def openligadb_result(home: str, away: str, d: str) -> Optional[Dict[str, Any]]:
    key = f"oldb::{norm(home)}::{norm(away)}::{d}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]
    # OpenLigaDB is mostly German leagues; cheap fallback.
    try:
        year = int(d[:4])
        for league in ("bl1", "bl2", "bl3", "dfb"):
            url = f"https://api.openligadb.de/getmatchdata/{league}/{year}"
            r = requests.get(url, timeout=12)
            if not r.ok:
                continue
            for m in r.json():
                h = m.get("team1", {}).get("teamName", "")
                a = m.get("team2", {}).get("teamName", "")
                if (norm(home) in norm(h) or norm(h) in norm(home)) and (norm(away) in norm(a) or norm(a) in norm(away)):
                    goals = m.get("matchResults") or []
                    final = None
                    half = None
                    for gr in goals:
                        if gr.get("resultTypeID") in (2, 3):
                            final = gr
                        if gr.get("resultTypeID") == 1:
                            half = gr
                    if not final:
                        continue
                    res = {
                        "home": h, "away": a,
                        "home_goals": int(final.get("pointsTeam1") or 0),
                        "away_goals": int(final.get("pointsTeam2") or 0),
                        "ht_home_goals": int(half.get("pointsTeam1") or 0) if half else None,
                        "ht_away_goals": int(half.get("pointsTeam2") or 0) if half else None,
                        "source": "openligadb",
                    }
                    RESULT_CACHE[key] = res
                    return res
    except Exception:
        pass
    RESULT_CACHE[key] = None
    return None


def get_result(home: str, away: str, d: str) -> Optional[Dict[str, Any]]:
    if not home or not away:
        return None
    key = f"result::{norm(home)}::{norm(away)}::{d}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]
    for fn in (football_data_result, openligadb_result):
        res = fn(home, away, d)
        if res:
            RESULT_CACHE[key] = res
            return res
    RESULT_CACHE[key] = None
    return None


def settle_market(tip: Dict[str, Any], res: Dict[str, Any]) -> Optional[str]:
    market = norm(tip.get("market") or tip.get("type") or tip.get("category") or "")
    pick = norm(tip.get("tip") or tip.get("pick") or tip.get("selection") or "")
    hg = int(res["home_goals"])
    ag = int(res["away_goals"])
    total = hg + ag
    hth = res.get("ht_home_goals")
    hta = res.get("ht_away_goals")
    ht_total = (hth + hta) if hth is not None and hta is not None else None

    if "btts ht" in market or "btts_ht" in market:
        if hth is None or hta is None:
            return None
        yes = hth > 0 and hta > 0
        return "won" if yes else "lost"

    if "btts" in market:
        yes = hg > 0 and ag > 0
        if "no" in pick:
            yes = not yes
        return "won" if yes else "lost"

    if "over15 ht" in market or "over1 5 ht" in market or "over 1 5 ht" in market:
        if ht_total is None:
            return None
        return "won" if ht_total > 1.5 else "lost"

    if "over25" in market or "over 2 5" in market or "over2 5" in market:
        return "won" if total > 2.5 else "lost"

    if "combo" in market:
        # Standard NETRATTLER combo = BTTS + Over2.5
        return "won" if (hg > 0 and ag > 0 and total > 2.5) else "lost"

    if "corner" in market or "corners" in market:
        # Ohne Corner-Resultat nicht auswerten.
        return None

    if any(x in market for x in ("prop", "builder", "card", "tackle", "shot", "sot", "foul")):
        return None

    return None


def update_tip(tip: Dict[str, Any], status: str, res: Optional[Dict[str, Any]] = None) -> bool:
    filters = {}
    if tip.get("id") is not None:
        filters["id"] = f"eq.{tip['id']}"
    elif tip.get("tip_id"):
        filters["tip_id"] = f"eq.{tip['tip_id']}"
    else:
        return False

    data = {
        "status": status,
        "result": status,
        "settled_at": datetime.now(timezone.utc).isoformat(),
    }
    if res:
        data["final_score"] = f"{res['home_goals']}-{res['away_goals']}"
        data["settlement_source"] = res.get("source", "")
    return sb_patch("tips", filters, data)


def group_key(tip: Dict[str, Any]) -> str:
    market = norm(tip.get("market") or tip.get("type") or tip.get("category") or "")
    if "btts ht" in market or "btts_ht" in market:
        return "btts_ht"
    if "over15 ht" in market or "over1 5 ht" in market:
        return "over15_ht"
    if "over25" in market or "over 2 5" in market:
        return "over25"
    if "combo" in market:
        return "combo"
    if "corner" in market:
        return "corners"
    if any(x in market for x in ("prop", "builder", "card", "tackle", "shot", "sot", "foul")):
        return "props"
    return "btts"


def calc_roi(items: List[Dict[str, Any]]) -> Tuple[int, int, int, float]:
    wins = sum(1 for x in items if x.get("status") == "won")
    losses = sum(1 for x in items if x.get("status") == "lost")
    pushes = sum(1 for x in items if x.get("status") in ("push", "void"))
    profit = 0.0
    for x in items:
        status = x.get("status")
        odds = x.get("odds") or x.get("oddsYes") or x.get("quote") or 1.0
        try:
            odds = float(str(odds).replace(",", "."))
        except Exception:
            odds = 1.0
        if status == "won":
            profit += odds - 1.0
        elif status == "lost":
            profit -= 1.0
    return wins, losses, pushes, round(profit, 2)


def send_summary(settled: List[Dict[str, Any]], skipped: int):
    if not settled:
        send_telegram(f"📊 <b>NETRATTLER Settlement</b>\nKeine neuen auswertbaren Tipps.\nOffen/ohne Ergebnis: {skipped}", TELEGRAM_GROUPS.get("stats", ""))
        return

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for x in settled:
        by_group.setdefault(group_key(x), []).append(x)

    for g, items in by_group.items():
        wins, losses, pushes, profit = calc_roi(items)
        total = wins + losses + pushes
        hr = round((wins / max(1, wins + losses)) * 100, 1)
        msg = (
            f"📊 <b>Settlement</b>\n"
            f"Gruppe: <b>{g.upper()}</b>\n"
            f"✅ {wins}  ❌ {losses}  ↔️ {pushes}\n"
            f"Hit Rate: <b>{hr}%</b>\n"
            f"Profit: <b>{profit:+.2f}u</b>"
        )
        send_telegram(msg, TELEGRAM_GROUPS.get(g) or TELEGRAM_GROUPS.get("stats", ""))

    wins, losses, pushes, profit = calc_roi(settled)
    total = wins + losses + pushes
    hr = round((wins / max(1, wins + losses)) * 100, 1)
    msg = (
        f"📊 <b>NETRATTLER Settlement V2</b>\n"
        f"Ausgewertet: <b>{total}</b>\n"
        f"✅ {wins}  ❌ {losses}  ↔️ {pushes}\n"
        f"Hit Rate: <b>{hr}%</b>\n"
        f"Profit: <b>{profit:+.2f}u</b>\n"
        f"Nicht auswertbar/offen: {skipped}"
    )
    send_telegram(msg, TELEGRAM_GROUPS.get("stats", ""))


def update_daily_stats(settled: List[Dict[str, Any]]):
    if not settled:
        return
    rows = []
    day = today_iso()
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for x in settled:
        by_group.setdefault(group_key(x), []).append(x)

    for g, items in by_group.items():
        wins, losses, pushes, profit = calc_roi(items)
        rows.append({
            "date": day,
            "group_name": g,
            "tips": len(items),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "profit_units": profit,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    # Optional table. If it doesn't exist, warning only.
    sb_upsert("settlement_daily_stats", rows, on_conflict="date,group_name")


def main():
    log("⚽ NETRATTLER Settlement V2 startet")
    tips = get_pending_tips(days_back=int(os.getenv("SETTLEMENT_DAYS_BACK", "3")), limit=int(os.getenv("SETTLEMENT_LIMIT", "500")))
    log(f"Offene Tipps geladen: {len(tips)}")

    settled: List[Dict[str, Any]] = []
    skipped = 0

    for tip in tips:
        home, away = parse_match(tip)
        d = parse_tip_date(tip)

        # Nicht vor Anpfiff/selber Tag zu früh auswerten: erst nach ca. 2h probieren.
        # Wenn keine Uhrzeit vorhanden, wird trotzdem versucht.
        res = get_result(home, away, d)
        if not res:
            skipped += 1
            continue

        status = settle_market(tip, res)
        if not status:
            skipped += 1
            continue

        if update_tip(tip, status, res):
            item = dict(tip)
            item["status"] = status
            item["final_score"] = f"{res['home_goals']}-{res['away_goals']}"
            settled.append(item)
            log(f"{status.upper()}: {tip.get('match')} {item['final_score']}")

        time.sleep(0.05)

    update_daily_stats(settled)
    if os.getenv("SETTLEMENT_SEND_SUMMARY", "true").lower() in ("1", "true", "yes", "on"):
        send_summary(settled, skipped)

    log(f"✅ Settlement fertig: {len(settled)} ausgewertet, {skipped} offen/nicht auswertbar")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "ERROR")
        print(traceback.format_exc())
        raise
