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
X1_HOSTS = [h.strip() for h in os.getenv("ONEX_HOSTS", "https://22bet.com,https://melbet.com,https://betwinner.com,https://megapari.com,https://betandyou.com").split(",") if h.strip()]


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
    if ("both teams to score" in m) and ("total" in m or "over" in m or "&" in m or " and " in m) \
            and not any(t in m for t in ("1st half", "first half", "2nd half", "second half")):
        if re.search(r"(?:yes|ja)\s*(?:&|and)\s*(?:over|o)\s*2[.,]5", o):
            return "btts_over_2_5", "yes", 2.5
        return None
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
    # Always derive the actual fixture teams from the fixture TITLE.
    # bwin participants can contain individual players for markets belonging
    # to a club game (confirmed in its public 3. Liga/Eredivisie feed). Taking
    # the first two participants silently re-labelled team corners/BTTS odds
    # as "player vs player" and polluted odds_history.
    from html import unescape
    name = unescape(_bwin_text(fx.get("name"))).strip()
    if " - " in name:
        home, away = name.split(" - ", 1)
    elif " vs " in name:
        home, away = name.split(" vs ", 1)
    else:
        # Futures such as "LaLiga 2026/27 – Relegation" can also list
        # two clubs as participants. No match title => do not invent a game.
        return out
    home, away = home.strip(), away.strip()
    if not home or not away or home.lower() == away.lower():
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
            oname = _bwin_text(op.get("name")) or _bwin_text(op.get("sourceName"))
            option_types = (op.get("parameters") or {}).get("optionTypes") or []
            if mname.lower().strip() in {"match result", "result 1x2", "1x2"}:
                if "Draw" in option_types:
                    oname = "draw"
                elif _bwin_text(op.get("sourceName")) in {"1", "2"}:
                    oname = _bwin_text(op.get("sourceName"))
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
    attempted = 0
    detailed = 0
    for fx in fixtures:
        new = _bwin_rows(fx)
        present = {row["market"] for row in new}
        # Listing markets can already contain 1X2/FT goals yet omit HT specials.
        # Probe bounded details for the missing markets, not only short listings.
        need_detail = (
            len(new) < 6
            or "btts_ht" not in present
            or "totals_ht_1_5" not in present
        )
        if need_detail and attempted < details and fx.get("id") is not None:
            attempted += 1  # Count failures too: never issue unbounded detail requests.
            dj, _ = _get(f"{BWIN_BASE}/fixture-view", {**BWIN_PARAMS, "offerMapping": "All",
                                                        "fixtureIds": fx.get("id"), "state": "Latest"})
            full = (dj or {}).get("fixture")
            if isinstance(full, dict):
                detailed += 1
                # Preserve the listing if a partial detail response has no prices.
                by_selection = {(row["market"], row["selection"]): row for row in new}
                for row in _bwin_rows(full):
                    by_selection[(row["market"], row["selection"])] = row
                new = list(by_selection.values())
            time.sleep(0.2)
        rows.extend(new)
    KEYLESS_DIAG["bwin"] = f"http={st} fixtures={len(fixtures)} detail_attempts={attempted} detail_ok={detailed} rows={len(rows)}"
    return rows


# --------------------------------------------------------------------- 1xBet platform
# Event type codes on the 1xBet LineFeed: 1/2/3 = 1X2, 9/10 = total over/under (P=line),
# 180/181 = both teams to score yes/no. Group 17 = totals, 19 = BTTS.
_X1_TYPES = {1: ("1x2", "home"), 2: ("1x2", "draw"), 3: ("1x2", "away"),
             180: ("btts", "yes"), 181: ("btts", "no"),
             4: ("double_chance", "1x"), 5: ("double_chance", "12"), 6: ("double_chance", "x2")}


_X1_PLACEHOLDER_TEAM = re.compile(r"^(?:home|away|team\s*[12])(?:\s*\([^)]*bets?\))?$", re.I)


