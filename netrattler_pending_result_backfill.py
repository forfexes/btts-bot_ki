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
APIF_LOOKBACK_DAYS = max(1,min(30,int(os.getenv('BACKFILL_APIF_LOOKBACK_DAYS','1'))))
RAPID_MAX_DAYS = int(os.getenv("BACKFILL_RAPID_MAX_DAYS", "1"))  # free plan: 100 requests/MONTH

_STOP = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "fk", "sk", "if", "bk", "club", "de", "the"}
_PAIR = re.compile(r"<b>\s*([^<]+?)\s+vs\.?\s+([^<]+?)\s*</b>", re.I)


def norm_team(name: Any) -> str:
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    toks = [x for x in t.split() if x not in _STOP]
    return " ".join(toks)


# Only named, unambiguous editorial short forms. Never generic substring
# matching: "Paris" could be Paris FC or Paris Saint-Germain, and a shared
# "United" does not identify any single football club.
_VERIFIED_TEAM_ALIASES = {
    "wolverhampton": "wolverhampton wanderers",
    "wolves": "wolverhampton wanderers",
}


def team_match(a: Any, b: Any) -> bool:
    """Conservative club identity match; do not accept a shared generic word.

    The old substring fallback matched e.g. "Paris FC" to "Paris
    Saint-Germain", or "United" to "Manchester United", potentially
    settling a real Telegram pick against the wrong club's score. A data
    gap is preferable to false WIN/LOSS or a fabricated HT settlement.
    """
    x, y = norm_team(a), norm_team(b)
    x = _VERIFIED_TEAM_ALIASES.get(x, x)
    y = _VERIFIED_TEAM_ALIASES.get(y, y)
    if not x or not y:
        return False
    if x == y:
        return True
    # Never collapse reserve/youth/women's squads into the senior club.
    squad = {"ii", "b", "reserves", "reserve", "u17", "u18", "u19", "u20",
             "u21", "u23", "women", "womens", "femenino", "feminino"}
    xt, yt = x.split(), y.split()
    if (set(xt) & squad) != (set(yt) & squad):
        return False
    # Partial club names are NOT verified aliases, even with two matching
    # words: "Boca Juniors" can mean Boca Juniors (Argentina) or Boca Juniors
    # de Cali (Colombia). Full normalized identity is mandatory. Teams that
    # cannot be verified remain PENDING for a canonical-ID source lookup.
    return False


def tip_pair(row: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    match = str(row.get("match") or row.get("fixture") or "")
    # Real bookmaker and builder legs use several explicit fixture separators.
    # Never split on bare hyphens: they occur inside club names.
    parts = re.split(r"\s+(?:vs\.?|v\.?|[-–—])\s+", match, maxsplit=1, flags=re.I)
    if len(parts) == 2 and all(part.strip() for part in parts):
        return parts[0].strip(), parts[1].strip()
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
    """Select exact official fixtures; reject ambiguous duplicate match events.

    A finished fixture must have an unambiguous opponent pair AND a unique
    source event on that calendar day. If a feed contains two separate games
    with the same club names, neither can safely settle a tip by name alone.
    """
    candidates = []
    for row in rows:
        needs = [
            bool(ht) for h, a, ht in wanted
            if team_match(h, row.get("home_team"))
            and team_match(a, row.get("away_team"))
        ]
        if needs:
            candidates.append((row, any(needs)))
    groups: Dict[Tuple[str, str], List[Tuple[Dict[str, Any], bool]]] = {}
    for row, need in candidates:
        key = norm_team(row.get("home_team")), norm_team(row.get("away_team"))
        groups.setdefault(key, []).append((row, need))
    out = []
    for group in groups.values():
        if len(group) > 1:
            signatures = {
                (str(row.get("event_id") or ""), str(row.get("home_score")),
                 str(row.get("away_score")))
                for row, _ in group
            }
            # Distinct event identifiers OR conflicting full-time scores
            # must never be silently collapsed into a fictitious settlement.
            if len(signatures) != 1 or not next(iter(signatures))[0]:
                continue
        # Identical feed duplicates count as one real fixture and inherit the
        # strongest halftime-evidence requirement across pending tips.
        out.append((group[0][0], any(need for _, need in group)))
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
        if rest and apif_budget > 0 and day >= (datetime.now(timezone.utc).date() - timedelta(days=APIF_LOOKBACK_DAYS)).isoformat():  # explicit account-plan lookback
            apif_budget -= 1
            alt = apif.fetch_day(day)
            extra = select_rows(alt, rest)
            stats["apif"] = stats.get("apif", 0) + len(extra)
            hits = hits + extra
        found_rows = [r for r, _ in hits]
        rest = unmatched(found_rows, rest)
        stats.setdefault("unmatched", []).extend(f"{day} {h} vs {a}" for h, a, _ in rest[:6])
        if rest and rapid_budget > 0 and day >= (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat():  # rate-limit window only; older tips remain PENDING
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
