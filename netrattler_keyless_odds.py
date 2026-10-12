#!/usr/bin/env python3
"""NETRATTLER keyless odds collectors (real observed prices, no API keys).

Every collector returns rows in the odds_history schema built by
netrattler_odds_harvester._row(). Nothing is estimated: a row exists only when the
source shows a price for that exact selection. Each collector is fail-safe and
bounded; diagnostics go to KEYLESS_DIAG.

Sources (verified reachable from GitHub Actions on 2026-10-12):
- bwin CDS public offer API (bwin / sportingbet / partypoker share these prices)
- 1xBet platform LineFeed via 22bet / melbet / betwinner mirrors (/service-api)
- Matchbook exchange (back prices, public read)
"""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "en-GB,en;q=0.9"}
TIMEOUT = float(os.getenv("KEYLESS_HTTP_TIMEOUT", "20"))
KEYLESS_DIAG: Dict[str, Any] = {}

BWIN_BASE = "https://sports.bwin.com/cds-api/bettingoffer"
BWIN_PARAMS = {"x-bwin-accessid": os.getenv("BWIN_ACCESS_ID", "NTZiMjk3OGMtNjU5Mi00NjA5LWI2MWItZmU4MDRhN2QxZmEz"),
               "lang": "en", "country": "GB", "userCountry": "GB"}
X1_HOSTS = [h.strip() for h in os.getenv("ONEX_HOSTS", "https://22bet.com,https://melbet.com,https://betwinner.com").split(",") if h.strip()]


def _row(**kw):
    from netrattler_odds_harvester import _row as harvester_row
    return harvester_row(**kw)


def _get(url: str, params: Optional[Mapping[str, Any]] = None, timeout: float = TIMEOUT):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
        if not r.ok:
            return None, r.status_code
        return r.json(), 200
    except Exception as exc:
        return None, type(exc).__name__


def _in_window(day: str, target_date: str, days: int = 3) -> bool:
    if not target_date:
        return True
    end = (date.fromisoformat(target_date) + timedelta(days=days)).isoformat()
    return target_date <= day <= end


def _line_tag(v: float) -> str:
    return str(float(v)).replace(".", "_")


def _num(text: Any) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(text or ""))
    return float(m.group(1).replace(",", ".")) if m else None


# --------------------------------------------------------------------------- bwin
def _bwin_text(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("value") or obj.get("short") or "")
    return str(obj or "")


def _bwin_market(mname: str, oname: str, home: str, away: str):
    """Map a bwin market/option to (market, selection, line). None if unsupported."""
    m = mname.lower().strip()
    o = oname.lower().strip()
    hn, an = home.lower(), away.lower()
    if m in {"match result", "result 1x2", "1x2"}:
        if o in {"x", "draw"}:
            return "1x2", "draw", None
        if o in {"1", hn} or (hn and o.startswith(hn[:6])):
            return "1x2", "home", None
        if o in {"2", an} or (an and o.startswith(an[:6])):
            return "1x2", "away", None
    if m == "both teams to score":
        if o in {"yes", "no"}:
            return "btts", o, None
    if m in {"both teams to score 1st half", "both teams to score - 1st half"} and o in {"yes", "no"}:
        return "btts_ht", o, None
    if m in {"total goals", "total goals - over/under", "over/under"} or m.startswith("total goals o/u"):
        if o.startswith(("over", "under")):
            v = _num(o)
            if v is not None:
                side = "over" if o.startswith("over") else "under"
                return f"totals_{_line_tag(v)}", f"{side}_{_line_tag(v)}", v
    if m in {"1st half - total goals", "total goals - 1st half"} and o.startswith(("over", "under")):
        v = _num(o)
        if v is not None:
            side = "over" if o.startswith("over") else "under"
            return f"totals_ht_{_line_tag(v)}", f"{side}_{_line_tag(v)}", v
    if m == "double chance":
        o2 = o.replace(" ", "")
        if o2 in {"1x", "x1"}:
            return "double_chance", "1x", None
        if o2 in {"x2", "2x"}:
            return "double_chance", "x2", None
        if o2 in {"12", "21"}:
            return "double_chance", "12", None
    if ("total corners" in m or m.startswith("corners")) and o.startswith(("over", "under")):
        v = _num(o)
        if v is not None:
            side = "over" if o.startswith("over") else "under"
            return f"corners_{_line_tag(v)}", f"{side}_{_line_tag(v)}", v
    return None


