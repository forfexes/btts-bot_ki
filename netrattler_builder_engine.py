#!/usr/bin/env python3
"""
NETRATTLER Builder Engine
=========================

Pure, testable builder selection layer for football player props and match markets.

It creates data-driven builder families from a normalized prop pool:
- Multi-player shot ladders (1+ / 2+ / 3+)
- Underdog shot ladders when match/team context is available
- Shots-on-target trios
- Fouls and tackles ladders
- Attacking mixed builders (shots, SOT, score/assist)
- Corner fusion builders (player props + one corner leg)
- Balanced cross-match builders

FIX40 adds keeper ladders, full 1+/2+/3+/4+/5+/6+ prop ladders, same-player correlations, player duels, match-market builders, mixed same-game builders and cross-match prop accas.

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
    "goalkeeper_saves": "🧤",
    "double_chance": "🛡️",
    "match_cards": "🟨",
    "btts_ht": "⏱️⚽",
}

PLAYER_CATEGORIES = {
    "shots", "sot", "sot_outside_box", "shots_outside_box",
    "fouls", "fouls_won", "tackles", "tackles_committed",
    "tackles_received", "yellow_cards", "score", "first_scorer",
    "last_scorer", "assist", "score_assist", "result", "offsides",
    "goalkeeper_saves",
}

TEAM_CATEGORIES = {
    "team_corners", "corners", "match_corners",
    "team_shots", "match_sot", "match_goals",
    "team_cards", "match_cards", "btts", "btts_ht", "over_goals",
    "double_chance", "result", "half_goals_1st", "half_goals_2nd",
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
    edge: float = 0.0
    fair_odds: float = 0.0

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


def is_bookmaker_source(source: str) -> bool:
    s = norm(source).replace(" ", "")
    tokens = (
        "pinnacle", "kambi", "bet365", "1xbet", "oddspedia",
        "oddsapi", "oddspapi", "betfair", "unibet", "betsson",
        "nordicbet", "888", "sportsbook", "bookmaker", "observed",
    )
    return any(token.replace(" ", "") in s for token in tokens)


def max_sane_leg_odds(category: str) -> float:
    """Sanity ceiling for one observed decimal quote.

    This is not a value filter. It only prevents parser/unit mistakes (e.g.
    145.0 being treated as a normal BTTS/corner/result leg) from poisoning
    builders and multi-combos.
    """
    category = str(category or "").lower()
    caps = {
        "btts": 6.0, "btts_ht": 10.0, "over_goals": 8.0,
        "half_goals_1st": 10.0, "half_goals_2nd": 10.0,
        "result": 8.0, "double_chance": 5.0,
        "team_corners": 10.0, "corners": 10.0, "match_corners": 10.0,
        "team_cards": 12.0, "match_cards": 12.0,
        "team_shots": 12.0, "match_sot": 12.0, "match_goals": 10.0,
        "shots": 15.0, "sot": 15.0, "sot_outside_box": 20.0,
        "shots_outside_box": 20.0, "fouls": 20.0, "fouls_won": 20.0,
        "tackles": 20.0, "tackles_committed": 20.0, "tackles_received": 20.0,
        "yellow_cards": 25.0, "offsides": 20.0, "goalkeeper_saves": 20.0,
        "assist": 25.0, "score_assist": 30.0,
        "score": 35.0, "first_scorer": 50.0, "last_scorer": 50.0,
    }
    try:
        fallback = max(2.0, as_float(os.getenv("NETRATTLER_BUILDER_MAX_LEG_ODDS", "25.0"), 25.0))
    except Exception:
        fallback = 25.0
    return float(caps.get(category, fallback))


def max_sane_builder_odds(style: str, variant: str) -> float:
    """Style-aware total-odds ceiling.

    High-risk/lottery families keep a wide ceiling, while anything labelled
    SAFE/VALUE from match markets must remain a normal usable builder.
    """
    env_global = as_float(os.getenv("NETRATTLER_BUILDER_MAX_ODDS", "0"), 0.0)
    if env_global > 0:
        return env_global

    tag = f"{style} {variant}".upper()
    if any(x in tag for x in ("LOTTERY", "HIGH ODDS", "BOOKING LADDER", "HIGH LINE")):
        return max(100.0, as_float(os.getenv("NETRATTLER_BUILDER_LOTTERY_MAX_ODDS", "5000"), 5000.0))
    if any(x in tag for x in ("MATCH BUILDER", "TEAM BUILDER", "SAME MATCH AVAILABLE", "CORNER FUSION")):
        return max(10.0, as_float(os.getenv("NETRATTLER_BUILDER_STANDARD_MAX_ODDS", "75"), 75.0))
    return max(25.0, as_float(os.getenv("NETRATTLER_BUILDER_FALLBACK_MAX_ODDS", "250"), 250.0))


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
        "saves": "goalkeeper_saves",
        "keeper_saves": "goalkeeper_saves",
        "goalkeeper_save": "goalkeeper_saves",
        "goalkeeper_saves": "goalkeeper_saves",
        "cards_total": "match_cards",
        "total_cards": "match_cards",
        "match_cards": "match_cards",
        "double_chance": "double_chance",
        "btts_ht": "btts_ht",
    }.get(category, category)
    if not player or not match or not market or not category:
        return None
    if category not in PLAYER_CATEGORIES | TEAM_CATEGORIES:
        return None
    line = as_float(row.get("line"), market_line(market, 1.0))
    # Builder bets require a real offered bookmaker price. Never turn fair/model odds into a quote.
    odds = as_float(row.get("odds") or row.get("pinnacle_odds") or row.get("bookmaker_odds") or row.get("decimal_odds") or row.get("oddsYes") or row.get("odd") or row.get("price"))
    probability = probability_from_row(row)
    if odds <= 1 or odds > max_sane_leg_odds(category):
        return None
    quote_source = str(row.get("source") or row.get("_source") or row.get("bookmaker") or row.get("odds_source") or "")
    if not is_bookmaker_source(quote_source):
        return None
    estimated = bool(row.get("estimated") or row.get("estimated_odds"))
    if estimated:
        return None
    fair_odds = as_float(row.get("fair_odds")) or (1.0 / probability if probability > 0 else 0.0)

    # SAFE ROLLBACK: before the FIX36 strict-edge gate, real observed player
    # props were allowed into the Builder pool even when no independent player
    # model/history was available. V37 accidentally converted those to implied
    # probability -> 0% edge -> rejected 623/624 legs. Restore compatibility.
    # Only probabilities with explicit independent provenance may create model edge.
    # Raw bookmaker-derived "prob"/"probability" values (e.g. Pinnacle 95% of
    # implied probability) are market context, not an independent model signal.
    probability_source = norm(
        row.get("probability_source")
        or row.get("model_source")
        or row.get("history_source")
        or ""
    )
    has_independent_probability = (
        as_float(row.get("model_prob")) > 0
        or any(token in probability_source for token in (
            "model", "history", "empirical", "fbref", "statsbomb", "fotmob", "supabase"
        ))
    )
    edge = as_float(row.get("edge_pct") or row.get("edge"))
    if 0 < abs(edge) < 1:
        edge *= 100.0
    if edge == 0 and probability > 0 and has_independent_probability:
        edge = (probability * odds - 1.0) * 100.0
    elif not has_independent_probability:
        edge = 0.0  # do not pretend bookmaker-implied probability is model edge

    strict_edge = str(os.getenv("NETRATTLER_BUILDER_STRICT_EDGE", "false")).lower() in {"1", "true", "yes", "on"}
    if strict_edge:
        min_edge = as_float(os.getenv("NETRATTLER_BUILDER_MIN_LEG_EDGE", "2.0"), 2.0)
        max_edge = as_float(os.getenv("NETRATTLER_BUILDER_MAX_LEG_EDGE", "35.0"), 35.0)
        if edge < min_edge or edge > max_edge:
            return None
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
        source=quote_source[:80],
        kickoff=str(row.get("ko") or row.get("kickoff") or row.get("kickoff_at") or "")[:40],
        hit_rate=as_float(row.get("hit_rate")),
        games=as_int(row.get("games") or row.get("sb_games")),
        quality=quality_score(row),
        estimated=estimated,
        edge=round(edge, 2),
        fair_odds=round(fair_odds, 2),
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
    max_legs = max(max_legs, as_int(os.getenv("NETRATTLER_BUILDER_MAX_LEGS", "12"), 12))
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
    min_odds = max(
        as_float(os.getenv("NETRATTLER_BUILDER_MIN_ODDS", "1.75"), 1.75),
        as_float(os.getenv("NETRATTLER_PROP_BUILDER_MIN_ODDS", "0"), 0.0),
    )
    max_odds = max_sane_builder_odds(style, variant)
    if odds < min_odds or odds > max_odds:
        return None
    if any(x.estimated for x in legs):
        return None
    _strict_edge = str(os.getenv("NETRATTLER_BUILDER_STRICT_EDGE", "false")).lower() in {"1", "true", "yes", "on"}
    if _strict_edge and any(x.edge < as_float(os.getenv("NETRATTLER_BUILDER_MIN_LEG_EDGE", "2.0"), 2.0) for x in legs):
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
    """Same-match PAIR/TRIO ladders using only exact real bookmaker lines."""
    builders: List[BuilderPick] = []
    labels = {
        "shots": "SHOT LADDER", "sot": "SOT LADDER", "sot_outside_box": "OUTSIDE BOX SOT",
        "fouls": "FOUL PRESS", "fouls_won": "FOUL MAGNET", "tackles": "TACKLES",
        "tackles_committed": "TACKLES", "tackles_received": "TACKLES RECEIVED",
        "yellow_cards": "BOOKING LADDER", "goalkeeper_saves": "KEEPER SAVES",
    }
    groups: Dict[Tuple[str, str, float], List[PropLeg]] = {}
    for leg in props:
        if leg.category in labels and not leg.estimated and leg.odds > 1:
            groups.setdefault((leg.match, leg.category, leg.line), []).append(leg)
    for (match, category, line), candidates in groups.items():
        base = _best_distinct_players(candidates, 3)
        for size in ([2, 3] if len(base) >= 3 else [2] if len(base) == 2 else []):
            chosen = base[:size]
            risk = "SAFE" if line <= 1 else "VALUE" if line <= 2 else "HIGH" if line <= 4 else "LOTTERY"
            pick = _make_builder(labels[category], f"{risk} {line:g}+ · {size}L", chosen, match_date, 0.5)
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
    """Build robust same-match builders from real quoted player props.

    The old version only tried a single prefix of the ranked legs. A couple of
    high-priced scorer/SOT legs could therefore push the combined price above
    the sane builder ceiling and yield zero builders despite dozens of valid
    same-match legs. This version searches several real-leg combinations and
    keeps the best usable pairs/triples without inventing prices.
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
            key=lambda x: (x.quality, x.probability, -x.odds),
            reverse=True,
        )

        # First preserve category diversity for the classic 2-5 leg builder.
        selected: List[PropLeg] = []
        used_keys = set()
        used_categories = set()
        for leg in ordered:
            key = (norm(leg.player), leg.category)
            if key in used_keys or leg.category in used_categories:
                continue
            selected.append(leg)
            used_keys.add(key)
            used_categories.add(leg.category)
            if len(selected) >= 5:
                break

        if len(selected) < 2:
            for leg in ordered:
                key = (norm(leg.player), leg.category)
                if key in used_keys:
                    continue
                selected.append(leg)
                used_keys.add(key)
                if len(selected) >= 5:
                    break

        seen_ids = set()
        for size in range(2, min(5, len(selected)) + 1):
            pick = _make_builder(
                "SAME MATCH AVAILABLE",
                f"{size} REAL LEGS",
                selected[:size],
                match_date,
                0.5 if size <= 3 else 0.25,
            )
            if pick and pick.builder_id not in seen_ids:
                builders.append(pick)
                seen_ids.add(pick.builder_id)

        # Robust fallback: search real pairs/triples instead of assuming that
        # the first ranked legs form a sane combined price. This is especially
        # important when the pool is mostly SOT + anytime-goalscorer markets.
        pool = ordered[:24]
        pair_candidates = []
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                if (norm(a.player), a.category, a.line) == (norm(b.player), b.category, b.line):
                    continue
                if not valid_builder([a, b], min_legs=2):
                    continue
                product = a.odds * b.odds
                if product < 1.75 or product > max_sane_builder_odds("SAME MATCH AVAILABLE", "SAFE PAIR"):
                    continue
                score = (a.quality + b.quality, a.probability + b.probability, -product)
                pair_candidates.append((score, [a, b]))
        pair_candidates.sort(key=lambda row: row[0], reverse=True)

        for _, legs in pair_candidates[:4]:
            pick = _make_builder(
                "SAME MATCH AVAILABLE",
                "SAFE REAL PAIR",
                legs,
                match_date,
                0.5,
            )
            if pick and pick.builder_id not in seen_ids:
                builders.append(pick)
                seen_ids.add(pick.builder_id)
                if len(seen_ids) >= 4:
                    break

        # Try a practical 3-leg combination from the best successful pair.
        if pair_candidates:
            base = list(pair_candidates[0][1])
            for extra in pool:
                if extra in base:
                    continue
                candidate = base + [extra]
                if not valid_builder(candidate, min_legs=3):
                    continue
                pick = _make_builder(
                    "SAME MATCH AVAILABLE",
                    "3 REAL LEGS",
                    candidate,
                    match_date,
                    0.35,
                )
                if pick and pick.builder_id not in seen_ids:
                    builders.append(pick)
                    seen_ids.add(pick.builder_id)
                    break

    return builders


