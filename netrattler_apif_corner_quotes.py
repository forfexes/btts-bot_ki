"""Echte Ecken-Over-Quoten (Bet365/Betano u.a.) aus API-Football als Ersatz fuer das blockierte Kambi."""
from __future__ import annotations
import os, re
import requests

_BASE = "https://v3.football.api-sports.io"
_FX_CACHE: dict = {}
_ODDS_CACHE: dict = {}
_PREF = ("bet365", "betano", "1xbet", "pinnacle", "marathonbet", "unibet")


def _key():
    for k in (os.getenv("API_FOOTBALL_KEYS") or "").replace("\n", ",").split(","):
        if k.strip():
            return k.strip()
    return ""


def _get(path, params):
    k = _key()
    if not k:
        return []
    try:
        r = requests.get(_BASE + path, params=params, headers={"x-apisports-key": k}, timeout=25)
        if r.ok:
            return r.json().get("response") or []
    except Exception:
        pass
    return []


def _fixtures(day):
    if day not in _FX_CACHE:
        _FX_CACHE[day] = _get("/fixtures", {"date": day})
    return _FX_CACHE[day]


def fetch_apif_corner_quotes(home, away, day):
    """-> {line: (odds, source)} fuer 'Over x.5' Gesamtecken, leer wenn nichts gefunden."""
    from netrattler_prop_sources import _team_pair_match
    fid = None
    for fx in _fixtures(str(day)):
        t = fx.get("teams") or {}
        if _team_pair_match((t.get("home") or {}).get("name"), (t.get("away") or {}).get("name"), home, away):
            fid = (fx.get("fixture") or {}).get("id")
            break
    if not fid:
        return {}
    if fid not in _ODDS_CACHE:
        _ODDS_CACHE[fid] = _get("/odds", {"fixture": fid})
    best = {}
    for item in _ODDS_CACHE[fid]:
        for bk in item.get("bookmakers") or []:
            name = str(bk.get("name") or "")
            rank = next((i for i, p in enumerate(_PREF) if p in name.lower()), len(_PREF))
            for bet in bk.get("bets") or []:
                if str(bet.get("name") or "").strip().lower() != "corners over under":
                    continue
                for v in bet.get("values") or []:
                    m = re.match(r"^over\s+(\d+(?:\.\d+)?)$", str(v.get("value") or "").strip(), re.I)
                    try:
                        odds = float(v.get("odd") or 0)
                    except Exception:
                        continue
                    if not m or odds <= 1.05:
                        continue
                    line = round(float(m.group(1)), 2)
                    prev = best.get(line)
                    if prev is None or rank < prev[2] or (rank == prev[2] and odds > prev[0]):
                        best[line] = (odds, f"apif_{name.lower()}", rank)
    return {ln: (o, s) for ln, (o, s, _) in best.items()}


def observed_corner_receipts(home,away,day,*,now=None):
    """Use exact fixture IDs, source update timestamps and offered half-lines.

    Return only current, unambiguous pre-match observations. Keep the
    legacy tuple API separate for historical/model use.
    """
    from datetime import datetime,timezone,timedelta
    from zoneinfo import ZoneInfo
    from math import isfinite
    from netrattler_crest_identity import same_club
    from netrattler_builder_engine import is_bookmaker_source
    clock=now or datetime.now(timezone.utc)
    def stamp(value):
        try:
            result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
            return result if result.tzinfo is not None and result.utcoffset() is not None else None
        except (TypeError,ValueError):
            return None
    matches=[]
    for fx in _fixtures(str(day)):
        f=fx.get("fixture") or {}
        teams=fx.get("teams") or {}
        ht,at=teams.get("home") or {},teams.get("away") or {}
        ko=stamp(f.get("date"))
        if (not ko or ko<=clock or ko.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()!=str(day)
            or not f.get("id") or not ht.get("id") or not at.get("id") or ht["id"]==at["id"]
            or not same_club(home,ht.get("name")) or not same_club(away,at.get("name"))
            or (f.get("status") or {}).get("short") not in ("NS","TBD")):
            continue
        matches.append((f["id"],ht["id"],at["id"],ko))
    if len(set(matches))!=1:
        return {}
    fid,hid,aid,ko=matches[0]
    if fid not in _ODDS_CACHE:
        _ODDS_CACHE[fid]=_get("/odds",{"fixture":fid})
    observations={}
    for item in _ODDS_CACHE[fid]:
        if str((item.get("fixture") or {}).get("id"))!=str(fid):
            continue
        seen=stamp(item.get("update"))
        if not seen or not timedelta(0)<=clock-seen<=timedelta(minutes=15):
            continue
        for book in item.get("bookmakers") or []:
            name=str(book.get("name") or "").strip()
            if not book.get("id") or not is_bookmaker_source(name):
                continue
            for market in book.get("bets") or []:
                if str(market.get("name") or "").strip().lower()!="corners over under" or not market.get("id"):
                    continue
                for value in market.get("values") or []:
                    if value.get("suspended") is True or value.get("available") is False:
                        continue
                    label=str(value.get("value") or "").strip()
                    m=re.fullmatch(r"Over\s+(\d+(?:\.\d+)?)",label,re.I)
                    if not m:
                        continue
                    try:
                        line=float(m.group(1));price=float(value.get("odd"))
                    except (TypeError,ValueError):
                        continue
                    if not (isfinite(price) and 1.05<price<=10 and 6.5<=line<=14.5 and line%1==.5):
                        continue
                    key=(line,str(book["id"]),str(market["id"]))
                    record={"fixture_id":str(fid),"fixture_provider":"api-football",
                        "home_id":str(hid),"away_id":str(aid),"kickoff":ko.isoformat(),
                        "quote_id":":".join(map(str,(fid,book["id"],market["id"],"over",line))),
                        "quote_observed_at":seen.isoformat(),"quote_observed":True,
                        "odds_observed":True,"price_estimated":False,
                        "bookmaker":name,"bookmaker_odds":price}
                    observations.setdefault(key,[]).append(record)
    best={}
    for (line,_,_),rows in observations.items():
        if len({r["bookmaker_odds"] for r in rows})!=1:
            continue
        record=max(rows,key=lambda r:r["quote_observed_at"])
        if line not in best or record["bookmaker_odds"]>best[line]["bookmaker_odds"]:
            best[line]=record
    return best
