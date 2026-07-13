#!/usr/bin/env python3
"""
NETRATTLER Builder Engine
=========================

Pure, testable builder selection layer for football player props.

It creates data-driven builder families from a normalized prop pool:
- Multi-player shot ladders (1+ / 2+ / 3+)
- Underdog shot ladders when match/team context is available
- Shots-on-target trios
- Fouls and tackles ladders
- Attacking mixed builders (shots, SOT, score/assist)
- Corner fusion builders (player props + one corner leg)
- Balanced cross-match builders

The module does not scrape. It consumes rows already gathered by btts_bot.py.
It never sends on import and can be unit-tested offline.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


SOURCE_WEIGHT = {
    "supabasestatsadaptive": 1.00,
    "supabasematchstats": 0.98,
    "supabasestats": 0.96,
    "statz.ai": 0.92,
    "scoutingstats": 0.90,
    "pinnacle": 0.88,
    "supabasedb:pinnacle": 0.86,
    "statsbomb": 0.84,
    "fotmob": 0.78,
    "oddspedia": 0.74,
    "supabasedb": 0.72,
}

CATEGORY_ICON = {
    "shots": "💥",
    "sot": "🎯",
    "fouls": "👊",
    "fouls_won": "🧲",
    "tackles": "🛡️",
    "yellow_cards": "🟨",
    "score": "⚽",
    "assist": "🅰️",
    "score_assist": "⚽🅰️",
    "team_corners": "🔵",
    "corners": "🔵",
    "team_shots": "📈",
    "team_cards": "🃏",
    "btts": "⚽",
    "over_goals": "🎯",
}

PLAYER_CATEGORIES = {
    "shots", "sot", "fouls", "fouls_won", "tackles",
    "yellow_cards", "score", "assist", "score_assist",
}

TEAM_CATEGORIES = {"team_corners", "corners", "team_shots", "team_cards", "btts", "over_goals"}


@dataclass(frozen=True)
class PropLeg:
    player: str
    team: str
    match: str
    league: str
    market: str
    category: str
    line: float
    odds: float
    probability: float
    source: str
    kickoff: str = ""
    hit_rate: float = 0.0
    games: int = 0
    quality: float = 0.0
    estimated: bool = False

    def key(self) -> Tuple[str, str, str, float]:
        return (norm(self.player), norm(self.match), self.category, round(self.line, 2))


@dataclass
class BuilderPick:
    builder_id: str
    style: str
    variant: str
    legs: List[PropLeg]
    total_odds: float
    stake: float
    estimated_odds: bool
    match_date: str
    market_group: str = "builder"

    @property
    def leg_count(self) -> int:
        return len(self.legs)

    def to_row(self) -> Dict[str, Any]:
        return {
            "builder_id": self.builder_id,
            "tip_id": self.builder_id,
            "style": self.style,
            "variant": self.variant,
            "market_group": self.market_group,
            "match_date": self.match_date,
            "status": "pending",
            "stake": self.stake,
            "total_odds": self.total_odds,
            "estimated_odds": self.estimated_odds,
            "leg_count": self.leg_count,
            "legs": [asdict(x) for x in self.legs],
            "source": "NETRATTLER_BUILDER_ENGINE",
        }


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def market_line(market: str, fallback: float = 1.0) -> float:
    text = str(market or "")
    plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", text)
    if plus:
        return as_float(plus.group(1), fallback)
    over = re.search(r"over\s*(\d+(?:\.\d+)?)", text, re.I)
    if over:
        # An over 1.5 market means 2+ occurrences.
        return math.floor(as_float(over.group(1), fallback)) + 1
    return fallback


def probability_from_row(row: Dict[str, Any]) -> float:
    candidates = [
        as_float(row.get("model_prob")),
        as_float(row.get("probability")),
        as_float(row.get("prob")),
        as_float(row.get("hit_rate")),
    ]
    normalized = []
    for value in candidates:
        if value <= 0:
            continue
        normalized.append(value / 100.0 if value > 1 else value)
    if normalized:
        return max(0.05, min(0.95, max(normalized)))
    odds = as_float(row.get("odds"))
    if odds > 1:
        return max(0.05, min(0.90, 1.0 / odds))
    return 0.50


def source_weight(source: str) -> float:
    source_norm = norm(source).replace(" ", "")
    for key, weight in SOURCE_WEIGHT.items():
        if key.replace(" ", "") in source_norm:
            return weight
    return 0.68


def quality_score(row: Dict[str, Any]) -> float:
    probability = probability_from_row(row)
    hit_rate = as_float(row.get("hit_rate"))
    hit_rate = hit_rate / 100.0 if hit_rate > 1 else hit_rate
    games = as_int(row.get("games") or row.get("sb_games"))
    sample = min(1.0, math.log(games + 1) / math.log(21)) if games > 0 else 0.15
    real_odds = 1.0 if str(row.get("source", "")).lower().startswith("pinnacle") else 0.55
    return round(
        probability * 0.48
        + max(hit_rate, probability) * 0.18
        + source_weight(str(row.get("source", ""))) * 0.18
        + sample * 0.10
        + real_odds * 0.06,
        4,
    )


def normalize_prop(row: Dict[str, Any]) -> Optional[PropLeg]:
    player = str(row.get("player") or row.get("selection") or "").strip()
    match = str(row.get("match") or row.get("fixture") or "").strip()
    market = str(row.get("market") or row.get("type") or "").strip()
    category = str(row.get("category") or "").strip().lower()
    if not player or not match or not market or not category:
        return None
    if category not in PLAYER_CATEGORIES | TEAM_CATEGORIES:
        return None
    line = as_float(row.get("line"), market_line(market, 1.0))
    odds = as_float(row.get("odds") or row.get("pinnacle_odds") or row.get("fair_odds"))
    probability = probability_from_row(row)
    if odds <= 1:
        odds = round(max(1.05, min(10.0, 1.0 / max(0.10, probability))), 2)
        estimated = True
    else:
        estimated = not str(row.get("source", "")).lower().startswith("pinnacle")
    return PropLeg(
        player=player[:100],
        team=str(row.get("team") or "")[:100],
        match=match[:180],
        league=str(row.get("league") or "")[:100],
        market=market[:160],
        category=category,
        line=line,
        odds=round(odds, 2),
        probability=round(probability, 4),
        source=str(row.get("source") or "unknown")[:80],
        kickoff=str(row.get("ko") or row.get("kickoff") or row.get("kickoff_at") or "")[:40],
        hit_rate=as_float(row.get("hit_rate")),
        games=as_int(row.get("games") or row.get("sb_games")),
        quality=quality_score(row),
        estimated=estimated,
    )


def deduplicate_props(rows: Iterable[Dict[str, Any]]) -> List[PropLeg]:
    best: Dict[Tuple[str, str, str, float], PropLeg] = {}
    for row in rows:
        leg = normalize_prop(row)
        if not leg:
            continue
        old = best.get(leg.key())
        if old is None or (leg.quality, not leg.estimated, leg.odds) > (old.quality, not old.estimated, old.odds):
            best[leg.key()] = leg
    return sorted(best.values(), key=lambda x: (x.quality, x.probability), reverse=True)


def parse_match(match: str) -> Tuple[str, str]:
    for separator in (" vs ", " v ", " - "):
        if separator in str(match):
            home, away = str(match).split(separator, 1)
            return home.strip(), away.strip()
    return "", ""


def _context_for_match(match: str, contexts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    target = norm(match)
    for row in contexts or []:
        candidate = norm(row.get("match") or row.get("fixture") or "")
        if candidate == target or (candidate and (candidate in target or target in candidate)):
            return row
    return {}


def underdog_team(match: str, contexts: Sequence[Dict[str, Any]]) -> str:
    context = _context_for_match(match, contexts)
    explicit = str(context.get("underdog_team") or context.get("underdog") or "").strip()
    if explicit:
        return explicit
    home, away = parse_match(match)
    home_odds = as_float(context.get("home_odds") or context.get("odds_home") or context.get("home_win_odds") or context.get("homeOdds"))
    away_odds = as_float(context.get("away_odds") or context.get("odds_away") or context.get("away_win_odds") or context.get("awayOdds"))
    if home and away and home_odds > 1 and away_odds > 1:
        if abs(home_odds - away_odds) >= 0.25:
            return home if home_odds > away_odds else away
    home_prob = as_float(context.get("home_prob") or context.get("home_probability") or context.get("home_win_probability") or context.get("homeWinProb"))
    away_prob = as_float(context.get("away_prob") or context.get("away_probability") or context.get("away_win_probability") or context.get("awayWinProb"))
    if home_prob > 1: home_prob /= 100.0
    if away_prob > 1: away_prob /= 100.0
    if home and away and home_prob > 0 and away_prob > 0 and abs(home_prob-away_prob) >= 0.08:
        return home if home_prob < away_prob else away
    favorite = str(context.get("favorite_team") or context.get("favorite") or "").strip()
    if favorite and home and away:
        return away if norm(favorite) == norm(home) else home
    return ""


def team_matches(leg_team: str, desired_team: str) -> bool:
    a, b = norm(leg_team), norm(desired_team)
    return bool(a and b and (a == b or a in b or b in a))


def total_odds(legs: Sequence[PropLeg]) -> float:
    result = 1.0
    for leg in legs:
        result *= max(1.01, leg.odds)
    return round(result, 2)


def builder_signature(style: str, legs: Sequence[PropLeg], match_date: str) -> str:
    tokens = sorted(f"{norm(x.match)}|{norm(x.player)}|{x.category}|{x.line}" for x in legs)
    raw = f"{match_date}|{style}|" + "||".join(tokens)
    return "nb_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def valid_builder(legs: Sequence[PropLeg], min_legs: int = 2, max_legs: int = 6) -> bool:
    if not (min_legs <= len(legs) <= max_legs):
        return False
    keys = [x.key() for x in legs]
    if len(keys) != len(set(keys)):
        return False
    # Prevent the low-probability same-player scorer + card stack.
    by_player: Dict[str, set] = {}
    for leg in legs:
        by_player.setdefault(norm(leg.player), set()).add(leg.category)
    for cats in by_player.values():
        if cats & {"score", "score_assist"} and "yellow_cards" in cats:
            return False
    return True


def _best_distinct_players(legs: Sequence[PropLeg], count: int = 3) -> List[PropLeg]:
    out: List[PropLeg] = []
    used = set()
    for leg in sorted(legs, key=lambda x: (x.quality, x.probability), reverse=True):
        key = norm(leg.player)
        if key in used:
            continue
        out.append(leg)
        used.add(key)
        if len(out) >= count:
            break
    return out


def _derive_lower_line(leg: PropLeg, line: int, market_name: str, probability_floor: float) -> PropLeg:
    if leg.line <= line and int(round(leg.line)) == line:
        return leg
    # Conservative derived line from a higher verified line. This is marked estimated.
    probability = max(probability_floor, min(0.90, leg.probability + 0.12 * max(0, leg.line - line)))
    odds = round(max(1.08, min(2.20, 1.0 / probability)), 2)
    return PropLeg(
        player=leg.player,
        team=leg.team,
        match=leg.match,
        league=leg.league,
        market=market_name,
        category=leg.category,
        line=float(line),
        odds=odds,
        probability=round(probability, 4),
        source=leg.source + ":derived",
        kickoff=leg.kickoff,
        hit_rate=leg.hit_rate,
        games=leg.games,
        quality=round(min(1.0, leg.quality + 0.04), 4),
        estimated=True,
    )


def _make_builder(style: str, variant: str, legs: List[PropLeg], match_date: str, stake: float = 0.5) -> Optional[BuilderPick]:
    if not valid_builder(legs):
        return None
    odds = total_odds(legs)
    min_odds = as_float(os.getenv("NETRATTLER_BUILDER_MIN_ODDS", "1.75"), 1.75)
    max_odds = as_float(os.getenv("NETRATTLER_BUILDER_MAX_ODDS", "80"), 80.0)
    if odds < min_odds or odds > max_odds:
        return None
    return BuilderPick(
        builder_id=builder_signature(style + variant, legs, match_date),
        style=style,
        variant=variant,
        legs=legs,
        total_odds=odds,
        stake=stake,
        estimated_odds=any(x.estimated for x in legs),
        match_date=match_date,
    )


def _shot_ladders(props: Sequence[PropLeg], contexts: Sequence[Dict[str, Any]], match_date: str) -> List[BuilderPick]:
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        if leg.category == "shots":
            by_match.setdefault(leg.match, []).append(leg)

    for match, shot_props in by_match.items():
        dog = underdog_team(match, contexts)
        candidate_pool = [x for x in shot_props if not dog or team_matches(x.team, dog)]
        if len({norm(x.player) for x in candidate_pool}) < 3:
            candidate_pool = shot_props
        base = _best_distinct_players(candidate_pool, 3)
        if len(base) < 3:
            continue
        style = "UNDERDOG SHOT LADDER" if dog and all(team_matches(x.team, dog) for x in base) else "SHOT LADDER"

        safe = [_derive_lower_line(x, 1, "1+ Shot", 0.74) for x in base]
        value = [_derive_lower_line(x, 2, "2+ Shots", 0.58) for x in base if x.line >= 2 or x.probability >= 0.56]
        aggressive = [_derive_lower_line(x, 3, "3+ Shots", 0.42) for x in base if x.line >= 3 or x.probability >= 0.50]

        for variant, legs in (("SAFE 1+", safe), ("VALUE 2+", value), ("AGGRESSIVE 3+", aggressive)):
            if len(legs) == 3:
                pick = _make_builder(style, variant, legs, match_date, 0.75 if variant.startswith("SAFE") else 0.5)
                if pick:
                    builders.append(pick)
    return builders


def _category_trios(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    builders: List[BuilderPick] = []
    styles = {
        "sot": ("SOT TRIO", 1, "1+ Shot on Target", 0.56),
        "fouls": ("FOUL PRESS", 1, "1+ Foul Committed", 0.64),
        "fouls_won": ("FOUL MAGNET", 1, "1+ Foul Won", 0.62),
        "tackles": ("TACKLE WALL", 1, "1+ Tackle", 0.65),
    }
    by_match_cat: Dict[Tuple[str, str], List[PropLeg]] = {}
    for leg in props:
        if leg.category in styles:
            by_match_cat.setdefault((leg.match, leg.category), []).append(leg)

    for (match, category), candidates in by_match_cat.items():
        style, safe_line, market_name, floor = styles[category]
        base = _best_distinct_players(candidates, 3)
        if len(base) < 3:
            continue
        safe = [_derive_lower_line(x, safe_line, market_name, floor) for x in base]
        pick = _make_builder(style, "SAFE", safe, match_date, 0.5)
        if pick:
            builders.append(pick)

        if category in {"fouls", "tackles"}:
            market = "2+ Fouls Committed" if category == "fouls" else "2+ Tackles"
            value = [_derive_lower_line(x, 2, market, 0.48) for x in base if x.line >= 2 or x.probability >= 0.50]
            if len(value) == 3:
                pick = _make_builder(style, "VALUE 2+", value, match_date, 0.5)
                if pick:
                    builders.append(pick)
    return builders


def _mixed_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        # One strong leg per category, distinct players where possible.
        ordered_categories = ["shots", "sot", "fouls", "tackles", "score_assist", "yellow_cards"]
        selected: List[PropLeg] = []
        used_players = set()
        for category in ordered_categories:
            pool = sorted((x for x in candidates if x.category == category), key=lambda x: x.quality, reverse=True)
            for leg in pool:
                player_key = norm(leg.player)
                if player_key in used_players and category not in {"fouls", "tackles"}:
                    continue
                selected.append(leg)
                used_players.add(player_key)
                break
            if len(selected) >= 4:
                break
        if len(selected) >= 3:
            pick = _make_builder("MIXED EDGE", "PLAYER MIX", selected[:4], match_date, 0.5)
            if pick:
                builders.append(pick)

        # Corner fusion: 2-3 player legs + exactly one team/corner leg.
        corner = next(iter(sorted((x for x in candidates if x.category in {"team_corners", "corners"}), key=lambda x: x.quality, reverse=True)), None)
        player_legs = _best_distinct_players([x for x in candidates if x.category in {"shots", "sot", "fouls", "tackles"}], 3)
        if corner and len(player_legs) >= 2:
            fusion_legs = player_legs[:3] + [corner]
            pick = _make_builder("CORNER FUSION", "PLAYER + CORNERS", fusion_legs, match_date, 0.5)
            if pick:
                builders.append(pick)
    return builders


def _cross_match_builder(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    best_by_match: Dict[str, PropLeg] = {}
    for leg in sorted(props, key=lambda x: (x.quality, x.probability), reverse=True):
        if leg.category not in {"shots", "sot", "fouls", "tackles", "score_assist"}:
            continue
        if leg.match not in best_by_match:
            best_by_match[leg.match] = leg
    legs = list(best_by_match.values())[:5]
    builders = []
    for size in (3, 4, 5):
        if len(legs) >= size:
            pick = _make_builder("CROSS MATCH", f"{size} LEGS", legs[:size], match_date, 0.5)
            if pick:
                builders.append(pick)
    return builders


def build_builder_picks(
    raw_props: Sequence[Dict[str, Any]],
    match_contexts: Optional[Sequence[Dict[str, Any]]] = None,
    match_date: Optional[str] = None,
    max_builders: Optional[int] = None,
) -> List[BuilderPick]:
    props = deduplicate_props(raw_props)
    run_date = match_date or date.today().isoformat()
    max_count = max_builders or as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "14"), 14)

    candidates: List[BuilderPick] = []
    candidates.extend(_shot_ladders(props, match_contexts or [], run_date))
    candidates.extend(_category_trios(props, run_date))
    candidates.extend(_mixed_builders(props, run_date))
    candidates.extend(_cross_match_builder(props, run_date))

    # Stable dedup, then rank safe/high-quality builders first.
    seen = set()
    unique: List[BuilderPick] = []
    for pick in candidates:
        if pick.builder_id in seen:
            continue
        seen.add(pick.builder_id)
        unique.append(pick)

    def rank(pick: BuilderPick) -> Tuple[float, float, float]:
        avg_quality = sum(x.quality for x in pick.legs) / max(1, len(pick.legs))
        avg_prob = sum(x.probability for x in pick.legs) / max(1, len(pick.legs))
        # Keep enormous jackpot odds below safer builders.
        odds_penalty = max(0.0, math.log(max(1.0, pick.total_odds / 12.0))) * 0.08
        return (avg_quality - odds_penalty, avg_prob, -pick.total_odds)

    unique.sort(key=rank, reverse=True)
    return unique[:max_count]


def format_builder_message(pick: BuilderPick) -> str:
    sep = "━" * 18
    estimate = " · Modell/Fair" if pick.estimated_odds else ""
    lines = [
        f"🏗️ <b>NETRATTLER {pick.style}</b>",
        f"<b>{pick.variant}</b>",
        sep,
    ]
    same_match = len({x.match for x in pick.legs}) == 1
    if same_match and pick.legs:
        lines.append(f"⚽ <b>{pick.legs[0].match}</b>")
    for index, leg in enumerate(pick.legs, 1):
        icon = CATEGORY_ICON.get(leg.category, "🎯")
        match_suffix = "" if same_match else f" · {leg.match}"
        source_note = " ~" if leg.estimated else ""
        lines.append(f"{index}. {icon} <b>{leg.player}</b>: {leg.market}{source_note}{match_suffix}")
    lines.extend([
        sep,
        f"💰 Gesamt-Quote: <b>{pick.total_odds:.2f}</b>{estimate}",
        f"🔥 Einsatz: <b>{pick.stake:.2f} Units</b>",
        f"🧠 Daten: {', '.join(dict.fromkeys(x.source.split(':')[0] for x in pick.legs))}",
    ])
    return "\n".join(lines)


def _supabase_headers(key: str, prefer: str = "resolution=merge-duplicates,return=minimal") -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def persist_builder_pick(pick: BuilderPick, supabase_url: str, supabase_key: str) -> Optional[bool]:
    """Return True for a newly stored pick, False if it already exists, None on DB failure/offline."""
    if not supabase_url or not supabase_key:
        return None
    base = supabase_url.rstrip('/')
    try:
        existing = requests.get(
            f"{base}/rest/v1/netrattler_builder_picks",
            headers=_supabase_headers(supabase_key, "return=representation"),
            params={"builder_id": f"eq.{pick.builder_id}", "select": "builder_id", "limit": "1"},
            timeout=8,
        )
        if existing.ok and existing.json():
            return False
        response = requests.post(
            f"{base}/rest/v1/netrattler_builder_picks",
            headers=_supabase_headers(supabase_key),
            params={"on_conflict": "builder_id"},
            data=json.dumps(pick.to_row(), ensure_ascii=False, default=str),
            timeout=12,
        )
        return True if response.status_code in (200, 201, 204) else None
    except Exception:
        return None


def run_builder_engine(
    raw_props: Sequence[Dict[str, Any]],
    send_message: Callable[[str], Any],
    match_contexts: Optional[Sequence[Dict[str, Any]]] = None,
    match_date: Optional[str] = None,
    supabase_url: str = "",
    supabase_key: str = "",
    logger: Optional[Callable[[str], Any]] = None,
) -> Tuple[int, List[BuilderPick]]:
    picks = build_builder_picks(raw_props, match_contexts, match_date)
    sent = 0
    for pick in picks:
        persisted = persist_builder_pick(pick, supabase_url, supabase_key)
        if persisted is False:
            if logger:
                logger(f"MASTER BUILDER duplicate skipped: {pick.builder_id}")
            continue
        try:
            send_message(format_builder_message(pick))
            sent += 1
            if logger:
                logger(f"MASTER BUILDER {pick.style} {pick.variant}: {pick.leg_count}L @ {pick.total_odds:.2f} | DB={persisted}")
        except Exception as exc:
            if logger:
                logger(f"MASTER BUILDER send failed: {exc}")
    return sent, picks


__all__ = [
    "PropLeg",
    "BuilderPick",
    "build_builder_picks",
    "format_builder_message",
    "persist_builder_pick",
    "run_builder_engine",
    "market_line",
    "quality_score",
    "underdog_team",
]
