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
