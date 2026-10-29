#!/usr/bin/env python3
"""Targeted result backfill for still-pending tips.

The daily FotMob job only fetches *yesterday* and fills half-time scores for the
first 150 matches.  Tips whose day was missed, or whose HT score was never
fetched, stay pending forever.  This job re-reads the FotMob day feed for every
day that still has pending tips (plus the adjacent days) and fetches half-time
scores only for matches that a pending tip refers to.  Only real reported
scores are written; nothing is estimated.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

import netrattler_fotmob_results as fr
import netrattler_apifootball_results as apif
import netrattler_rapid_results as rapid

SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}"}
MAX_DAYS = int(os.getenv("BACKFILL_MAX_DAYS", "21"))
MAX_HT = int(os.getenv("BACKFILL_MAX_HT", "400"))
APIF_MAX_DAYS = int(os.getenv("BACKFILL_APIF_MAX_DAYS", "10"))
RAPID_MAX_DAYS = int(os.getenv("BACKFILL_RAPID_MAX_DAYS", "1"))  # free plan: 100 requests/MONTH

_STOP = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "fk", "sk", "if", "bk", "club", "de", "the"}
_PAIR = re.compile(r"<b>\s*([^<]+?)\s+vs\.?\s+([^<]+?)\s*</b>", re.I)


def norm_team(name: Any) -> str:
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    toks = [x for x in t.split() if x not in _STOP]
    return " ".join(toks)


def team_match(a: Any, b: Any) -> bool:
    x, y = norm_team(a), norm_team(b)
    if not x or not y:
        return False
    if x == y:
        return True
    # containment only for reasonably specific names (avoid 'united' matching everything)
    return (len(x) >= 5 and len(y) >= 5) and (x in y or y in x)


def tip_pair(row: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    match = str(row.get("match") or "")
    if " vs " in match:
        home, away = match.split(" vs ", 1)
        if home.strip() and away.strip():
            return home.strip(), away.strip()
    m = _PAIR.search(str(row.get("message_text") or ""))
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def tip_day(row: Dict[str, Any]) -> Optional[str]:
    explicit = row.get("date") or row.get("match_date")
    if explicit:
        return str(explicit)[:10]
    m = re.search(r"(20\d\d-\d\d-\d\d)", str(row.get("tip_id") or ""))
    if m:
        return m.group(1)
    c = str(row.get("created_at") or "")
    return c[:10] if len(c) >= 10 else None


def pending_tips() -> List[Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=MAX_DAYS)).isoformat()
    until = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    r = requests.get(f"{SB}/rest/v1/tips", headers=H, timeout=40, params={
        "select": "tip_id,market,match,date,builder_legs,message_text,created_at", "status": "eq.pending",
        "created_at": f"gte.{since}", "and": f"(created_at.lte.{until})", "limit": "5000"})
    r.raise_for_status()
    tips = r.json()
    if not isinstance(tips, list):
        raise RuntimeError("Invalid pending-tip response")
    # Builders are stored separately; include all published legs and their own dates.
    r = requests.get(f"{SB}/rest/v1/netrattler_builder_picks", headers=H, timeout=40, params={
        "select": "tip_id,match_date,legs,created_at", "status": "eq.pending",
        "telegram_msg_id": "not.is.null", "created_at": f"gte.{since}",
        "and": f"(created_at.lte.{until})", "limit": "5000"})
    r.raise_for_status()
    builders = r.json()
    if not isinstance(builders, list) or len(tips) >= 5000 or len(builders) >= 5000:
        raise RuntimeError("Incomplete pending backfill read")
    return tips + builders


def plan(tips: List[Dict[str, Any]]):
    """Return {day: [(home, away, needs_ht)]} including adjacent days."""
    by_day: Dict[str, List[Tuple[str, str, bool]]] = {}
    expanded = []
    for t in tips:
        legs = t.get("legs") or t.get("builder_legs")
        if isinstance(legs, list) and legs:
            for leg in legs:
                if isinstance(leg, dict):
                    expanded.append({**t, **leg})
        else:
            expanded.append(t)
    for t in expanded:
        pair, d = tip_pair(t), tip_day(t)
        if not pair or not d:
            continue
        needs_ht = str(t.get("market") or "").endswith("_ht")
        try:
            base = datetime.fromisoformat(d).date()
        except ValueError:
            continue
        for off in (0, 1, -1):
            by_day.setdefault((base + timedelta(days=off)).isoformat(), []).append((pair[0], pair[1], needs_ht))
    return by_day


def select_rows(rows: List[Dict[str, Any]], wanted: List[Tuple[str, str, bool]]):
    """Rows matching a pending tip (both teams), with a flag whether HT is needed."""
    out = []
    for row in rows:
        need = None
        for h, a, ht in wanted:
            if team_match(h, row.get("home_team")) and team_match(a, row.get("away_team")):
                need = bool(need) or ht
        if need is not None:
            out.append((row, need))
    return out


def unmatched(rows, wanted):
    """Wanted (home, away, ht) pairs for which no row matched."""
    return [w for w in wanted if not select_rows(rows, [w])]


def run() -> Dict[str, int]:
    stats = {"days": 0, "matched": 0, "ht": 0, "saved": 0}
    if not SB or not SK:
        return stats
    today = datetime.now(timezone.utc).date().isoformat()
    by_day = plan(pending_tips())
    ht_budget = MAX_HT
    apif_budget = APIF_MAX_DAYS
    rapid_budget = RAPID_MAX_DAYS
    for day in sorted(by_day):
        if day >= today:
            continue
        payload = None
        compact = day.replace("-", "")
        for url, params in (("https://www.fotmob.com/api/data/matches", {"date": compact}),
                            ("https://www.fotmob.com/api/matches", {"date": compact})):
            payload = fr._fetch_json(url, params)
            if isinstance(payload, dict) and (payload.get("leagues") or payload.get("matches")):
                break
        rows = fr.parse_daily_payload(payload, day)
        stats["days"] += 1
        hits = select_rows(rows, by_day[day])
        rest = unmatched(rows, by_day[day])
        if rest and apif_budget > 0 and day >= (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat():  # free plan: only yesterday..tomorrow
            apif_budget -= 1
            alt = apif.fetch_day(day)
            extra = select_rows(alt, rest)
            stats["apif"] = stats.get("apif", 0) + len(extra)
            hits = hits + extra
        found_rows = [r for r, _ in hits]
        rest = unmatched(found_rows, rest)
        if rest and rapid_budget > 0 and day >= (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat():  # older tips are voided anyway
            rapid_budget -= 1
            extra = select_rows(rapid.fetch_day(day), rest)
            stats["rapid"] = stats.get("rapid", 0) + len(extra)
            hits = hits + extra
        save = []
        for row, need_ht in hits:
            row = dict(row)
            row.pop("ht_home", None)
            row.pop("ht_away", None)  # never overwrite a stored HT score with null
            if need_ht and ht_budget > 0:
                ht_budget -= 1
                ht = fr.fetch_halftime(row.get("event_id"))
                if ht is not None:
                    row["ht_home"], row["ht_away"] = ht
                    stats["ht"] += 1
                time.sleep(0.15)
            save.append(row)
        stats["matched"] += len(save)
        stats["saved"] += fr.persist(save)
        time.sleep(0.3)
    print(f"Pending result backfill: {stats}")
    try:
        requests.post(f"{SB}/rest/v1/netrattler_card_diag", timeout=20,
                      json={"info": {"probe": "pending_backfill", "stats": stats, "apif_key": bool(apif._key()),
                                     "pending": sum(len(v) for v in by_day.values()), "days": sorted(by_day)[:25]}},
                      headers={**H, "Content-Type": "application/json"})
    except Exception:
        pass
    return stats


if __name__ == "__main__":
    run()
