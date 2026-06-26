#!/usr/bin/env python3
"""
NETRATTLER Settlement V4 DATECACHE
=================================
Schnellere Settlement-Engine:
- lädt Ergebnisse pro Datum nur 1x statt pro Tipp
- TheSportsDB Eventsday als kostenloser Haupt-Fallback
- Football-Data optional pro Datum
- OpenLigaDB optional pro Saison
- wertet alle Tipps eines Spiels gemeinsam aus
"""

import os
import re
import time
import json
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

DAYS_BACK = int(os.getenv("SETTLEMENT_DAYS_BACK", "2"))
LIMIT = int(os.getenv("SETTLEMENT_LIMIT", "250"))
MAX_DATES = int(os.getenv("SETTLEMENT_MAX_DATES", "3"))
TIMEOUT_SECONDS = int(os.getenv("SETTLEMENT_TIMEOUT_SECONDS", "60"))
SEND_SUMMARY = os.getenv("SETTLEMENT_SEND_SUMMARY", "true").lower() in ("1", "true", "yes", "on")

TELEGRAM_STATS = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID", "")

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

START = time.time()
DATE_RESULTS: Dict[str, List[Dict[str, Any]]] = {}


def log(msg: str, level: str = "INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def timeout() -> bool:
    return time.time() - START > TIMEOUT_SECONDS


def norm(s: Any) -> str:
    s = str(s or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\b(fc|cf|sc|afc|u19|u20|u21|ii|b)\b", " ", s)
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def team_match(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    return inter >= max(1, min(len(wa), len(wb)) - 1)


def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_STATS:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_STATS, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
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
        log(f"PATCH Fehler {r.status_code}: {r.text[:120]}", "WARN")
    return r.ok


def tip_date(tip: Dict[str, Any]) -> str:
    for k in ("date", "match_date", "kickoff_date", "kickoff_at", "created_at"):
        v = str(tip.get(k) or "")
        m = re.search(r"\d{4}-\d{2}-\d{2}", v)
        if m:
            return m.group(0)
    return datetime.now(timezone.utc).date().isoformat()


def parse_match(tip: Dict[str, Any]) -> Tuple[str, str]:
    m = tip.get("match") or tip.get("fixture") or tip.get("game") or ""
    for sep in (" vs ", " v ", " - "):
        if sep in m:
            a, b = m.split(sep, 1)
            return a.strip(), b.strip()
    return str(tip.get("home_team") or tip.get("home") or "").strip(), str(tip.get("away_team") or tip.get("away") or "").strip()


def load_pending() -> List[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).date().isoformat()
    q = {
        "select": "*",
        "status": "eq.pending",
        "date": f"gte.{since}",
        "order": "date.asc",
        "limit": str(LIMIT),
    }
    rows = sb_get("tips", q)
    return rows[:LIMIT]


def source_thesportsdb_date(d: str) -> List[Dict[str, Any]]:
    out = []
    try:
        url = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php"
        r = requests.get(url, params={"d": d, "s": "Soccer"}, timeout=12)
        if not r.ok:
            return out
        for e in (r.json().get("events") or []):
            hs = e.get("intHomeScore")
            aw = e.get("intAwayScore")
            if hs in (None, "") or aw in (None, ""):
                continue
            out.append({
                "home": e.get("strHomeTeam") or "",
                "away": e.get("strAwayTeam") or "",
                "home_goals": int(hs),
                "away_goals": int(aw),
                "ht_home_goals": None,
                "ht_away_goals": None,
                "source": "thesportsdb",
            })
    except Exception as e:
        log(f"TheSportsDB {d} skip: {e}", "WARN")
    return out


def source_football_data_date(d: str) -> List[Dict[str, Any]]:
    out = []
    if not FOOTBALL_DATA_KEYS:
        return out
    for api_key in FOOTBALL_DATA_KEYS[:2]:
        try:
            r = requests.get(
                "https://api.football-data.org/v4/matches",
                headers={"X-Auth-Token": api_key},
                params={"dateFrom": d, "dateTo": d},
                timeout=12,
            )
            if r.status_code in (401, 403, 429):
                continue
            if not r.ok:
                continue
            for m in r.json().get("matches", []):
                ft = (m.get("score") or {}).get("fullTime") or {}
                ht = (m.get("score") or {}).get("halfTime") or {}
                if ft.get("home") is None or ft.get("away") is None:
                    continue
                out.append({
                    "home": (m.get("homeTeam") or {}).get("name", ""),
                    "away": (m.get("awayTeam") or {}).get("name", ""),
                    "home_goals": int(ft.get("home") or 0),
                    "away_goals": int(ft.get("away") or 0),
                    "ht_home_goals": int(ht.get("home") or 0) if ht.get("home") is not None else None,
                    "ht_away_goals": int(ht.get("away") or 0) if ht.get("away") is not None else None,
                    "source": "football-data",
                })
            if out:
                return out
        except Exception:
            continue
    return out


def load_results_for_date(d: str) -> List[Dict[str, Any]]:
    if d in DATE_RESULTS:
        return DATE_RESULTS[d]
    results = []
    # Kostenlos und breit zuerst
    results.extend(source_thesportsdb_date(d))
    # Football-Data als Zusatz für Top-Ligen
    results.extend(source_football_data_date(d))

    # Dedupe
    seen = set()
    clean = []
    for r in results:
        key = (norm(r.get("home")), norm(r.get("away")), r.get("home_goals"), r.get("away_goals"))
        if key in seen:
            continue
        seen.add(key)
        clean.append(r)
    DATE_RESULTS[d] = clean
    log(f"Ergebnisse {d}: {len(clean)} geladen")
    return clean


def find_result(home: str, away: str, d: str) -> Optional[Dict[str, Any]]:
    for r in load_results_for_date(d):
        if team_match(home, r.get("home", "")) and team_match(away, r.get("away", "")):
            return r
    return None


def settle_market(tip: Dict[str, Any], res: Dict[str, Any]) -> Optional[str]:
    market = norm(tip.get("market") or tip.get("type") or tip.get("category") or "")
    pick = norm(tip.get("tip") or tip.get("pick") or tip.get("selection") or "")
    hg, ag = int(res["home_goals"]), int(res["away_goals"])
    total = hg + ag
    hth, hta = res.get("ht_home_goals"), res.get("ht_away_goals")

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

    return None


def group_key(tip: Dict[str, Any]) -> str:
    m = norm(tip.get("market") or tip.get("type") or tip.get("category") or "")
    if "btts ht" in m or "btts_ht" in m:
        return "BTTS HT"
    if "over15 ht" in m or "over1 5 ht" in m:
        return "Over HT"
    if "over25" in m or "over 2 5" in m:
        return "Over2.5"
    if "combo" in m:
        return "Combo"
    if "corner" in m:
        return "Corners"
    return "BTTS"


def send_summary(settled: List[Dict[str, Any]], skipped: int):
    if not SEND_SUMMARY:
        return
    if not settled:
        send_telegram(f"📊 <b>Settlement V4</b>\nKeine Tipps ausgewertet.\nOffen/ohne Ergebnis: {skipped}")
        return
    by = {}
    for x in settled:
        by.setdefault(group_key(x), []).append(x)
    lines = ["📊 <b>Settlement V4</b>"]
    tw = tl = 0
    for g, items in sorted(by.items()):
        w = sum(1 for i in items if i["status"] == "won")
        l = sum(1 for i in items if i["status"] == "lost")
        tw += w; tl += l
        hr = round(w / max(1, w+l) * 100, 1)
        lines.append(f"{g}: ✅ {w} ❌ {l} · {hr}%")
    lines.append(f"\nTotal: ✅ {tw} ❌ {tl} · <b>{round(tw / max(1, tw+tl) * 100, 1)}%</b>")
    lines.append(f"Offen/ohne Ergebnis: {skipped}")
    send_telegram("\n".join(lines))


def main():
    log("⚽ NETRATTLER Settlement V4 DATECACHE startet")
    tips = load_pending()
    log(f"Offene Tipps geladen: {len(tips)} | Limit={LIMIT} | Days={DAYS_BACK}")

    dates = sorted({tip_date(t) for t in tips})[:MAX_DATES]
    log(f"Dates: {dates}")

    # Ergebnisse pro Datum vorladen
    for d in dates:
        if time.time() - START > TIMEOUT_SECONDS:
            break
        load_results_for_date(d)

    settled = []
    skipped = 0
    checked_games = set()

    for tip in tips:
        if time.time() - START > TIMEOUT_SECONDS:
            log("⏱️ Timeout-Limit erreicht, stoppe sauber", "WARN")
            break
        d = tip_date(tip)
        if d not in dates:
            skipped += 1
            continue
        home, away = parse_match(tip)
        if not home or not away:
            skipped += 1
            continue

        res = find_result(home, away, d)
        if not res:
            skipped += 1
            continue

        status = settle_market(tip, res)
        if not status:
            skipped += 1
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

    send_summary(settled, skipped)
    log(f"✅ Settlement V4 fertig: {len(settled)} ausgewertet, {skipped} offen/nicht auswertbar, Dates={len(dates)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "ERROR")
        print(traceback.format_exc())
        raise