def _same_game_narratives(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Screenshot-inspirierte Same-Game-Builder mit einer klaren Match-Hypothese."""
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
    High Odds Booking Ladder — High-Odds:
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
            (4, "4× BOOKED HIGH",   50.0,  800.0, 0.10),
            (5, "5× BOOKED LOTTERY",   200.0, 5000.0, 0.05),
        ]:
            if len(legs_pool) >= size:
                pick = _make_builder("BOOKING LADDER", label, legs_pool[:size], match_date, stake)
                if pick and min_odds <= pick.total_odds:
                    builders.append(pick)

    return builders


def _fouls_tackles_combo_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    Fouls + Tackles Combo — High-Odds (Screenshot: Haaland 3+ Fouls + Konsa 4+ Tackles = 170/1)
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
                if pick and 8.0 <= pick.total_odds:
                    builders.append(pick)
                    break

        # High-Line Variante (3+ Fouls, 4+ Tackles wie Screenshot)
        hi_fouls = [_derive_lower_line(l, 3, "3+ Fouls Committed", 0.25) for l in fouls[:2]]
        hi_tackles = [_derive_lower_line(l, 3, "3+ Tackles Committed", 0.25) for l in tackles[:2]]
        selected_hi = [l for l in hi_fouls + hi_tackles if l is not None]
        if len(selected_hi) >= 2:
            pick = _make_builder("FOULS + TACKLES", "HIGH LINE FOUL+TACKLE",
                                 selected_hi[:3], match_date, 0.1)
            if pick and 30.0 <= pick.total_odds:
                builders.append(pick)

    return builders


def _jk_multi_shot_builder(
    props: Sequence[PropLeg], match_date: str
) -> List[BuilderPick]:
    """
    High-Odds Multi-Shot Builder — Screenshot (France vs Spain):
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
    Full Profile Builder — High-Odds (Screenshot England vs Argentina):
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
                    if pick and 6.0 <= pick.total_odds:
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
                if pick and 10.0 <= pick.total_odds:
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
                if pick and 4.0 <= pick.total_odds:
                    builders.append(pick)
                    break
    return builders



def _goalkeeper_save_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Keeper ladders/pairs from real offered 2+/3+/4+/5+/6+ save lines."""
    out: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        if leg.category == "goalkeeper_saves":
            by_match.setdefault(leg.match, []).append(leg)
    for match, legs in by_match.items():
        # One best real quote per keeper/line.
        for line in sorted({x.line for x in legs}):
            same_line = _best_distinct_players([x for x in legs if x.line == line], 2)
            if len(same_line) == 2:
                risk = "SAFE" if line <= 3 else "VALUE" if line <= 4 else "HIGH" if line <= 5 else "LOTTERY"
                pick = _make_builder("KEEPER SAVES", f"{risk} {line:g}+", same_line, match_date, 0.5)
                if pick:
                    out.append(pick)
        # Mixed keeper lines when two keepers have different best-value thresholds.
        best_by_keeper: Dict[str, PropLeg] = {}
        for leg in sorted(legs, key=lambda x: (x.edge, x.quality, x.probability), reverse=True):
            best_by_keeper.setdefault(norm(leg.player), leg)
        pair = list(best_by_keeper.values())[:2]
        if len(pair) == 2:
            pick = _make_builder("KEEPER SAVES", "BEST VALUE PAIR", pair, match_date, 0.5)
            if pick:
                out.append(pick)
    return out


def _same_player_correlation_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Same-player profiles such as booked+fouls and shots+fouls-won+tackles."""
    out: List[BuilderPick] = []
    groups: Dict[Tuple[str, str], List[PropLeg]] = {}
    for leg in props:
        if leg.player and leg.category in {"shots", "sot", "fouls", "fouls_won", "tackles", "tackles_committed", "yellow_cards"}:
            groups.setdefault((leg.match, norm(leg.player)), []).append(leg)
    for (_, _), legs in groups.items():
        best: Dict[str, PropLeg] = {}
        for leg in sorted(legs, key=lambda x: (x.edge, x.quality), reverse=True):
            best.setdefault(leg.category, leg)
        profiles = [
            ("BOOKED + FOULS", [best.get("yellow_cards"), best.get("fouls")]),
            ("SHOT + FOUL MAGNET", [best.get("shots"), best.get("fouls_won")]),
            ("FULL PLAYER PROFILE", [best.get("shots"), best.get("fouls_won"), best.get("tackles") or best.get("tackles_committed")]),
        ]
        for variant, maybe in profiles:
            chosen = [x for x in maybe if x is not None]
            if len(chosen) >= 2:
                pick = _make_builder("SAME PLAYER", variant, chosen, match_date, 0.35)
                if pick:
                    out.append(pick)
    return out


def _long_fouls_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """4-9 leg same-game foul builders, preserving only independently qualified legs."""
    out: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    for leg in props:
        if leg.category in {"fouls", "fouls_won"}:
            by_match.setdefault(leg.match, []).append(leg)
    for match, legs in by_match.items():
        ranked = sorted(legs, key=lambda x: (x.edge, x.quality, x.probability), reverse=True)
        selected: List[PropLeg] = []
        seen = set()
        for leg in ranked:
            key = (norm(leg.player), leg.category)
            if key in seen:
                continue
            seen.add(key); selected.append(leg)
            if len(selected) == 9:
                break
        for n in (4, 6, 9):
            if len(selected) >= n:
                pick = _make_builder("FOULS BUILDER", f"{n} LEGS", selected[:n], match_date, 0.2)
                if pick:
                    out.append(pick)
    return out



def _match_market_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Same-game builders from team/match markets plus optional qualified player legs.

    Supports the screenshot structures BTTS, double chance, goals/cards and player props.
    Only real quoted, positive-edge legs have survived normalize_prop at this point.
    """
    out: List[BuilderPick] = []
    by_match: Dict[str, List[PropLeg]] = {}
    team_families = {"btts", "btts_ht", "over_goals", "half_goals_1st", "half_goals_2nd",
                     "double_chance", "result", "team_cards", "match_cards", "team_shots",
                     "team_corners", "corners", "match_corners"}
    player_families = {"shots", "sot", "fouls", "fouls_won", "tackles",
                       "tackles_committed", "yellow_cards", "goalkeeper_saves",
                       "score", "assist", "score_assist"}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)
    for match, legs in by_match.items():
        team = sorted([x for x in legs if x.category in team_families],
                      key=lambda x: (x.edge, x.quality, x.probability), reverse=True)
        players = sorted([x for x in legs if x.category in player_families],
                         key=lambda x: (x.edge, x.quality, x.probability), reverse=True)
        # one leg per team-market family, so we do not stack duplicate lines blindly
        distinct_team: List[PropLeg] = []
        seen_fam = set()
        for leg in team:
            if leg.category in seen_fam:
                continue
            seen_fam.add(leg.category); distinct_team.append(leg)
        if len(distinct_team) >= 2:
            for n, label in ((2, "SAFE"), (3, "VALUE"), (4, "HIGH")):
                if len(distinct_team) >= n:
                    pick = _make_builder("MATCH BUILDER", label, distinct_team[:n], match_date, 0.5)
                    if pick: out.append(pick)
        # Mixed same-game: team narrative + player props. Avoid duplicate player/category.
        mixed = distinct_team[:2]
        used = set()
        for leg in players:
            k=(norm(leg.player), leg.category)
            if k in used: continue
            used.add(k); mixed.append(leg)
            if len(mixed) >= 8: break
        for n, label in ((4, "MIXED SAFE"), (6, "MIXED VALUE"), (8, "MIXED HIGH")):
            if len(mixed) >= n:
                pick = _make_builder("SAME GAME MIXED", label, mixed[:n], match_date, 0.25)
                if pick: out.append(pick)
    return out


def _cross_match_prop_accas(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Cross-match prop accumulators: one independently qualified player prop per match."""
    allowed = {"shots", "sot", "fouls", "fouls_won", "tackles", "tackles_committed",
               "goalkeeper_saves", "yellow_cards", "score", "assist", "score_assist"}
    grouped: Dict[str, List[PropLeg]] = {}
    for leg in [x for x in props if x.category in allowed]:
        grouped.setdefault(norm(leg.match), []).append(leg)
    best_by_match: Dict[str, PropLeg] = {}
    for key, legs in grouped.items():
        # Prefer a strong but usable real price. If every leg is long odds, keep
        # the best-quality one and let _make_builder's sanity ceiling decide.
        practical = [x for x in legs if 1.15 < x.odds <= 6.0]
        source = practical or legs
        best_by_match[key] = sorted(
            source, key=lambda x: (x.quality, x.probability, x.edge, -x.odds), reverse=True
        )[0]
    ranked = sorted(
        best_by_match.values(),
        key=lambda x: (x.quality, x.probability, -x.odds),
        reverse=True,
    )
    out=[]
    for n, label in ((2,"DOUBLE"),(3,"TRIPLE"),(4,"4-FOLD"),(5,"5-FOLD"),(6,"6-FOLD")):
        if len(ranked) >= n:
            pick=_make_builder("CROSS MATCH PROP ACCA", label, ranked[:n], match_date, 0.25)
            if pick: out.append(pick)
    return out


def _correlated_duel_builders(props: Sequence[PropLeg], match_date: str) -> List[BuilderPick]:
    """Two-player duel: each player's booked + fouls committed when all four real lines exist."""
    out=[]
    by_match: Dict[str, Dict[str, Dict[str, PropLeg]]] = {}
    for leg in props:
        if leg.category not in {"yellow_cards", "fouls"} or not leg.player:
            continue
        slot=by_match.setdefault(leg.match,{}).setdefault(norm(leg.player),{})
        old=slot.get(leg.category)
        if old is None or (leg.edge,leg.quality)>(old.edge,old.quality): slot[leg.category]=leg
    for match, players in by_match.items():
        complete=[]
        for _, cats in players.items():
            if "yellow_cards" in cats and "fouls" in cats:
                complete.append((cats["yellow_cards"].quality+cats["fouls"].quality, cats))
        complete.sort(key=lambda x:x[0], reverse=True)
        if len(complete)>=2:
            legs=[]
            for _,cats in complete[:2]: legs.extend([cats["yellow_cards"],cats["fouls"]])
            pick=_make_builder("PLAYER DUEL", "2x BOOKED + FOULS", legs, match_date, 0.20)
            if pick: out.append(pick)
    return out

def build_builder_picks(
    raw_props: Sequence[Dict[str, Any]],
    match_contexts: Optional[Sequence[Dict[str, Any]]] = None,
    match_date: Optional[str] = None,
    max_builders: Optional[int] = None,
) -> List[BuilderPick]:
    props = deduplicate_props(raw_props)
    run_date = match_date or date.today().isoformat()
    max_count = max_builders or as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "30"), 30)

    # Stable production default: Prop Builder is PLAYER-PROP only.
    # Team/match markets (BTTS, goals, corners, 1X2) already have their own
    # single-tip + multi-combo pipeline and must not leak into the Player Builder.
    # They can be re-enabled later behind an explicit opt-in once regression-tested.
    _allow_team = str(os.getenv("NETRATTLER_BUILDER_ALLOW_TEAM_MARKETS", "false")).lower() in {"1", "true", "yes", "on"}
    if not _allow_team:
        props = [p for p in props if p.category in PLAYER_CATEGORIES and p.category != "result"]

    # A known negative edge is never a publishable builder leg. edge=0 remains
    # allowed in COMPAT mode only for real bookmaker rows lacking an independent
    # player model/history signal.
    props = [p for p in props if p.edge >= 0]

    candidates: List[BuilderPick] = []
    candidates.extend(_shot_ladders(props, match_contexts or [], run_date))
    candidates.extend(_goalkeeper_save_builders(props, run_date))
    candidates.extend(_same_player_correlation_builders(props, run_date))
    candidates.extend(_long_fouls_builders(props, run_date))
    candidates.extend(_correlated_duel_builders(props, run_date))
    candidates.extend(_match_market_builders(props, run_date))
    candidates.extend(_cross_match_prop_accas(props, run_date))
    candidates.extend(_category_trios(props, run_date))
    candidates.extend(_mixed_builders(props, run_date))
    candidates.extend(_same_match_available_builders(props, run_date))
    candidates.extend(_same_game_narratives(props, run_date))
    candidates.extend(_cross_match_builder(props, run_date))
    # Team & Korrelations-Builder
    candidates.extend(_team_correlation_builders(props, run_date))
    candidates.extend(_goalscorer_combo_builder(props, run_date))
    # High-Odds High-Odds Builder
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
        if match_key != "CROSS" and match_counts.get(match_key, 0) >= as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_MATCH", "30"), 30):
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
        "btts": "BTTS YES", "over25": "Over 2.5 Tore", "combo": "BTTS + Over 2.5",
        "btts_ht": "BTTS HT", "over15_ht": "Over 1.5 HT", "corners": "Ecken",
        "shots": "Schüsse", "cards": "Karte", "goals": "Tor",
    }
    same_match = len({x.match for x in pick.legs}) == 1
    if same_match and pick.legs:
        lines.append(f"⚽ <b>{pick.legs[0].match}</b>")
    for index, leg in enumerate(pick.legs, 1):
        icon = CATEGORY_ICON.get(leg.category, "🎯")
        match_suffix = "" if same_match else f" · {leg.match}"
        source_note = " ~" if leg.estimated else (f" · Edge {leg.edge:+.1f}%" if abs(leg.edge) >= 0.1 else " · echte Quote")
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
    ])
    return "\n".join(lines)


