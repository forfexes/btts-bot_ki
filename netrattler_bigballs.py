#!/usr/bin/env python3
"""Big Balls Sports Data adapter for NETRATTLER.

Optional feature/lineup/stat fallback only. It never manufactures or publishes
bookmaker odds. The adapter stays dormant unless BIGBALLS_API_KEY or BBS_API_KEY
is configured.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

BASE_URL = (os.getenv("BIGBALLS_API_BASE") or "https://api.bigballsdata.com").rstrip("/")
API_KEY = os.getenv("BIGBALLS_API_KEY") or os.getenv("BBS_API_KEY") or ""
TIMEOUT = float(os.getenv("NETRATTLER_BIGBALLS_TIMEOUT", "5"))
MAX_MATCH_DETAILS = max(0, int(os.getenv("NETRATTLER_BIGBALLS_MAX_MATCHES", "8")))

_SESSION = requests.Session()
_DATE_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_MATCH_CACHE: Dict[str, Dict[str, Any]] = {}
_DETAIL_CALLS = 0


def enabled() -> bool:
    return bool(API_KEY)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\b(fc|cf|sc|afc|ac|club|team|women|wfc)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _team_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("name") or value.get("display_name") or value.get("short_name") or "")
    return str(value or "")


def _date_of(row: Mapping[str, Any]) -> str:
    raw = row.get("kickoff_utc") or row.get("kickoff") or row.get("date") or row.get("match_date") or row.get("start_time")
    if raw:
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except Exception:
            return text[:10]
    return ""


def _rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(x) for x in payload if isinstance(x, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [dict(x) for x in data if isinstance(x, Mapping)]
    if isinstance(data, Mapping):
        for key in ("matches", "results", "items", "rows", "players"):
            value = data.get(key)
            if isinstance(value, list):
                return [dict(x) for x in value if isinstance(x, Mapping)]
    for key in ("matches", "results", "items", "rows", "players"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(x) for x in value if isinstance(x, Mapping)]
    return []


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    if not enabled():
        return None
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "x-api-key": API_KEY,
        "Accept": "application/json",
        "User-Agent": "NETRATTLER/37",
    }
    try:
        response = _SESSION.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after or 0)
            except Exception:
                delay = 0
            # Runtime-safe: respect short server retry windows; do not stall the tips run.
            if 0 < delay <= 5:
                time.sleep(delay)
                response = _SESSION.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
        if not response.ok:
            return None
        return response.json()
    except Exception:
        return None


def matches_for_date(target_date: Any) -> List[Dict[str, Any]]:
    day = str(target_date or date.today().isoformat())[:10]
    if day in _DATE_CACHE:
        return _DATE_CACHE[day]
    payload = _get("/v1/stored/matches", {"date": day, "limit": 200})
    rows = _rows(payload)
    if not rows:
        # Stored route can be sparse during live ingest; the unified football list is the fallback.
        payload = _get("/v1/matches", {"sport": "football", "limit": 200})
        rows = [r for r in _rows(payload) if not _date_of(r) or _date_of(r) == day]
    _DATE_CACHE[day] = rows
    return rows


def find_match(home: str, away: str, target_date: Any) -> Optional[Dict[str, Any]]:
    nh, na = _norm(home), _norm(away)
    if not nh or not na:
        return None
    for row in matches_for_date(target_date):
        rh = _norm(_team_name(row.get("home") or row.get("home_team")))
        ra = _norm(_team_name(row.get("away") or row.get("away_team")))
        if rh == nh and ra == na:
            return row
    # Conservative token containment only; never swap home/away.
    for row in matches_for_date(target_date):
        rh = _norm(_team_name(row.get("home") or row.get("home_team")))
        ra = _norm(_team_name(row.get("away") or row.get("away_team")))
        if rh and ra and (rh in nh or nh in rh) and (ra in na or na in ra):
            return row
    return None


def _flatten_numeric(obj: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            name = f"{prefix}_{key}" if prefix else str(key)
            if isinstance(value, (Mapping, list)):
                out.update(_flatten_numeric(value, name))
            else:
                try:
                    if value not in (None, "", True, False):
                        out[_norm(name).replace(" ", "_")] = float(value)
                except Exception:
                    pass
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            out.update(_flatten_numeric(value, f"{prefix}_{idx}" if prefix else str(idx)))
    return out


def _first_metric(flat: Mapping[str, float], aliases: Iterable[str]) -> Optional[float]:
    normalized = [_norm(x).replace(" ", "_") for x in aliases]
    for alias in normalized:
        if alias in flat:
            return flat[alias]
    for key, value in flat.items():
        if any(alias in key for alias in normalized):
            return value
    return None


def _lineup_names(payload: Any, side: str) -> List[str]:
    if not isinstance(payload, Mapping):
        return []
    root = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
    candidates: List[Any] = []
    for key in (side, f"{side}_lineup", f"{side}Lineup"):
        if isinstance(root, Mapping) and root.get(key) is not None:
            candidates.append(root.get(key))
    # Generic lineup arrays often carry team/side metadata.
    if isinstance(root, Mapping):
        for key in ("lineups", "players", "starting_xi", "starters"):
            if root.get(key) is not None:
                candidates.append(root.get(key))
    names: List[str] = []
    for block in candidates:
        if isinstance(block, Mapping):
            block = block.get("starters") or block.get("starting_xi") or block.get("players") or list(block.values())
        if not isinstance(block, list):
            continue
        for item in block:
            if isinstance(item, Mapping):
                item_side = _norm(item.get("side") or item.get("home_away") or item.get("team_side"))
                if item_side and side not in item_side:
                    continue
                player = item.get("player") if isinstance(item.get("player"), Mapping) else item
                name = player.get("name") or player.get("player_name") or player.get("display_name")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
    return list(dict.fromkeys(names))[:11]


def get_match_context(home: str, away: str, target_date: Any) -> Dict[str, Any]:
    """Return normalized Big Balls context for one exact fixture.

    Calls are budgeted. The function is safe to call from the normal tips path;
    after the configured match-detail budget it becomes a no-op.
    """
    global _DETAIL_CALLS
    if not enabled() or MAX_MATCH_DETAILS <= 0:
        return {}
    key = f"{str(target_date)[:10]}|{_norm(home)}|{_norm(away)}"
    if key in _MATCH_CACHE:
        return dict(_MATCH_CACHE[key])
    if _DETAIL_CALLS >= MAX_MATCH_DETAILS:
        return {}
    match = find_match(home, away, target_date)
    if not match:
        _MATCH_CACHE[key] = {}
        return {}
    match_id = str(match.get("id") or match.get("match_id") or "")
    if not match_id:
        _MATCH_CACHE[key] = {}
        return {}
    _DETAIL_CALLS += 1
    stats_payload = _get(f"/v1/stored/matches/{match_id}/stats") or {}
    lineups_payload = _get(f"/v1/stored/matches/{match_id}/lineups") or {}
    flat = _flatten_numeric(stats_payload)
    out: Dict[str, Any] = {
        "source": "bigballs",
        "match_id": match_id,
        "home": _team_name(match.get("home") or match.get("home_team")) or home,
        "away": _team_name(match.get("away") or match.get("away_team")) or away,
        "home_lineup": _lineup_names(lineups_payload, "home"),
        "away_lineup": _lineup_names(lineups_payload, "away"),
    }
    metric_map = {
        "xg_home": ("home_xg", "home_expected_goals", "xg_home"),
        "xg_away": ("away_xg", "away_expected_goals", "xg_away"),
        "shots_home": ("home_total_shots", "home_shots", "shots_home"),
        "shots_away": ("away_total_shots", "away_shots", "shots_away"),
        "sot_home": ("home_shots_on_target", "home_sot", "shots_on_target_home"),
        "sot_away": ("away_shots_on_target", "away_sot", "shots_on_target_away"),
        "possession_home": ("home_possession", "possession_home"),
        "possession_away": ("away_possession", "possession_away"),
        "corners_home": ("home_corners", "home_won_corners", "corners_home"),
        "corners_away": ("away_corners", "away_won_corners", "corners_away"),
        "fouls_home": ("home_fouls_committed", "home_fouls", "fouls_home"),
        "fouls_away": ("away_fouls_committed", "away_fouls", "fouls_away"),
    }
    for dest, aliases in metric_map.items():
        value = _first_metric(flat, aliases)
        if value is not None:
            out[dest] = value
    # Do not surface empty shells as a successful feature source.
    if not any(k in out for k in metric_map) and not out["home_lineup"] and not out["away_lineup"]:
        out = {}
    _MATCH_CACHE[key] = dict(out)
    return out


def player_season_stats(player_name: str) -> Dict[str, Any]:
    """Optional season-level player stat fallback; never used as a bookmaker line."""
    if not enabled() or not player_name:
        return {}
    search = _get("/v1/players", {"sport": "football", "name": player_name, "limit": 10})
    rows = _rows(search)
    target = _norm(player_name)
    player = next((r for r in rows if _norm(r.get("name") or r.get("player_name")) == target), rows[0] if rows else None)
    if not player:
        return {}
    pid = player.get("id")
    if not pid:
        return {}
    payload = _get(f"/v1/players/{pid}/stats", {"sport": "football"})
    if not payload:
        return {}
    flat = _flatten_numeric(payload)
    aliases = {
        "shots": ("shots", "total_shots"),
        "sot": ("shots_on_target", "sot"),
        "tackles": ("tackles", "total_tackles"),
        "fouls_committed": ("fouls_committed", "fouls"),
        "fouls_won": ("fouls_drawn", "fouls_won"),
        "cards": ("yellow_cards", "cards"),
        "saves": ("saves", "goalkeeper_saves"),
        "assists": ("assists",),
        "goals": ("goals",),
        "passes": ("passes", "total_passes"),
        "minutes": ("minutes", "minutes_played"),
        "xg": ("xg", "expected_goals"),
        "xa": ("xa", "expected_assists"),
    }
    out: Dict[str, Any] = {"source": "bigballs", "player": player_name, "player_id": str(pid)}
    for dest, names in aliases.items():
        value = _first_metric(flat, names)
        if value is not None:
            out[dest] = value
    return out if len(out) > 3 else {}


__all__ = [
    "enabled", "matches_for_date", "find_match", "get_match_context", "player_season_stats",
]
