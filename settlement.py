#!/usr/bin/env python3
"""
NETRATTLER Settlement V3 FAST
============================

V3 ist absichtlich schnell:
- prüft nur begrenzte Anzahl offener Tipps pro Run
- gruppiert nach Spiel
- lädt Ergebnis pro Spiel nur einmal
- bricht sauber ab statt ewig zu laufen
"""

import os
import re
import json
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

SETTLEMENT_DAYS_BACK = int(os.getenv("SETTLEMENT_DAYS_BACK", "1"))
SETTLEMENT_LIMIT = int(os.getenv("SETTLEMENT_LIMIT", "120"))
SETTLEMENT_MAX_GAMES = int(os.getenv("SETTLEMENT_MAX_GAMES", "35"))
SETTLEMENT_TIMEOUT_SECONDS = int(os.getenv("SETTLEMENT_TIMEOUT_SECONDS", "90"))
SETTLEMENT_SEND_SUMMARY = os.getenv("SETTLEMENT_SEND_SUMMARY", "true").lower() in ("1", "true", "yes", "on")

TELEGRAM_STATS = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_GROUPS = {
    "btts": os.getenv("TELEGRAM_GROUP_BTTS") or TELEGRAM_STATS,
    "over25": os.getenv("TELEGRAM_GROUP_OVER25") or TELEGRAM_STATS,
    "combo": os.getenv("TELEGRAM_GROUP_COMBO") or os.getenv("TELEGRAM_GROUP_COMBOS") or TELEGRAM_STATS,
    "btts_ht": os.getenv("TELEGRAM_GROUP_BTTS_HT") or TELEGRAM_STATS,
    "over15_ht": os.getenv("TELEGRAM_GROUP_OVER15_HT") or os.getenv("TELEGRAM_GROUP_HZ_LIVE") or TELEGRAM_STATS,
    "corners": os.getenv("TELEGRAM_GROUP_HZ_LIVE") or TELEGRAM_STATS,
    "props": TELEGRAM_STATS,
    "stats": TELEGRAM_STATS,
}

FOOTBALL_DATA_KEYS = []
for name in ("FOOTBALL_DATA_API_KEYS", "FOOTBALL_DATA_API_KEY"):
    raw = os.getenv(name, "")
    for x in raw.replace("\n", ",").replace(";", ",").split(","):
        x = x.strip()
        if x and x not in FOOTBALL_DATA_KEYS:
            FOOTBALL_DATA_KEYS.append(x)

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

START_TS = time.time()
RESULT_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


def log(msg: str, level: str = "INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def timed_out() -> bool:
    return (time.time() - START_TS) > SETTLEMENT_TIMEOUT_SECONDS


def norm(s: Any) -> str:
    s = str(s or "").lower()
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def send_telegram(text: str, chat_id: str = "") -> bool:
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def sb_get(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS_SB, params=params, timeout=20)
    if not r.ok:
        raise RuntimeError(f"Supabase GET {table} {r.status_code}: {r.text[:300]}")
    return r.json()


def sb_patch_tip(tip: Dict[str, Any], data: Dict[str, Any]) -> bool:
    if tip.get("id") is not None:
        params = {"id": f"eq.{tip['id']}"}
    elif tip.get("tip_id"):
        params = {"tip_id": f"eq.{tip['tip_id']}"}
    else:
        return False
    headers = dict(HEADERS_SB)
    headers["Prefer"] = "return=minimal"
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/tips", headers=headers, params=params, json=data, timeout=12)
    if not r.ok:
        log(f"PATCH Fehler: {r.status_code} {r.text[:120]}", "WARN")
    return r.ok


def get_pending_tips() -> List[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=SETTLEMENT_DAYS_BACK)).date().isoformat()
    # Nur pending der letzten X Tage, begrenzt.
    q = {
        "select": "*",
        "status": "eq.pending",
        "date": f"gte.{since}",
        "order": "date.asc",
        "limit": str(SETTLEMENT_LIMIT),
    }
    try:
        rows = sb_get("tips", q)
    except Exception as e:
        log(f"pending/status query failed: {e}", "WARN")
        rows = []

    # Fallback: result null, aber auch begrenzt.
    if not rows:
        q2 = {
            "select": "*",
            "result": "is.null",
            "date": f"gte.{since}",
            "order": "date.asc",
            "limit": str(SETTLEMENT_LIMIT),
        }
        rows = sb_get("tips", q2)

    return rows[:SETTLEMENT_LIMIT]