def _x1_has_real_teams(home: Any, away: Any) -> bool:
    """Never emit prices for synthetic Home/Away special-bets pseudo-events."""
    h, a = str(home or "").strip(), str(away or "").strip()
    return bool(h and a and h.casefold() != a.casefold()
                and not _X1_PLACEHOLDER_TEAM.fullmatch(h)
                and not _X1_PLACEHOLDER_TEAM.fullmatch(a))


def _x1_rows(g: Mapping[str, Any], host: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    home, away = g.get("O1") or "", g.get("O2") or ""
    if not _x1_has_real_teams(home, away):
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


def _x1_ht_rows(g: Mapping[str, Any], sub: Mapping[str, Any], host: str) -> List[Dict[str, Any]]:
    """1st-half subgame of a 1xBet event. Same type codes as full time:
    9/10 = total over/under (P=line), 180/181 = BTTS yes/no. Real prices only."""
    out: List[Dict[str, Any]] = []
    home, away = g.get("O1") or "", g.get("O2") or ""
    if not _x1_has_real_teams(home, away):
        return out
    start = datetime.fromtimestamp(int(g.get("S") or 0), tz=timezone.utc).isoformat() if g.get("S") else None
    league = g.get("L") or g.get("LE") or ""
    bk = "1x_" + re.sub(r"^https?://(www\.)?|\.com.*$", "", host)
    evs = []
    for grp in sub.get("GE") or []:
        for arr in grp.get("E") or []:
            evs.extend(arr if isinstance(arr, list) else [arr])
    for e in evs:
        t = e.get("T")
        line = None
        if t in (180, 181) and e.get("P") is None:
            market, sel = "btts_ht", "yes" if t == 180 else "no"
        elif t in (9, 10) and e.get("P") is not None:
            line = float(e.get("P"))
            market, sel = f"totals_ht_{_line_tag(line)}", f"{'over' if t == 9 else 'under'}_{_line_tag(line)}"
        else:
            continue
        row = _row(source="1xbet_platform", bookmaker=bk, event_id=f"1x_{g.get('I')}", league=league,
                   home=home, away=away, commence_time=start, market=market, selection=sel,
                   odds=e.get("C"), line=line, raw={"platform": "1xbet", "host": host, "period": 1})
        if row:
            out.append(row)
    return out


def _x1_ht_worker(host: str, games: List[Mapping[str, Any]], deadline: float, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for g in games:
        if time.time() > deadline:
            stats["budget_stop"] = stats.get("budget_stop", 0) + 1
            break
        stats["tried"] = stats.get("tried", 0) + 1
        gj, code = None, None
        for attempt in range(2):
            gj, code = _get(f"{host}/service-api/LineFeed/GetGameZip",
                            {"id": str(g.get("I")), "lng": "en", "isSubGames": "true", "GroupEvents": "true",
                             "countevents": "250", "grMode": "2"})
            if gj:
                break
            time.sleep(0.6)
        if not gj:
            stats["no_json"] = stats.get("no_json", 0) + 1
            c = stats.setdefault("codes", {})
            c[str(code)] = c.get(str(code), 0) + 1
            continue
        val = gj.get("Value") or {}
        # Mirrors share the LineFeed, but never trust an id that points at a different fixture.
        if val.get("O1") and g.get("O1") and str(val.get("O1")).strip().lower() != str(g.get("O1")).strip().lower():
            stats["id_mismatch"] = stats.get("id_mismatch", 0) + 1
            continue
        sgs = val.get("SG") or []
        if not sgs:
            stats["no_sg"] = stats.get("no_sg", 0) + 1
        for sg in sgs:
            if str(sg.get("PN") or "").lower().startswith("1st") and sg.get("I"):
                stats["has_1h"] = stats.get("has_1h", 0) + 1
                hj, _ = _get(f"{host}/service-api/LineFeed/GetGameZip",
                             {"id": str(sg["I"]), "lng": "en", "GroupEvents": "true",
                              "countevents": "250", "grMode": "2"})
                new = _x1_ht_rows(g, (hj or {}).get("Value") or {}, host)
                if not new:
                    stats["rows0"] = stats.get("rows0", 0) + 1
                rows.extend(new)
                break
        time.sleep(0.15)
    return rows


def _x1_collect_ht(host: str, games: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """1st-half lookups spread over all mirror hosts (one worker per host) so one slow host cannot starve the run."""
    from concurrent.futures import ThreadPoolExecutor
    cap = int(os.getenv("ONEX_HT_GAMES", "200"))
    hosts = [host] + [h for h in X1_HOSTS if h != host]
    slices = [games[:cap][i::len(hosts)] for i in range(len(hosts))]
    deadline = time.time() + float(os.getenv("ONEX_HT_BUDGET_S", "300"))
    stats_all: List[Dict[str, Any]] = [{} for _ in hosts]
    with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futs = [pool.submit(_x1_ht_worker, h, sl, deadline, st) for h, sl, st in zip(hosts, slices, stats_all)]
        rows: List[Dict[str, Any]] = []
        for f in futs:
            try:
                rows.extend(f.result() or [])
            except Exception:
                pass
    KEYLESS_DIAG["1x_ht_stats"] = {h.split("//")[-1]: st for h, st in zip(hosts, stats_all)}
    return rows


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
        kept_games = [g for g in games if not g.get("SC") and g.get("S")
                      and _in_window(datetime.fromtimestamp(int(g["S"]), tz=timezone.utc).date().isoformat(), target_date)]
        try:
            ht = _x1_collect_ht(host, kept_games)
        except Exception:
            ht = []
        rows.extend(ht)
        KEYLESS_DIAG["1x_ht_rows"] = len(ht)
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


# --------------------------------------------------------------------- Altenar platform
# Public widget endpoint observed on the already-vetted Vegas.hu public homepage
# (see netrattler_altenar_schema_probe.py / BETCLONE_STATUS.md). A plain keyless
# GET with the same public query the page's own browser makes; confirmed
# reachable (HTTP 200) without any login, token or bypass. Only emits a
# complete 1x2 market: the Altenar response has no totals/btts markets in the
# fields observed so far, so this is conservative by construction, and is
# wired through the exact same never-auto-promote shadow+corroboration gate
# used for 1xbet_platform in netrattler_odds_cache_guard.py.
ALTENAR_INTEGRATIONS = {"vegas.hu": "https://hu-sb2frontend-altenar2.biahosted.com"}
ALTENAR_FOOTBALL_ICON = "soccer"


# Altenar market/selection ids, confirmed from the public GetEvents payload
# (headers[] + full market samples, 2026-10-17). These are locale-free
# integers; market/selection NAMES are in the operator's language.
#   market typeId 1  = 1X2            odds typeId 1/2/3 = home/draw/away
#   market typeId 18 = total goals    market.sv = line; odds 12/13 = over/under
#   market typeId 29 = both to score  odds 74/76 = yes/no
# typeId 20135 ("1X2 - Odds+") is a boosted promo price, never a normal
# market quote, and is excluded simply by not being listed here.
ALTENAR_MARKETS = {
    1: ("1x2", {1: "home", 2: "draw", 3: "away"}),
    18: ("totals", {12: "over", 13: "under"}),
    29: ("btts", {74: "yes", 76: "no"}),
}
ALTENAR_TOTAL_LINES = {"2.5"}  # only the line the corroboration gate covers


def _altenar_market_kind(market: Mapping[str, Any]):
    # GetTopEvents markets carry a headerName: keep the original, verified
    # rule there (only the 1X2 header, 1X2 only). GetEvents markets have no
    # headerName and are identified by the locale-free market typeId.
    if "headerName" in market:
        return 1 if str(market.get("headerName") or "").strip() == "1X2" else None
    tid = market.get("typeId")
    return tid if tid in ALTENAR_MARKETS else None


def _altenar_rows(payload: Mapping[str, Any], bookmaker: str) -> List[Dict[str, Any]]:
    """Normalize an Altenar GetEvents / GetTopEvents response into odds_history rows.

    Join path: event.sportId -> sports[].iconName == "soccer" (locale-proof);
    event.competitorIds[0/1] -> competitors[].name for home/away;
    event.marketIds[] -> markets[] (by locale-free typeId, see ALTENAR_MARKETS)
    -> oddIds[] -> odds[] (selection role = odds.typeId, active = oddStatus 0).
    A market only counts when EVERY selection is present and active, so no
    partial lines ever reach the corroboration gate.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return out
    sports = {s.get("id"): s for s in (payload.get("sports") or []) if isinstance(s, dict)}
    football_sport_ids = {sid for sid, s in sports.items()
                           if str(s.get("iconName") or "").lower() == ALTENAR_FOOTBALL_ICON}
    competitors = {c.get("id"): c.get("name") for c in (payload.get("competitors") or []) if isinstance(c, dict)}
    champs = {c.get("id"): c.get("name") for c in (payload.get("champs") or []) if isinstance(c, dict)}
    markets = {m.get("id"): m for m in (payload.get("markets") or []) if isinstance(m, dict)}
    odds_by_id = {o.get("id"): o for o in (payload.get("odds") or []) if isinstance(o, dict)}
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict) or ev.get("sportId") not in football_sport_ids:
            continue
        if ev.get("status") not in (0, None):
            continue  # anything other than the normal/scheduled state is skipped
        comp_ids = ev.get("competitorIds") or []
        home = competitors.get(comp_ids[0]) if len(comp_ids) >= 1 else None
        away = competitors.get(comp_ids[1]) if len(comp_ids) >= 2 else None
        if not home or not away:
            name = str(ev.get("name") or "")
            parts = re.split(r"\s+vs\.?\s+", name, maxsplit=1)
            if len(parts) == 2:
                home, away = home or parts[0].strip(), away or parts[1].strip()
        if not home or not away:
            continue
        start = ev.get("startDate")
        league = champs.get(ev.get("champId")) or ""
        for market_id in ev.get("marketIds") or []:
            market = markets.get(market_id)
            kind = _altenar_market_kind(market) if market else None
            if kind is None:
                continue
            market_key, sel_by_type = ALTENAR_MARKETS[kind]
            line_suffix = ""
            if market_key == "totals":
                line = str(market.get("sv") or "").strip()
                if line not in ALTENAR_TOTAL_LINES:
                    continue
                line_suffix = "_" + line.replace(".", "_")
            selections: Dict[str, float] = {}
            for odd_id in market.get("oddIds") or []:
                odd = odds_by_id.get(odd_id)
                if not isinstance(odd, dict) or odd.get("oddStatus") not in (0, None):
                    continue
                sel = sel_by_type.get(odd.get("typeId"))
                if not sel or odd.get("price") is None:
                    continue
                selections[sel] = odd.get("price")
            if len(selections) != len(sel_by_type):
                continue  # only complete markets; no partial lines
            for sel, price in selections.items():
                row = _row(source="altenar_platform", bookmaker=bookmaker, event_id=f"alt_{ev.get('id')}",
                           league=league, home=home, away=away, commence_time=start,
                           market=market_key + line_suffix, selection=sel + line_suffix, odds=price,
                           raw={"platform": "altenar", "integration": bookmaker,
                                "line": (line_suffix[1:].replace("_", ".") or None)})
                if row:
                    out.append(row)
    return out


ALTENAR_FOOTBALL_SPORT_ID = os.getenv("ALTENAR_FOOTBALL_SPORT_ID", "66")


def collect_altenar_platform(target_date: str) -> List[Dict[str, Any]]:
    """Altenar public widget prices (1x2, totals 2.5, btts); shadow-only.

    GetEvents (the full football listing the public page itself calls) is
    used first; GetTopEvents (a handful of featured matches) is the fallback.
    """
    rows: List[Dict[str, Any]] = []
    base = {"culture": "hu-HU", "timezoneOffset": "-300", "deviceType": "1",
            "numFormat": "hu-HU", "countryCode": "", "eventCount": "0", "timePeriod": "0"}
    for brand, host in ALTENAR_INTEGRATIONS.items():
        js, st = _get(f"{host}/api/widget/GetEvents",
                      {**base, "integration": brand, "sportId": ALTENAR_FOOTBALL_SPORT_ID})
        endpoint = "GetEvents"
        if not js or not (js.get("events") if isinstance(js, dict) else None):
            js, st = _get(f"{host}/api/widget/GetTopEvents", {**base, "integration": brand, "sportId": "0",
                                                              "eventCount": os.getenv("ALTENAR_EVENT_COUNT", "50")})
            endpoint = "GetTopEvents"
        if not js:
            KEYLESS_DIAG[f"altenar_{brand}"] = f"http={st} events=0"
            continue
        n_events = len(js.get("events") or []) if isinstance(js, dict) else 0
        new_rows = _altenar_rows(js, bookmaker=f"altenar_{brand}")
        by_market: Dict[str, int] = {}
        for r in new_rows:
            by_market[r.get("market")] = by_market.get(r.get("market"), 0) + 1
        KEYLESS_DIAG[f"altenar_{brand}"] = (
            f"{endpoint} http={st} events={n_events} rows={len(new_rows)} markets={by_market}"
        )
        rows.extend(new_rows)
    # Production diagnostic (Actions logs are not retrievable here).
    try:
        SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
        if SUPABASE_URL and SUPABASE_KEY:
            import requests as _rq
            _rq.post(
                f"{SUPABASE_URL}/rest/v1/netrattler_card_diag", timeout=10,
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                json={"info": {"probe": "altenar_collector_run",
                                "diag": {k: v for k, v in KEYLESS_DIAG.items() if k.startswith("altenar_")},
                                "rows": len(rows)}},
            )
    except Exception:
        pass
    return rows


# ------------------------------------------------------------------------ Smarkets
# Public exchange API (no login, no key). Schema confirmed by
# netrattler_smarkets_probe.py on 2026-10-17: quotes are order-book entries in
# basis points of probability; the best OFFER is the price a backer can take,
# so decimal back odds = 10000 / lowest offer price.
SMARKETS_API = "https://api.smarkets.com/v3"
SMARKETS_MARKETS = {
    ("WINNER_3_WAY", None): ("1x2", {"HOME": "home", "DRAW": "draw", "AWAY": "away"}),
    ("BTTS", None): ("btts", {"YES": "yes", "NO": "no"}),
    ("OVER_UNDER", "2.5"): ("totals_2_5", {"OVER": "over_2_5", "UNDER": "under_2_5"}),
    ("BTTS_FIRST_HALF", None): ("btts_ht", {"YES": "yes", "NO": "no"}),
    ("FIRST_HALF_OVER_UNDER", "1.5"): ("totals_ht_1_5", {"OVER": "over_1_5", "UNDER": "under_1_5"}),
}


def _sm_market_key(m: Mapping[str, Any]):
    mt = m.get("market_type") if isinstance(m.get("market_type"), dict) else {}
    name, param = str(mt.get("name") or ""), mt.get("param")
    if (name, None) in SMARKETS_MARKETS:
        return SMARKETS_MARKETS[(name, None)]
    return SMARKETS_MARKETS.get((name, str(param) if param is not None else None))


SMARKETS_MIN_SPREAD_RATIO = float(os.getenv("SMARKETS_MIN_SPREAD_RATIO", "0.90"))


def _sm_back_odds(quote: Mapping[str, Any]) -> Optional[float]:
    """Back price = 10000 / best offer, but ONLY on a tight two-sided book.

    A thin exchange market can show a stale offer far from the real price
    (seen: 7.00 vs 4.91 elsewhere). Require a bid and best_bid/best_offer >=
    SMARKETS_MIN_SPREAD_RATIO (in probability points), otherwise drop it."""
    offers = [o for o in (quote or {}).get("offers") or [] if isinstance(o, dict) and o.get("price")]
    bids = [b for b in (quote or {}).get("bids") or [] if isinstance(b, dict) and b.get("price")]
    if not offers or not bids:
        return None
    best = min(int(o["price"]) for o in offers)
    best_bid = max(int(b["price"]) for b in bids)
    if best <= 0 or best >= 10000 or best_bid <= 0:
        return None
    if best_bid / best < SMARKETS_MIN_SPREAD_RATIO:
        return None
    return round(10000.0 / best, 3)


def _sm_complete(market: str, by_sel: Mapping[str, float]) -> bool:
    need = {"1x2": {"home", "draw", "away"}, "btts": {"yes", "no"}, "btts_ht": {"yes", "no"},
            "totals_2_5": {"over_2_5", "under_2_5"}, "totals_ht_1_5": {"over_1_5", "under_1_5"}}[market]
    if not need <= set(by_sel):
        return False
    overround = sum(1.0 / by_sel[s] for s in need)
    return 0.98 <= overround <= 1.15  # thin/broken books are dropped, never "fixed"


def collect_smarkets(target_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    params = {"type": "football_match", "state": "upcoming", "limit": "50", "sort": "start_datetime,id"}
    max_events = int(os.getenv("SMARKETS_MAX_EVENTS", "400"))
    now = datetime.now(timezone.utc)
    for _ in range(max_events // 50 + 1):
        js, st = _get(f"{SMARKETS_API}/events/", params)
        page = (js or {}).get("events") or []
        for ev in page:
            day = str(ev.get("start_date") or "")[:10]
            try:
                start = datetime.fromisoformat(str(ev.get("start_datetime")).replace("Z", "+00:00"))
            except Exception:
                continue
            if start <= now or not _in_window(day, target_date) or " vs " not in str(ev.get("name") or ""):
                continue
            events.append(ev)
        nxt = ((js or {}).get("pagination") or {}).get("next_page")
        if not page or not nxt or len(events) >= max_events:
            break
        from urllib.parse import parse_qsl
        params = dict(parse_qsl(nxt.lstrip("?")))
    events = events[:max_events]
    n_markets = 0
    for i in range(0, len(events), 20):
        batch = events[i:i + 20]
        ids = ",".join(str(e["id"]) for e in batch)
        mj, _ = _get(f"{SMARKETS_API}/events/{ids}/markets/")
        wanted = {}
        for m in (mj or {}).get("markets") or []:
            spec = _sm_market_key(m)
            if spec and m.get("state") == "open":
                wanted[str(m["id"])] = (m, spec)
        if not wanted:
            continue
        mids = list(wanted)
        for j in range(0, len(mids), 40):
            chunk = ",".join(mids[j:j + 40])
            cj, _ = _get(f"{SMARKETS_API}/markets/{chunk}/contracts/")
            qj, _ = _get(f"{SMARKETS_API}/markets/{chunk}/quotes/")
            contracts = (cj or {}).get("contracts") or []
            quotes = qj or {}
            per_market: Dict[str, Dict[str, float]] = {}
            for c in contracts:
                mid = str(c.get("market_id"))
                if mid not in wanted:
                    continue
                ctype = str((c.get("contract_type") or {}).get("name") or "").upper()
                sel = wanted[mid][1][1].get(ctype)
                odds = _sm_back_odds(quotes.get(str(c.get("id"))) or {})
                if sel and odds:
                    per_market.setdefault(mid, {})[sel] = odds
            ev_by_id = {str(e["id"]): e for e in batch}
            for mid, by_sel in per_market.items():
                m, (market, _sels) = wanted[mid]
                if not _sm_complete(market, by_sel):
                    continue
                ev = ev_by_id.get(str(m.get("event_id")))
                if not ev:
                    continue
                home, away = [x.strip() for x in str(ev["name"]).split(" vs ", 1)]
                n_markets += 1
                for sel, odds in by_sel.items():
                    line = 2.5 if market == "totals_2_5" else 1.5 if market == "totals_ht_1_5" else None
                    row = _row(source="smarkets", bookmaker="smarkets_exchange", event_id=f"sm_{ev['id']}",
                               league="", home=home, away=away, commence_time=ev.get("start_datetime"),
                               market=market, selection=sel, odds=odds, line=line, raw={"platform": "exchange"})
                    if row:
                        rows.append(row)
    KEYLESS_DIAG["smarkets"] = f"events={len(events)} markets={n_markets} rows={len(rows)}"
    return rows

COLLECTORS = (("bwin", collect_bwin), ("1xbet_platform", collect_1x_platform),
              ("matchbook", collect_matchbook), ("altenar_platform", collect_altenar_platform),
              ("smarkets", collect_smarkets))


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