def _supabase_headers(key: str, prefer: str = "resolution=merge-duplicates,return=minimal") -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def builder_pick_exists(pick: BuilderPick, supabase_url: str, supabase_key: str) -> Optional[bool]:
    if not supabase_url or not supabase_key:
        return None
    base = supabase_url.rstrip("/")
    try:
        existing = requests.get(
            f"{base}/rest/v1/netrattler_builder_picks",
            headers=_supabase_headers(supabase_key, "return=representation"),
            params={"builder_id": f"eq.{pick.builder_id}", "select": "builder_id", "limit": "1"},
            timeout=8,
        )
        if not existing.ok:
            return None
        return bool(existing.json())
    except Exception:
        return None


def persist_builder_pick(
    pick: BuilderPick,
    supabase_url: str,
    supabase_key: str,
    check_existing: bool = True,
) -> Optional[bool]:
    """Return True for a newly stored pick, False if it exists, None on DB failure/offline."""
    if not supabase_url or not supabase_key:
        return None
    base = supabase_url.rstrip("/")
    try:
        if check_existing:
            exists = builder_pick_exists(pick, supabase_url, supabase_key)
            if exists is True:
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
        _strict = str(os.getenv("NETRATTLER_BUILDER_STRICT_EDGE", "false")).lower() in {"1", "true", "yes", "on"}
        logger(f"MASTER BUILDER mode={'STRICT_EDGE' if _strict else 'COMPAT_REAL_ODDS'}")
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
        # Check duplicate before Telegram, but write only after a confirmed send.
        # A Telegram 429 must never create a DB row that blocks the retry next run.
        exists = builder_pick_exists(pick, supabase_url, supabase_key)
        if exists is True:
            if logger:
                logger(f"MASTER BUILDER duplicate skipped: {pick.builder_id}")
            continue
        try:
            send_result = send_message(format_builder_message(pick))
            if send_result is None or send_result is False:
                if logger:
                    logger(f"MASTER BUILDER send failed/no message_id: {pick.style} {pick.variant}")
                continue

            persisted = persist_builder_pick(
                pick, supabase_url, supabase_key, check_existing=False
            )
            sent += 1
            if logger:
                logger(
                    f"MASTER BUILDER {pick.style} {pick.variant}: "
                    f"{pick.leg_count}L @ {pick.total_odds:.2f} | DB={persisted}"
                )
        except Exception as exc:
            if logger:
                logger(f"MASTER BUILDER send failed: {exc}")
    return sent, picks


__all__ = [
    "PropLeg",
    "BuilderPick",
    "build_builder_picks",
    "format_builder_message",
    "builder_pick_exists",
    "persist_builder_pick",
    "run_builder_engine",
    "market_line",
    "quality_score",
    "underdog_team",
]
