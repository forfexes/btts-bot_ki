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
    "tackles_committed": "🛡️",
    "tackles_received": "🎯🛡️",
    "yellow_cards": "🟨",
    "sot_outside_box": "🎯",
    "shots_outside_box": "💥",
    "first_scorer": "🥇⚽",
    "last_scorer": "🏁⚽",
    "result": "🏆",
    "score": "⚽",
    "assist": "🅰️",
    "score_assist": "⚽🅰️",
    "team_corners": "🔵",
    "corners": "🔵",
    "match_corners": "🔵",
    "team_shots": "📈",
    "match_sot": "🎯",
    "team_cards": "🟨",
    "match_goals": "⚽",
    "btts": "⚽",
    "over_goals": "🎯",
    "offsides": "🚩",
}

PLAYER_CATEGORIES = {
    "shots", "sot", "sot_outside_box", "shots_outside_box",
    "fouls", "fouls_won", "tackles", "tackles_committed",
    "tackles_received", "yellow_cards", "score", "first_scorer",
    "last_scorer", "assist", "score_assist", "result", "offsides",
}

TEAM_CATEGORIES = {
    "team_corners", "corners", "match_corners",
    "team_shots", "match_sot", "match_goals",
    "team_cards", "btts", "btts_ht", "over_goals", "match_goals",
    "half_goals_1st", "half_goals_2nd",
}


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
    category = {
        "booked": "yellow_cards",
        "cards": "yellow_cards",
        "fouls_committed": "fouls",
        "fouls_drawn": "fouls_won",
        "tackles_made": "tackles_committed",
        "tackles_won": "tackles_committed",
        "tackled": "tackles_received",
    }.get(category, category)
    if not player or not match or not market or not category:
        return None
    if category not in PLAYER_CATEGORIES | TEAM_CATEGORIES:
        return None
    line = as_float(row.get("line"), market_line(market, 1.0))
    odds = as_float(row.get("odds") or row.get("pinnacle_odds") or row.get("fair_odds"))
    probability = probability_from_row(row)
    source_text = str(row.get("source") or "").lower()
    explicit_estimated = str(row.get("estimated") or "").lower() in {"1", "true", "yes", "on"}
    bookmaker_tokens = (
        "pinnacle", "bet365", "betfair", "oddsportal", "oddsharvester",
        "the odds api", "odds api", "odds_api", "oddsapi", "oddspapi",
        "kambi", "unibet", "1xbet", "melbet", "oddspedia", "footymetrics",
        "bookmaker", "sportsbook",
    )
    observed_bookmaker = odds > 1 and any(token in source_text for token in bookmaker_tokens)
    if odds <= 1:
        odds = round(max(1.05, min(10.0, 1.0 / max(0.10, probability))), 2)
        estimated = True
    else:
        estimated = explicit_estimated or not observed_bookmaker
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



def _scale_builder_stake(total_odds: float, requested: float = 0.5) -> float:
    try:
        o = float(total_odds or 0)
    except Exception:
        o = 0.0
    if o >= 100:
        return min(requested, 0.05)
    if o >= 50:
        return min(requested, 0.10)
    if o >= 20:
        return min(requested, 0.15)
    if o >= 8:
        return min(requested, 0.25)
    if o >= 3.5:
        return min(requested, 0.35)
    return requested

