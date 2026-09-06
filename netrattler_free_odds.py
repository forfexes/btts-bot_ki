#!/usr/bin/env python3
"""NETRATTLER free/low-cost observed-odds hub.

Only returns bookmaker-observed decimal prices. No fair/synthetic/model odds.
Sources are fault-isolated and cached per process to reduce API calls:
- 1xBet/Melbet LineFeed bulk pregame
- Kambi/Unibet bulk events + matched event betoffers
- odds-api.net (optional free key: ODDS_API_NET_KEY)
- persisted OddsHarvester/OddsPortal/Bet365 snapshots when present

The main bot still owns Pinnacle/SofaScore/The Odds API/BetExplorer fallbacks.
"""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

UA = os.getenv("NTR_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
_TIMEOUT = float(os.getenv("NETRATTLER_FREE_ODDS_TIMEOUT", "5"))
_TTL = int(os.getenv("NETRATTLER_FREE_ODDS_TTL", "900"))
_CACHE: Dict[str, Tuple[float, Any]] = {}


def _get_cache(key: str):
    v = _CACHE.get(key)
    if v and time.time() - v[0] < _TTL:
        return v[1]
    return None


def _set_cache(key: str, value: Any):
    _CACHE[key] = (time.time(), value)
    return value


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower())
    for token in (" fc ", " cf ", " ac ", " sc ", " afc ", " club "):
        s = f" {s} ".replace(token, " ").strip()
    return " ".join(s.split())


