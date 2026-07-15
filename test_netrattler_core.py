#!/usr/bin/env python3
from netrattler_builder_engine import build_builder_picks, deduplicate_props, market_line

def row(player, match, market, category, line, odds, prob=68):
    return {
        "player": player,
        "team": match.split(" vs ")[0],
        "match": match,
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

m1 = "France vs Spain"
m2 = "England vs Argentina"
rows = [
    row("A", m1, "1+ Tackles Committed", "tackles_committed", 1, 1.35, 76),
    row("B", m1, "1+ Tackles Committed", "tackles_committed", 1, 1.40, 73),
    row("C", m1, "2+ Tackles Received", "tackles_received", 2, 1.70, 62),
    row("D", m1, "2+ Tackles Received", "tackles_received", 2, 1.75, 60),
    row("E", m1, "Player to be Booked", "yellow_cards", 1, 2.40, 42),
    row("F", m1, "Player to be Booked", "yellow_cards", 1, 2.50, 40),
    row("G", m1, "1+ Shot on Target", "sot", 1, 1.55, 67),
    row("H", m1, "1+ Shot on Target", "sot", 1, 1.60, 64),
    row("England", m2, "England to Qualify", "result", 1, 1.55, 68),
    row("Kane", m2, "Anytime Goalscorer", "score", 1, 2.20, 48),
    row("Bellingham", m2, "1+ Shot on Target", "sot", 1, 1.65, 63),
]

assert market_line("3+ Tackles") == 3
props = deduplicate_props(rows)
assert "tackles_committed" in {x.category for x in props}
assert "tackles_received" in {x.category for x in props}

picks = build_builder_picks(rows, match_date="2026-07-15", max_builders=50)
assert len(picks) >= 10, len(picks)
styles = {p.style for p in picks}
assert "TACKLES COMMITTED" in styles, styles
assert "TACKLES RECEIVED" in styles, styles
assert "BOOKING LADDER" in styles, styles
assert "SAME MATCH AVAILABLE" in styles, styles
assert any(len({x.match for x in p.legs}) == 1 for p in picks)
assert any(len(p.legs) == 2 for p in picks)
assert all(2 <= len(p.legs) <= 6 for p in picks)

print(f"OK: {len(picks)} builders")
print("Styles:", sorted(styles))
