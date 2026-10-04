#!/usr/bin/env python3
"""NETRATTLER V37 compact football odds harvester.

Stable public interface used by the rest of the repository:
- collect_live_all(target_date) -> normalized observed bookmaker rows
- persist_odds(rows, snapshot_path) -> Supabase + local snapshot counts
- CLI: --live / --all / --start-year

Design goals:
- real observed prices only; never synthesize odds;
- Pinnacle guest soccer feed is the broad low-cost primary source;
- The Odds API is quota-aware, key-rotating and deliberately capped;
- one source failure never stops the next source;
- historical Football-Data.co.uk import runs only in the slow maintenance path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
TIMEOUT = float(os.getenv("ODDS_HTTP_TIMEOUT", "12"))
SNAPSHOT_FILE = Path(os.getenv("NETRATTLER_ODDS_SNAPSHOT", "netrattler_odds_snapshot.json"))

PINNACLE_BASE = os.getenv("PINNACLE_BASE", "https://guest.api.arcadia.pinnacle.com/0.1")
PINNACLE_SPORT_SOCCER = int(os.getenv("PINNACLE_SOCCER_SPORT_ID", "29"))
PINNACLE_GUEST_KEY = os.getenv("PINNACLE_GUEST_KEY", "")
PINNACLE_HEADERS = {
    "x-api-key": PINNACLE_GUEST_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (NETRATTLER-V37-Odds)",
    "Referer": "https://www.pinnacle.com/",
    "Origin": "https://www.pinnacle.com",
    "Accept": "application/json",
}

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_REGIONS = os.getenv("ODDS_API_REGIONS", "eu,uk")
ODDS_API_MARKETS = os.getenv("ODDS_API_MARKETS", "h2h,totals")
ODDS_API_MAX_SPORTS = max(0, int(os.getenv("ODDS_API_MAX_SPORTS_PER_RUN", "8")))
ODDS_API_SPORT_KEYS = [x.strip() for x in os.getenv("ODDS_API_SPORT_KEYS", "").split(",") if x.strip()]

_MAJOR_SOCCER_KEYS = [
    "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
    "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_uefa_champs_league",
    "soccer_uefa_europa_league", "soccer_portugal_primeira_liga",
    "soccer_netherlands_eredivisie", "soccer_brazil_campeonato",
    "soccer_argentina_primera_division", "soccer_usa_mls",
]


def log(message: str, level: str = "INFO") -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [{level}] {message}", flush=True)


def _keys() -> List[str]:
    raw = os.getenv("ODDS_API_KEYS") or os.getenv("ODDS_API_KEY") or ""
    return list(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _stable(*parts: Any) -> str:
    return hashlib.sha256("||".join(str(x or "") for x in parts).encode("utf-8")).hexdigest()[:48]


def _date_of(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return text[:10] if len(text) >= 10 else fallback


def _decimal(value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        return 0.0
    if v <= -100:
        return round(1.0 + 100.0 / abs(v), 4)
    if v >= 100:
        return round(1.0 + v / 100.0, 4)
    return round(v, 4) if 1.001 <= v <= 1000 else 0.0


def _row(
    *, source: str, bookmaker: str, event_id: Any, league: str, home: str, away: str,
    commence_time: Any, market: str, selection: str, odds: Any, line: Any = None,
    raw: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    price = _decimal(odds)
    if price <= 1 or not home or not away or not market or not selection:
        return None
    now = datetime.now(timezone.utc).isoformat()
    day = _date_of(commence_time, date.today().isoformat())
    match_id = str(event_id or _stable(day, home, away))
    return {
        "source": source,
        "match_id": match_id,
        "home_team": str(home).strip(),
        "away_team": str(away).strip(),
        "match_date": day,
        "captured_date": now[:10],
        "market": str(market),
        "bookmaker": str(bookmaker or source),
        "selection": str(selection),
        "odds": price,
        "raw": {
            "line": line,
            "commence_time": commence_time,
            "league": league,
            "captured_at": now,
            **(dict(raw or {})),
        },
    }


def collect_pinnacle(target_date: str) -> List[Dict[str, Any]]:
    """Two-request broad soccer pass: matchups + straight markets."""
    try:
        matchups_r = requests.get(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/matchups",
            headers=PINNACLE_HEADERS,
            params={"withSpecials": "false", "brandId": "0"},
            timeout=TIMEOUT,
        )
        if not matchups_r.ok:
            log(f"Pinnacle matchups HTTP {matchups_r.status_code}", "WARN")
            return []
        matchups = matchups_r.json() or []
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in matchups if isinstance(matchups, list) else []:
            if item.get("type") != "matchup":
                continue
            participants = item.get("participants") or []
            home = next((p.get("name") for p in participants if p.get("alignment") == "home"), "")
            away = next((p.get("name") for p in participants if p.get("alignment") == "away"), "")
            mid = str(item.get("id") or "")
            if mid and home and away:
                by_id[mid] = {
                    "home": home, "away": away,
                    "league": (item.get("league") or {}).get("name") or "",
                    "starts": item.get("startTime") or "",
                }
        markets_r = requests.get(
            f"{PINNACLE_BASE}/sports/{PINNACLE_SPORT_SOCCER}/markets/straight",
            headers=PINNACLE_HEADERS,
            params={"primaryOnly": "false", "withSpecials": "false"},
            timeout=TIMEOUT,
        )
        if not markets_r.ok:
            log(f"Pinnacle markets HTTP {markets_r.status_code}", "WARN")
            return []
        rows: List[Dict[str, Any]] = []
        for market in markets_r.json() or []:
            mid = str(market.get("matchupId") or "")
            match = by_id.get(mid)
            if not match:
                continue
            # Keep the requested date only when the feed exposes a parseable date.
            match_day = _date_of(match.get("starts"), target_date)
            if target_date and match_day != target_date:
                continue
            mtype = str(market.get("type") or "").lower()
            period = int(market.get("period") or 0)
            if period != 0 or mtype not in {"moneyline", "total"}:
                continue
            for price in market.get("prices") or []:
                designation = str(price.get("designation") or "").lower()
                points = price.get("points")
                if mtype == "moneyline":
                    selection = {"home": "home", "draw": "draw", "away": "away"}.get(designation)
                    market_name = "1x2"
                else:
                    if designation not in {"over", "under"} or points is None:
                        continue
                    selection = f"{designation}_{str(points).replace('.', '_')}"
                    market_name = f"totals_{str(points).replace('.', '_')}"
                if not selection:
                    continue
                item = _row(
                    source="pinnacle", bookmaker="pinnacle", event_id=mid,
                    league=match["league"], home=match["home"], away=match["away"],
                    commence_time=match["starts"], market=market_name,
                    selection=selection, odds=price.get("price"), line=points,
                    raw={"period": period, "market_type": mtype},
                )
                if item:
                    rows.append(item)
        log(f"Pinnacle live rows={len(rows)} matches={len(by_id)}")
        return rows
    except Exception as exc:
        log(f"Pinnacle failed: {str(exc)[:140]}", "WARN")
        return []


KAMBI_BRANDS = [x.strip() for x in os.getenv("KAMBI_BRANDS", "ubse,ub,ubnl,svenskaspel").split(",") if x.strip()]
KAMBI_DIAG: Dict[str, Any] = {}
KAMBI_DETAIL_EVENTS = int(os.getenv("KAMBI_DETAIL_EVENTS", "60"))

def _kambi_rows(brand: str, ev: Mapping[str, Any], offers: Sequence[Mapping[str, Any]], league: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    home, away, start = ev.get("homeName"), ev.get("awayName"), ev.get("start") or ""
    for bo in offers or []:
        label = str((bo.get("criterion") or {}).get("label") or "").lower()
        for oc in bo.get("outcomes") or []:
            if oc.get("status") not in (None, "OPEN"):
                continue
            otype = str(oc.get("type") or "")
            price = (oc.get("odds") or 0) / 1000.0
            market = sel = None
            line = oc.get("line")
            if label == "full time" and otype in {"OT_ONE", "OT_CROSS", "OT_TWO"}:
                market, sel = "1x2", {"OT_ONE": "home", "OT_CROSS": "draw", "OT_TWO": "away"}[otype]
            elif label == "both teams to score" and otype in {"OT_YES", "OT_NO"}:
                market, sel = "btts", "yes" if otype == "OT_YES" else "no"
            elif label == "total goals" and otype in {"OT_OVER", "OT_UNDER"} and line:
                pts = line / 1000.0
                tag = str(pts).replace(".", "_")
                market, sel = f"totals_{tag}", f"{'over' if otype == 'OT_OVER' else 'under'}_{tag}"
                line = pts
            elif label.startswith("both teams to score") and ("half" in label) and otype in {"OT_YES", "OT_NO"}:
                market = "btts_ht" if ("1st" in label or "first" in label) else "btts_2h"
                sel = "yes" if otype == "OT_YES" else "no"
            elif "total goals" in label and ("1st" in label or "first half" in label) and otype in {"OT_OVER", "OT_UNDER"} and line:
                pts = line / 1000.0
                tag = str(pts).replace(".", "_")
                market, sel = f"totals_ht_{tag}", f"{'over' if otype == 'OT_OVER' else 'under'}_{tag}"
                line = pts
            if not market:
                continue
            row = _row(source="kambi", bookmaker=f"kambi_{brand}", event_id=ev.get("id"), league=league,
                       home=home, away=away, commence_time=start, market=market, selection=sel,
                       odds=price, line=line, raw={"brand": brand})
            if row:
                out.append(row)
    return out



def collect_kambi(target_date: str) -> List[Dict[str, Any]]:
    """Kambi (Unibet-Gruppe) oeffentlicher Offering-Feed, ohne Key. Quoten in Tausendstel."""
    rows: List[Dict[str, Any]] = []
    for brand in KAMBI_BRANDS:
        url = f"https://eu-offering-api.kambicdn.com/offering/v2018/{brand}/listView/football/all/all/all/matches.json"
        try:
            r = requests.get(url, params={"lang": "en_GB", "market": "GB", "useCombined": "true", "includeParticipants": "false"},
                             headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=max(TIMEOUT, 25))
        except Exception as exc:
            KAMBI_DIAG[brand] = f"ERR {type(exc).__name__}"
            continue
        if not r.ok:
            KAMBI_DIAG[brand] = f"HTTP {r.status_code}"
            continue
        try:
            events = (r.json() or {}).get("events") or []
        except Exception:
            KAMBI_DIAG[brand] = "bad json"
            continue
        got = 0
        wanted: List[Tuple[Mapping[str, Any], str]] = []
        for item in events:
            ev = item.get("event") or {}
            home, away = ev.get("homeName"), ev.get("awayName")
            start = ev.get("start") or ""
            if not home or not away or ev.get("state") == "STARTED":
                continue
            _d = _date_of(start, target_date)
            if target_date and not (target_date <= _d <= (date.fromisoformat(target_date) + timedelta(days=3)).isoformat()):
                continue
            league = ev.get("group") or ""
            offers = item.get("betOffers") or []
            new = _kambi_rows(brand, ev, offers, league)
            rows.extend(new); got += len(new)
            if len(wanted) < KAMBI_DETAIL_EVENTS:
                wanted.append((ev, league))
        for ev, league in wanted:
            try:
                dr = requests.get(f"https://eu-offering-api.kambicdn.com/offering/v2018/{brand}/betoffer/event/{ev.get('id')}.json",
                                  params={"lang": "en_GB", "market": "GB"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                if dr.ok:
                    seen = {(r["market"], r["selection"]) for r in rows if r["match_id"] == str(ev.get("id"))}
                    for r2 in _kambi_rows(brand, ev, (dr.json() or {}).get("betOffers") or [], league):
                        if (r2["market"], r2["selection"]) not in seen:
                            rows.append(r2); got += 1
                time.sleep(0.15)
            except Exception:
                continue
        KAMBI_DIAG[brand] = f"events={len(events)} rows={got}"
    log(f"Kambi rows={len(rows)} diag={KAMBI_DIAG}")
    return rows


FD_BOOKS = {"B365": "bet365", "PS": "pinnacle_fd", "MaxH": None, "AvgH": "avg_market", "WH": "williamhill", "BW": "bwin", "IW": "interwetten"}


def collect_football_data_fixtures(target_date: str) -> List[Dict[str, Any]]:
    """football-data.co.uk fixtures.csv: kommende Spiele mit Buchmacher-Quoten (kein Key)."""
    import csv, io
    rows: List[Dict[str, Any]] = []
    try:
        r = requests.get("https://www.football-data.co.uk/fixtures.csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
        if not r.ok:
            return []
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="ignore")))
        limit = (date.fromisoformat(target_date) + timedelta(days=7)).isoformat()
        for rec in reader:
            h, a, ds = rec.get("HomeTeam"), rec.get("AwayTeam"), rec.get("Date")
            if not h or not a or not ds:
                continue
            try:
                d = datetime.strptime(ds.strip(), "%d/%m/%Y").date().isoformat()
            except Exception:
                try:
                    d = datetime.strptime(ds.strip(), "%d/%m/%y").date().isoformat()
                except Exception:
                    continue
            if not (target_date <= d <= limit):
                continue
            for pre, book in (("B365", "bet365"), ("PS", "pinnacle"), ("Avg", "avg_market"), ("Max", "max_market"), ("WH", "williamhill"), ("BW", "bwin")):
                for col, sel in ((f"{pre}H", "home"), (f"{pre}D", "draw"), (f"{pre}A", "away")):
                    it = _row(source="football_data", bookmaker=f"fd_{book}", event_id=_stable(d, h, a), league=rec.get("Div") or "",
                              home=h, away=a, commence_time=d, market="1x2", selection=sel, odds=rec.get(col))
                    if it:
                        rows.append(it)
                for col, sel in ((f"{pre}>2.5", "over_2_5"), (f"{pre}<2.5", "under_2_5")):
                    it = _row(source="football_data", bookmaker=f"fd_{book}", event_id=_stable(d, h, a), league=rec.get("Div") or "",
                              home=h, away=a, commence_time=d, market="totals_2_5", selection=sel, odds=rec.get(col), line=2.5)
                    if it:
                        rows.append(it)
    except Exception as exc:
        log(f"football-data fixtures: {str(exc)[:120]}", "WARN")
    log(f"football-data fixtures rows={len(rows)}")
    return rows


ESPN_LEAGUES = [x for x in os.getenv("ESPN_LEAGUES", "eng.1,eng.2,esp.1,ger.1,ita.1,fra.1,ned.1,por.1,tur.1,bel.1,usa.1,uefa.champions,uefa.europa,uefa.europa.conf,bra.1,arg.1,mex.1").split(",") if x]


def collect_espn(target_date: str) -> List[Dict[str, Any]]:
    """ESPN Scoreboard JSON inkl. Buchmacher-Quoten (kein Key)."""
    rows: List[Dict[str, Any]] = []
    d0 = date.fromisoformat(target_date)
    rng = f"{d0.strftime('%Y%m%d')}-{(d0 + timedelta(days=3)).strftime('%Y%m%d')}"
    for lg in ESPN_LEAGUES:
        try:
            r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard",
                             params={"dates": rng, "limit": 100}, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if not r.ok:
                continue
            for ev in r.json().get("events") or []:
                comp = (ev.get("competitions") or [{}])[0]
                teams = {c.get("homeAway"): (c.get("team") or {}).get("displayName") for c in comp.get("competitors") or []}
                h, a = teams.get("home"), teams.get("away")
                if not h or not a:
                    continue
                for od in comp.get("odds") or []:
                    prov = str((od.get("provider") or {}).get("name") or "espn").lower().replace(" ", "_")
                    mapping = (
                        ("homeTeamOdds", "home"), ("awayTeamOdds", "away"), ("drawOdds", "draw"),
                    )
                    for key, sel in mapping:
                        node = od.get(key) or {}
                        ml = node.get("moneyLine")
                        if ml is None:
                            continue
                        it = _row(source="espn", bookmaker=f"espn_{prov}", event_id=ev.get("id"), league=lg, home=h, away=a,
                                  commence_time=ev.get("date"), market="1x2", selection=sel, odds=ml)
                        if it:
                            rows.append(it)
            time.sleep(0.2)
        except Exception:
            continue
    log(f"ESPN rows={len(rows)}")
    return rows


ODDS_API_EXHAUSTED = False
ODDS_API_DIAG: Dict[str, Any] = {"calls": 0, "status": {}, "remaining": None, "last_error": ""}


def _odds_api_get(path: str, params: Dict[str, Any], keys: Sequence[str]) -> Tuple[Any, Optional[str]]:
    global ODDS_API_EXHAUSTED
    if ODDS_API_EXHAUSTED:
        return None, None
    quota_hits = 0
    for key in keys:
        try:
            p = dict(params); p["apiKey"] = key
            r = requests.get(f"{ODDS_API_BASE}/{path.lstrip('/')}", params=p, timeout=TIMEOUT)
            ODDS_API_DIAG["calls"] += 1
            if r.status_code in {401, 429} and "quota" in r.text.lower():
                quota_hits += 1
            ODDS_API_DIAG["status"][str(r.status_code)] = ODDS_API_DIAG["status"].get(str(r.status_code), 0) + 1
            rem = r.headers.get("x-requests-remaining")
            if rem is not None:
                ODDS_API_DIAG["remaining"] = rem
            if r.status_code in {401, 403, 429}:
                ODDS_API_DIAG["last_error"] = f"{r.status_code} {r.text[:80]}"
                continue
            if r.ok:
                return r.json(), key
            ODDS_API_DIAG["last_error"] = f"{r.status_code} {r.text[:80]}"
        except Exception as exc:
            ODDS_API_DIAG["last_error"] = f"exc {str(exc)[:80]}"
            continue
    if keys and quota_hits >= len(keys):
        ODDS_API_EXHAUSTED = True   # alle Keys leer -> keine weiteren Calls in diesem Lauf
    return None, None


def _soccer_sport_keys(keys: Sequence[str]) -> List[str]:
    if ODDS_API_SPORT_KEYS:
        return ODDS_API_SPORT_KEYS[:ODDS_API_MAX_SPORTS or None]
    sports, _ = _odds_api_get("sports/", {}, keys)
    available = [
        str(x.get("key")) for x in (sports or [])
        if str(x.get("key") or "").startswith("soccer_")
        and bool(x.get("active", True)) and not bool(x.get("has_outrights"))
    ]
    ordered = [x for x in _MAJOR_SOCCER_KEYS if x in available]
    ordered += [x for x in available if x not in ordered]
    return ordered[:ODDS_API_MAX_SPORTS] if ODDS_API_MAX_SPORTS else ordered


def collect_the_odds_api(target_date: str) -> List[Dict[str, Any]]:
    keys = _keys()
    if not keys or ODDS_API_MAX_SPORTS == 0:
        return []
    sport_keys = _soccer_sport_keys(keys)
    if not sport_keys:
        return []
    start = f"{target_date}T00:00:00Z"
    end = f"{target_date}T23:59:59Z"
    rows: List[Dict[str, Any]] = []
    used_calls = 0
    for sport in sport_keys:
        payload, used = _odds_api_get(
            f"sports/{sport}/odds/",
            {
                "regions": ODDS_API_REGIONS,
                "markets": ODDS_API_MARKETS,
                "oddsFormat": "decimal",
                "dateFormat": "iso",
                "commenceTimeFrom": start,
                "commenceTimeTo": end,
            },
            keys,
        )
        if payload is None:
            continue
        used_calls += 1
        for event in payload if isinstance(payload, list) else []:
            home = event.get("home_team") or ""
            away = event.get("away_team") or ""
            commence = event.get("commence_time") or ""
            eid = event.get("id") or ""
            for book in event.get("bookmakers") or []:
                bookmaker = str(book.get("key") or book.get("title") or "unknown")
                for market in book.get("markets") or []:
                    mkey = str(market.get("key") or "")
                    for outcome in market.get("outcomes") or []:
                        name = str(outcome.get("name") or "")
                        point = outcome.get("point")
                        if mkey == "h2h":
                            if _norm(name) == _norm(home): selection = "home"
                            elif _norm(name) == _norm(away): selection = "away"
                            elif name.lower() == "draw": selection = "draw"
                            else: continue
                            market_name = "1x2"
                        elif mkey == "totals":
                            side = name.lower()
                            if side not in {"over", "under"} or point is None:
                                continue
                            selection = f"{side}_{str(point).replace('.', '_')}"
                            market_name = f"totals_{str(point).replace('.', '_')}"
                        else:
                            continue
                        item = _row(
                            source="the_odds_api", bookmaker=bookmaker, event_id=eid,
                            league=str(event.get("sport_title") or sport), home=home, away=away,
                            commence_time=commence, market=market_name, selection=selection,
                            odds=outcome.get("price"), line=point,
                            raw={"sport_key": sport, "book_last_update": book.get("last_update")},
                        )
                        if item:
                            rows.append(item)
    log(f"The Odds API rows={len(rows)} sports={used_calls}/{len(sport_keys)} cap={ODDS_API_MAX_SPORTS}")
    return rows


def _dedupe(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        odds = float(row.get("odds") or 0)
        if odds <= 1:
            continue
        key = (
            _norm(row.get("home_team")), _norm(row.get("away_team")),
            str(row.get("market") or ""), str(row.get("selection") or ""),
            _norm(row.get("bookmaker") or row.get("source")), str(row.get("match_date") or ""),
        )
        previous = best.get(key)
        if previous is None or odds > float(previous.get("odds") or 0):
            best[key] = row
    return list(best.values())


def collect_live_all(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    day = str(target_date or date.today().isoformat())[:10]
    rows: List[Dict[str, Any]] = []
    for name, fn in (
        ("pinnacle", lambda: collect_pinnacle(day)),
        ("kambi", lambda: collect_kambi(day)),
        ("football_data", lambda: collect_football_data_fixtures(day)),
        ("espn", lambda: collect_espn(day)),
        ("the_odds_api", lambda: collect_the_odds_api(day)),
    ):
        note = ""
        got: List[Dict[str, Any]] = []
        try:
            got = fn() or []
            rows.extend(got)
            if name == "kambi":
                note = f"diag={KAMBI_DIAG}"
            if name == "the_odds_api":
                if not _keys():
                    note = "kein ODDS_API_KEY(S) gesetzt"
                else:
                    d = ODDS_API_DIAG
                    note = (f"calls={d['calls']} status={d['status']} remaining={d['remaining']} "
                            f"err={d['last_error']} regions={ODDS_API_REGIONS} max_sports={ODDS_API_MAX_SPORTS}")
        except Exception as exc:
            note = f"Fehler: {str(exc)[:200]}"
            log(f"{name}: {str(exc)[:120]}", "WARN")
        try:
            from netrattler_health import record
            record("odds_harvester", name, len(got), note=note)
        except Exception:
            pass
    clean = _dedupe(rows)
    log(f"Live odds total={len(clean)} sources={dict(Counter(x.get('source') for x in clean))}")
    return clean


def _headers(prefer: str = "resolution=merge-duplicates,return=minimal") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def persist_odds(rows: Sequence[Mapping[str, Any]], snapshot_path: str = "netrattler_odds_snapshot.json") -> Dict[str, int]:
    clean = _dedupe(rows)
    payload = {
        "version": "V37",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "rows": clean,
        "source_counts": dict(Counter(str(x.get("source") or "unknown") for x in clean)),
        "bookmaker_counts": dict(Counter(str(x.get("bookmaker") or "unknown") for x in clean)),
    }
    Path(snapshot_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    saved = 0
    failed = 0
    if SUPABASE_URL and SUPABASE_KEY and clean:
        endpoint = f"{SUPABASE_URL}/rest/v1/odds_history"
        conflict = "source,match_id,market,bookmaker,captured_date,selection"
        for i in range(0, len(clean), 250):
            batch = clean[i:i+250]
            try:
                r = requests.post(
                    endpoint, headers=_headers(), params={"on_conflict": conflict},
                    json=batch, timeout=max(20.0, TIMEOUT),
                )
                if r.ok:
                    saved += len(batch)
                else:
                    failed += len(batch)
                    log(f"odds_history {r.status_code}: {r.text[:180]}", "WARN")
            except Exception as exc:
                failed += len(batch)
                log(f"odds_history write: {str(exc)[:120]}", "WARN")
    return {"local": len(clean), "odds_history": saved, "data_lake": 0, "failed": failed}


def _season_code(year: int) -> str:
    return f"{str(year)[-2:]}{str(year + 1)[-2:]}"


def import_recent_history(start_year: int) -> int:
    """Storage/runtime-safe FD.co.uk maintenance; full history is opt-in."""
    current = datetime.now(timezone.utc).year
    full = os.getenv("ODDS_FULL_HISTORY", "false").lower() in {"1", "true", "yes", "on"}
    recent_years = max(1, int(os.getenv("ODDS_HISTORY_YEARS_PER_RUN", "3")))
    effective = max(start_year, current - recent_years) if not full else start_year
    seasons = [_season_code(y) for y in range(effective, current + 1)]
    try:
        # The existing importer owns the normalized Football-Data schema and dedupe logic.
        os.environ["FD_SEASONS"] = ",".join(seasons)
        os.environ["STORE_HISTORICAL_ODDS"] = "true"
        import importlib
        mod = importlib.import_module("import_football_data_sources_v14")
        # Constants are read at import time; reload after setting env for deterministic CLI behavior.
        mod = importlib.reload(mod)
        count = int(mod.import_football_data_co_uk() or 0)
        log(f"Historical odds maintenance seasons={seasons} matches={count} full={full}")
        return count
    except Exception as exc:
        log(f"Historical odds maintenance skipped: {str(exc)[:160]}", "WARN")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--all", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--start-year", type=int, default=int(os.getenv("ODDS_HISTORY_START_YEAR", "2010")))
    args = parser.parse_args()

    rows = collect_live_all(args.date)
    saved = persist_odds(rows, str(SNAPSHOT_FILE))
    log(f"Persist live: {saved}")
    if args.all:
        import_recent_history(args.start_year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