def _match(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    aa = {x for x in a.split() if len(x) >= 4}
    bb = {x for x in b.split() if len(x) >= 4}
    return bool(aa and bb and len(aa & bb) >= min(2, len(aa), len(bb)))


def _decimal(v: Any) -> Optional[float]:
    try:
        x = float(v)
        # common decimal formats only; never reinterpret arbitrary huge values
        return round(x, 4) if 1.01 <= x <= 50 else None
    except Exception:
        return None


def _merge(dst: Dict[str, Any], src: Dict[str, Any], source: str) -> bool:
    got = False
    bounds = {
        "home": (1.01, 15), "draw": (1.5, 15), "away": (1.01, 15),
        "btts_yes": (1.1, 8), "over_25": (1.1, 8),
        "btts_yes_ht": (1.2, 15), "over_15_ht": (1.2, 15),
    }
    aliases = {"home_win":"home", "away_win":"away", "over25":"over_25", "over15_ht":"over_15_ht", "btts_ht_yes":"btts_yes_ht"}
    for k, v in (src or {}).items():
        k = aliases.get(k, k)
        if k not in bounds or k in dst:
            continue
        d = _decimal(v)
        lo, hi = bounds[k]
        if d and lo <= d <= hi:
            dst[k] = d; got = True
    if got:
        dst.setdefault("_sources", []).append(source)
        dst.setdefault("_source", source)
    return got


# ---------- 1xBet / Melbet bulk ----------
_1X_HOSTS = [
    x.strip().rstrip("/") for x in os.getenv("NETRATTLER_1XBET_HOSTS", "https://1xbet.com,https://ind.1xbet.com,https://melbet.com").split(",") if x.strip()
]


def _1x_bulk() -> List[dict]:
    cached = _get_cache("1x_bulk")
    if cached is not None: return cached
    for host in _1X_HOSTS:
        try:
            r = requests.get(host + "/LineFeed/Get1x2_VZip", params={"sports":1,"count":1500,"lng":"en","mode":4,"country":1}, headers=H, timeout=_TIMEOUT)
            if r.ok:
                rows = r.json().get("Value") or []
                if isinstance(rows, list) and rows:
                    return _set_cache("1x_bulk", rows)
        except Exception:
            pass
    return _set_cache("1x_bulk", [])


def _1x_event_odds(row: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    # LineFeed commonly exposes E[] with T=1/2/3 for 1/X/2 and T=9/10 totals.
    # Parse only explicit type/price combinations; unknown schema is ignored.
    for e in row.get("E") or []:
        try:
            t = int(e.get("T")); c = _decimal(e.get("C"))
        except Exception:
            continue
        if not c: continue
        if t == 1: out["home"] = c
        elif t == 2: out["draw"] = c
        elif t == 3: out["away"] = c
        elif t in (9, 180):
            p = e.get("P")
            try: p = float(p)
            except Exception: p = None
            if p == 2.5: out["over_25"] = c
    return out


def get_1xbet(home: str, away: str) -> Dict[str, Any]:
    for row in _1x_bulk():
        h = row.get("O1") or row.get("HomeTeam") or ""
        a = row.get("O2") or row.get("AwayTeam") or ""
        if _match(h, home) and _match(a, away):
            d = _1x_event_odds(row)
            if d: d["_source"] = "1xbet_bulk"
            return d
    return {}


# ---------- Kambi/Unibet bulk ----------
_KAMBI = [
    "https://eu-offering-api.kambicdn.com/offering/v2018/ub",
    "https://eu-offering.kambicdn.org/offering/v2018/ub",
]


def _kambi_events() -> Tuple[Optional[str], List[dict]]:
    cached = _get_cache("kambi_events")
    if cached is not None: return cached
    for host in _KAMBI:
        try:
            r = requests.get(host + "/listView/football.json", headers=H, timeout=_TIMEOUT)
            if not r.ok: continue
            rows = r.json().get("events") or []
            if rows: return _set_cache("kambi_events", (host, rows))
        except Exception: pass
    return _set_cache("kambi_events", (None, []))


def get_kambi(home: str, away: str) -> Dict[str, Any]:
    host, rows = _kambi_events()
    if not host: return {}
    eid = None
    for row in rows:
        ev = row.get("event") or row
        h = ev.get("homeName") or ev.get("homeParticipant") or ev.get("name", "").split(" - ")[0]
        a = ev.get("awayName") or ev.get("awayParticipant") or (ev.get("name", "").split(" - ")[1] if " - " in ev.get("name", "") else "")
        if _match(h, home) and _match(a, away):
            eid = ev.get("id"); break
    if not eid: return {}
    ck = f"kambi_offer:{eid}"
    data = _get_cache(ck)
    if data is None:
        try:
            r = requests.get(f"{host}/betoffer/event/{eid}.json", headers=H, timeout=_TIMEOUT)
            data = r.json() if r.ok else {}
        except Exception: data = {}
        _set_cache(ck, data)
    out: Dict[str, Any] = {}
    for bo in (data or {}).get("betOffers") or []:
        crit = str((bo.get("criterion") or {}).get("label") or "").lower()
        outcomes = bo.get("outcomes") or []
        def ko(oc):
            try: return round(float(oc.get("odds"))/1000.0, 4)
            except Exception: return None
        if any(x in crit for x in ("match result", "full time result", "1x2")):
            for oc in outcomes:
                lab = str(oc.get("label") or "").lower(); v=ko(oc)
                if not v: continue
                if lab in ("1","home"): out["home"] = v
                elif lab in ("x","draw"): out["draw"] = v
                elif lab in ("2","away"): out["away"] = v
        elif "both teams" in crit and "score" in crit:
            for oc in outcomes:
                if str(oc.get("label") or "").lower() in ("yes","ja"):
                    v=ko(oc)
                    if v: out["btts_yes"] = v
        elif ("total goals" in crit or "over/under" in crit) and "2.5" in crit:
            for oc in outcomes:
                if "over" in str(oc.get("label") or "").lower():
                    v=ko(oc)
                    if v: out["over_25"] = v
    if out: out["_source"] = "kambi_unibet"
    return out


# ---------- odds-api.net optional free key ----------
def get_odds_api_net(home: str, away: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    key = os.getenv("ODDS_API_NET_KEY", "").strip()
    if not key: return {}
    base = os.getenv("ODDS_API_NET_BASE", "https://api.odds-api.net/v1").rstrip("/")
    q = f"{home} {away}"
    ck = "oan:" + _norm(q)
    cached = _get_cache(ck)
    if cached is not None: return cached
    try:
        r = requests.get(base + "/events", headers={**H, "X-API-Key":key}, params={"sport":"soccer","search":q,"limit":20}, timeout=_TIMEOUT)
        if not r.ok: return _set_cache(ck, {})
        payload = r.json(); events = payload.get("events") or payload.get("data") or payload.get("items") or []
        ev = next((x for x in events if _match(x.get("home_team") or x.get("home") or "", home) and _match(x.get("away_team") or x.get("away") or "", away)), None)
        if not ev: return _set_cache(ck, {})
        eid = ev.get("id") or ev.get("event_id")
        if not eid: return _set_cache(ck, {})
        s = requests.get(f"{base}/events/{eid}/odds/snapshot", headers={**H, "X-API-Key":key}, timeout=_TIMEOUT)
        if not s.ok: return _set_cache(ck, {})
        data=s.json(); lines=data.get("lines") or data.get("odds") or data.get("data") or []
        out: Dict[str, Any] = {}
        # Accept only clearly labelled market/selection price rows.
        for line in lines if isinstance(lines,list) else []:
            market=str(line.get("market") or line.get("market_key") or "").lower()
            sel=str(line.get("selection") or line.get("name") or "").lower()
            price=_decimal(line.get("odds") or line.get("price"))
            if not price: continue
            if market in ("h2h","moneyline","1x2"):
                if _match(sel, home) or sel in ("home","1"): out["home"]=max(out.get("home",0),price)
                elif _match(sel, away) or sel in ("away","2"): out["away"]=max(out.get("away",0),price)
                elif sel in ("draw","x"): out["draw"]=max(out.get("draw",0),price)
            elif "btts" in market or "both teams" in market:
                if sel in ("yes","y"): out["btts_yes"]=max(out.get("btts_yes",0),price)
            elif "total" in market or "over_under" in market:
                p=line.get("line") or line.get("points")
                try: p=float(p)
                except Exception: p=None
                if p==2.5 and "over" in sel: out["over_25"]=max(out.get("over_25",0),price)
        if out: out["_source"]="odds_api_net"
        return _set_cache(ck,out)
    except Exception:
        return _set_cache(ck,{})


# ---------- persisted OddsHarvester / multi-bookmaker snapshot ----------
def get_snapshot(home: str, away: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    rows = _get_cache("snapshot_rows")
    if rows is None:
        candidates = [os.getenv("NETRATTLER_ODDS_SNAPSHOT", "netrattler_odds_snapshot.json"), "odds_snapshot.json"]
        rows = []
        for fn in candidates:
            p=Path(fn)
            if p.exists():
                try:
                    loaded=json.loads(p.read_text(encoding="utf-8"))
                    rows=loaded if isinstance(loaded,list) else []
                    break
                except Exception:
                    pass
        _set_cache("snapshot_rows", rows)
    if not isinstance(rows,list): return {}
    out: Dict[str,Any]={}
    for r in rows:
        if target_date and str(r.get("match_date") or "")[:10] not in ("", str(target_date)[:10]): continue
        if not (_match(r.get("home_team") or "",home) and _match(r.get("away_team") or "",away)): continue
        m=str(r.get("market") or "").lower(); s=str(r.get("selection") or "").lower(); o=_decimal(r.get("odds"))
        if not o: continue
        if m in ("1x2","h2h","moneyline"):
            if s in ("1","home") or _match(s,home): out["home"]=max(out.get("home",0),o)
            elif s in ("x","draw"): out["draw"]=max(out.get("draw",0),o)
            elif s in ("2","away") or _match(s,away): out["away"]=max(out.get("away",0),o)
        elif "btts" in m and s in ("yes","y"): out["btts_yes"]=max(out.get("btts_yes",0),o)
        elif ("over" in m or "total" in m) and ("2.5" in m or str((r.get("raw") or {}).get("line"))=="2.5") and "over" in s:
            out["over_25"]=max(out.get("over_25",0),o)
    if out: out["_source"]="odds_snapshot"
    return out


def get_free_odds(home: str, away: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    """Return merged best observed prices from free/low-cost sources.
    Order is chosen for bulk efficiency. Does not call OddsPapi.
    """
    out: Dict[str,Any]={}
    for name, fn in (
        ("snapshot", lambda: get_snapshot(home,away,target_date)),
        ("1xbet", lambda: get_1xbet(home,away)),
        ("kambi", lambda: get_kambi(home,away)),
        ("odds_api_net", lambda: get_odds_api_net(home,away,target_date)),
    ):
        try: _merge(out, fn(), name)
        except Exception: pass
        if all(out.get(k) for k in ("home","draw","away","btts_yes","over_25")):
            break
    return out


__all__=["get_free_odds","get_1xbet","get_kambi","get_odds_api_net","get_snapshot"]
