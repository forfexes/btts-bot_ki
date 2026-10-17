"""Read licensed football.csv-style historical results for offline H2H research.

No network calls, bookmaker quotes, Telegram output or production activation.
Source datasets: https://github.com/footballcsv (verify dataset license).
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
import re
from typing import Iterable

_SCORE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")


def parse_results(path: str | Path) -> list[dict]:
    """Parse a football.csv export; ignore unknown score formats and missing teams."""
    matches = []
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            home = (row.get("Team 1") or row.get("Team1") or row.get("HomeTeam") or "").strip()
            away = (row.get("Team 2") or row.get("Team2") or row.get("AwayTeam") or "").strip()
            score = _SCORE.fullmatch(row.get("FT") or row.get("FTR") or "")
            if not home or not away or home.casefold() == away.casefold() or not score:
                continue
            matches.append({"home": home, "away": away, "home_goals": int(score[1]),
                            "away_goals": int(score[2]), "date": row.get("Date") or ""})
    return matches


def h2h(matches: Iterable[dict], team_a: str, team_b: str) -> dict:
    """Aggregate only explicitly matched historical fixtures, never inferred odds."""
    a, b = team_a.strip().casefold(), team_b.strip().casefold()
    if not a or not b or a == b:
        raise ValueError("Two different team names required")
    counts = Counter()
    for m in matches:
        home, away = m["home"].strip().casefold(), m["away"].strip().casefold()
        if {home, away} != {a, b}:
            continue
        gh, ga = m["home_goals"], m["away_goals"]
        counts["games"] += 1
        counts["btts"] += int(gh > 0 and ga > 0)
        counts["over25"] += int(gh + ga > 2)
        counts["a_wins"] += int((gh > ga and home == a) or (ga > gh and away == a))
        counts["b_wins"] += int((gh > ga and home == b) or (ga > gh and away == b))
        counts["draws"] += int(gh == ga)
    return {k: counts[k] for k in ("games", "a_wins", "b_wins", "draws", "btts", "over25")}
