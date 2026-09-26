#!/usr/bin/env python3
"""Persist completed FotMob football scores into match_results.

The daily player-stat scraper already reaches FotMob successfully on GitHub
Actions, but historically only wrote player stats. This tiny companion reuses
FotMob's working daily feed so settlement has far broader exact score coverage.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _fetch_json(url: str, params: dict):
    try:
        from curl_cffi import requests as crequests
        response = crequests.get(url, params=params, headers=HEADERS, impersonate="chrome", timeout=20)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if response.ok:
            return response.json()
    except Exception:
        pass
    return None


def _num(value: Any):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _score(team: Any):
    if not isinstance(team, dict):
        return None
    raw = team.get("score")
    if isinstance(raw, dict):
        raw = raw.get("current") if raw.get("current") is not None else raw.get("score")
    return _num(raw)


def _scores(match: Dict[str, Any]):
    home = _score(match.get("home") or {})
    away = _score(match.get("away") or {})
    if home is not None and away is not None:
        return home, away
    status = match.get("status") or {}
    text = status.get("scoreStr") or match.get("scoreStr") or ""
    found = re.search(r"(\d+)\s*[-:]\s*(\d+)", str(text))
    if found:
        return int(found.group(1)), int(found.group(2))
    return None, None


def _finished(match: Dict[str, Any]) -> bool:
    status = match.get("status") or {}
    if status.get("finished") is True or str(status.get("finished", "")).lower() in {"true", "1"}:
        return True
    if str(status.get("statusId", "")).lower() in {"6", "finished"}:
        return True
    reason = status.get("reason") or ""
    if isinstance(reason, dict):
        reason = " ".join(str(reason.get(k) or "") for k in ("short", "long", "name"))
    text = f"{reason} {status.get('status') or ''}".lower()
    return any(x in text for x in ("full time", "finished", "after penalties", "after extra time"))


def parse_daily_payload(payload: Any, date_str: str) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    listed = []
    for league in payload.get("leagues") or []:
        league_name = str(league.get("name") or "")
        for match in league.get("matches") or []:
            listed.append((league_name, match))
    if not listed:
        for match in payload.get("matches") or []:
            listed.append((str(match.get("leagueName") or ""), match))

    rows: List[Dict[str, Any]] = []
    for league_name, match in listed:
        if not isinstance(match, dict) or not _finished(match):
            continue
        home_obj = match.get("home") or {}
        away_obj = match.get("away") or {}
        home = str(home_obj.get("name") or match.get("homeName") or "").strip()
        away = str(away_obj.get("name") or match.get("awayName") or "").strip()
        hs, aw = _scores(match)
        event_id = match.get("id") or match.get("matchId")
        if not event_id or not home or not away or hs is None or aw is None:
            continue
        rows.append({
            "source": "fotmob",
            "event_id": str(event_id),
            "match_date": date_str,
            "home_team": home,
            "away_team": away,
            "home_score": hs,
            "away_score": aw,
            "ht_home": None,
            "ht_away": None,
            "league": league_name,
            "country": "",
            "status": "finished",
        })
    return rows


def fetch_results(date_str: str) -> List[Dict[str, Any]]:
    compact = date_str.replace("-", "")
    payload = None
    for url, params in (
        ("https://www.fotmob.com/api/data/matches", {"date": compact}),
        ("https://www.fotmob.com/api/data/matches", {"date": date_str}),
        ("https://www.fotmob.com/api/matches", {"date": compact}),
    ):
        payload = _fetch_json(url, params)
        if isinstance(payload, dict) and (payload.get("leagues") or payload.get("matches")):
            break
    rows = parse_daily_payload(payload, date_str)
    print(f"✅ FotMob results: {len(rows)} completed matches for {date_str}")
    return rows


def persist(rows: List[Dict[str, Any]]) -> int:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    endpoint = f"{SUPABASE_URL}/rest/v1/match_results"
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            params={"on_conflict": "source,event_id"},
            json=rows,
            timeout=45,
        )
        if response.ok:
            print(f"💾 FotMob results saved: {len(rows)}")
            return len(rows)
        print(f"⚠️ FotMob result save {response.status_code}: {response.text[:220]}")
    except Exception as exc:
        print(f"⚠️ FotMob result save: {str(exc)[:160]}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--yesterday", action="store_true")
    args = parser.parse_args()
    date_str = args.date.strip() if args.date else ""
    if args.yesterday or not date_str:
        date_str = str((datetime.now(timezone.utc) - timedelta(days=1)).date())
    persist(fetch_results(date_str))


if __name__ == "__main__":
    main()
