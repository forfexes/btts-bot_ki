#!/usr/bin/env python3
from netrattler_builder_engine import (
    build_builder_picks, deduplicate_props, market_line
)

MATCH = "France vs Spain"

def row(player, market, category, line, odds, prob=68):
    return {
        "player": player,
        "team": "France",
        "match": MATCH,
        "league": "FIFA World Cup",
        "market": market,
        "category": category,
        "line": line,
        "odds": odds,
        "probability": prob,
        "source": "pinnacle",
        "games": 10,
        "hit_rate": prob,
    }

rows = [
    row("Player A", "1+ Tackles Committed", "tackles_committed", 1, 1.35, 76),
    row("Player B", "1+ Tackles Committed", "tackles_committed", 1, 1.40, 73),
    row("Player C", "1+ Tackles Committed", "tackles_committed", 1, 1.45, 70),
    row("Player D", "2+ Tackles Received", "tackles_received", 2, 1.70, 62),
    row("Player E", "2+ Tackles Received", "tackles_received", 2, 1.75, 60),
    row("Player F", "2+ Tackles Received", "tackles_received", 2, 1.80, 58),
    row("Player G", "Player to be Booked", "yellow_cards", 1, 2.40, 42),
    row("Player H", "Player to be Booked", "yellow_cards", 1, 2.50, 40),
    row("Player I", "Player to be Booked", "yellow_cards", 1, 2.60, 38),
    row("Player J", "1+ Shot on Target", "sot", 1, 1.55, 67),
    row("Player K", "1+ Shot on Target", "sot", 1, 1.60, 64),
    row("Player L", "1+ Shot on Target", "sot", 1, 1.65, 62),
    row("France", "France to Qualify", "result", 1, 1.50, 70),
    row("Player M", "Anytime Goalscorer", "score", 1, 2.20, 48),
    row("Both Teams", "Both Teams to Receive a Card", "team_cards", 1, 1.50, 68),
]

assert market_line("3+ Tackles") == 3
props = deduplicate_props(rows)
cats = {x.category for x in props}
assert "tackles_committed" in cats
assert "tackles_received" in cats

picks = build_builder_picks(rows, match_date="2026-07-15", max_builders=50)
assert picks, "No builders generated"
styles = {p.style for p in picks}
assert "TACKLES COMMITTED" in styles, styles
assert "TACKLES RECEIVED" in styles, styles
assert "BOOKING TRIO" in styles, styles
assert any(p.variant == "HIGH ODDS" for p in picks), [(p.style, p.variant) for p in picks]
assert any(p.style in {"FAVORITE SCRIPT", "INTENSITY SCRIPT", "ATTACK SCRIPT", "MIDFIELD BATTLE"} for p in picks)
assert all(2 <= len(p.legs) <= 6 for p in picks)
assert any(p.variant == "HIGH ODDS" and abs(p.stake - 0.1) < 1e-9 for p in picks)

print(f"OK: {len(picks)} builders")
print("Styles:", sorted(styles))
