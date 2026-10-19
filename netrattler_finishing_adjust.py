"""NETRATTLER finishing-radar adjustment for anytime-scorer tips.

analyze_scorer_tips() in btts_bot.py estimates P(scores) from raw goals/game
only: prob = 1 - exp(-goals_per_game). The finishing_radar.py backtest
(14'388 real player_game_log rows) showed this naive model is badly
miscalibrated at the extremes:
  - players who recently scored well above their xG: naive model says
    34.6% real rate is only 28.4% (regression to the mean, pure variance)
  - players well below their xG: naive model says 15.9%, real rate is 29.7%

This module fetches each player's last-WINDOW xG/goals window from
player_game_log (already routed to the V2 archive project by
netrattler_table_router.py — no extra plumbing needed) and blends goals
with xG the same way finishing_radar.py does, pulling the published
probability toward the backtest-validated reality. If no window data is
found for a player (most props, since this needs per-player history),
the raw probability is returned unchanged — this only ever corrects an
existing estimate, never fabricates a new one, and never raises a
probability beyond what the blended model computes.
"""
import math
import re
import unicodedata
from typing import Dict, Optional

WINDOW = 8
K = 6.0
ALPHA = 0.25
MIN_PRIOR = 5

_cache: Dict[str, dict] = {}
_calibration: Optional[dict] = None
_loaded = False


def _norm(name: str) -> str:
    value = unicodedata.normalize("NFKD", str(name or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value)


def _window_stats(rows):
    m = sum(r["minutes"] for r in rows)
    return {"g": sum(r["goals"] for r in rows), "x": sum(r["xg"] for r in rows),
            "m": m, "n": len(rows)}


def load(requests_mod, base_url: str, key: str, timeout: float = 60.0) -> None:
    """Fetch and cache the per-player xG/goals window. Safe to call once per
    bot run; any failure leaves the cache empty so callers fall back to the
    raw probability untouched."""
    global _calibration, _loaded
    if _loaded:
        return
    _loaded = True
    if not base_url or not key:
        return
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "select": "player_key,player_name,team,match_date,minutes,goals,xg",
            "xg": "not.is.null", "minutes": "not.is.null", "goals": "not.is.null",
            "match_date": "not.is.null", "order": "match_date.asc,event_id.asc",
        }
        rows, start, page = [], 0, 1000
        while True:
            h = dict(headers, **{"Range-Unit": "items", "Range": f"{start}-{start + page - 1}"})
            r = requests_mod.get(f"{base_url.rstrip('/')}/rest/v1/player_game_log",
                                  params=params, headers=h, timeout=timeout)
            r.raise_for_status()
            batch = r.json()
            rows.extend(batch)
            if len(batch) < page:
                break
            start += page
            if start > 400000:  # safety cap
                break
        by_player: Dict[str, list] = {}
        for r in rows:
            try:
                r["minutes"] = float(r["minutes"]); r["goals"] = float(r["goals"]); r["xg"] = float(r["xg"])
            except (TypeError, ValueError):
                continue
            key_norm = _norm(r.get("player_name") or r.get("player_key") or "")
            if key_norm:
                by_player.setdefault(key_norm, []).append(r)
        sg = sum(r["goals"] for lst in by_player.values() for r in lst if r["minutes"] >= 45)
        sx = sum(r["xg"] for lst in by_player.values() for r in lst if r["minutes"] >= 45)
        sm = sum(r["minutes"] for lst in by_player.values() for r in lst if r["minutes"] >= 45)
        if sm <= 0 or sx <= 0:
            return
        _calibration = {"lam_g": sg / sm * 90.0, "lam_x": sx / sm * 90.0, "ratio": sg / sx}
        for k, lst in by_player.items():
            lst.sort(key=lambda r: str(r["match_date"]))
            window = lst[-WINDOW:]
            if len(window) >= MIN_PRIOR:
                _cache[k] = _window_stats(window)
    except Exception:
        # Any network/parsing failure must never block scorer tips.
        _calibration = None


def adjusted_prob_pct(player_name: str, raw_prob_pct: float) -> float:
    """Returns a finishing-radar-adjusted probability (0-100) for this
    player, or raw_prob_pct unchanged if no window data / calibration is
    available. Never raises the probability above what the blended model
    computes, and never touches players with no recent xG history."""
    if not _calibration:
        return raw_prob_pct
    ws = _cache.get(_norm(player_name))
    if not ws or ws["m"] <= 0:
        return raw_prob_pct
    cal = _calibration
    matches = ws["m"] / 90.0
    rg = (ws["g"] + K * cal["lam_g"]) / (matches + K)
    rx = (ws["x"] + K * cal["lam_x"]) / (matches + K) * cal["ratio"]
    rate = ALPHA * rg + (1.0 - ALPHA) * rx
    avgm = min(ws["m"] / ws["n"], 90.0) / 90.0
    mix = (1.0 - math.exp(-rate * avgm)) * 100.0
    return round(mix, 1)


def reset() -> None:
    """Test helper: clears the module cache so load() runs again."""
    global _calibration, _loaded
    _cache.clear()
    _calibration = None
    _loaded = False
