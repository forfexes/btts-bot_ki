"""SportsGameOdds (Gratisplan: MLS + Champions League) -> Spieler-Prop-Zeilen fuer den Builder-Pool.

Nur echte Buchmacher-Quoten (beste Quote ueber die Buecher). Quoten kommen im amerikanischen Format und werden in
Dezimal umgerechnet. Keine Wahrscheinlichkeit: die bestimmt das ML-Modell anhand der Spielerhistorie (player_game_log).
Aktiv nur mit SPORTSGAMEODDS_API_KEY; Abschalten: NETRATTLER_SGO=off."""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

BASE = os.getenv("SGO_BASE", "https://api.sportsgameodds.com/v2")
LEAGUES = {"MLS": "MLS", "UEFA_CHAMPIONS_LEAGUE": "Champions League"}
# SGO statID -> Builder-Kategorie
STAT_CATEGORY = {"shots": "shots", "shots_onGoal": "sot", "tackles": "tackles", "assists": "assist",
                 "goalie_saves": "saves", "yellowCards": "yellow_cards", "combinedCards": "yellow_cards"}
MIN_ODDS, MAX_ODDS = 1.20, 15.0


def american_to_decimal(value: Any) -> Optional[float]:
    try:
        v = float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    return round(1 + v / 100.0, 3) if v > 0 else round(1 + 100.0 / abs(v), 3)


def _line_to_n_plus(over_under: Any) -> Optional[float]:
    """Over 2.5 -> '3+' (Engine-Semantik: ganzzahlige Linie = N oder mehr)."""
    try:
        return float(math.floor(float(over_under)) + 1)
    except (TypeError, ValueError):
        return None


def parse_event(ev: Dict[str, Any], league_label: str) -> List[Dict[str, Any]]:
    """Ein Event -> Zeilen {player, team, match, league, category, line, odds, source, kickoff}."""
    teams = ev.get("teams") or {}
    home = ((teams.get("home") or {}).get("names") or {}).get("long") or ""
    away = ((teams.get("away") or {}).get("names") or {}).get("long") or ""
    if not home or not away:
        return []
    match = f"{home} vs {away}"
    kickoff = str((ev.get("status") or {}).get("startsAt") or "")
    players = ev.get("players") or {}
    best: Dict[tuple, Dict[str, Any]] = {}
    for oid, od in (ev.get("odds") or {}).items():
        stat = od.get("statID")
        cat = STAT_CATEGORY.get(stat)
        pid = od.get("playerID")
        if not cat or not pid or od.get("periodID") != "game":
            continue
        bt, side = od.get("betTypeID"), od.get("sideID")
        if (bt, side) not in {("ou", "over"), ("yn", "yes")}:
            continue
        pinfo = players.get(pid) or {}
        name = pinfo.get("name") or " ".join(str(pid).split("_")[:-2]).title()
        team_id = pinfo.get("teamID") or ""
        team = home if team_id and team_id == (teams.get("home") or {}).get("teamID") else (
            away if team_id and team_id == (teams.get("away") or {}).get("teamID") else "")
        for book, bd in (od.get("byBookmaker") or {}).items():
            if not bd.get("available", True):
                continue
            dec = american_to_decimal(bd.get("odds"))
            if dec is None or not (MIN_ODDS <= dec <= MAX_ODDS):
                continue
            line = 1.0 if bt == "yn" else _line_to_n_plus(bd.get("overUnder"))
            if line is None or line < 1:
                continue
            key = (pid, cat, line)
            if key not in best or dec > best[key]["odds"]:
                best[key] = {"player": name, "team": team, "match": match, "league": league_label, "category": cat,
                             "line": line, "odds": dec, "source": f"sgo_{book}", "kickoff": kickoff,
                             "market": f"{stat} {'1+' if bt == 'yn' else 'Over ' + str(bd.get('overUnder'))}"}
    return list(best.values())


def fetch_rows(hours_ahead: int = 36, limit: int = 10) -> List[Dict[str, Any]]:
    key = os.getenv("SPORTSGAMEODDS_API_KEY", "")
    if not key or os.getenv("NETRATTLER_SGO", "on").lower() in {"off", "0", "false"}:
        return []
    now = datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for lg, label in LEAGUES.items():
        try:
            r = requests.get(f"{BASE}/events", headers={"X-Api-Key": key}, timeout=40, params={
                "leagueID": lg, "oddsAvailable": "true", "finalized": "false", "limit": str(limit),
                "startsAfter": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "startsBefore": (now + timedelta(hours=hours_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            if not r.ok:
                continue
            for ev in (r.json().get("data") or []):
                rows.extend(parse_event(ev, label))
        except Exception:
            continue
    return rows
