#!/usr/bin/env python3
"""Screenshot-derived NETRATTLER Prop Builder styles.

This module is a surgical runtime layer over netrattler_builder_engine. It keeps
REAL_ODDS_ONLY and the existing guard, but replaces the noisy "one of every
legacy style" output with a small set of patterns reconstructed from the user's
Aystar / Tips-Bible / Nate / GodTipster screenshot library.

Important pricing rule: same-game builder legs are correlated. Individual leg
odds are observed bookmaker prices; their mathematical product is used only as
an internal selection/risk heuristic and is NEVER published as a bookmaker
Bet-Builder quote. The message explicitly asks for the live builder price.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import netrattler_builder_engine as builder

_INSTALLED = False
_ORIG_BUILD = builder.build_builder_picks
_ORIG_FORMAT = builder.format_builder_message
_ORIG_TO_ROW = builder.BuilderPick.to_row
_ORIG_VALID = builder.valid_builder


def _f(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _min_edge() -> float:
    return _f(os.getenv("NETRATTLER_BUILDER_MIN_LEG_EDGE", "2.0"), 2.0)


def _modelled(leg: builder.PropLeg, min_edge: Optional[float] = None) -> bool:
    threshold = _min_edge() if min_edge is None else float(min_edge)
    return bool(not leg.estimated and leg.odds > 1 and leg.edge >= threshold)


def _strength(leg: builder.PropLeg) -> float:
    edge = max(0.0, min(30.0, float(leg.edge or 0.0))) / 100.0
    return (
        max(0.0, min(0.95, leg.probability)) * 0.57
        + max(0.0, min(1.0, leg.quality)) * 0.28
        + edge * 0.15
    )


def _valid_builder(legs, min_legs=2, max_legs=6):
    if not _ORIG_VALID(legs, min_legs=min_legs, max_legs=max_legs):
        return False
    by_player: Dict[str, set] = {}
    for leg in legs:
        by_player.setdefault(builder.norm(leg.player), set()).add(leg.category)
    for cats in by_player.values():
        if "score" in cats and "assist" in cats:
            return False
    return True


def _low_line(leg: builder.PropLeg) -> bool:
    limits = {
        "shots": 1.5,
        "sot": 1.5,
        "fouls": 1.5,
        "fouls_won": 1.5,
        "tackles": 2.0,
        "tackles_committed": 2.0,
        "tackles_received": 2.0,
        "offsides": 1.5,
        "goalkeeper_saves": 3.0,
    }
    limit = limits.get(leg.category)
    return bool(limit is not None and leg.line <= limit and leg.probability >= 0.53 and _modelled(leg))


def _pick_distinct(legs: Sequence[builder.PropLeg], count: int) -> List[builder.PropLeg]:
    out: List[builder.PropLeg] = []
    used = set()
    for leg in sorted(legs, key=_strength, reverse=True):
        key = builder.norm(leg.player)
        if not key or key in used:
            continue
        used.add(key)
        out.append(leg)
        if len(out) >= count:
            break
    return out


def _tips_bible(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)

    for _, rows in by_match.items():
        volume = sorted([x for x in rows if _low_line(x)], key=_strength, reverse=True)
        anchors = sorted(
            [x for x in rows if x.category == "score_assist" and x.probability >= 0.35 and _modelled(x)],
            key=_strength,
            reverse=True,
        )
        if len(volume) < 3:
            continue

        def pick_volume(max_legs: int, min_prob: float) -> List[builder.PropLeg]:
            chosen: List[builder.PropLeg] = []
            per_player: Dict[str, int] = {}
            per_cat: Dict[str, int] = {}
            for leg in volume:
                if leg.probability < min_prob:
                    continue
                pkey = builder.norm(leg.player)
                if per_player.get(pkey, 0) >= 2 or per_cat.get(leg.category, 0) >= 4:
                    continue
                if not _valid_builder(chosen + [leg], min_legs=1, max_legs=12):
                    continue
                chosen.append(leg)
                per_player[pkey] = per_player.get(pkey, 0) + 1
                per_cat[leg.category] = per_cat.get(leg.category, 0) + 1
                if len(chosen) >= max_legs:
                    break
            return chosen

        safe = pick_volume(3, 0.62)
        value = pick_volume(5, 0.56)
        deep8 = pick_volume(8, 0.53)
        deep9 = pick_volume(9, 0.53)
        if anchors:
            anchor = anchors[0]
            deep8 = ([anchor] + [x for x in deep8 if x.key() != anchor.key()])[:8]
            deep9 = ([anchor] + [x for x in deep9 if x.key() != anchor.key()])[:9]

        configs = (
            (safe, 3, "SAFE LOW-LINE 3L", 2.0, 7.5, 0.75),
            (value, 5, "VALUE LOW-LINE 5L", 3.0, 16.0, 0.50),
            (deep8, 8, "DEEP LOW-LINE 8L", 5.0, 35.0, 0.25),
            (deep9, 9, "DEEP LOW-LINE 9L", 7.0, 55.0, 0.10),
        )
        for legs, size, variant, min_product, max_product, stake in configs:
            if len(legs) != size:
                continue
            pick = builder._make_builder("TIPS BIBLE", variant, legs, match_date, stake)
            if pick and min_product <= pick.total_odds <= max_product:
                out.append(pick)
    return out


def _nate_category(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    labels = {
        "shots": "SHOTS", "sot": "SOT", "fouls": "FOULS", "fouls_won": "FOULS WON",
        "tackles": "TACKLES", "tackles_committed": "TACKLES", "tackles_received": "TACKLES RECEIVED",
        "goalkeeper_saves": "KEEPER SAVES",
    }
    groups: Dict[Tuple[str, str], List[builder.PropLeg]] = {}
    for leg in props:
        if leg.category in labels and _modelled(leg):
            groups.setdefault((leg.match, leg.category), []).append(leg)
    for (_, category), rows in groups.items():
        ranked = _pick_distinct(rows, 6)
        for size, tier, cap in ((3, "SAFE", 18.0), (4, "VALUE", 22.0), (5, "VALUE", 35.0), (6, "HIGH", 65.0)):
            if len(ranked) < size:
                continue
            if tier == "SAFE" and any(x.probability < 0.60 for x in ranked[:size]):
                continue
            pick = builder._make_builder("NATE CATEGORY", f"{labels[category]} {tier} {size}L", ranked[:size], match_date, 0.5)
            if pick and pick.total_odds <= cap:
                out.append(pick)
    return out


def _godtipster_profiles(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    groups: Dict[Tuple[str, str], List[builder.PropLeg]] = {}
    for leg in props:
        if _modelled(leg):
            groups.setdefault((leg.match, builder.norm(leg.player)), []).append(leg)
    for _, rows in groups.items():
        best: Dict[str, builder.PropLeg] = {}
        for leg in sorted(rows, key=_strength, reverse=True):
            best.setdefault(leg.category, leg)
        profiles = (
            ("ATTACK", [best.get("score_assist"), best.get("sot"), best.get("shots")]),
            ("ATTACK + FOUL MAGNET", [best.get("score_assist"), best.get("sot"), best.get("fouls_won")]),
            ("SHOTS + SOT", [best.get("shots"), best.get("sot")]),
            ("ALL-ROUND VOLUME", [best.get("shots"), best.get("sot"), best.get("fouls_won"), best.get("tackles") or best.get("tackles_committed")]),
            ("MIDFIELD", [best.get("fouls"), best.get("fouls_won"), best.get("tackles") or best.get("tackles_committed")]),
            ("DISCIPLINE", [best.get("yellow_cards"), best.get("fouls")]),
        )
        for variant, maybe in profiles:
            legs = [x for x in maybe if x is not None]
            if len(legs) < 2 or not _valid_builder(legs):
                continue
            pick = builder._make_builder("GODTIPSTER PROFILE", variant, legs, match_date, 0.35)
            if pick and pick.total_odds <= (35.0 if variant == "DISCIPLINE" else 18.0):
                out.append(pick)
    return out


def _nate_alt_lines(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)
    allowed = {"shots", "sot", "fouls", "fouls_won", "tackles", "tackles_committed", "goalkeeper_saves"}
    for _, rows in by_match.items():
        groups: Dict[Tuple[str, str], List[builder.PropLeg]] = {}
        for leg in rows:
            if leg.category in allowed and _modelled(leg):
                groups.setdefault((builder.norm(leg.player), leg.category), []).append(leg)
        for (player_key, _), lines in groups.items():
            by_line: Dict[float, builder.PropLeg] = {}
            for leg in sorted(lines, key=_strength, reverse=True):
                by_line.setdefault(round(leg.line, 3), leg)
            variants = sorted(by_line.values(), key=lambda x: x.line)
            if len(variants) < 2:
                continue
            supports = sorted(
                [x for x in rows if builder.norm(x.player) != player_key and x.category in allowed and _modelled(x)],
                key=_strength,
                reverse=True,
            )
            if not supports:
                continue
            support = supports[0]
            for leg in variants[:3]:
                tier = "SAFE" if leg.probability >= 0.68 else "VALUE" if leg.probability >= 0.52 else "HIGH"
                pick = builder._make_builder("NATE ALT-LINE", f"{tier} {leg.line:g}+", [leg, support], match_date, 0.35)
                if pick and pick.total_odds <= 20.0:
                    out.append(pick)
    return out


def _aystar_booking(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    cards = [x for x in props if x.category == "yellow_cards" and _modelled(x)]
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in cards:
        by_match.setdefault(leg.match, []).append(leg)
    for _, rows in by_match.items():
        ranked = _pick_distinct(rows, 4)
        for size, variant, cap in ((2, "SAME GAME 2L", 25.0), (3, "SAME GAME 3L", 55.0), (4, "SAME GAME 4L", 100.0)):
            if len(ranked) >= size:
                pick = builder._make_builder("AYSTAR BOOKING", variant, ranked[:size], match_date, 0.20)
                if pick and pick.total_odds <= cap:
                    out.append(pick)
    best_by_match: Dict[str, builder.PropLeg] = {}
    for leg in sorted(cards, key=_strength, reverse=True):
        best_by_match.setdefault(builder.norm(leg.match), leg)
    cross = list(best_by_match.values())
    for size, cap in ((3, 60.0), (4, 120.0)):
        if len(cross) >= size:
            pick = builder._make_builder("AYSTAR BOOKING", f"CROSS MATCH {size}L", cross[:size], match_date, 0.10)
            if pick and pick.total_odds <= cap:
                out.append(pick)
    return out


def _aystar_mix(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    out: List[builder.BuilderPick] = []
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)
    for _, rows in by_match.items():
        attack = sorted([x for x in rows if x.category == "score_assist" and _modelled(x)], key=_strength, reverse=True)
        cards = _pick_distinct([x for x in rows if x.category == "yellow_cards" and _modelled(x)], 4)
        configs = (
            (attack[:1] + cards[:2], 3, "ATTACK + 2 BOOKED 3L", 45.0),
            (attack[:2] + cards[:2], 4, "2 ATTACK + 2 BOOKED 4L", 100.0),
        )
        for legs, size, variant, cap in configs:
            if len(legs) != size or not _valid_builder(legs):
                continue
            pick = builder._make_builder("AYSTAR MIX", variant, legs, match_date, 0.10)
            if pick and pick.total_odds <= cap:
                out.append(pick)
    return out


def _library_same_game_mix(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    """Library-style same-game mixes using only real/modelled legs.

    Examples mirrored from the user's reference set:
    attack/scorer/assist + cards, player volume + fouls, player + corners/teamline.
    Same-game combined price is never synthesized for publication.
    """
    out: List[builder.BuilderPick] = []
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in props:
        if _modelled(leg):
            by_match.setdefault(leg.match, []).append(leg)

    attack_cats = {"score", "assist", "score_assist", "shots", "sot"}
    contact_cats = {"fouls", "fouls_won", "tackles", "tackles_committed", "tackles_received", "yellow_cards"}
    team_cats = {"team_cards", "match_cards", "team_corners", "corners", "match_corners", "btts", "btts_ht", "over_goals", "match_goals"}

    for match, rows in by_match.items():
        attack = sorted([x for x in rows if x.category in attack_cats], key=_strength, reverse=True)
        contact = sorted([x for x in rows if x.category in contact_cats], key=_strength, reverse=True)
        team = sorted([x for x in rows if x.category in team_cats], key=_strength, reverse=True)

        configs = []
        if attack and team:
            configs.append(("PLAYER + TEAMLINE 2L", [attack[0], team[0]], 0.50))
        if attack and contact:
            configs.append(("ATTACK + CONTACT 2L", [attack[0], contact[0]], 0.50))
        if attack and contact and team:
            configs.append(("ATTACK + CONTACT + TEAMLINE 3L", [attack[0], contact[0], team[0]], 0.30))

        scorer = next((x for x in attack if x.category in {"score", "assist", "score_assist"}), None)
        cards = next((x for x in team if x.category in {"team_cards", "match_cards"}), None)
        second_attack = next((x for x in attack if scorer is None or x.key() != scorer.key()), None)
        if scorer and cards and second_attack:
            configs.append(("SCORER/ASSIST + CARDS + ATTACK 3L", [scorer, cards, second_attack], 0.25))

        corner = next((x for x in team if x.category in {"team_corners", "corners", "match_corners"}), None)
        player_volume = next((x for x in attack if x.category in {"shots", "sot"}), None)
        if corner and player_volume:
            configs.append(("PLAYER + CORNERS 2L", [player_volume, corner], 0.40))

        seen = set()
        for variant, legs, stake in configs:
            key = tuple(sorted(x.key() for x in legs))
            if key in seen or len({x.key() for x in legs}) != len(legs):
                continue
            seen.add(key)
            if not _valid_builder(legs, min_legs=2, max_legs=4):
                continue
            pick = builder._make_builder("LIBRARY SAME GAME", variant, legs, match_date, stake)
            if pick:
                out.append(pick)
    return out


def _library_cross_match(props: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    """Library rule: cross-match builders use 2-5 DIFFERENT games.

    One real/modelled leg per game; mixed-market and same-category variants.
    REAL_ODDS_ONLY/model-edge guards remain unchanged.
    """
    eligible = [
        x for x in props
        if _modelled(x)
        and x.category in {
            "shots", "sot", "fouls", "fouls_won", "tackles",
            "tackles_committed", "tackles_received", "yellow_cards",
            "goalkeeper_saves", "score", "assist", "score_assist", "offsides",
        }
    ]
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in eligible:
        by_match.setdefault(builder.norm(leg.match), []).append(leg)

    best_per_match: List[builder.PropLeg] = []
    for rows in by_match.values():
        ranked = sorted(rows, key=_strength, reverse=True)
        if ranked:
            best_per_match.append(ranked[0])
    best_per_match.sort(key=_strength, reverse=True)

    out: List[builder.BuilderPick] = []
    configs = (
        (2, "CROSS 2 MATCHES", 12.0, 0.75),
        (3, "CROSS 3 MATCHES", 25.0, 0.50),
        (4, "CROSS 4 MATCHES", 60.0, 0.25),
        (5, "CROSS 5 MATCHES", 120.0, 0.10),
    )
    for size, label, max_odds, stake in configs:
        if len(best_per_match) < size:
            continue
        chosen: List[builder.PropLeg] = []
        used_cats = set()
        # First pass favors market diversity.
        for leg in best_per_match:
            if leg.category in used_cats:
                continue
            chosen.append(leg)
            used_cats.add(leg.category)
            if len(chosen) >= size:
                break
        # Fill remaining slots from other matches if categories repeat.
        if len(chosen) < size:
            used_matches = {builder.norm(x.match) for x in chosen}
            for leg in best_per_match:
                if builder.norm(leg.match) in used_matches:
                    continue
                chosen.append(leg)
                used_matches.add(builder.norm(leg.match))
                if len(chosen) >= size:
                    break
        if len(chosen) != size or len({builder.norm(x.match) for x in chosen}) != size:
            continue
        pick = builder._make_builder("LIBRARY CROSS MATCH", label, chosen, match_date, stake)
        if pick and pick.total_odds <= max_odds:
            out.append(pick)

    # Same-category cross-match variants like booking/shots/fouls accas.
    labels = {
        "yellow_cards": "BOOKINGS",
        "shots": "SHOTS",
        "sot": "SOT",
        "fouls": "FOULS",
        "fouls_won": "FOULS WON",
        "tackles": "TACKLES",
        "tackles_committed": "TACKLES",
        "goalkeeper_saves": "SAVES",
    }
    for cat, title in labels.items():
        per_match: List[builder.PropLeg] = []
        for rows in by_match.values():
            ranked = sorted([x for x in rows if x.category == cat], key=_strength, reverse=True)
            if ranked:
                per_match.append(ranked[0])
        per_match.sort(key=_strength, reverse=True)
        for size, cap in ((2, 18.0), (3, 40.0), (4, 80.0)):
            if len(per_match) < size:
                continue
            legs = per_match[:size]
            if len({builder.norm(x.match) for x in legs}) != size:
                continue
            pick = builder._make_builder(
                "LIBRARY CROSS MATCH",
                f"{title} {size} GAMES",
                legs,
                match_date,
                0.35 if size == 2 else 0.20,
            )
            if pick and pick.total_odds <= cap:
                out.append(pick)
    return out


def _pick_rank(pick: builder.BuilderPick) -> Tuple[float, float, float, float]:
    avg_q = sum(x.quality for x in pick.legs) / len(pick.legs)
    avg_p = sum(x.probability for x in pick.legs) / len(pick.legs)
    avg_e = sum(max(0.0, x.edge) for x in pick.legs) / len(pick.legs)
    diversity = len({x.category for x in pick.legs}) / len(pick.legs)
    style_bonus = {
        "TIPS BIBLE": 0.30,
        "GODTIPSTER PROFILE": 0.28,
        "NATE CATEGORY": 0.24,
        "NATE ALT-LINE": 0.20,
        "AYSTAR BOOKING": 0.16,
        "AYSTAR MIX": 0.15,
        "KEEPER SAVES": 0.10,
        "SAME PLAYER": 0.08,
        "PLAYER DUEL": 0.07,
        "CROSS MATCH PROP ACCA": 0.05,
    }.get(pick.style, 0.0)
    odds_penalty = max(0.0, math.log(max(1.0, pick.total_odds / 15.0))) * 0.10
    score = avg_q + avg_p * 0.22 + min(0.12, avg_e / 100.0 * 0.35) + diversity * 0.06 + style_bonus - odds_penalty
    return score, avg_p, avg_e, -pick.total_odds


def build_builder_picks(raw_props, match_contexts=None, match_date=None, max_builders=None):
    run_date = match_date or builder.date.today().isoformat()
    max_count = max_builders or builder.as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "30"), 30)
    props = builder.deduplicate_props(raw_props)
    allow_team = str(os.getenv("NETRATTLER_BUILDER_ALLOW_TEAM_MARKETS", "false")).lower() in {"1", "true", "yes", "on"}
    if not allow_team:
        props = [p for p in props if p.category in builder.PLAYER_CATEGORIES and p.category != "result"]
    props = [p for p in props if _modelled(p)]

    premium: List[builder.BuilderPick] = []
    premium += _tips_bible(props, run_date)
    premium += _nate_category(props, run_date)
    premium += _godtipster_profiles(props, run_date)
    premium += _nate_alt_lines(props, run_date)
    premium += _aystar_booking(props, run_date)
    premium += _aystar_mix(props, run_date)
    premium += _library_same_game_mix(props, run_date)
    premium += _library_cross_match(props, run_date)

    legacy = _ORIG_BUILD(raw_props, match_contexts, run_date, max_builders=max(30, max_count * 2))
    fallback_styles = {"KEEPER SAVES", "SAME PLAYER", "PLAYER DUEL", "CROSS MATCH PROP ACCA"}
    legacy = [
        p for p in legacy
        if p.style in fallback_styles
        and all(_modelled(x) for x in p.legs)
        and not any(x.estimated for x in p.legs)
    ]

    combined = premium + legacy
    seen = set()
    unique: List[builder.BuilderPick] = []
    for pick in combined:
        if pick.builder_id in seen:
            continue
        seen.add(pick.builder_id)
        unique.append(pick)
    unique.sort(key=_pick_rank, reverse=True)

    limits = {
        "TIPS BIBLE": 4, "GODTIPSTER PROFILE": 4, "NATE CATEGORY": 4,
        "NATE ALT-LINE": 4, "AYSTAR BOOKING": 3, "AYSTAR MIX": 2,
        "KEEPER SAVES": 2, "SAME PLAYER": 2, "PLAYER DUEL": 1,
        "CROSS MATCH PROP ACCA": 2,
        "LIBRARY SAME GAME": 4,
        "LIBRARY CROSS MATCH": 4,
    }
    out: List[builder.BuilderPick] = []
    style_count: Dict[str, int] = {}
    match_count: Dict[str, int] = {}
    max_per_match = builder.as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_MATCH", "8"), 8)

    for style in ("TIPS BIBLE", "GODTIPSTER PROFILE", "NATE CATEGORY", "NATE ALT-LINE", "AYSTAR BOOKING", "AYSTAR MIX", "LIBRARY SAME GAME", "LIBRARY CROSS MATCH"):
        for pick in unique:
            if pick.style != style:
                continue
            out.append(pick)
            style_count[style] = 1
            key = pick.legs[0].match if len({x.match for x in pick.legs}) == 1 else "CROSS"
            match_count[key] = match_count.get(key, 0) + 1
            break
        if len(out) >= max_count:
            return out

    selected = {x.builder_id for x in out}
    for pick in unique:
        if pick.builder_id in selected:
            continue
        limit = limits.get(pick.style, 1)
        if style_count.get(pick.style, 0) >= limit:
            continue
        key = pick.legs[0].match if len({x.match for x in pick.legs}) == 1 else "CROSS"
        if key != "CROSS" and match_count.get(key, 0) >= max_per_match:
            continue
        out.append(pick)
        selected.add(pick.builder_id)
        style_count[pick.style] = style_count.get(pick.style, 0) + 1
        match_count[key] = match_count.get(key, 0) + 1
        if len(out) >= max_count:
            break
    return out


def format_builder_message(pick: builder.BuilderPick) -> str:
    sep = "━" * 18
    same_match = len({x.match for x in pick.legs}) == 1
    lines = [f"🏗️ <b>NETRATTLER {pick.style}</b>", f"<b>{pick.variant}</b>", sep]
    if same_match:
        lines.append(f"⚽ <b>{pick.legs[0].match}</b>")
    for i, leg in enumerate(pick.legs, 1):
        icon = builder.CATEGORY_ICON.get(leg.category, "🎯")
        match_suffix = "" if same_match else f" · {leg.match}"
        lines.append(
            f"{i}. {icon} <b>{leg.player}</b> — {leg.market} @ {leg.odds:.2f}"
            f" · Edge {leg.edge:+.1f}%{match_suffix}"
        )
    lines.append(sep)
    if same_match:
        lines.append("💰 Builder-Quote: <b>live beim Bookmaker prüfen</b>")
        lines.append("🔒 Keine synthetische Produktquote für Same-Game-Builder")
        lines.append("🔥 Einsatz: <b>erst nach echter Builder-Quote</b>")
    else:
        lines.append(f"💰 Gesamt-Quote: <b>{pick.total_odds:.2f}</b>")
        lines.append(f"🔥 Einsatz: <b>{pick.stake:.2f} Units</b>")
    lines.append(f"🧠 Daten: {', '.join(dict.fromkeys(x.source.split(':')[0] for x in pick.legs))}")
    return "\n".join(lines)


def _to_row(self: builder.BuilderPick):
    row = _ORIG_TO_ROW(self)
    if len({x.match for x in self.legs}) == 1:
        row["total_odds"] = 0.0
        row["stake"] = 0.0
        row["estimated_odds"] = True
    return row


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    builder.valid_builder = _valid_builder
    builder.build_builder_picks = build_builder_picks
    builder.format_builder_message = format_builder_message
    builder.BuilderPick.to_row = _to_row
    _INSTALLED = True