def _bwin_rows(fx: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    parts = [p for p in fx.get("participants") or [] if isinstance(p, dict)]
    name = _bwin_text(fx.get("name"))
    home = _bwin_text(parts[0].get("name")) if len(parts) >= 2 else name.split(" - ")[0]
    away = _bwin_text(parts[1].get("name")) if len(parts) >= 2 else (name.split(" - ") + [""])[1]
    if not home or not away:
        return out
    league = _bwin_text((fx.get("competition") or {}).get("name"))
    start = fx.get("startDate")
    markets = list(fx.get("optionMarkets") or []) + list(fx.get("games") or [])
    for mk in markets:
        mname = _bwin_text(mk.get("name"))
        if str(mk.get("status") or "Visible") not in {"Visible", "Open"}:
            continue
        opts = mk.get("options") or mk.get("results") or []
        for op in opts:
            oname = _bwin_text(op.get("name"))
            price = (op.get("price") or {}).get("odds") if isinstance(op.get("price"), dict) else op.get("odds")
            mapped = _bwin_market(mname, oname, home, away)
            if not mapped or not price:
                continue
            market, sel, line = mapped
            row = _row(source="bwin", bookmaker="bwin", event_id=f"bwin_{fx.get('id')}", league=league,
                       home=home, away=away, commence_time=start, market=market, selection=sel,
                       odds=price, line=line, raw={"platform": "bwin", "market_name": mname[:60]})
            if row:
                out.append(row)
    return out


def collect_bwin(target_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    take = int(os.getenv("BWIN_FIXTURES", "200"))
    details = int(os.getenv("BWIN_DETAIL_FIXTURES", "40"))
    js, st = _get(f"{BWIN_BASE}/fixtures", {**BWIN_PARAMS, "fixtureTypes": "Standard", "state": "Latest",
                                            "offerMapping": "Filtered", "sportIds": "4", "skip": "0", "take": str(take),
                                            "sortBy": "StartDate"})
    fixtures = (js or {}).get("fixtures") or []
    fixtures = [f for f in fixtures if f.get("stage") == "PreMatch"
                and _in_window(str(f.get("startDate") or "")[:10], target_date)]
    detailed = 0
    for fx in fixtures:
        new = _bwin_rows(fx)
        if len(new) < 6 and detailed < details:
            dj, _ = _get(f"{BWIN_BASE}/fixture-view", {**BWIN_PARAMS, "offerMapping": "All",
                                                        "fixtureIds": fx.get("id"), "state": "Latest"})
            full = (dj or {}).get("fixture")
            if full:
                new = _bwin_rows(full)
                detailed += 1
                time.sleep(0.2)
        rows.extend(new)
    KEYLESS_DIAG["bwin"] = f"http={st} fixtures={len(fixtures)} detail={detailed} rows={len(rows)}"
    return rows


# --------------------------------------------------------------------- 1xBet platform
# Event type codes on the 1xBet LineFeed: 1/2/3 = 1X2, 9/10 = total over/under (P=line),
# 180/181 = both teams to score yes/no. Group 17 = totals, 19 = BTTS.
_X1_TYPES = {1: ("1x2", "home"), 2: ("1x2", "draw"), 3: ("1x2", "away"),
             180: ("btts", "yes"), 181: ("btts", "no"),
             4: ("double_chance", "1x"), 5: ("double_chance", "12"), 6: ("double_chance", "x2")}


def _x1_rows(g: Mapping[str, Any], host: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    home, away = g.get("O1") or "", g.get("O2") or ""
    if not home or not away:
        return out
    start = datetime.fromtimestamp(int(g.get("S") or 0), tz=timezone.utc).isoformat() if g.get("S") else None
    league = g.get("L") or g.get("LE") or ""
    events = list(g.get("E") or [])
    for ae in g.get("AE") or []:
        for me in ae.get("ME") or []:
            events.append(me)
    bk = "1x_" + re.sub(r"^https?://(www\.)?|\.com.*$", "", host)
    for e in events:
        t = e.get("T")
        price = e.get("C")
        market = sel = None
        line = None
        if t in _X1_TYPES:
            market, sel = _X1_TYPES[t]
        elif t in (9, 10) and e.get("P") is not None:
            line = float(e.get("P"))
            market, sel = f"totals_{_line_tag(line)}", f"{'over' if t == 9 else 'under'}_{_line_tag(line)}"
        if not market:
            continue
        row = _row(source="1xbet_platform", bookmaker=bk, event_id=f"1x_{g.get('I')}", league=league,
                   home=home, away=away, commence_time=start, market=market, selection=sel,
                   odds=price, line=line, raw={"platform": "1xbet", "host": host})
        if row:
            out.append(row)
    return out


def collect_1x_platform(target_date: str) -> List[Dict[str, Any]]:
    """1xBet platform prices; the mirrors share one book, so stop at the first that works."""
    for host in X1_HOSTS:
        js, st = _get(f"{host}/service-api/LineFeed/Get1x2_VZip",
                      {"sports": "1", "count": os.getenv("ONEX_COUNT", "1000"), "lng": "en", "mode": "4",
                       "country": "1", "getEmpty": "true"})
        games = (js or {}).get("Value") or []
        if not games:
            KEYLESS_DIAG[f"1x_{host}"] = f"http={st} games=0"
            continue
        rows: List[Dict[str, Any]] = []
        kept = 0
        # The top list is capped (~50 games); walk championships for wider coverage.
        seen_ids = {g.get("I") for g in games}
        cj, _ = _get(f"{host}/service-api/LineFeed/GetChampsZip", {"sport": "1", "lng": "en", "country": "1"})
        champs = sorted((cj or {}).get("Value") or [], key=lambda c: -(c.get("GC") or 0))
        max_champs = int(os.getenv("ONEX_MAX_CHAMPS", "60"))
        for ch in champs[:max_champs]:
            cid = ch.get("LI")
            if not cid:
                continue
            gj, _ = _get(f"{host}/service-api/LineFeed/Get1x2_VZip",
                         {"sports": "1", "champs": str(cid), "count": "50", "lng": "en", "mode": "4",
                          "country": "1", "getEmpty": "true"})
            for g in (gj or {}).get("Value") or []:
                if g.get("I") not in seen_ids:
                    seen_ids.add(g.get("I"))
                    games.append(g)
            time.sleep(0.1)
        KEYLESS_DIAG["1x_champs"] = len(champs)
        for g in games:
            if g.get("SC") or not g.get("S"):
                continue
            day = datetime.fromtimestamp(int(g["S"]), tz=timezone.utc).date().isoformat()
            if not _in_window(day, target_date):
                continue
            kept += 1
            rows.extend(_x1_rows(g, host))
        KEYLESS_DIAG["1x_platform"] = f"host={host} games={len(games)} kept={kept} rows={len(rows)}"
        return rows
    return []


# ------------------------------------------------------------------------ Matchbook
def _mb_market(mname: str, rname: str, home: str, away: str):
    m, r = mname.lower(), rname.lower().strip()
    if m in {"match odds", "moneyline", "1x2"}:
        if r in {"draw", "the draw", "x"}:
            return "1x2", "draw", None
        if r == home.lower():
            return "1x2", "home", None
        if r == away.lower():
            return "1x2", "away", None
    if m.startswith("both teams to score") and r in {"yes", "no"}:
        return "btts", r, None
    if m.startswith(("over/under", "total goals", "total")) and r.startswith(("over", "under")):
        v = _num(r) or _num(m)
        if v is not None:
            side = "over" if r.startswith("over") else "under"
            return f"totals_{_line_tag(v)}", f"{side}_{_line_tag(v)}", v
    return None


def collect_matchbook(target_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    total = 0
    for offset in range(0, int(os.getenv("MATCHBOOK_MAX_EVENTS", "400")), 100):
        js, st = _get("https://api.matchbook.com/edge/rest/events",
                      {"sport-ids": "15", "per-page": "100", "offset": str(offset), "include-prices": "true",
                       "odds-type": "DECIMAL", "price-depth": "1", "states": "open"})
        events = (js or {}).get("events") or []
        if not events:
            break
        for ev in events:
            name = str(ev.get("name") or "")
            if " vs " not in name or ev.get("in-running-flag") is True and str(ev.get("status")) == "in-running":
                continue
            day = str(ev.get("start") or "")[:10]
            if not _in_window(day, target_date):
                continue
            try:  # prematch only: an in-play price is not a pre-kickoff quote
                if datetime.fromisoformat(str(ev.get("start")).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                    continue
            except Exception:
                continue
            total += 1
            home, away = [x.strip() for x in name.split(" vs ", 1)]
            if "matchbook_sample" not in KEYLESS_DIAG and ev.get("markets"):
                _m0 = (ev.get("markets") or [{}])[0]
                _r0 = (_m0.get("runners") or [{}])[0]
                KEYLESS_DIAG["matchbook_sample"] = {"market": _m0.get("name"), "mtype": _m0.get("market-type"),
                                                    "runner": _r0.get("name"), "runner_keys": sorted(_r0.keys())[:15],
                                                    "prices": (_r0.get("prices") or [])[:2],
                                                    "markets": [m.get("name") for m in ev.get("markets") or []][:12]}
            for mk in ev.get("markets") or []:
                mname = str(mk.get("name") or "")
                for rn in mk.get("runners") or []:
                    mapped = _mb_market(mname, str(rn.get("name") or ""), home, away)
                    if not mapped:
                        continue
                    backs = [p for p in rn.get("prices") or [] if p.get("side") in ("back", "win") and p.get("decimal-odds")]
                    if not backs:
                        continue
                    best = max(float(p["decimal-odds"]) for p in backs)
                    market, sel, line = mapped
                    row = _row(source="matchbook", bookmaker="matchbook_exchange", event_id=f"mb_{ev.get('id')}",
                               league="", home=home, away=away, commence_time=ev.get("start"), market=market,
                               selection=sel, odds=best, line=line, raw={"platform": "exchange"})
                    if row:
                        rows.append(row)
        if len(events) < 100:
            break
    KEYLESS_DIAG["matchbook"] = f"events={total} rows={len(rows)}"
    return rows


COLLECTORS = (("bwin", collect_bwin), ("1xbet_platform", collect_1x_platform), ("matchbook", collect_matchbook))


if __name__ == "__main__":
    import json
    day = date.today().isoformat()
    summary = {"probe": "keyless_odds_dryrun"}
    for name, fn in COLLECTORS:
        try:
            got = fn(day)
        except Exception as exc:
            got = []
            summary[f"{name}_err"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        markets: Dict[str, int] = {}
        for r in got:
            markets[r["market"].split("_")[0]] = markets.get(r["market"].split("_")[0], 0) + 1
        summary[name] = {"rows": len(got), "markets": markets,
                         "sample": [{k: r[k] for k in ("home_team", "away_team", "market", "selection", "odds")} for r in got[:3]]}
    summary["diag"] = KEYLESS_DIAG
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
    if url and key:
        requests.post(f"{url}/rest/v1/netrattler_card_diag", json={"info": summary}, timeout=20,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
