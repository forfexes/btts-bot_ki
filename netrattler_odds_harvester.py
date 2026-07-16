#!/usr/bin/env python3
"""
NETRATTLER V34 — BOOKMAKER ODDS HARVESTER
==========================================
Collects every free/public odds source that is actually usable and falls back
source-by-source without aborting the run.

Historical ML odds:
- Football-Data.co.uk: Bet365, Pinnacle, Betfair, William Hill, Interwetten,
  BetVictor, market average/max, totals 2.5 and Asian handicap when present.

Live/upcoming odds:
1. Pinnacle guest API (no paid key)
2. The Odds API (only when a key has quota)
3. OddsHarvester / OddsPortal via Playwright (all bookies + target Bet365)
4. Bet365 public-page Playwright best effort (no login, no anti-bot bypass)
5. Betfair Exchange API only when official credentials are supplied

Writes normalized rows to Supabase odds_history. If that table is unavailable,
it also attempts netrattler_data_lake_raw and always writes a local JSON report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
USER_AGENT = os.getenv(
    "NTR_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"}

PINNACLE_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
PINNACLE_SPORT_SOCCER = 29
PINNACLE_GUEST_KEY = os.getenv("PINNACLE_GUEST_KEY", "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R")
PINNACLE_HEADERS = {
    "x-api-key": PINNACLE_GUEST_KEY,
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
    "Referer": "https://www.pinnacle.com/",
    "Origin": "https://www.pinnacle.com",
    "Accept": "application/json",
}

FD_LEAGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "D1": "Bundesliga", "D2": "2. Bundesliga",
    "SP1": "La Liga", "SP2": "Segunda Division",
    "I1": "Serie A", "I2": "Serie B",
    "F1": "Ligue 1", "F2": "Ligue 2",
    "N1": "Eredivisie", "P1": "Primeira Liga",
    "B1": "Jupiler Pro League", "T1": "Super Lig",
    "SC0": "Scottish Premiership", "G1": "Super League Greece",
}

BOOKMAKER_PREFIXES = {
    "B365": "bet365", "PS": "pinnacle", "P": "pinnacle", "BF": "betfair_sportsbook",
    "BFE": "betfair_exchange", "WH": "william_hill", "IW": "interwetten",
    "BW": "bwin", "BV": "betvictor", "VC": "betvictor", "LB": "ladbrokes",
    "CL": "coral", "GB": "gamebookers", "SB": "sportingbet", "SJ": "stan_james",
    "1XB": "1xbet", "BMGM": "betmgm", "Avg": "market_average", "Max": "market_maximum",
}


def log(message: str, level: str = "INFO") -> None:
    icon = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌"}.get(level, "•")
    print(f"{icon} {message}")


def _bool_env(name: str, default: bool = True) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


def _float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        x = float(str(value).strip().replace(",", "."))
        return x if x > 1.0 else None
    except Exception:
        return None


def _date_text(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _match_id(source: str, match_date: str, home: str, away: str, league: str = "") -> str:
    raw = f"{source}|{match_date}|{league}|{home}|{away}".lower().encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:32]


def _clean_team(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _odds_row(
    *, source: str, bookmaker: str, market: str, selection: str, odds: float,
    match_date: str, home: str, away: str, match_id: Optional[str] = None,
    line: Optional[float] = None, captured_at: Optional[str] = None,
    league: str = "", raw: Optional[dict] = None,
) -> Dict[str, Any]:
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    captured_date = captured_at[:10]
    mid = match_id or _match_id(source, match_date, home, away, league)
    payload = {
        "source": source[:80],
        "match_id": str(mid),
        "home_team": _clean_team(home),
        "away_team": _clean_team(away),
        "match_date": match_date,
        "captured_date": captured_date,
        "market": market,
        "bookmaker": bookmaker[:80],
        "selection": selection,
        "odds": round(float(odds), 4),
        "raw": raw or {},
    }
    # Some schemas have these columns, some do not. They remain inside raw too.
    if line is not None:
        payload["raw"] = {**payload["raw"], "line": line}
    if league:
        payload["raw"] = {**payload["raw"], "league": league}
    payload["raw"] = {**payload["raw"], "captured_at": captured_at}
    return payload


def _dedupe(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        try:
            key = tuple(str(row.get(k) or "") for k in (
                "source", "match_id", "market", "bookmaker", "captured_date", "selection"
            ))
            if all(key):
                best[key] = row
        except Exception:
            continue
    return list(best.values())


def _sb_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _sb_post(table: str, rows: Sequence[Dict[str, Any]], conflict: str) -> Tuple[int, int]:
    if not rows or not SUPABASE_URL or not SUPABASE_KEY:
        return 0, 0
    ok = fail = 0
    endpoint = f"{SUPABASE_URL}/rest/v1/{table}"
    for i in range(0, len(rows), 400):
        chunk = list(rows[i:i + 400])
        try:
            r = requests.post(
                endpoint, headers=_sb_headers(), params={"on_conflict": conflict}, json=chunk, timeout=90
            )
            if r.ok:
                ok += len(chunk)
            else:
                fail += len(chunk)
                log(f"Supabase {table} {r.status_code}: {r.text[:240]}", "WARN")
        except Exception as exc:
            fail += len(chunk)
            log(f"Supabase {table}: {exc}", "WARN")
    return ok, fail


def persist_odds(rows: Sequence[Dict[str, Any]], output: str = "netrattler_odds_snapshot.json") -> Dict[str, int]:
    clean = _dedupe(rows)
    Path(output).write_text(json.dumps(clean, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result = {"local": len(clean), "odds_history": 0, "data_lake": 0}
    ok, _ = _sb_post(
        "odds_history", clean,
        "source,match_id,market,bookmaker,captured_date,selection",
    )
    result["odds_history"] = ok
    if ok == 0 and clean:
        lake = []
        for row in clean:
            raw = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            lake.append({
                "source": row["source"],
                "source_type": "bookmaker_odds",
                "entity_type": "odds_snapshot",
                "entity_name": f"{row['home_team']} vs {row['away_team']}",
                "market": row["market"],
                "category": row["bookmaker"],
                "payload": row,
                "data_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
        lake_ok, _ = _sb_post("netrattler_data_lake_raw", lake, "data_hash")
        result["data_lake"] = lake_ok
    return result


def _fd_season_codes(start_year: int = 2010, end_year: Optional[int] = None) -> List[str]:
    end_year = end_year or datetime.now(timezone.utc).year
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(start_year, end_year + 1)]


def _bookie(prefix: str) -> str:
    return BOOKMAKER_PREFIXES.get(prefix, prefix.lower())


def _read_fd_csv(season: str, code: str) -> List[Dict[str, str]]:
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if not r.ok or len(r.content) < 100:
            return []
        text = r.content.decode("utf-8-sig", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return []


def collect_football_data_history(
    start_year: int = 2010, max_leagues: int = 0, max_rows_per_csv: int = 0
) -> List[Dict[str, Any]]:
    """Historical pre-match odds including Bet365 and other bookmakers."""
    rows: List[Dict[str, Any]] = []
    leagues = list(FD_LEAGUES.items())[:max_leagues or None]
    seasons = _fd_season_codes(start_year)
    log(f"Football-Data history: {len(seasons)} seasons × {len(leagues)} leagues")
    for season in seasons:
        season_rows = 0
        for code, league in leagues:
            data = _read_fd_csv(season, code)
            if max_rows_per_csv:
                data = data[:max_rows_per_csv]
            for raw in data:
                match_date = _date_text(raw.get("Date"))
                home, away = _clean_team(raw.get("HomeTeam")), _clean_team(raw.get("AwayTeam"))
                if not match_date or not home or not away:
                    continue
                mid = _match_id("football_data_co_uk", match_date, home, away, f"{season}_{code}")
                # 1X2 opening/current columns.
                for prefix, bookie in BOOKMAKER_PREFIXES.items():
                    h, d, a = (_float(raw.get(prefix + suffix)) for suffix in ("H", "D", "A"))
                    for selection, odd in (("home", h), ("draw", d), ("away", a)):
                        if odd:
                            rows.append(_odds_row(
                                source="football_data_co_uk", bookmaker=bookie, market="1x2",
                                selection=selection, odds=odd, match_date=match_date, home=home, away=away,
                                match_id=mid, captured_at=match_date + "T00:00:00+00:00", league=league,
                            ))
                    # Closing 1X2, e.g. B365CH/B365CD/B365CA, PSCH/PSCD/PSCA.
                    ch, cd, ca = (_float(raw.get(prefix + "C" + suffix)) for suffix in ("H", "D", "A"))
                    for selection, odd in (("home", ch), ("draw", cd), ("away", ca)):
                        if odd:
                            rows.append(_odds_row(
                                source="football_data_co_uk", bookmaker=bookie + "_closing", market="1x2",
                                selection=selection, odds=odd, match_date=match_date, home=home, away=away,
                                match_id=mid, captured_at=match_date + "T00:00:00+00:00", league=league,
                            ))
                # Totals 2.5.
                total_prefixes = {
                    "B365": "bet365", "P": "pinnacle", "PS": "pinnacle", "GB": "gamebookers",
                    "Avg": "market_average", "Max": "market_maximum",
                }
                for prefix, bookie in total_prefixes.items():
                    over = _float(raw.get(prefix + ">2.5"))
                    under = _float(raw.get(prefix + "<2.5"))
                    for selection, odd in (("over_2_5", over), ("under_2_5", under)):
                        if odd:
                            rows.append(_odds_row(
                                source="football_data_co_uk", bookmaker=bookie, market="totals_2_5",
                                selection=selection, odds=odd, match_date=match_date, home=home, away=away,
                                match_id=mid, line=2.5, captured_at=match_date + "T00:00:00+00:00", league=league,
                            ))
                # Asian handicap.
                ah_line = raw.get("AHh") or raw.get("BbAHh") or raw.get("B365AH")
                try:
                    ah_line_f = float(str(ah_line).replace(",", ".")) if ah_line not in (None, "") else None
                except Exception:
                    ah_line_f = None
                for prefix, bookie in (("B365", "bet365"), ("P", "pinnacle"), ("Avg", "market_average"), ("Max", "market_maximum")):
                    ho = _float(raw.get(prefix + "AHH"))
                    ao = _float(raw.get(prefix + "AHA"))
                    for selection, odd in (("home", ho), ("away", ao)):
                        if odd:
                            rows.append(_odds_row(
                                source="football_data_co_uk", bookmaker=bookie, market="asian_handicap",
                                selection=selection, odds=odd, match_date=match_date, home=home, away=away,
                                match_id=mid, line=ah_line_f, captured_at=match_date + "T00:00:00+00:00", league=league,
                            ))
                season_rows += 1
        log(f"Football-Data {season}: {season_rows} matches", "OK" if season_rows else "WARN")
    log(f"Football-Data normalized odds rows: {len(rows)}", "OK")
    return rows


def _american_to_decimal(value: Any) -> Optional[float]:
    try:
        x = float(value)
        if abs(x) < 1:
            return None
        return round(1 + (x / 100 if x > 0 else 100 / abs(x)), 4)
    except Exception:
        return None


def collect_pinnacle_live(target_date: Optional[str] = None, max_matches: int = 250) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        r = requests.get(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/matchups",
            headers=PINNACLE_HEADERS, params={"withSpecials": "false", "brandId": "0"}, timeout=30,
        )
        if not r.ok:
            log(f"Pinnacle matchups HTTP {r.status_code}", "WARN")
            return []
        matchups = []
        for m in r.json():
            if m.get("type") != "matchup":
                continue
            parts = m.get("participants") or []
            home = next((p.get("name") for p in parts if p.get("alignment") == "home"), None)
            away = next((p.get("name") for p in parts if p.get("alignment") == "away"), None)
            start = str(m.get("startTime") or "")
            mdate = start[:10]
            if not home or not away or (target_date and mdate != target_date):
                continue
            matchups.append((m, home, away, mdate))
        for m, home, away, mdate in matchups[:max_matches]:
            mid = str(m.get("id"))
            rr = requests.get(
                f"{PINNACLE_BASE}/matchups/{mid}/markets/related/straight",
                headers=PINNACLE_HEADERS, timeout=20,
            )
            if not rr.ok:
                continue
            league = (m.get("league") or {}).get("name", "")
            for market in rr.json():
                mtype, period = market.get("type", ""), market.get("period", 0)
                for price in market.get("prices") or []:
                    odd = _float(price.get("price")) or _american_to_decimal(price.get("price"))
                    if not odd:
                        continue
                    des = str(price.get("designation") or "").lower()
                    points = price.get("points")
                    normalized_market = selection = None
                    line = None
                    if mtype == "moneyline" and period == 0 and des in {"home", "draw", "away"}:
                        normalized_market, selection = "1x2", des
                    elif mtype == "total" and period == 0 and des in {"over", "under"}:
                        normalized_market = "totals"
                        line = float(points) if points is not None else None
                        selection = f"{des}_{str(line).replace('.', '_')}" if line is not None else des
                    elif mtype == "spread" and period == 0 and des in {"home", "away"}:
                        normalized_market, selection = "asian_handicap", des
                        line = float(points) if points is not None else None
                    if normalized_market and selection:
                        rows.append(_odds_row(
                            source="pinnacle_guest", bookmaker="pinnacle", market=normalized_market,
                            selection=selection, odds=odd, match_date=mdate, home=home, away=away,
                            match_id=mid, line=line, league=league,
                            raw={"period": period, "type": mtype},
                        ))
        log(f"Pinnacle live: {len(rows)} odds rows", "OK" if rows else "WARN")
    except Exception as exc:
        log(f"Pinnacle live: {exc}", "WARN")
    return rows


def _odds_api_keys() -> List[str]:
    raw = os.getenv("ODDS_API_KEYS") or os.getenv("ODDS_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def collect_the_odds_api(target_date: Optional[str] = None, max_sports: int = 80) -> List[Dict[str, Any]]:
    keys = _odds_api_keys()
    if not keys:
        log("The Odds API: no key; next source", "WARN")
        return []
    for key in keys:
        try:
            sr = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": key}, timeout=25)
            if not sr.ok:
                continue
            sports = [s for s in sr.json() if s.get("active") and str(s.get("key", "")).startswith("soccer_")]
            rows: List[Dict[str, Any]] = []
            for sport in sports[:max_sports]:
                rr = requests.get(
                    f"https://api.the-odds-api.com/v4/sports/{sport['key']}/odds",
                    params={
                        "apiKey": key, "regions": os.getenv("ODDS_API_REGIONS", "eu,uk"),
                        "markets": "h2h,totals", "oddsFormat": "decimal", "dateFormat": "iso",
                    }, timeout=30,
                )
                if rr.status_code in {401, 402, 429}:
                    break
                if not rr.ok:
                    continue
                for game in rr.json():
                    start = str(game.get("commence_time") or "")
                    mdate = start[:10]
                    if target_date and mdate != target_date:
                        continue
                    home, away = game.get("home_team", ""), game.get("away_team", "")
                    for bm in game.get("bookmakers") or []:
                        bookie = bm.get("key") or bm.get("title") or "unknown"
                        for market in bm.get("markets") or []:
                            mkey = market.get("key")
                            for outcome in market.get("outcomes") or []:
                                odd = _float(outcome.get("price"))
                                if not odd:
                                    continue
                                name = str(outcome.get("name") or "")
                                line = outcome.get("point")
                                if mkey == "h2h":
                                    if name == home:
                                        selection = "home"
                                    elif name == away:
                                        selection = "away"
                                    else:
                                        selection = "draw"
                                    market_name = "1x2"
                                elif mkey == "totals":
                                    side = name.lower()
                                    market_name = "totals"
                                    selection = f"{side}_{str(line).replace('.', '_')}"
                                else:
                                    continue
                                rows.append(_odds_row(
                                    source="the_odds_api", bookmaker=str(bookie), market=market_name,
                                    selection=selection, odds=odd, match_date=mdate, home=home, away=away,
                                    match_id=game.get("id"), line=float(line) if line is not None else None,
                                    league=sport.get("title", ""), raw={"last_update": bm.get("last_update")},
                                ))
            if rows:
                log(f"The Odds API: {len(rows)} rows", "OK")
                return rows
        except Exception as exc:
            log(f"The Odds API key failed: {str(exc)[:120]}", "WARN")
    log("The Odds API: all keys empty/exhausted; next source", "WARN")
    return []


def _find_json_files(root: Path) -> List[Path]:
    return sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".csv"}])


def _walk_odds_objects(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        if any(k in node for k in ("home_team", "home", "homeTeam")) and any(k in node for k in ("away_team", "away", "awayTeam")):
            yield node
        for value in node.values():
            yield from _walk_odds_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_odds_objects(value)


def _parse_oddsharvester_outputs(files: Sequence[Path], target_date: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in files:
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                objects = list(_walk_odds_objects(data))
            else:
                objects = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
        except Exception:
            continue
        for obj in objects:
            home = obj.get("home_team") or obj.get("home") or obj.get("homeTeam") or obj.get("team1")
            away = obj.get("away_team") or obj.get("away") or obj.get("awayTeam") or obj.get("team2")
            dt = _date_text(obj.get("date") or obj.get("match_date") or obj.get("start_time"))
            if not home or not away or not dt or (target_date and dt != target_date):
                continue
            league = str(obj.get("league") or obj.get("tournament") or "OddsPortal")
            mid = _match_id("oddsportal", dt, str(home), str(away), league)
            # Flatten common OddsHarvester variants.
            bookmaker_nodes = obj.get("bookmakers") or obj.get("odds") or obj.get("bookmaker_odds") or []
            if isinstance(bookmaker_nodes, dict):
                bookmaker_nodes = [{"bookmaker": k, **(v if isinstance(v, dict) else {"odds": v})} for k, v in bookmaker_nodes.items()]
            for bm in bookmaker_nodes if isinstance(bookmaker_nodes, list) else []:
                bookie = str(bm.get("bookmaker") or bm.get("name") or bm.get("title") or "oddsportal")
                market = str(bm.get("market") or obj.get("market") or "1x2").lower()
                # Direct outcomes list.
                outcomes = bm.get("outcomes") or bm.get("prices")
                if isinstance(outcomes, list):
                    for out in outcomes:
                        odd = _float(out.get("odds") or out.get("price") or out.get("value"))
                        if not odd:
                            continue
                        selection = str(out.get("selection") or out.get("name") or out.get("designation") or "")
                        line = out.get("line") or out.get("point")
                        rows.append(_odds_row(
                            source="oddsharvester_oddsportal", bookmaker=bookie, market=market,
                            selection=selection, odds=odd, match_date=dt, home=str(home), away=str(away),
                            match_id=mid, line=float(line) if line not in (None, "") else None, league=league,
                        ))
                # Common flat 1X2 columns.
                for selection, keys in {
                    "home": ("home_odds", "home", "1"), "draw": ("draw_odds", "draw", "x"),
                    "away": ("away_odds", "away", "2"),
                }.items():
                    odd = next((_float(bm.get(k)) for k in keys if _float(bm.get(k))), None)
                    if odd:
                        rows.append(_odds_row(
                            source="oddsharvester_oddsportal", bookmaker=bookie, market="1x2",
                            selection=selection, odds=odd, match_date=dt, home=str(home), away=str(away),
                            match_id=mid, league=league,
                        ))
    return rows


def collect_oddsharvester(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    if not _bool_env("ENABLE_ODDSHARVESTER", True):
        return []
    exe = os.getenv("ODDSHARVESTER_BIN", "oddsharvester")
    with tempfile.TemporaryDirectory(prefix="ntr_oddsharvester_") as td:
        root = Path(td)
        output_base = root / "odds"
        day = (target_date or date.today().isoformat()).replace("-", "")
        commands = [
            [exe, "upcoming", "-s", "football", "-d", day, "-m", "1x2,btts,over_under", "--headless", "-f", "json", "-o", str(output_base)],
            # Explicit Bet365 pass. If Bet365 is absent, this exits/returns empty and all-bookie pass still remains.
            [exe, "upcoming", "-s", "football", "-d", day, "-m", "1x2,btts,over_under", "--target-bookmaker", "Bet365", "--headless", "-f", "json", "-o", str(root / "bet365")],
        ]
        for cmd in commands:
            try:
                subprocess.run(cmd, cwd=root, check=False, timeout=int(os.getenv("ODDSHARVESTER_TIMEOUT", "900")), capture_output=True, text=True)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                log(f"OddsHarvester unavailable: {str(exc)[:120]}", "WARN")
                return []
        rows = _parse_oddsharvester_outputs(_find_json_files(root), target_date)
        log(f"OddsHarvester/OddsPortal: {len(rows)} rows", "OK" if rows else "WARN")
        return rows


def _extract_json_candidates_from_text(text: str) -> List[Any]:
    out = []
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            out.append(json.loads(stripped))
        except Exception:
            pass
    for match in re.finditer(r"(?:\{|\[).{100,200000}?(?:\}|\])", text, re.S):
        try:
            out.append(json.loads(match.group(0)))
        except Exception:
            continue
        if len(out) >= 20:
            break
    return out


def collect_bet365_public(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Best effort only. Public page/network responses, no account/login and no bypass."""
    if not _bool_env("ENABLE_BET365_PUBLIC", True):
        return []
    rows: List[Dict[str, Any]] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        log("Bet365 direct: Playwright not installed; next source", "WARN")
        return []
    responses: List[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(user_agent=USER_AGENT, locale="en-GB")
            page = context.new_page()

            def capture(response):
                u = response.url.lower()
                if any(k in u for k in ("fixture", "event", "market", "prematch", "sportsbook", "api")):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct or "text" in ct:
                            body = response.text()
                            if body and len(body) < 5_000_000:
                                responses.append(body)
                    except Exception:
                        pass

            page.on("response", capture)
            page.goto(os.getenv("BET365_PUBLIC_URL", "https://www.bet365.com/#/AC/B1/C1/D1002/E908/F10/"), wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(int(os.getenv("BET365_WAIT_MS", "12000")))
            responses.append(page.content())
            browser.close()
    except Exception as exc:
        log(f"Bet365 direct unavailable ({str(exc)[:140]}); aggregator fallback remains", "WARN")
        return []

    # Bet365 payload formats change. Parse only objects that carry recognizable participants + prices.
    for text in responses:
        for payload in _extract_json_candidates_from_text(text):
            for obj in _walk_odds_objects(payload):
                home = obj.get("home_team") or obj.get("home") or obj.get("homeTeam") or obj.get("team1")
                away = obj.get("away_team") or obj.get("away") or obj.get("awayTeam") or obj.get("team2")
                dt = _date_text(obj.get("date") or obj.get("startTime") or obj.get("start_time"))
                if not home or not away or not dt or (target_date and dt != target_date):
                    continue
                prices = obj.get("prices") or obj.get("outcomes") or obj.get("odds") or []
                if isinstance(prices, dict):
                    prices = [{"selection": k, "odds": v} for k, v in prices.items()]
                for p in prices if isinstance(prices, list) else []:
                    odd = _float(p.get("odds") or p.get("price") or p.get("decimal"))
                    if not odd:
                        continue
                    selection = str(p.get("selection") or p.get("name") or p.get("designation") or "")
                    market = str(p.get("market") or obj.get("market") or "unknown")
                    rows.append(_odds_row(
                        source="bet365_public_playwright", bookmaker="bet365", market=market,
                        selection=selection, odds=odd, match_date=dt, home=str(home), away=str(away),
                        league=str(obj.get("league") or ""), raw={"public_only": True},
                    ))
    rows = _dedupe(rows)
    log(f"Bet365 direct public: {len(rows)} rows", "OK" if rows else "WARN")
    return rows


def collect_betfair_official(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Official Exchange API only. No credentials means clean fallback."""
    app_key = os.getenv("BETFAIR_APP_KEY", "")
    session = os.getenv("BETFAIR_SESSION_TOKEN", "")
    if not app_key or not session:
        log("Betfair official API: credentials absent; next source", "WARN")
        return []
    # A full market-catalogue adapter is intentionally credential-gated. Keep the request official.
    headers = {"X-Application": app_key, "X-Authentication": session, "Content-Type": "application/json"}
    try:
        body = [{"jsonrpc": "2.0", "method": "SportsAPING/v1.0/listMarketCatalogue", "params": {
            "filter": {"eventTypeIds": ["1"], "marketTypeCodes": ["MATCH_ODDS", "OVER_UNDER_25"]},
            "maxResults": "200", "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        }, "id": 1}]
        r = requests.post("https://api.betfair.com/exchange/betting/json-rpc/v1", headers=headers, json=body, timeout=30)
        if not r.ok:
            log(f"Betfair catalogue HTTP {r.status_code}", "WARN")
            return []
        # Price calls require market IDs. Kept simple and official; odds are fetched in batches.
        catalog = (r.json() or [{}])[0].get("result") or []
        ids = [m.get("marketId") for m in catalog if m.get("marketId")]
        if not ids:
            return []
        price_body = [{"jsonrpc": "2.0", "method": "SportsAPING/v1.0/listMarketBook", "params": {
            "marketIds": ids[:40], "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}
        }, "id": 2}]
        pr = requests.post("https://api.betfair.com/exchange/betting/json-rpc/v1", headers=headers, json=price_body, timeout=30)
        if not pr.ok:
            return []
        books = {m.get("marketId"): m for m in ((pr.json() or [{}])[0].get("result") or [])}
        rows = []
        for market in catalog:
            event = market.get("event") or {}
            event_name = str(event.get("name") or "")
            parts = re.split(r"\s+v\s+|\s+vs\.?\s+", event_name, maxsplit=1, flags=re.I)
            if len(parts) != 2:
                continue
            home, away = parts
            dt = str(market.get("marketStartTime") or "")[:10]
            if target_date and dt != target_date:
                continue
            book = books.get(market.get("marketId")) or {}
            desc_by_id = {str(r.get("selectionId")): r.get("runnerName") for r in market.get("runners") or []}
            for runner in book.get("runners") or []:
                offers = ((runner.get("ex") or {}).get("availableToBack") or [])
                if not offers:
                    continue
                odd = _float(offers[0].get("price"))
                if not odd:
                    continue
                name = str(desc_by_id.get(str(runner.get("selectionId"))) or runner.get("selectionId"))
                rows.append(_odds_row(
                    source="betfair_exchange_api", bookmaker="betfair_exchange",
                    market=str(market.get("marketName") or "exchange"), selection=name,
                    odds=odd, match_date=dt, home=home, away=away, match_id=market.get("marketId"),
                    raw={"size": offers[0].get("size")},
                ))
        log(f"Betfair official: {len(rows)} rows", "OK" if rows else "WARN")
        return rows
    except Exception as exc:
        log(f"Betfair official: {exc}", "WARN")
        return []


def collect_live_all(target_date: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    collectors = [
        ("Pinnacle guest", lambda: collect_pinnacle_live(target_date)),
        ("The Odds API", lambda: collect_the_odds_api(target_date)),
        ("OddsHarvester/OddsPortal", lambda: collect_oddsharvester(target_date)),
        ("Bet365 direct public", lambda: collect_bet365_public(target_date)),
        ("Betfair official", lambda: collect_betfair_official(target_date)),
    ]
    for name, fn in collectors:
        try:
            got = fn() or []
        except Exception as exc:
            log(f"{name}: {str(exc)[:120]}; next source", "WARN")
            got = []
        rows.extend(got)
    return _dedupe(rows)


def get_best_quote_from_supabase(home: str, away: str, market: str, selection: str = "") -> Optional[Tuple[float, str]]:
    """Runtime helper for btts_bot / builder fallback with tolerant team matching."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    def norm_team(value: str) -> str:
        value = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
        for token in (" fc ", " cf ", " afc ", " sc ", " ac "):
            value = value.replace(token, " ")
        return re.sub(r"\s+", " ", value).strip()

    hn, an = norm_team(home), norm_team(away)
    htoken = next((x for x in hn.split() if len(x) >= 4), hn.split()[0] if hn.split() else hn)
    atoken = next((x for x in an.split() if len(x) >= 4), an.split()[0] if an.split() else an)
    params = {
        "select": "home_team,away_team,bookmaker,selection,odds,market,captured_date",
        "home_team": f"ilike.*{htoken}*", "away_team": f"ilike.*{atoken}*",
        "market": f"eq.{market}", "order": "captured_date.desc,odds.desc", "limit": "100",
    }
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/odds_history", headers=_sb_headers(), params=params, timeout=12)
        if not r.ok:
            return None
        candidates = []
        for row in r.json():
            rh, ra = norm_team(row.get("home_team")), norm_team(row.get("away_team"))
            home_ok = hn == rh or hn in rh or rh in hn or bool(set(hn.split()) & set(rh.split()))
            away_ok = an == ra or an in ra or ra in an or bool(set(an.split()) & set(ra.split()))
            if not (home_ok and away_ok):
                continue
            if selection and str(row.get("selection", "")).lower() != selection.lower():
                continue
            candidates.append(row)
        if not candidates:
            return None
        best = max(candidates, key=lambda x: float(x.get("odds") or 0))
        return float(best["odds"]), str(best.get("bookmaker") or "odds_history")
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD for live odds")
    parser.add_argument("--history", action="store_true", help="Collect Football-Data historical odds")
    parser.add_argument("--live", action="store_true", help="Collect live/upcoming odds")
    parser.add_argument("--all", action="store_true", help="Collect history and live")
    parser.add_argument("--start-year", type=int, default=int(os.getenv("ODDS_HISTORY_START_YEAR", "2015")))
    parser.add_argument("--max-leagues", type=int, default=int(os.getenv("ODDS_MAX_LEAGUES", "0")))
    parser.add_argument("--max-rows-per-csv", type=int, default=int(os.getenv("ODDS_MAX_ROWS_PER_CSV", "0")))
    parser.add_argument("--output", default="netrattler_odds_snapshot.json")
    args = parser.parse_args()

    do_history = args.history or args.all or (not args.history and not args.live and not args.all)
    do_live = args.live or args.all or (not args.history and not args.live and not args.all)
    target_date = args.date or date.today().isoformat()

    print("🎰 NETRATTLER V34 ODDS HARVESTER")
    print(f"   target_date={target_date} history={do_history} live={do_live}")
    rows: List[Dict[str, Any]] = []
    if do_history:
        rows.extend(collect_football_data_history(args.start_year, args.max_leagues, args.max_rows_per_csv))
    if do_live:
        rows.extend(collect_live_all(target_date))
    result = persist_odds(rows, args.output)
    print(f"✅ Odds complete: raw={len(rows)} local={result['local']} odds_history={result['odds_history']} data_lake={result['data_lake']}")


if __name__ == "__main__":
    main()
