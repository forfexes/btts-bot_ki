#!/usr/bin/env python3
"""Extra screenshot-derived NETRATTLER builder concepts.

This is intentionally a small layer over netrattler_builder_styles. It adds only
concepts that were still missing from the latest screenshot set:
- Contact Mix
- Attack + Contact Mix
- High-Line Mix
- Shot Bomb

All legs must already be real bookmaker quotes with independent model edge.
Same-game product odds remain internal only; the installed style formatter asks
for the live bookmaker builder price.
"""
from __future__ import annotations

import os
from typing import Dict, List, Sequence, Tuple

import netrattler_builder_engine as builder

_INSTALLED = False
_ORIG_BUILD = None

CONTACT = {"fouls", "fouls_won", "tackles", "tackles_committed", "tackles_received"}
ATTACK = {"shots", "sot", "score_assist", "score", "assist"}


def _f(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _modelled(leg: builder.PropLeg) -> bool:
    min_edge = _f(os.getenv("NETRATTLER_BUILDER_MIN_LEG_EDGE", "2.0"), 2.0)
    return bool(not leg.estimated and leg.odds > 1 and leg.edge >= min_edge)


def _rank(leg: builder.PropLeg) -> Tuple[float, float, float]:
    return (leg.edge, leg.quality, leg.probability)


def _distinct(rows: Sequence[builder.PropLeg], count: int, allow_same_player: bool = False) -> List[builder.PropLeg]:
    out: List[builder.PropLeg] = []
    used = set()
    for leg in sorted(rows, key=_rank, reverse=True):
        p = builder.norm(leg.player)
        if not allow_same_player and p in used:
            continue
        if not builder.valid_builder(out + [leg], min_legs=1, max_legs=9):
            continue
        out.append(leg)
        used.add(p)
        if len(out) >= count:
            break
    return out


def _contact_mix(rows: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    contact = [x for x in rows if x.category in CONTACT and _modelled(x)]
    out: List[builder.BuilderPick] = []
    for size, label, stake in ((3, "CONTACT SAFE 3L", 0.50), (5, "CONTACT VALUE 5L", 0.25)):
        legs = _distinct(contact, size)
        if len(legs) != size:
            continue
        pick = builder._make_builder("CONTACT MIX", label, legs, match_date, stake)
        if pick:
            out.append(pick)
    return out


def _attack_contact_mix(rows: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    attack = _distinct([x for x in rows if x.category in ATTACK and _modelled(x)], 3)
    contact = _distinct([x for x in rows if x.category in CONTACT and _modelled(x)], 4)
    out: List[builder.BuilderPick] = []
    configs = [
        (attack[:2] + contact[:2], 4, "ATTACK + CONTACT 4L", 0.35),
        (attack[:2] + contact[:3], 5, "ATTACK + CONTACT 5L", 0.20),
    ]
    for legs, size, label, stake in configs:
        # Resolve duplicate players/categories conservatively.
        chosen: List[builder.PropLeg] = []
        for leg in legs:
            if leg.key() in {x.key() for x in chosen}:
                continue
            if builder.valid_builder(chosen + [leg], min_legs=1, max_legs=9):
                chosen.append(leg)
        if len(chosen) != size:
            continue
        pick = builder._make_builder("ATTACK CONTACT MIX", label, chosen, match_date, stake)
        if pick:
            out.append(pick)
    return out


def _high_line(rows: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    # Bookmaker totals use the actual O/U line: O1.5 == 2+, O2.5 == 3+.
    # Therefore the first true "higher" ladder step begins at 1.5, not 2.0.
    thresholds = {
        "shots": 1.5,
        "sot": 1.5,
        "fouls": 1.5,
        "fouls_won": 1.5,
        "tackles": 1.5,
        "tackles_committed": 1.5,
        "tackles_received": 1.5,
    }
    high = [
        x for x in rows
        if x.category in thresholds and x.line >= thresholds[x.category] and _modelled(x)
    ]
    legs = _distinct(high, 5)
    out: List[builder.BuilderPick] = []
    for size in (3, 4, 5):
        if len(legs) < size:
            continue
        pick = builder._make_builder("HIGH LINE MIX", f"REAL HIGH-LINE {size}L", legs[:size], match_date, 0.10)
        if pick:
            out.append(pick)
    return out


def _shot_bomb(rows: Sequence[builder.PropLeg], match_date: str) -> List[builder.BuilderPick]:
    # Screenshot concept: 2+/3+ shots = bookmaker O1.5/O2.5 lines.
    shots = [x for x in rows if x.category == "shots" and x.line >= 1.5 and _modelled(x)]
    legs = _distinct(shots, 5)
    out: List[builder.BuilderPick] = []
    for size, label, stake in ((3, "SHOT BOMB 3L", 0.20), (4, "SHOT BOMB 4L", 0.10), (5, "SHOT BOMB 5L", 0.05)):
        if len(legs) < size:
            continue
        pick = builder._make_builder("SHOT BOMB", label, legs[:size], match_date, stake)
        if pick:
            out.append(pick)
    return out


def _extra(raw_props, match_date: str) -> List[builder.BuilderPick]:
    props = [p for p in builder.deduplicate_props(raw_props) if _modelled(p)]
    by_match: Dict[str, List[builder.PropLeg]] = {}
    for leg in props:
        by_match.setdefault(leg.match, []).append(leg)
    out: List[builder.BuilderPick] = []
    for rows in by_match.values():
        out += _contact_mix(rows, match_date)
        out += _attack_contact_mix(rows, match_date)
        out += _high_line(rows, match_date)
        out += _shot_bomb(rows, match_date)
    return out


def install() -> None:
    global _INSTALLED, _ORIG_BUILD
    if _INSTALLED:
        return
    _ORIG_BUILD = builder.build_builder_picks

    def build(raw_props, match_contexts=None, match_date=None, max_builders=None):
        run_date = match_date or builder.date.today().isoformat()
        base = list(_ORIG_BUILD(raw_props, match_contexts, run_date, max_builders=max_builders))
        extras = _extra(raw_props, run_date)
        seen = {x.builder_id for x in base}
        for pick in extras:
            if pick.builder_id not in seen:
                base.append(pick)
                seen.add(pick.builder_id)
        cap = max_builders or builder.as_int(os.getenv("NETRATTLER_MAX_BUILDERS_PER_RUN", "30"), 30)
        # The base style layer has already ranked its picks; extras are appended in
        # conservative-to-risky order and never displace a previously qualified pick.
        return base[:cap]

    builder.build_builder_picks = build
    _INSTALLED = True