def _make_builder(style: str, variant: str, legs: List[PropLeg], match_date: str, stake: float = 0.5) -> Optional[BuilderPick]:
    if not valid_builder(legs):
        return None
    odds = total_odds(legs)
    min_odds = as_float(os.getenv("NETRATTLER_BUILDER_MIN_ODDS", "1.75"), 1.75)
    max_odds = as_float(os.getenv("NETRATTLER_BUILDER_MAX_ODDS", "150"), 150.0)
    if odds < min_odds or odds > max_odds:
        return None
    # Einsatz automatisch nach Risikostufe. Explizit kleinere Stakes bleiben erhalten.
    auto_stake = 0.75 if odds <= 3.5 else 0.50 if odds <= 10 else 0.25 if odds <= 25 else 0.10
    stake = min(stake, auto_stake) if stake else auto_stake
    return BuilderPick(
        builder_id=builder_signature(style + variant, legs, match_date),
        style=style,
        variant=variant,
        legs=legs,
        total_odds=odds,
        stake=_scale_builder_stake(odds, stake),
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
    """
    Same-Match Ladders als PAIR oder TRIO.
    Zwei reale Legs reichen bereits; drei werden bevorzugt.
    """
    builders: List[BuilderPick] = []
    styles = {
        "sot": ("SOT LADDER", 1, "1+ Shot on Target", 0.56),
        "sot_outside_box": ("OUTSIDE BOX SOT", 1, "1+ SOT Outside the Box", 0.30),
        "fouls": ("FOUL PRESS", 1, "1+ Foul Committed", 0.64),
        "fouls_won": ("FOUL MAGNET", 1, "1+ Foul Won", 0.62),
        "tackles": ("TACKLES COMMITTED", 1, "1+ Tackle Committed", 0.65),
        "tackles_committed": ("TACKLES COMMITTED", 1, "1+ Tackle Committed", 0.65),
        "tackles_received": ("TACKLES RECEIVED", 1, "1+ Tackle Received", 0.62),
        "yellow_cards": ("BOOKING LADDER", 1, "Player to be Booked", 0.28),
        "shots": ("SHOT LADDER", 1, "1+ Shot", 0.70),
    }
    by_match_category: Dict[Tuple[str, str], List[PropLeg]] = {}
    for leg in props:
        if leg.category in styles:
            by_match_category.setdefault((leg.match, leg.category), []).append(leg)

    ladder_markets = {
        "fouls": ("2+ Fouls Committed", "3+ Fouls Committed"),
        "fouls_won": ("2+ Fouls Won", "3+ Fouls Won"),
        "tackles": ("2+ Tackles Committed", "3+ Tackles Committed"),
        "tackles_committed": ("2+ Tackles Committed", "3+ Tackles Committed"),
        "tackles_received": ("2+ Tackles Received", "3+ Tackles Received"),
        "yellow_cards": ("Player to be Booked", "Player to be Booked"),
        "sot": ("1+ Shot on Target", "2+ Shots on Target"),
        "sot_outside_box": ("1+ SOT Outside the Box", "1+ SOT Outside the Box"),
        "shots": ("2+ Shots", "3+ Shots"),
    }

    for (match, category), candidates in by_match_category.items():
        style, safe_line, safe_market, safe_floor = styles[category]
        base = _best_distinct_players(candidates, 3)
        if len(base) < 2:
            continue

        sizes = [2] if len(base) == 2 else [2, 3]
        for size in sizes:
            safe = [
                _derive_lower_line(x, safe_line, safe_market, safe_floor)
                for x in base[:size]
            ]
            pick = _make_builder(style, f"SAFE {size}L", safe, match_date, 0.75)
            if pick:
                builders.append(pick)

            value_market, high_market = ladder_markets[category]
            value_line = 1 if category in {"yellow_cards", "sot", "sot_outside_box"} else 2
            high_line = (
                1 if category in {"yellow_cards", "sot_outside_box"}
                else 2 if category == "sot"
                else 3
            )

            value = [
                _derive_lower_line(x, value_line, value_market, 0.44)
                for x in base[:size]
                if x.line >= value_line or x.probability >= 0.46
            ]
            if len(value) >= 2:
                pick = _make_builder(style, f"VALUE {len(value)}L", value, match_date, 0.5)
                if pick:
                    builders.append(pick)

            high = [
                _derive_lower_line(x, high_line, high_market, 0.25)
                for x in base[:size]
                if x.line >= high_line or x.probability >= 0.34
            ]
            if len(high) >= 2:
                pick = _make_builder(style, f"HIGH ODDS {len(high)}L", high, match_date, 0.1)
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
        ordered_categories = [
            "result", "score", "first_scorer", "shots", "sot",
            "fouls", "tackles_committed", "tackles_received",
            "team_cards", "yellow_cards", "score_assist"
        ]
        selected: List[PropLeg] = []
        used_players = set()
        for category in ordered_categories:
            pool = sorted((x for x in candidates if x.category == category), key=lambda x: x.quality, reverse=True)
            for leg in pool:
                player_key = norm(leg.player)
                if player_key in used_players and category not in {
                    "fouls", "tackles", "tackles_committed", "tackles_received"
                }:
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
        player_legs = _best_distinct_players([
            x for x in candidates if x.category in {
                "shots", "sot", "fouls", "fouls_won",
                "tackles", "tackles_committed", "tackles_received"
            }
        ], 3)
        if corner and len(player_legs) >= 2:
            fusion_legs = player_legs[:3] + [corner]
            pick = _make_builder("CORNER FUSION", "PLAYER + CORNERS", fusion_legs, match_date, 0.5)
            if pick:
                builders.append(pick)
    return builders




def _same_match_available_builders(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Baut aus jedem Match mit mindestens zwei echten Props einen kompakten
    Same-Match-Builder. Bevorzugt Marktvielfalt und echte Quoten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        if len(candidates) < 2:
            continue

        ordered = sorted(
            candidates,
            key=lambda x: (not x.estimated, x.quality, x.probability),
            reverse=True,
        )
        selected: List[PropLeg] = []
        used_keys = set()
        used_categories = set()

        # Erst Marktvielfalt.
        for leg in ordered:
            key = (norm(leg.player), leg.category)
            if key in used_keys:
                continue
            if leg.category in used_categories:
                continue
            if len(selected) >= 1 and not valid_builder(selected + [leg], min_legs=2):
                continue
            selected.append(leg)
            used_keys.add(key)
            used_categories.add(leg.category)
            if len(selected) >= 5:
                break

        # Danach bei Bedarf weitere Player Legs.
        if len(selected) < 2:
            for leg in ordered:
                key = (norm(leg.player), leg.category)
                if key in used_keys:
                    continue
                if len(selected) >= 1 and not valid_builder(selected + [leg], min_legs=2):
                    continue
                selected.append(leg)
                used_keys.add(key)
                if len(selected) >= 4:
                    break

        if len(selected) < 2:
            continue

        for size in range(2, min(5, len(selected)) + 1):
            legs = selected[:size]
            pick = _make_builder(
                "SAME MATCH AVAILABLE",
                f"{size} REAL LEGS",
                legs,
                match_date,
                0.5 if size <= 3 else 0.25,
            )
            if pick:
                builders.append(pick)

    return builders



def _same_game_narratives(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """JK/NATE-artige Same-Game-Builder mit einer klaren Match-Hypothese."""
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    templates = [
        ("FAVORITE SCRIPT", ["result", "score", "shots", "sot"], 3),
        ("INTENSITY SCRIPT", ["team_cards", "yellow_cards", "fouls", "tackles_committed", "tackles_received"], 4),
        ("ATTACK SCRIPT", ["score", "shots", "sot", "sot_outside_box", "assist"], 4),
        ("MIDFIELD BATTLE", ["fouls", "fouls_won", "tackles_committed", "tackles_received", "yellow_cards"], 4),
    ]

    for match, candidates in by_match.items():
        for style, categories, max_legs in templates:
            selected: List[PropLeg] = []
            used_players = set()
            for category in categories:
                pool = sorted(
                    (x for x in candidates if x.category == category),
                    key=lambda x: (x.quality, x.probability, not x.estimated),
                    reverse=True,
                )
                for leg in pool:
                    pkey = norm(leg.player)
                    if pkey in used_players and category not in {
                        "fouls", "fouls_won", "tackles_committed", "tackles_received"
                    }:
                        continue
                    selected.append(leg)
                    used_players.add(pkey)
                    break
                if len(selected) >= max_legs:
                    break
            if len(selected) >= 2:
                pick = _make_builder(
                    style,
                    f"SAME GAME {len(selected)}L",
                    selected,
                    match_date,
                    0.5 if len(selected) <= 3 else 0.25,
                )
                if pick:
                    builders.append(pick)
    return builders



def _cross_match_builder(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    best_by_match: Dict[str, PropLeg] = {}
    for leg in sorted(props, key=lambda x: (x.quality, x.probability), reverse=True):
        if leg.category not in {
            "shots", "sot", "fouls", "fouls_won", "tackles",
            "tackles_committed", "tackles_received", "score",
            "first_scorer", "score_assist"
        }:
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


def _team_correlation_builders(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Team Correlation Builder — wie Screenshot 4:
    BTTS HT + BTTS 2HT + Over 2 Goals HT/2HT aus demselben Spiel.
    Erkennt torreiches Profil und kombiniert passende Team-Märkte.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    TEAM_CATS = {"btts", "btts_ht", "over_goals", "over15_ht", "team_corners", "corners", "match_corners", "team_cards", "match_sot", "match_goals", "half_goals_1st", "half_goals_2nd"}

    for match, candidates in by_match.items():
        team_legs = [l for l in candidates if l.category in TEAM_CATS]
        if len(team_legs) < 2:
            continue

        # BTTS-Kombination: BTTS + BTTS HT (Screenshot 4 Stil)
        btts = [l for l in team_legs if l.category == "btts"]
        btts_ht = [l for l in team_legs if l.category == "btts_ht"]
        over_goals = [l for l in team_legs if l.category in {"over_goals", "over15_ht"}]
        corners = [l for l in team_legs if l.category in {"team_corners", "corners"}]

        # 1. BTTS Team Builder (BTTS + BTTS HT + Over Goals)
        combo1 = (btts[:1] + btts_ht[:1] + over_goals[:1])
        if len(combo1) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS COMBO", combo1[:3], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 2. Voller Korrelations-Builder (alle 4 Märkte wie Screenshot 4)
        combo2 = (btts[:1] + btts_ht[:1] + over_goals[:2])
        if len(combo2) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS FULL CORR", combo2[:4], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 3. Corners + BTTS (Eckball-Tore-Kombi)
        if corners and btts:
            combo3 = btts[:1] + corners[:1]
            if len(combo3) >= 2:
                pick = _make_builder("TEAM BUILDER", "BTTS + CORNERS", combo3, match_date, 0.5)
                if pick:
                    builders.append(pick)

        # 4. Half Goals Builder (1st Half + 2nd Half Goal Lines — Screenshot)
        half1 = [l for l in team_legs if l.category == "half_goals_1st"]
        half2 = [l for l in team_legs if l.category == "half_goals_2nd"]

        # BTTS HT + BTTS 2HT + Half Goals = 9.00 (Screenshot)
        combo_half = btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_half) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS HT + HALF GOALS", combo_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # Full Half Goals: BTTS HT + BTTS 2HT + Over Goals HT + Over Goals 2HT = 13.00
        combo_full_half = btts[:1] + btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_full_half) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS HALF CORR FULL", combo_full_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # 5. Match SOT + Goals (torreiche Spiele)
        match_sot = [l for l in team_legs if l.category == "match_sot"]
        match_goals = [l for l in team_legs if l.category == "match_goals"]
        if match_sot and match_goals:
            combo_sot = match_sot[:1] + match_goals[:1] + btts[:1]
            if len(combo_sot) >= 2:
                pick = _make_builder("TEAM BUILDER", "SOT + GOALS", combo_sot, match_date, 0.5)
                if pick:
                    builders.append(pick)

    return builders


def _high_odds_booking_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    High Odds Booking Ladder — JK-Style:
    2× Booked = ~15-30 (Quote 9/2–14/1)
    3× Booked = ~40-80 (Quote 55/1)
    4× Booked = ~150-400 (Quote 321/1)
    5× Booked = ~500-2000 (extreme)
    Einsatz: 0.1u für alle Varianten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        booking_legs = sorted(
            [l for l in candidates if l.category == "yellow_cards"],
            key=lambda x: x.quality, reverse=True
        )
        legs_pool = _best_distinct_players(booking_legs, 5)

        for size, label, min_odds, max_odds, stake in [
            (2, "2× BOOKED",      8.0,   60.0,  0.25),
            (3, "3× BOOKED HIGH", 15.0,  200.0, 0.10),
            (4, "4× BOOKED JK",   50.0,  800.0, 0.10),
            (5, "5× BOOKED JK",   200.0, 5000.0, 0.05),
        ]:
            if len(legs_pool) >= size:
                pick = _make_builder("BOOKING LADDER", label, legs_pool[:size], match_date, stake)
                if pick and min_odds <= pick.total_odds <= max_odds:
                    builders.append(pick)

    return builders


def _fouls_tackles_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Fouls + Tackles Combo — JK-Style (Screenshot: Haaland 3+ Fouls + Konsa 4+ Tackles = 170/1)
    Kombiniert hohe Fouls-Lines mit hohen Tackles-Lines für High-Odds Builder.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        fouls = sorted(
            [l for l in candidates if l.category in {"fouls", "fouls_won"}],
            key=lambda x: x.quality, reverse=True
        )
        tackles = sorted(
            [l for l in candidates if l.category in {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )

        if not fouls or not tackles:
            continue

        # Fouls + Tackles (2-3 Spieler total, gemischte Märkte)
        for n_fouls, n_tackles in [(2, 1), (1, 2), (1, 1), (2, 2)]:
            selected = (
                [_derive_lower_line(l, 2, "2+ Fouls Committed", 0.44) for l in fouls[:n_fouls]] +
                [_derive_lower_line(l, 2, "2+ Tackles Committed", 0.44) for l in tackles[:n_tackles]]
            )
            selected = [l for l in selected if l is not None]
            if len(selected) >= 2 and valid_builder(selected):
                pick = _make_builder("FOULS + TACKLES", f"FOUL+TACKLE {len(selected)}L",
                                     selected, match_date, 0.1)
                if pick and 8.0 <= pick.total_odds <= 500.0:
                    builders.append(pick)
                    break

        # High-Line Variante (3+ Fouls, 4+ Tackles wie Screenshot)
        hi_fouls = [_derive_lower_line(l, 3, "3+ Fouls Committed", 0.25) for l in fouls[:2]]
        hi_tackles = [_derive_lower_line(l, 3, "3+ Tackles Committed", 0.25) for l in tackles[:2]]
        selected_hi = [l for l in hi_fouls + hi_tackles if l is not None]
        if len(selected_hi) >= 2:
            pick = _make_builder("FOULS + TACKLES", "HIGH LINE FOUL+TACKLE",
                                 selected_hi[:3], match_date, 0.1)
            if pick and 30.0 <= pick.total_odds <= 1000.0:
                builders.append(pick)

    return builders


def _jk_multi_shot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    JK Multi-Shot Builder — Screenshot (France vs Spain):
    Olise 3+ Shots + Baena 2+ Shots + Olmo 3+ Shots + Porro 1+ Shots + Rodri 1+ Shots
    Bis zu 5 Spieler, gemischte Shot-Lines, hohe Quoten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        shot_legs = sorted(
            [l for l in candidates if l.category in {"shots", "sot", "sot_outside_box"}],
            key=lambda x: x.quality, reverse=True
        )
        pool = _best_distinct_players(shot_legs, 5)
        if len(pool) < 3:
            continue

        for size, label, min_odds, stake in [
            (3, "3-SHOT LADDER",  6.0,  0.25),
            (4, "4-SHOT LADDER", 15.0,  0.10),
            (5, "5-SHOT LADDER", 40.0,  0.10),
        ]:
            if len(pool) >= size:
                # Gemischte Lines: Top-Spieler höhere Line, Rest 1+
                legs_mixed = []
                for i, leg in enumerate(pool[:size]):
                    if i == 0 and leg.probability >= 0.50:
                        legs_mixed.append(_derive_lower_line(leg, 2, "2+ Shots", 0.45))
                    else:
                        legs_mixed.append(_derive_lower_line(leg, 1, "1+ Shot", 0.60))
                legs_mixed = [l for l in legs_mixed if l is not None]
                if len(legs_mixed) >= size:
                    pick = _make_builder("SHOT LADDER", label, legs_mixed, match_date, stake)
                    if pick and pick.total_odds >= min_odds:
                        builders.append(pick)

    return builders



def _outside_box_sot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    SOT Outside Box Builder — wie Screenshot 2:
    2 Spieler mit 1+ SOT Outside the Box aus demselben Spiel = Quote ~20.
    Typisch für technische Mittelfeldspieler (Fabian Ruiz, Olise etc.)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        outside = sorted(
            [l for l in candidates if l.category == "sot_outside_box"],
            key=lambda x: x.quality, reverse=True
        )
        if len(outside) < 2:
            continue

        legs = _best_distinct_players(outside, 3)
        for size in [2, 3]:
            if len(legs) >= size:
                pick = _make_builder("OUTSIDE BOX SOT", f"SOT OUTSIDE {size}L",
                                     legs[:size], match_date, 0.25)
                if pick and pick.total_odds >= 8.0:
                    builders.append(pick)
    return builders


def _full_profile_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Full Profile Builder — JK-Style (Screenshot England vs Argentina):
    Messi To Score + Bellingham Score/Assist + 3× Tackles + Over Corners + Over SOT = 17.00

    Kombiniert das KOMPLETTE Spielprofil:
    1. Goalscorer/Score-or-Assist (1-2 Spieler)
    2. Defensive Midfield Tackles (2-3 Spieler)
    3. Match-Level Team-Märkte (Corners, SOT)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        # 1. Goalscorer-Legs
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "score_assist", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        # 2. Tackle-Legs (defensive Sechser, Innenverteidiger)
        tackles = sorted(
            [l for l in candidates if l.category in
             {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )
        # 3. Team/Match Märkte
        team_mkt = sorted(
            [l for l in candidates if l.category in
             {"team_corners", "corners", "match_corners", "over_goals", "btts", "btts_ht", "match_sot", "match_goals", "team_cards"}],
            key=lambda x: x.quality, reverse=True
        )

        if not scorers or len(tackles) < 2:
            continue

        tackle_pool = _best_distinct_players(tackles, 3)

        # Variante A: Scorer + 2 Tackles + Corner/SOT (wie Screenshot)
        for n_tackles in [3, 2]:
            if len(tackle_pool) >= n_tackles:
                legs = scorers[:1] + tackle_pool[:n_tackles]
                if team_mkt:
                    legs += team_mkt[:1]
                if valid_builder(legs, min_legs=4):
                    pick = _make_builder("FULL PROFILE", f"SCORE+TACKLE+TEAM {len(legs)}L",
                                         legs, match_date, 0.5)
                    if pick and 6.0 <= pick.total_odds <= 100.0:
                        builders.append(pick)
                        break

        # Variante B: Score+Assist + Tackles (2 Goalscorer-Legs + 2 Tackles)
        if len(scorers) >= 2 and len(tackle_pool) >= 2:
            legs_b = scorers[:2] + tackle_pool[:2]
            if team_mkt:
                legs_b += team_mkt[:1]
            if valid_builder(legs_b, min_legs=4):
                pick = _make_builder("FULL PROFILE", "DUAL SCORER+TACKLE",
                                      legs_b, match_date, 0.5)
                if pick and 10.0 <= pick.total_odds <= 150.0:
                    builders.append(pick)

    return builders


def _goalscorer_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """Goalscorer Combo: Messi To Score + Fouls/Cards/Tackles = 8.50"""
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        if not scorers:
            continue

        # Anker-Legs: Fouls, Tackles, Bookings vom gleichen Spiel
        anchors = sorted(
            [l for l in candidates if l.category in
             {"fouls", "fouls_won", "yellow_cards", "tackles_committed",
              "sot", "shots", "team_cards", "btts"}],
            key=lambda x: x.quality, reverse=True
        )
        if not anchors:
            continue

        # Top Scorer + 1-2 Anker
        top_scorer = scorers[0]
        for n_anchors in [2, 1]:
            selected = [top_scorer] + anchors[:n_anchors]
            if valid_builder(selected):
                label = "GOALSCORER MIX" if n_anchors == 1 else "GOALSCORER + FOULS"
                pick = _make_builder("PLAYER BUILDER", label, selected, match_date, 0.5)
                if pick and 4.0 <= pick.total_odds <= 50.0:
                    builders.append(pick)
                    break
    return builders




def _player_prop_mix_builders(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Real Player Prop Mix:
    gebaut für genau solche Kombis:
    - Harry Kane 2+ SOT
    - Messi To Score
    - Otamendi To Be Carded

    Nimmt bevorzugt echte Pinnacle-Player-Props und kombiniert Scorer/SOT/Card/Foul/Tackle.
    Same-Match wird bevorzugt, Cross-Match ist erlaubt, wenn ein einzelnes Match nicht genug echte Spielerprops hat.
    """
    builders: List[BuilderPick] = []
    player_cats = {"score", "first_scorer", "last_scorer", "sot", "shots", "yellow_cards", "fouls", "fouls_won", "tackles_committed", "tackles_received"}
    real_player_props = [
        l for l in props
        if l.category in player_cats
        and "pinnacle" in norm(l.source)
        and norm(l.player) not in {"yes", "no", "over", "under", "home", "away", "draw"}
    ]

    by_match: Dict[str, List[PropLeg]] = {}
    for leg in real_player_props:
        by_match.setdefault(leg.match, []).append(leg)

    templates = [
        ("PLAYER PROP MIX", "SCORE + SOT + CARD", ["score", "first_scorer", "sot", "shots", "yellow_cards"], 3),
        ("PLAYER PROP MIX", "ATTACK + DISCIPLINE", ["score", "sot", "shots", "fouls", "yellow_cards"], 4),
        ("PLAYER PROP MIX", "SHOT + CARD MIX", ["sot", "shots", "yellow_cards", "fouls", "tackles_committed"], 3),
    ]

    for match, candidates in by_match.items():
        if len(candidates) < 2:
            continue
        for style, variant, cats, max_legs in templates:
            selected: List[PropLeg] = []
            used_players = set()
            used_categories = set()
            for cat in cats:
                pool = sorted(
                    [x for x in candidates if x.category == cat],
                    key=lambda x: (not x.estimated, x.quality, x.probability, x.odds),
                    reverse=True,
                )
                for leg in pool:
                    pkey = norm(leg.player)
                    if pkey in used_players and leg.category not in {"fouls", "tackles_committed", "tackles_received"}:
                        continue
                    if leg.category in used_categories and leg.category not in {"sot", "shots"}:
                        continue
                    selected.append(leg)
                    used_players.add(pkey)
                    used_categories.add(leg.category)
                    break
                if len(selected) >= max_legs:
                    break
            if len(selected) >= 2:
                pick = _make_builder(style, f"SAME MATCH {len(selected)}L", selected, match_date, 0.5 if len(selected) <= 3 else 0.25)
                if pick:
                    builders.append(pick)

    # Cross-Match Mix: bester Scorer + bester SOT/Shot + beste Card/Foul/Tackle aus verschiedenen Spielen
    buckets = [
        ("SCORER", [x for x in real_player_props if x.category in {"score", "first_scorer", "last_scorer"}]),
        ("SOT", [x for x in real_player_props if x.category in {"sot", "shots"}]),
        ("CARD", [x for x in real_player_props if x.category in {"yellow_cards", "fouls", "tackles_committed", "tackles_received"}]),
    ]
    selected = []
    used_players = set()
    used_matches = set()
    for _, bucket in buckets:
        for leg in sorted(bucket, key=lambda x: (not x.estimated, x.quality, x.probability, x.odds), reverse=True):
            pkey = norm(leg.player)
            if pkey in used_players:
                continue
            selected.append(leg)
            used_players.add(pkey)
            used_matches.add(norm(leg.match))
            break
    if len(selected) >= 3:
        pick = _make_builder("PLAYER PROP MIX", "CROSS MATCH STAR MIX 3L", selected, match_date, 0.25)
        if pick:
            builders.append(pick)

    # Zusätzlicher 2-Leg Fallback, wenn nur Scorer+Card oder SOT+Card vorhanden sind.
    if len(selected) >= 2:
        pick = _make_builder("PLAYER PROP MIX", "CROSS MATCH 2L", selected[:2], match_date, 0.5)
        if pick:
            builders.append(pick)

    return builders



# ============================================================
# 🎯 SCREENSHOT BUILDERS (JK-Style, Full Profile, Team Correlation)
# ============================================================
def _team_correlation_builders(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Team Correlation Builder — wie Screenshot 4:
    BTTS HT + BTTS 2HT + Over 2 Goals HT/2HT aus demselben Spiel.
    Erkennt torreiches Profil und kombiniert passende Team-Märkte.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    TEAM_CATS = {"btts", "btts_ht", "over_goals", "over15_ht", "team_corners", "corners", "match_corners", "team_cards", "match_sot", "match_goals", "half_goals_1st", "half_goals_2nd"}

    for match, candidates in by_match.items():
        team_legs = [l for l in candidates if l.category in TEAM_CATS]
        if len(team_legs) < 2:
            continue

        # BTTS-Kombination: BTTS + BTTS HT (Screenshot 4 Stil)
        btts = [l for l in team_legs if l.category == "btts"]
        btts_ht = [l for l in team_legs if l.category == "btts_ht"]
        over_goals = [l for l in team_legs if l.category in {"over_goals", "over15_ht"}]
        corners = [l for l in team_legs if l.category in {"team_corners", "corners"}]

        # 1. BTTS Team Builder (BTTS + BTTS HT + Over Goals)
        combo1 = (btts[:1] + btts_ht[:1] + over_goals[:1])
        if len(combo1) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS COMBO", combo1[:3], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 2. Voller Korrelations-Builder (alle 4 Märkte wie Screenshot 4)
        combo2 = (btts[:1] + btts_ht[:1] + over_goals[:2])
        if len(combo2) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS FULL CORR", combo2[:4], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 3. Corners + BTTS (Eckball-Tore-Kombi)
        if corners and btts:
            combo3 = btts[:1] + corners[:1]
            if len(combo3) >= 2:
                pick = _make_builder("TEAM BUILDER", "BTTS + CORNERS", combo3, match_date, 0.5)
                if pick:
                    builders.append(pick)

        # 4. Half Goals Builder (1st Half + 2nd Half Goal Lines — Screenshot)
        half1 = [l for l in team_legs if l.category == "half_goals_1st"]
        half2 = [l for l in team_legs if l.category == "half_goals_2nd"]

        # BTTS HT + BTTS 2HT + Half Goals = 9.00 (Screenshot)
        combo_half = btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_half) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS HT + HALF GOALS", combo_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # Full Half Goals: BTTS HT + BTTS 2HT + Over Goals HT + Over Goals 2HT = 13.00
        combo_full_half = btts[:1] + btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_full_half) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS HALF CORR FULL", combo_full_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # 5. Match SOT + Goals (torreiche Spiele)
        match_sot = [l for l in team_legs if l.category == "match_sot"]
        match_goals = [l for l in team_legs if l.category == "match_goals"]
        if match_sot and match_goals:
            combo_sot = match_sot[:1] + match_goals[:1] + btts[:1]
            if len(combo_sot) >= 2:
                pick = _make_builder("TEAM BUILDER", "SOT + GOALS", combo_sot, match_date, 0.5)
                if pick:
                    builders.append(pick)

    return builders



def _high_odds_booking_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    High Odds Booking Ladder — JK-Style:
    2× Booked = ~15-30 (Quote 9/2–14/1)
    3× Booked = ~40-80 (Quote 55/1)
    4× Booked = ~150-400 (Quote 321/1)
    5× Booked = ~500-2000 (extreme)
    Einsatz: 0.1u für alle Varianten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        booking_legs = sorted(
            [l for l in candidates if l.category == "yellow_cards"],
            key=lambda x: x.quality, reverse=True
        )
        legs_pool = _best_distinct_players(booking_legs, 5)

        for size, label, min_odds, max_odds, stake in [
            (2, "2× BOOKED",      8.0,   60.0,  0.25),
            (3, "3× BOOKED HIGH", 15.0,  200.0, 0.10),
            (4, "4× BOOKED JK",   50.0,  800.0, 0.10),
            (5, "5× BOOKED JK",   200.0, 5000.0, 0.05),
        ]:
            if len(legs_pool) >= size:
                pick = _make_builder("BOOKING LADDER", label, legs_pool[:size], match_date, stake)
                if pick and min_odds <= pick.total_odds <= max_odds:
                    builders.append(pick)

    return builders



def _fouls_tackles_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Fouls + Tackles Combo — JK-Style (Screenshot: Haaland 3+ Fouls + Konsa 4+ Tackles = 170/1)
    Kombiniert hohe Fouls-Lines mit hohen Tackles-Lines für High-Odds Builder.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        fouls = sorted(
            [l for l in candidates if l.category in {"fouls", "fouls_won"}],
            key=lambda x: x.quality, reverse=True
        )
        tackles = sorted(
            [l for l in candidates if l.category in {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )

        if not fouls or not tackles:
            continue

        # Fouls + Tackles (2-3 Spieler total, gemischte Märkte)
        for n_fouls, n_tackles in [(2, 1), (1, 2), (1, 1), (2, 2)]:
            selected = (
                [_derive_lower_line(l, 2, "2+ Fouls Committed", 0.44) for l in fouls[:n_fouls]] +
                [_derive_lower_line(l, 2, "2+ Tackles Committed", 0.44) for l in tackles[:n_tackles]]
            )
            selected = [l for l in selected if l is not None]
            if len(selected) >= 2 and valid_builder(selected):
                pick = _make_builder("FOULS + TACKLES", f"FOUL+TACKLE {len(selected)}L",
                                     selected, match_date, 0.1)
                if pick and 8.0 <= pick.total_odds <= 500.0:
                    builders.append(pick)
                    break

        # High-Line Variante (3+ Fouls, 4+ Tackles wie Screenshot)
        hi_fouls = [_derive_lower_line(l, 3, "3+ Fouls Committed", 0.25) for l in fouls[:2]]
        hi_tackles = [_derive_lower_line(l, 3, "3+ Tackles Committed", 0.25) for l in tackles[:2]]
        selected_hi = [l for l in hi_fouls + hi_tackles if l is not None]
        if len(selected_hi) >= 2:
            pick = _make_builder("FOULS + TACKLES", "HIGH LINE FOUL+TACKLE",
                                 selected_hi[:3], match_date, 0.1)
            if pick and 30.0 <= pick.total_odds <= 1000.0:
                builders.append(pick)

    return builders



def _jk_multi_shot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    JK Multi-Shot Builder — Screenshot (France vs Spain):
    Olise 3+ Shots + Baena 2+ Shots + Olmo 3+ Shots + Porro 1+ Shots + Rodri 1+ Shots
    Bis zu 5 Spieler, gemischte Shot-Lines, hohe Quoten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        shot_legs = sorted(
            [l for l in candidates if l.category in {"shots", "sot", "sot_outside_box"}],
            key=lambda x: x.quality, reverse=True
        )
        pool = _best_distinct_players(shot_legs, 5)
        if len(pool) < 3:
            continue

        for size, label, min_odds, stake in [
            (3, "3-SHOT LADDER",  6.0,  0.25),
            (4, "4-SHOT LADDER", 15.0,  0.10),
            (5, "5-SHOT LADDER", 40.0,  0.10),
        ]:
            if len(pool) >= size:
                # Gemischte Lines: Top-Spieler höhere Line, Rest 1+
                legs_mixed = []
                for i, leg in enumerate(pool[:size]):
                    if i == 0 and leg.probability >= 0.50:
                        legs_mixed.append(_derive_lower_line(leg, 2, "2+ Shots", 0.45))
                    else:
                        legs_mixed.append(_derive_lower_line(leg, 1, "1+ Shot", 0.60))
                legs_mixed = [l for l in legs_mixed if l is not None]
                if len(legs_mixed) >= size:
                    pick = _make_builder("SHOT LADDER", label, legs_mixed, match_date, stake)
                    if pick and pick.total_odds >= min_odds:
                        builders.append(pick)

    return builders




def _outside_box_sot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    SOT Outside Box Builder — wie Screenshot 2:
    2 Spieler mit 1+ SOT Outside the Box aus demselben Spiel = Quote ~20.
    Typisch für technische Mittelfeldspieler (Fabian Ruiz, Olise etc.)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        outside = sorted(
            [l for l in candidates if l.category == "sot_outside_box"],
            key=lambda x: x.quality, reverse=True
        )
        if len(outside) < 2:
            continue

        legs = _best_distinct_players(outside, 3)
        for size in [2, 3]:
            if len(legs) >= size:
                pick = _make_builder("OUTSIDE BOX SOT", f"SOT OUTSIDE {size}L",
                                     legs[:size], match_date, 0.25)
                if pick and pick.total_odds >= 8.0:
                    builders.append(pick)
    return builders



def _full_profile_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Full Profile Builder — JK-Style (Screenshot England vs Argentina):
    Messi To Score + Bellingham Score/Assist + 3× Tackles + Over Corners + Over SOT = 17.00

    Kombiniert das KOMPLETTE Spielprofil:
    1. Goalscorer/Score-or-Assist (1-2 Spieler)
    2. Defensive Midfield Tackles (2-3 Spieler)
    3. Match-Level Team-Märkte (Corners, SOT)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        # 1. Goalscorer-Legs
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "score_assist", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        # 2. Tackle-Legs (defensive Sechser, Innenverteidiger)
        tackles = sorted(
            [l for l in candidates if l.category in
             {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )
        # 3. Team/Match Märkte
        team_mkt = sorted(
            [l for l in candidates if l.category in
             {"team_corners", "corners", "match_corners", "over_goals", "btts", "btts_ht", "match_sot", "match_goals", "team_cards"}],
            key=lambda x: x.quality, reverse=True
        )

        if not scorers or len(tackles) < 2:
            continue

        tackle_pool = _best_distinct_players(tackles, 3)

        # Variante A: Scorer + 2 Tackles + Corner/SOT (wie Screenshot)
        for n_tackles in [3, 2]:
            if len(tackle_pool) >= n_tackles:
                legs = scorers[:1] + tackle_pool[:n_tackles]
                if team_mkt:
                    legs += team_mkt[:1]
                if valid_builder(legs, min_legs=4):
                    pick = _make_builder("FULL PROFILE", f"SCORE+TACKLE+TEAM {len(legs)}L",
                                         legs, match_date, 0.5)
                    if pick and 6.0 <= pick.total_odds <= 100.0:
                        builders.append(pick)
                        break

        # Variante B: Score+Assist + Tackles (2 Goalscorer-Legs + 2 Tackles)
        if len(scorers) >= 2 and len(tackle_pool) >= 2:
            legs_b = scorers[:2] + tackle_pool[:2]
            if team_mkt:
                legs_b += team_mkt[:1]
            if valid_builder(legs_b, min_legs=4):
                pick = _make_builder("FULL PROFILE", "DUAL SCORER+TACKLE",
                                      legs_b, match_date, 0.5)
                if pick and 10.0 <= pick.total_odds <= 150.0:
                    builders.append(pick)

    return builders



def _goalscorer_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """Goalscorer Combo: Messi To Score + Fouls/Cards/Tackles = 8.50"""
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        if not scorers:
            continue

        # Anker-Legs: Fouls, Tackles, Bookings vom gleichen Spiel
        anchors = sorted(
            [l for l in candidates if l.category in
             {"fouls", "fouls_won", "yellow_cards", "tackles_committed",
              "sot", "shots", "team_cards", "btts"}],
            key=lambda x: x.quality, reverse=True
        )
        if not anchors:
            continue

        # Top Scorer + 1-2 Anker
        top_scorer = scorers[0]
        for n_anchors in [2, 1]:
            selected = [top_scorer] + anchors[:n_anchors]
            if valid_builder(selected):
                label = "GOALSCORER MIX" if n_anchors == 1 else "GOALSCORER + FOULS"
                pick = _make_builder("PLAYER BUILDER", label, selected, match_date, 0.5)
                if pick and 4.0 <= pick.total_odds <= 50.0:
                    builders.append(pick)
                    break
    return builders





def build_builder_picks(
    raw_props: Sequence[Dict[str, Any]],
    match_contexts: Optional[Sequence[Dict[str, Any]]] = None,
    match_date: Optional[str] = None,
    max_builders: Optional[int] = None,
) -> List[BuilderPick]:
    props = deduplicate_props(raw_props)
    run_date = match_date or date.today().isoformat()
    max_count = max_builders or as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "30"), 30)

    candidates: List[BuilderPick] = []
    # Real Player Prop Mix zuerst sichern, damit echte Spielerprops nicht von Team-Märkten verdrängt werden.
    candidates.extend(_player_prop_mix_builders(props, run_date))
    candidates.extend(_shot_ladders(props, match_contexts or [], run_date))
    candidates.extend(_category_trios(props, run_date))
    candidates.extend(_mixed_builders(props, run_date))
    candidates.extend(_same_match_available_builders(props, run_date))
    candidates.extend(_same_game_narratives(props, run_date))
    candidates.extend(_cross_match_builder(props, run_date))
    # Team & Korrelations-Builder
    candidates.extend(_team_correlation_builders(props, run_date))
    candidates.extend(_goalscorer_combo_builder(props, run_date))
    # JK-Style High-Odds Builder
    candidates.extend(_high_odds_booking_builder(props, run_date))    # 2-5× Booked
    candidates.extend(_fouls_tackles_combo_builder(props, run_date))  # Fouls + Tackles = 170/1
    candidates.extend(_jk_multi_shot_builder(props, run_date))        # 3-5 Spieler Shots = 100/1+
    candidates.extend(_outside_box_sot_builder(props, run_date))      # SOT Outside Box = 21/1
    candidates.extend(_full_profile_builder(props, run_date))         # Messi+Bellingham+Tackles+Corners

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

    diversified: List[BuilderPick] = []
    style_counts: Dict[str, int] = {}
    match_counts: Dict[str, int] = {}
    selected_ids = set()

    def _try_add(pick: BuilderPick, force_style: bool = False) -> bool:
        if pick.builder_id in selected_ids:
            return False
        match_key = pick.legs[0].match if len({x.match for x in pick.legs}) == 1 else "CROSS"
        if not force_style and style_counts.get(pick.style, 0) >= 8:
            return False
        if match_key != "CROSS" and match_counts.get(match_key, 0) >= 20:
            return False
        diversified.append(pick)
        selected_ids.add(pick.builder_id)
        style_counts[pick.style] = style_counts.get(pick.style, 0) + 1
        match_counts[match_key] = match_counts.get(match_key, 0) + 1
        return True

    # Pass 1: Mindestens einen Builder pro tatsächlich vorhandener Stilart sichern.
    seen_styles = set()
    for pick in unique:
        if pick.style in seen_styles:
            continue
        if _try_add(pick, force_style=True):
            seen_styles.add(pick.style)
        if len(diversified) >= max_count:
            return diversified

    # Pass 2: Restliche Plätze nach Ranking auffüllen.
    for pick in unique:
        _try_add(pick)
        if len(diversified) >= max_count:
            break

    return diversified


def format_builder_message(pick: BuilderPick) -> str:
    sep = "━" * 18
    estimate = " · Modell/Fair" if pick.estimated_odds else ""
    lines = [
        f"🏗️ <b>NETRATTLER {pick.style}</b>",
        f"<b>{pick.variant}</b>",
        sep,
    ]
    MARKET_LABELS = {
        "score": "Anytime Goalscorer",
        "first_scorer": "First Goalscorer",
        "last_scorer": "Last Goalscorer",
        "sot": "Shots on Target",
        "shots": "Shots",
        "yellow_cards": "To Be Carded",
        "fouls": "Fouls Committed",
        "fouls_won": "Fouls Won",
        "tackles_committed": "Tackles Committed",
        "tackles_received": "Tackles Received",
        "btts": "BTTS YES", "over25": "Over 2.5 Tore", "combo": "BTTS + Over 2.5",
        "btts_ht": "BTTS HT", "match_goals": "Team trifft", "over15_ht": "Over 1.5 HT", "corners": "Ecken",
        "shots": "Schüsse", "cards": "Karte", "goals": "Tor",
    }
    same_match = len({x.match for x in pick.legs}) == 1
    if same_match and pick.legs:
        lines.append(f"⚽ <b>{pick.legs[0].match}</b>")
    for index, leg in enumerate(pick.legs, 1):
        icon = CATEGORY_ICON.get(leg.category, "🎯")
        match_suffix = "" if same_match else f" · {leg.match}"
        source_note = " ~" if leg.estimated else ""
        # Zeige nur den lesbaren Namen, nicht die market_id
        market_label = MARKET_LABELS.get(leg.market, leg.market)
        display_name = leg.player if leg.player and leg.player != leg.market else market_label
        lines.append(
            f"{index}. {icon} <b>{display_name}</b> — {market_label}"
            f"{source_note}{match_suffix}"
        )
    lines.extend([
        sep,
        f"💰 Gesamt-Quote: <b>{pick.total_odds:.2f}</b>{estimate}",
        f"🔥 Einsatz: <b>{pick.stake:.2f} Units</b>",
        ("🎲 Risiko: <b>LOTTERY</b>" if pick.total_odds >= 50 else "🎯 Risiko: <b>VALUE</b>" if pick.total_odds >= 8 else "✅ Risiko: <b>STANDARD</b>"),
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
    normalized = deduplicate_props(raw_props)
    picks = build_builder_picks(raw_props, match_contexts, match_date)
    if logger:
        category_counts: Dict[str, int] = {}
        match_counts: Dict[str, int] = {}
        for leg in normalized:
            category_counts[leg.category] = category_counts.get(leg.category, 0) + 1
            match_counts[leg.match] = match_counts.get(leg.match, 0) + 1
        logger(
            "MASTER BUILDER normalized="
            f"{len(normalized)} · matches={len(match_counts)} · "
            f"same-match≥2={sum(1 for v in match_counts.values() if v >= 2)} · "
            f"generated={len(picks)}"
        )
        logger(
            "MASTER BUILDER categories: "
            + ", ".join(
                f"{k}={v}" for k, v in sorted(
                    category_counts.items(), key=lambda item: item[1], reverse=True
                )[:12]
            )
        )
    sent = 0
    for pick in picks:
        if not _v31_valid_prop_builder(pick):
            if logger:
                logger(
                    "MASTER BUILDER rejected before send: "
                    f"{pick.style} {pick.variant} @ {pick.total_odds:.2f}"
                )
            continue
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


# ============================================================
# V31 PROP QUALITY LAYER
# ============================================================
# Ziel: weniger generische Team-Builder, mehr echte Spieler-Props wie:
# Kane SOT, Messi Tor, Otamendi Karte, Fouls/Tackles, mit Edge/Read.

_ORIGINAL_BUILD_BUILDER_PICKS_V30 = build_builder_picks
_ORIGINAL_FORMAT_BUILDER_MESSAGE_V30 = format_builder_message

_GENERIC_PLAYERS_V31 = {
    "yes", "no", "over", "under", "home", "away", "draw", "both teams",
    "team", "player", "any other player", "field", "none"
}

_SHARP_PLAYER_CATS_V31 = {
    "sot", "shots", "sot_outside_box", "shots_outside_box",
    "yellow_cards", "fouls", "fouls_won",
    "tackles_committed", "tackles_received", "tackles",
    "score", "first_scorer", "last_scorer", "assist", "score_assist",
    "offsides",
}

_CAT_WEIGHT_V31 = {
    "sot": 1.24,
    "shots": 1.14,
    "sot_outside_box": 1.18,
    "shots_outside_box": 1.10,
    "yellow_cards": 1.22,
    "fouls": 1.13,
    "fouls_won": 1.12,
    "tackles_committed": 1.12,
    "tackles_received": 1.12,
    "tackles": 1.08,
    "score": 1.05,
    "first_scorer": 0.94,
    "last_scorer": 0.88,
    "assist": 0.96,
    "score_assist": 1.02,
    "offsides": 0.90,
}

def _v31_is_real_player_leg(leg: PropLeg) -> bool:
    if leg.category not in _SHARP_PLAYER_CATS_V31:
        return False
    p = norm(leg.player)
    if not p or p in _GENERIC_PLAYERS_V31:
        return False
    # Team props kommen manchmal als "Argentina To Score?" / "England To Score?"
    # in score-Kategorie rein. Diese nicht als Spielerprop behandeln.
    m = norm(leg.market)
    if leg.category in {"score", "first_scorer", "last_scorer"} and (
        " to score" in str(leg.market).lower() and norm(leg.player) in norm(leg.match)
    ):
        return False
    if leg.category == "score" and any(x in m for x in ["team to score", "to score yes", "to score?"]):
        return False
    return True

def _v31_edge(leg: PropLeg) -> float:
    implied = 1.0 / leg.odds if leg.odds and leg.odds > 1 else 0.0
    return max(-0.25, min(0.50, float(leg.probability or 0) - implied))


def _v31_min_edge() -> float:
    value = as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_EDGE", "0.0"), 0.0)
    return max(0.0, min(0.50, value))


def _v31_min_total_odds() -> float:
    value = as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_ODDS", "5.0"), 5.0)
    return max(5.0, value)


def _v31_has_observed_bookmaker_odds(leg: PropLeg) -> bool:
    if leg.estimated or not leg.odds or leg.odds <= 1:
        return False
    source = norm(leg.source)
    return any(token in source for token in {
        "pinnacle", "bet365", "betfair", "oddsportal", "oddsharvester",
        "the odds api", "odds api", "odds_api", "oddsapi", "oddspapi",
        "kambi", "unibet", "1xbet", "melbet", "oddspedia", "footymetrics",
        "bookmaker", "sportsbook",
    })


def _v31_valid_prop_leg(leg: PropLeg) -> bool:
    # line >= 0 erlaubt binary Props (To Score, To Be Booked etc.) mit line=0
    return (
        _v31_is_real_player_leg(leg)
        and _v31_has_observed_bookmaker_odds(leg)
        and _v31_edge(leg) > _v31_min_edge()
        and leg.line >= 0
    )


def _v31_valid_prop_builder(pick: BuilderPick) -> bool:
    if not pick or len(pick.legs) < 2:
        return False
    if pick.total_odds < _v31_min_total_odds():
        return False
    if pick.estimated_odds:
        return False
    # REAL-ODDS-ONLY: jedes einzelne Leg muss eine beobachtete Buchmacherquote
    # und positive, unabhängige Modell-Edge haben. Kein geschätztes Leg in Buildern.
    return all(_v31_valid_prop_leg(l) for l in pick.legs)

def _v31_leg_score(leg: PropLeg) -> float:
    base = float(leg.quality or 0.0)
    cat_w = _CAT_WEIGHT_V31.get(leg.category, 0.70)
    edge = _v31_edge(leg)
    src = norm(leg.source)
    source_bonus = 0.12 if "pinnacle" in src else 0.06 if any(x in src for x in ["statsbomb", "fotmob", "soccerdata"]) else 0.0
    real_bonus = 0.10 if _v31_is_real_player_leg(leg) else -0.25
    estimated_penalty = -0.10 if leg.estimated else 0.0

    # Sweet spot: nicht zu hoch, nicht zu langweilig.
    if 1.50 <= leg.odds <= 6.50:
        odds_adj = 0.08
    elif 6.50 < leg.odds <= 12.0:
        odds_adj = 0.03
    elif 12.0 < leg.odds <= 25.0:
        odds_adj = -0.05
    elif leg.odds > 25.0:
        odds_adj = -0.18
    else:
        odds_adj = -0.08

    # Lines mit realistischem Schwierigkeitsgrad bevorzugen.
    line_adj = 0.0
    if leg.category == "sot" and leg.line <= 2:
        line_adj += 0.06
    if leg.category == "shots" and leg.line <= 3:
        line_adj += 0.05
    if leg.category == "yellow_cards" and leg.line <= 1:
        line_adj += 0.05
    if leg.category in {"fouls", "fouls_won", "tackles_committed", "tackles_received"} and leg.line <= 2:
        line_adj += 0.04

    return round(base * cat_w + edge * 0.75 + source_bonus + real_bonus + estimated_penalty + odds_adj + line_adj, 5)

def _v31_distinct_add(pool: Sequence[PropLeg], selected: List[PropLeg], cats: Optional[set] = None, same_match: Optional[str] = None) -> None:
    used_players = {norm(x.player) for x in selected}
    used_keys = {x.key() for x in selected}
    for leg in sorted(pool, key=_v31_leg_score, reverse=True):
        if leg.key() in used_keys:
            continue
        if norm(leg.player) in used_players:
            continue
        if cats is not None and leg.category not in cats:
            continue
        if same_match is not None and norm(leg.match) != norm(same_match):
            continue
        selected.append(leg)
        return

def _v31_make(style: str, variant: str, legs: List[PropLeg], match_date: str, stake: float = 0.35) -> Optional[BuilderPick]:
    legs = [x for x in legs if x and _v31_is_real_player_leg(x)]
    if len(legs) < 2:
        return None
    # sort for readability: scorer -> shots/SOT -> cards/fouls/tackles
    order = {
        "score": 0, "first_scorer": 0, "last_scorer": 0,
        "sot": 1, "shots": 1, "sot_outside_box": 1, "shots_outside_box": 1,
        "yellow_cards": 2, "fouls": 2, "fouls_won": 2,
        "tackles_committed": 3, "tackles_received": 3, "tackles": 3,
    }
    legs = sorted(legs, key=lambda x: (order.get(x.category, 9), -_v31_leg_score(x)))
    pick = _make_builder(style, variant, legs, match_date, stake)
    if not pick:
        return None
    # Player-Prop Builder: only observed bookmaker quotes, positive edge and 5.00+.
    if pick.total_odds > float(os.getenv("NETRATTLER_SHARP_PROP_MAX_ODDS", "80")):
        return None
    if not _v31_valid_prop_builder(pick):
        return None
    return pick

def _v31_same_match_builders(real_props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    out: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in real_props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, pool in by_match.items():
        if len(pool) < 2:
            continue
        pool_sorted = sorted(pool, key=_v31_leg_score, reverse=True)

        scorers = [x for x in pool_sorted if x.category in {"score", "first_scorer", "last_scorer"}]
        shots = [x for x in pool_sorted if x.category in {"sot", "shots", "sot_outside_box", "shots_outside_box"}]
        cards = [x for x in pool_sorted if x.category in {"yellow_cards"}]
        physical = [x for x in pool_sorted if x.category in {"fouls", "fouls_won", "tackles_committed", "tackles_received", "tackles"}]

        # A) Scorer + Karte/Foul/SOT
        legs: List[PropLeg] = []
        _v31_distinct_add(scorers, legs)
        _v31_distinct_add(shots, legs)
        _v31_distinct_add(cards + physical, legs)
        if len(legs) >= 2:
            p = _v31_make("SHARP PLAYER PROP", "SAME GAME ATTACK + DISCIPLINE", legs[:3], match_date, 0.25)
            if p:
                out.append(p)

        # B) Shot/SOT + Card/Foul
        legs = []
        _v31_distinct_add(shots, legs)
        _v31_distinct_add(cards + physical, legs)
        _v31_distinct_add(shots + physical + cards, legs)
        if len(legs) >= 2:
            p = _v31_make("SHARP PLAYER PROP", "SAME GAME SHOT + CONTACT", legs[:3], match_date, 0.35)
            if p:
                out.append(p)

        # C) Beste 2 im Match
        legs = []
        for leg in pool_sorted:
            if _v31_is_real_player_leg(leg) and norm(leg.player) not in {norm(x.player) for x in legs}:
                legs.append(leg)
            if len(legs) >= 2:
                break
        if len(legs) >= 2:
            p = _v31_make("SHARP PLAYER DOUBLE", "BEST 2 REAL PROPS", legs[:2], match_date, 0.45)
            if p:
                out.append(p)

    return out

def _v31_cross_match_builders(real_props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    out: List[BuilderPick] = []
    top = sorted(real_props, key=_v31_leg_score, reverse=True)

    # Cross-Match: nicht mehr blind 3 random legs, sondern Kategorie-Rollen.
    roles = [
        ("ATTACK", {"score", "first_scorer", "sot", "shots"}),
        ("CARD", {"yellow_cards"}),
        ("CONTACT", {"fouls", "fouls_won", "tackles_committed", "tackles_received", "tackles"}),
    ]
    legs: List[PropLeg] = []
    used_matches = set()
    for _, cats in roles:
        for leg in top:
            if leg.category not in cats:
                continue
            if norm(leg.match) in used_matches and len(used_matches) >= 2:
                continue
            if norm(leg.player) in {norm(x.player) for x in legs}:
                continue
            legs.append(leg)
            used_matches.add(norm(leg.match))
            break
    if len(legs) >= 2:
        p = _v31_make("SHARP CROSS-MATCH", f"{len(legs)} REAL PLAYER LEGS", legs[:3], match_date, 0.25)
        if p:
            out.append(p)

    # Best-2 Value Double
    legs = []
    used_matches = set()
    for leg in top:
        if norm(leg.player) in {norm(x.player) for x in legs}:
            continue
        if norm(leg.match) in used_matches and len(real_props) > 2:
            continue
        legs.append(leg)
        used_matches.add(norm(leg.match))
        if len(legs) == 2:
            break
    if len(legs) == 2:
        p = _v31_make("SHARP PLAYER DOUBLE", "TOP EDGE 2L", legs, match_date, 0.45)
        if p:
            out.append(p)

    return out

def _v31_ladder_builders(real_props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    out: List[BuilderPick] = []
    top = sorted(real_props, key=_v31_leg_score, reverse=True)

    for style, cats, variant in [
        ("BOOKING LADDER", {"yellow_cards"}, "2-3 CARDS"),
        ("SHOT/SOT LADDER", {"sot", "shots", "sot_outside_box", "shots_outside_box"}, "2-3 ATTACKERS"),
        ("CONTACT LADDER", {"fouls", "fouls_won", "tackles_committed", "tackles_received", "tackles"}, "2-3 FOULS/TACKLES"),
    ]:
        legs = []
        for leg in top:
            if leg.category not in cats:
                continue
            if norm(leg.player) in {norm(x.player) for x in legs}:
                continue
            legs.append(leg)
            if len(legs) == 3:
                break
        if len(legs) >= 2:
            p = _v31_make(style, variant, legs[:3], match_date, 0.25)
            if p:
                out.append(p)
            p2 = _v31_make(style, variant + " SAFE 2L", legs[:2], match_date, 0.45)
            if p2:
                out.append(p2)

    return out

def _v31_pick_score(pick: BuilderPick) -> float:
    scores = [_v31_leg_score(x) for x in pick.legs]
    avg = sum(scores) / max(1, len(scores))
    real_ratio = sum(1 for x in pick.legs if _v31_is_real_player_leg(x)) / max(1, len(pick.legs))
    cat_div = len({x.category for x in pick.legs}) / max(1, len(pick.legs))
    odds = pick.total_odds
    if odds <= 1.7:
        odds_adj = -0.20
    elif odds <= 8:
        odds_adj = 0.12
    elif odds <= 25:
        odds_adj = 0.05
    elif odds <= 80:
        odds_adj = -0.08
    else:
        odds_adj = -0.30
    return avg + real_ratio * 0.35 + cat_div * 0.10 + odds_adj

# ============================================================
# 🎯 SCREENSHOT BUILDERS (JK-Style, Full Profile, Team Correlation)
# ============================================================
def _team_correlation_builders(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Team Correlation Builder — wie Screenshot 4:
    BTTS HT + BTTS 2HT + Over 2 Goals HT/2HT aus demselben Spiel.
    Erkennt torreiches Profil und kombiniert passende Team-Märkte.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    TEAM_CATS = {"btts", "btts_ht", "over_goals", "over15_ht", "team_corners", "corners", "match_corners", "team_cards", "match_sot", "match_goals", "half_goals_1st", "half_goals_2nd"}

    for match, candidates in by_match.items():
        team_legs = [l for l in candidates if l.category in TEAM_CATS]
        if len(team_legs) < 2:
            continue

        # BTTS-Kombination: BTTS + BTTS HT (Screenshot 4 Stil)
        btts = [l for l in team_legs if l.category == "btts"]
        btts_ht = [l for l in team_legs if l.category == "btts_ht"]
        over_goals = [l for l in team_legs if l.category in {"over_goals", "over15_ht"}]
        corners = [l for l in team_legs if l.category in {"team_corners", "corners"}]

        # 1. BTTS Team Builder (BTTS + BTTS HT + Over Goals)
        combo1 = (btts[:1] + btts_ht[:1] + over_goals[:1])
        if len(combo1) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS COMBO", combo1[:3], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 2. Voller Korrelations-Builder (alle 4 Märkte wie Screenshot 4)
        combo2 = (btts[:1] + btts_ht[:1] + over_goals[:2])
        if len(combo2) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS FULL CORR", combo2[:4], match_date, 0.5)
            if pick:
                builders.append(pick)

        # 3. Corners + BTTS (Eckball-Tore-Kombi)
        if corners and btts:
            combo3 = btts[:1] + corners[:1]
            if len(combo3) >= 2:
                pick = _make_builder("TEAM BUILDER", "BTTS + CORNERS", combo3, match_date, 0.5)
                if pick:
                    builders.append(pick)

        # 4. Half Goals Builder (1st Half + 2nd Half Goal Lines — Screenshot)
        half1 = [l for l in team_legs if l.category == "half_goals_1st"]
        half2 = [l for l in team_legs if l.category == "half_goals_2nd"]

        # BTTS HT + BTTS 2HT + Half Goals = 9.00 (Screenshot)
        combo_half = btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_half) >= 2:
            pick = _make_builder("TEAM BUILDER", "BTTS HT + HALF GOALS", combo_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # Full Half Goals: BTTS HT + BTTS 2HT + Over Goals HT + Over Goals 2HT = 13.00
        combo_full_half = btts[:1] + btts_ht[:1] + half1[:1] + half2[:1]
        if len(combo_full_half) >= 3:
            pick = _make_builder("TEAM BUILDER", "BTTS HALF CORR FULL", combo_full_half, match_date, 0.5)
            if pick:
                builders.append(pick)

        # 5. Match SOT + Goals (torreiche Spiele)
        match_sot = [l for l in team_legs if l.category == "match_sot"]
        match_goals = [l for l in team_legs if l.category == "match_goals"]
        if match_sot and match_goals:
            combo_sot = match_sot[:1] + match_goals[:1] + btts[:1]
            if len(combo_sot) >= 2:
                pick = _make_builder("TEAM BUILDER", "SOT + GOALS", combo_sot, match_date, 0.5)
                if pick:
                    builders.append(pick)

    return builders



def _high_odds_booking_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    High Odds Booking Ladder — JK-Style:
    2× Booked = ~15-30 (Quote 9/2–14/1)
    3× Booked = ~40-80 (Quote 55/1)
    4× Booked = ~150-400 (Quote 321/1)
    5× Booked = ~500-2000 (extreme)
    Einsatz: 0.1u für alle Varianten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        booking_legs = sorted(
            [l for l in candidates if l.category == "yellow_cards"],
            key=lambda x: x.quality, reverse=True
        )
        legs_pool = _best_distinct_players(booking_legs, 5)

        for size, label, min_odds, max_odds, stake in [
            (2, "2× BOOKED",      8.0,   60.0,  0.25),
            (3, "3× BOOKED HIGH", 15.0,  200.0, 0.10),
            (4, "4× BOOKED JK",   50.0,  800.0, 0.10),
            (5, "5× BOOKED JK",   200.0, 5000.0, 0.05),
        ]:
            if len(legs_pool) >= size:
                pick = _make_builder("BOOKING LADDER", label, legs_pool[:size], match_date, stake)
                if pick and min_odds <= pick.total_odds <= max_odds:
                    builders.append(pick)

    return builders



def _fouls_tackles_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Fouls + Tackles Combo — JK-Style (Screenshot: Haaland 3+ Fouls + Konsa 4+ Tackles = 170/1)
    Kombiniert hohe Fouls-Lines mit hohen Tackles-Lines für High-Odds Builder.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        fouls = sorted(
            [l for l in candidates if l.category in {"fouls", "fouls_won"}],
            key=lambda x: x.quality, reverse=True
        )
        tackles = sorted(
            [l for l in candidates if l.category in {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )

        if not fouls or not tackles:
            continue

        # Fouls + Tackles (2-3 Spieler total, gemischte Märkte)
        for n_fouls, n_tackles in [(2, 1), (1, 2), (1, 1), (2, 2)]:
            selected = (
                [_derive_lower_line(l, 2, "2+ Fouls Committed", 0.44) for l in fouls[:n_fouls]] +
                [_derive_lower_line(l, 2, "2+ Tackles Committed", 0.44) for l in tackles[:n_tackles]]
            )
            selected = [l for l in selected if l is not None]
            if len(selected) >= 2 and valid_builder(selected):
                pick = _make_builder("FOULS + TACKLES", f"FOUL+TACKLE {len(selected)}L",
                                     selected, match_date, 0.1)
                if pick and 8.0 <= pick.total_odds <= 500.0:
                    builders.append(pick)
                    break

        # High-Line Variante (3+ Fouls, 4+ Tackles wie Screenshot)
        hi_fouls = [_derive_lower_line(l, 3, "3+ Fouls Committed", 0.25) for l in fouls[:2]]
        hi_tackles = [_derive_lower_line(l, 3, "3+ Tackles Committed", 0.25) for l in tackles[:2]]
        selected_hi = [l for l in hi_fouls + hi_tackles if l is not None]
        if len(selected_hi) >= 2:
            pick = _make_builder("FOULS + TACKLES", "HIGH LINE FOUL+TACKLE",
                                 selected_hi[:3], match_date, 0.1)
            if pick and 30.0 <= pick.total_odds <= 1000.0:
                builders.append(pick)

    return builders



def _jk_multi_shot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    JK Multi-Shot Builder — Screenshot (France vs Spain):
    Olise 3+ Shots + Baena 2+ Shots + Olmo 3+ Shots + Porro 1+ Shots + Rodri 1+ Shots
    Bis zu 5 Spieler, gemischte Shot-Lines, hohe Quoten.
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        shot_legs = sorted(
            [l for l in candidates if l.category in {"shots", "sot", "sot_outside_box"}],
            key=lambda x: x.quality, reverse=True
        )
        pool = _best_distinct_players(shot_legs, 5)
        if len(pool) < 3:
            continue

        for size, label, min_odds, stake in [
            (3, "3-SHOT LADDER",  6.0,  0.25),
            (4, "4-SHOT LADDER", 15.0,  0.10),
            (5, "5-SHOT LADDER", 40.0,  0.10),
        ]:
            if len(pool) >= size:
                # Gemischte Lines: Top-Spieler höhere Line, Rest 1+
                legs_mixed = []
                for i, leg in enumerate(pool[:size]):
                    if i == 0 and leg.probability >= 0.50:
                        legs_mixed.append(_derive_lower_line(leg, 2, "2+ Shots", 0.45))
                    else:
                        legs_mixed.append(_derive_lower_line(leg, 1, "1+ Shot", 0.60))
                legs_mixed = [l for l in legs_mixed if l is not None]
                if len(legs_mixed) >= size:
                    pick = _make_builder("SHOT LADDER", label, legs_mixed, match_date, stake)
                    if pick and pick.total_odds >= min_odds:
                        builders.append(pick)

    return builders




def _outside_box_sot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    SOT Outside Box Builder — wie Screenshot 2:
    2 Spieler mit 1+ SOT Outside the Box aus demselben Spiel = Quote ~20.
    Typisch für technische Mittelfeldspieler (Fabian Ruiz, Olise etc.)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        outside = sorted(
            [l for l in candidates if l.category == "sot_outside_box"],
            key=lambda x: x.quality, reverse=True
        )
        if len(outside) < 2:
            continue

        legs = _best_distinct_players(outside, 3)
        for size in [2, 3]:
            if len(legs) >= size:
                pick = _make_builder("OUTSIDE BOX SOT", f"SOT OUTSIDE {size}L",
                                     legs[:size], match_date, 0.25)
                if pick and pick.total_odds >= 8.0:
                    builders.append(pick)
    return builders



def _full_profile_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Full Profile Builder — JK-Style (Screenshot England vs Argentina):
    Messi To Score + Bellingham Score/Assist + 3× Tackles + Over Corners + Over SOT = 17.00

    Kombiniert das KOMPLETTE Spielprofil:
    1. Goalscorer/Score-or-Assist (1-2 Spieler)
    2. Defensive Midfield Tackles (2-3 Spieler)
    3. Match-Level Team-Märkte (Corners, SOT)
    """
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        # 1. Goalscorer-Legs
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "score_assist", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        # 2. Tackle-Legs (defensive Sechser, Innenverteidiger)
        tackles = sorted(
            [l for l in candidates if l.category in
             {"tackles_committed", "tackles_received", "tackles"}],
            key=lambda x: x.quality, reverse=True
        )
        # 3. Team/Match Märkte
        team_mkt = sorted(
            [l for l in candidates if l.category in
             {"team_corners", "corners", "match_corners", "over_goals", "btts", "btts_ht", "match_sot", "match_goals", "team_cards"}],
            key=lambda x: x.quality, reverse=True
        )

        if not scorers or len(tackles) < 2:
            continue

        tackle_pool = _best_distinct_players(tackles, 3)

        # Variante A: Scorer + 2 Tackles + Corner/SOT (wie Screenshot)
        for n_tackles in [3, 2]:
            if len(tackle_pool) >= n_tackles:
                legs = scorers[:1] + tackle_pool[:n_tackles]
                if team_mkt:
                    legs += team_mkt[:1]
                if valid_builder(legs, min_legs=4):
                    pick = _make_builder("FULL PROFILE", f"SCORE+TACKLE+TEAM {len(legs)}L",
                                         legs, match_date, 0.5)
                    if pick and 6.0 <= pick.total_odds <= 100.0:
                        builders.append(pick)
                        break

        # Variante B: Score+Assist + Tackles (2 Goalscorer-Legs + 2 Tackles)
        if len(scorers) >= 2 and len(tackle_pool) >= 2:
            legs_b = scorers[:2] + tackle_pool[:2]
            if team_mkt:
                legs_b += team_mkt[:1]
            if valid_builder(legs_b, min_legs=4):
                pick = _make_builder("FULL PROFILE", "DUAL SCORER+TACKLE",
                                      legs_b, match_date, 0.5)
                if pick and 10.0 <= pick.total_odds <= 150.0:
                    builders.append(pick)

    return builders



def _goalscorer_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """Goalscorer Combo: Messi To Score + Fouls/Cards/Tackles = 8.50"""
    builders: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for match, candidates in by_match.items():
        scorers = sorted(
            [l for l in candidates if l.category in {"score", "first_scorer"}],
            key=lambda x: x.quality, reverse=True
        )
        if not scorers:
            continue

        # Anker-Legs: Fouls, Tackles, Bookings vom gleichen Spiel
        anchors = sorted(
            [l for l in candidates if l.category in
             {"fouls", "fouls_won", "yellow_cards", "tackles_committed",
              "sot", "shots", "team_cards", "btts"}],
            key=lambda x: x.quality, reverse=True
        )
        if not anchors:
            continue

        # Top Scorer + 1-2 Anker
        top_scorer = scorers[0]
        for n_anchors in [2, 1]:
            selected = [top_scorer] + anchors[:n_anchors]
            if valid_builder(selected):
                label = "GOALSCORER MIX" if n_anchors == 1 else "GOALSCORER + FOULS"
                pick = _make_builder("PLAYER BUILDER", label, selected, match_date, 0.5)
                if pick and 4.0 <= pick.total_odds <= 50.0:
                    builders.append(pick)
                    break
    return builders





def build_builder_picks(
    raw_props: Sequence[Dict[str, Any]],
    match_contexts: Optional[Sequence[Dict[str, Any]]] = None,
    match_date: Optional[str] = None,
    max_builders: Optional[int] = None,
) -> List[BuilderPick]:
    props = deduplicate_props(raw_props)
    run_date = match_date or date.today().isoformat()
    max_count = max_builders or as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "18"), 18)

    real_props = [
        x for x in props
        if _v31_valid_prop_leg(x)
        and x.odds >= 1.35
        and x.odds <= float(os.getenv("NETRATTLER_SHARP_PROP_LEG_MAX_ODDS", "25"))
        and x.probability >= float(os.getenv("NETRATTLER_SHARP_PROP_MIN_PROB", "0.15"))
    ]

    focused: List[BuilderPick] = []
    focused.extend(_v31_same_match_builders(real_props, run_date))
    focused.extend(_v31_cross_match_builders(real_props, run_date))
    focused.extend(_v31_ladder_builders(real_props, run_date))

    # Legacy Engine als Fallback, aber nur echte Spieler-Builder bevorzugen.
    legacy: List[BuilderPick] = []
    try:
        legacy = _ORIGINAL_BUILD_BUILDER_PICKS_V30(raw_props, match_contexts, run_date, max_count * 2)
    except Exception:
        legacy = []

    legacy_filtered = []
    for pick in legacy:
        # Legacy may still create useful combinations, but every leg must pass
        # the same strict player-prop rules. Never fall back to team markets.
        if pick.total_odds <= 80 and _v31_valid_prop_builder(pick):
            legacy_filtered.append(pick)

    candidates = [
        pick for pick in (focused + legacy_filtered)
        if _v31_valid_prop_builder(pick)
    ]
    if not candidates:
        return []

    # Dedupe nach Legs, nicht nur builder_id, damit gleiche Kombi mit anderem Style nicht doppelt kommt.
    seen = set()
    unique: List[BuilderPick] = []
    for pick in candidates:
        sig = "|".join(sorted(f"{norm(x.player)}:{norm(x.match)}:{x.category}:{round(x.line,2)}" for x in pick.legs))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(pick)

    unique.sort(key=_v31_pick_score, reverse=True)

    selected: List[BuilderPick] = []
    style_counts: Dict[str, int] = {}
    match_counts: Dict[str, int] = {}
    for pick in unique:
        if not _v31_valid_prop_builder(pick):
            continue
        style_counts[pick.style] = style_counts.get(pick.style, 0)
        match_key = pick.legs[0].match if len({x.match for x in pick.legs}) == 1 else "CROSS"
        if style_counts[pick.style] >= 5:
            continue
        if match_key != "CROSS" and match_counts.get(match_key, 0) >= 3:
            continue
        selected.append(pick)
        style_counts[pick.style] = style_counts.get(pick.style, 0) + 1
        match_counts[match_key] = match_counts.get(match_key, 0) + 1
        if len(selected) >= max_count:
            break

    # 🆕 Screenshot-Builder parallel hinzufügen (JK-Style, nicht durch V31-Filter)
    all_props = deduplicate_props(raw_props)
    screenshot: List[BuilderPick] = []
    screenshot.extend(_team_correlation_builders(all_props, run_date))
    screenshot.extend(_high_odds_booking_builder(all_props, run_date))
    screenshot.extend(_fouls_tackles_combo_builder(all_props, run_date))
    screenshot.extend(_jk_multi_shot_builder(all_props, run_date))
    screenshot.extend(_outside_box_sot_builder(all_props, run_date))
    screenshot.extend(_full_profile_builder(all_props, run_date))
    screenshot.extend(_goalscorer_combo_builder(all_props, run_date))

    existing_sigs = {"|".join(sorted(f"{norm(x.player)}:{x.category}" for x in p.legs)) for p in selected}
    for pick in screenshot:
        sig = "|".join(sorted(f"{norm(x.player)}:{x.category}" for x in pick.legs))
        if sig not in existing_sigs:
            existing_sigs.add(sig)
            selected.append(pick)

    return selected

def _v31_market_label(leg: PropLeg) -> str:
    labels = {
        "score": "Anytime Goalscorer",
        "first_scorer": "First Goalscorer",
        "last_scorer": "Last Goalscorer",
        "sot": f"Over {leg.line:g} Shots on Target" if leg.line and leg.line > 1 else "1+ Shot on Target",
        "shots": f"Over {leg.line:g} Shots" if leg.line and leg.line > 1 else "1+ Shot",
        "sot_outside_box": "SOT Outside Box",
        "shots_outside_box": "Shot Outside Box",
        "yellow_cards": "To Be Carded",
        "fouls": f"Over {leg.line:g} Fouls Committed" if leg.line and leg.line > 1 else "1+ Foul Committed",
        "fouls_won": f"Over {leg.line:g} Fouls Won" if leg.line and leg.line > 1 else "1+ Foul Won",
        "tackles_committed": f"Over {leg.line:g} Tackles Committed" if leg.line and leg.line > 1 else "1+ Tackle Committed",
        "tackles_received": f"Over {leg.line:g} Tackles Received" if leg.line and leg.line > 1 else "1+ Tackle Received",
        "tackles": f"Over {leg.line:g} Tackles" if leg.line and leg.line > 1 else "1+ Tackle",
        "assist": "Assist",
        "score_assist": "Goal or Assist",
        "offsides": "Offside",
    }
    return labels.get(leg.category, leg.market)

def _v31_reason(leg: PropLeg) -> str:
    e = _v31_edge(leg)
    if leg.category in {"yellow_cards"}:
        base = "Karten-/Duell-Profil"
    elif leg.category in {"sot", "shots", "sot_outside_box", "shots_outside_box"}:
        base = "Abschluss-Volumen"
    elif leg.category in {"fouls", "fouls_won"}:
        base = "Kontakt-/Foul-Profil"
    elif leg.category in {"tackles_committed", "tackles_received", "tackles"}:
        base = "Tackle-Matchup"
    elif leg.category in {"score", "first_scorer", "last_scorer"}:
        base = "Tor-/Rollen-Profil"
    else:
        base = "Player-Prop Profil"
    edge_txt = f"Edge {e*100:+.1f}%" if e else "Fair"
    return f"{base} · {edge_txt}"

def format_builder_message(pick: BuilderPick) -> str:
    sep = "━" * 22
    same_match = len({x.match for x in pick.legs}) == 1
    avg_score = sum(_v31_leg_score(x) for x in pick.legs) / max(1, len(pick.legs))
    if avg_score >= 0.92:
        read = "A-SETUP"
    elif avg_score >= 0.82:
        read = "B+ VALUE"
    elif avg_score >= 0.72:
        read = "B VALUE"
    else:
        read = "SPECULATIVE"

    risk = "LOTTERY" if pick.total_odds >= 35 else "VALUE" if pick.total_odds >= 8 else "SHARP"
    lines = [
        f"🔑 <b>NETRATTLER PROP BUILDER</b>",
        f"<b>{pick.style} · {pick.variant}</b>",
        sep,
    ]
    if same_match and pick.legs:
        lines.append(f"⚽ <b>{pick.legs[0].match}</b>")
    for i, leg in enumerate(pick.legs, 1):
        icon = CATEGORY_ICON.get(leg.category, "🎯")
        match_suffix = "" if same_match else f" · {leg.match}"
        source_note = "Pinnacle" if "pinnacle" in norm(leg.source) else leg.source.split(":")[0]
        prob = int(round(float(leg.probability or 0) * 100))
        fair = (1.0 / max(0.01, float(leg.probability or 0))) if leg.probability else 0
        fair_txt = f"{fair:.2f}" if fair and fair < 99 else "?"
        lines.append(f"{i}. {icon} <b>{leg.player}</b> — {_v31_market_label(leg)}{match_suffix}")
        lines.append(f"   Quote {leg.odds:.2f} · Fair {fair_txt} · Prob {prob}% · {source_note}")
        lines.append(f"   ↳ {_v31_reason(leg)}")
    lines.extend([
        sep,
        f"💰 Gesamt-Quote: <b>{pick.total_odds:.2f}</b>",
        f"🔥 Einsatz: <b>{pick.stake:.2f} Units</b>",
        f"🧠 <b>PROP BUILDER READ:</b> {read} · {risk}",
        "<i>Fokus: echte Spielerprops, Markt-Edge, Rollenprofil, keine generischen Team-Combos.</i>",
    ])
    return "\n".join(lines)