def parse_match(tip: Dict[str, Any]) -> Tuple[str, str]:
    m = tip.get("match") or tip.get("fixture") or tip.get("game") or ""
    for sep in (" vs ", " v ", " - "):
        if sep in m:
            a, b = m.split(sep, 1)
            return a.strip(), b.strip()
    return str(tip.get("home_team") or tip.get("home") or "").strip(), str(tip.get("away_team") or tip.get("away") or "").strip()


def tip_date(tip: Dict[str, Any]) -> str:
    for k in ("date", "match_date", "kickoff_date", "kickoff_at"):
        v = str(tip.get(k) or "")
        m = re.search(r"\d{4}-\d{2}-\d{2}", v)
        if m:
            return m.group(0)
    return datetime.now(timezone.utc).date().isoformat()


def match_key(tip: Dict[str, Any]) -> str:
    h, a = parse_match(tip)
    return f"{tip_date(tip)}::{norm(h)}::{norm(a)}"


def group_tips_by_match(tips: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped = {}
    for t in tips:
        h, a = parse_match(t)
        if not h or not a:
            continue
        grouped.setdefault(match_key(t), []).append(t)
    # Nur max Spiele
    out = {}
    for k in list(grouped.keys())[:SETTLEMENT_MAX_GAMES]:
        out[k] = grouped[k]
    return out


def football_data_result(home: str, away: str, d: str) -> Optional[Dict[str, Any]]:
    key = f"fd::{d}::{norm(home)}::{norm(away)}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]

    if not FOOTBALL_DATA_KEYS:
        RESULT_CACHE[key] = None
        return None

    for api_key in FOOTBALL_DATA_KEYS[:4]:
        if timed_out():
            break
        try:
            r = requests.get(
                "https://api.football-data.org/v4/matches",
                headers={"X-Auth-Token": api_key},
                params={"dateFrom": d, "dateTo": d},
                timeout=8,
            )
            if r.status_code in (401, 403, 429):
                continue
            if not r.ok:
                continue
            for m in r.json().get("matches", []):
                h = (m.get("homeTeam") or {}).get("name", "")
                a = (m.get("awayTeam") or {}).get("name", "")
                h_ok = norm(home) in norm(h) or norm(h) in norm(home)
                a_ok = norm(away) in norm(a) or norm(a) in norm(away)
                if not (h_ok and a_ok):
                    continue

                ft = (m.get("score") or {}).get("fullTime") or {}
                ht = (m.get("score") or {}).get("halfTime") or {}
                if ft.get("home") is None or ft.get("away") is None:
                    continue

                res = {
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
    # Sehr schneller Fallback nur deutsche Ligen.
    key = f"oldb::{d}::{norm(home)}::{norm(away)}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]
    try:
        year = int(d[:4])
        for league in ("bl1", "bl2", "bl3"):
            if timed_out():
                break
            r = requests.get(f"https://api.openligadb.de/getmatchdata/{league}/{year}", timeout=8)
            if not r.ok:
                continue
            for m in r.json():
                h = (m.get("team1") or {}).get("teamName", "")
                a = (m.get("team2") or {}).get("teamName", "")
                if not ((norm(home) in norm(h) or norm(h) in norm(home)) and (norm(away) in norm(a) or norm(a) in norm(away))):
                    continue
                final = None
                half = None
                for rr in m.get("matchResults") or []:
                    if rr.get("resultTypeID") in (2, 3):
                        final = rr
                    if rr.get("resultTypeID") == 1:
                        half = rr
                if final:
                    res = {
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
    key = f"res::{d}::{norm(home)}::{norm(away)}"
    if key in RESULT_CACHE:
        return RESULT_CACHE[key]
    res = football_data_result(home, away, d) or openligadb_result(home, away, d)
    RESULT_CACHE[key] = res
    return res


def settle_market(tip: Dict[str, Any], res: Dict[str, Any]) -> Optional[str]:
    market = norm(tip.get("market") or tip.get("type") or tip.get("category") or "")
    pick = norm(tip.get("tip") or tip.get("pick") or tip.get("selection") or "")
    hg = int(res["home_goals"])
    ag = int(res["away_goals"])
    total = hg + ag
    hth = res.get("ht_home_goals")
    hta = res.get("ht_away_goals")

    if "btts ht" in market or "btts_ht" in market:
        if hth is None or hta is None:
            return None
        return "won" if hth > 0 and hta > 0 else "lost"

    if "btts" in market:
        yes = hg > 0 and ag > 0
        if "no" in pick:
            yes = not yes
        return "won" if yes else "lost"

    if "over15 ht" in market or "over1 5 ht" in market:
        if hth is None or hta is None:
            return None
        return "won" if (hth + hta) > 1.5 else "lost"

    if "over25" in market or "over 2 5" in market or "over2 5" in market:
        return "won" if total > 2.5 else "lost"

    if "combo" in market:
        return "won" if (hg > 0 and ag > 0 and total > 2.5) else "lost"

    # Ecken/Props/Builder später separat, wenn Ergebnisdaten vorhanden sind.
    return None


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
    return "btts"


def send_summary(settled: List[Dict[str, Any]], open_count: int):
    if not SETTLEMENT_SEND_SUMMARY:
        return

    if not settled:
        send_telegram(f"📊 <b>Settlement V3</b>\nKeine neuen Tipps ausgewertet.\nOffen/ohne Ergebnis: {open_count}", TELEGRAM_STATS)
        return

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for x in settled:
        by_group.setdefault(group_key(x), []).append(x)

    lines = ["📊 <b>Settlement V3</b>"]
    total_w = total_l = 0
    for g, items in sorted(by_group.items()):
        w = sum(1 for x in items if x["status"] == "won")
        l = sum(1 for x in items if x["status"] == "lost")
        total_w += w
        total_l += l
        hr = round(w / max(1, w + l) * 100, 1)
        lines.append(f"{g.upper()}: ✅ {w} ❌ {l} · {hr}%")

    hr_total = round(total_w / max(1, total_w + total_l) * 100, 1)
    lines.append(f"\nTotal: ✅ {total_w} ❌ {total_l} · <b>{hr_total}%</b>")
    lines.append(f"Offen/ohne Ergebnis: {open_count}")
    send_telegram("\n".join(lines), TELEGRAM_STATS)


def main():
    log("⚽ NETRATTLER Settlement V3 FAST startet")
    tips = get_pending_tips()
    log(f"Offene Tipps geladen: {len(tips)} | Limit={SETTLEMENT_LIMIT} | Days={SETTLEMENT_DAYS_BACK}")

    grouped = group_tips_by_match(tips)
    log(f"Unique Spiele zu prüfen: {len(grouped)} / max {SETTLEMENT_MAX_GAMES}")

    settled: List[Dict[str, Any]] = []
    open_count = 0

    for _, game_tips in grouped.items():
        if timed_out():
            log("⏱️ Timeout-Limit erreicht, stoppe sauber", "WARN")
            break

        sample = game_tips[0]
        home, away = parse_match(sample)
        d = tip_date(sample)
        res = get_result(home, away, d)

        if not res:
            open_count += len(game_tips)
            continue

        for tip in game_tips:
            status = settle_market(tip, res)
            if not status:
                open_count += 1
                continue

            data = {
                "status": status,
                "result": status,
                "settled_at": datetime.now(timezone.utc).isoformat(),
                "final_score": f"{res['home_goals']}-{res['away_goals']}",
                "settlement_source": res.get("source", ""),
            }
            if sb_patch_tip(tip, data):
                item = dict(tip)
                item["status"] = status
                settled.append(item)

        time.sleep(0.03)

    send_summary(settled, open_count)
    log(f"✅ Settlement V3 fertig: {len(settled)} ausgewertet, {open_count} offen/nicht auswertbar, Cache={len(RESULT_CACHE)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "ERROR")
        print(traceback.format_exc())
        raise
