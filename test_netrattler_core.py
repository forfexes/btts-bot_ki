#!/usr/bin/env python3
from pathlib import Path
from netrattler_builder_engine import build_builder_picks, deduplicate_props


def row(player, match, market, category, line, odds, prob=68, source="pinnacle"):
    return {"player": player, "team": "", "match": match, "league": "FIFA - World Cup",
            "market": market, "category": category, "line": line, "odds": odds,
            "probability": prob, "source": source, "games": 10, "hit_rate": prob}

eng_arg = "England vs Argentina"
team_rows = [
    row("England To Score", eng_arg, "England To Score?", "match_goals", 1, 1.42, 70),
    row("Argentina To Score", eng_arg, "Argentina To Score?", "match_goals", 1, 1.48, 68),
    row("Either Team To Score 1st Half", eng_arg, "Either Team To Score? 1st Half", "btts_ht", 1, 1.72, 61),
]
team_picks = build_builder_picks(team_rows, match_date="2026-07-15", max_builders=50)
assert team_picks, "England-Argentina produced no builder"
assert any(all(x.match == eng_arg for x in p.legs) and len(p.legs) >= 2 for p in team_picks)

player_rows = team_rows + [
    row("Bellingham", eng_arg, "1+ Shot on Target", "sot", 1, 1.62, 64),
    row("Rice", eng_arg, "2+ Tackles Committed", "tackles_committed", 2, 1.70, 62),
    row("Mac Allister", eng_arg, "2+ Tackles Committed", "tackles_committed", 2, 1.76, 59),
    row("Enzo Fernandez", eng_arg, "2+ Fouls Committed", "fouls", 2, 1.78, 59),
    row("De Paul", eng_arg, "2+ Tackles Received", "tackles_received", 2, 1.82, 57),
    row("Saka", eng_arg, "2+ Tackles Received", "tackles_received", 2, 1.88, 55),
]
player_picks = build_builder_picks(player_rows, match_date="2026-07-15", max_builders=50)
styles = {p.style for p in player_picks}
assert len(player_picks) >= 5
assert any(p.style in {"SAME MATCH AVAILABLE", "TEAM BUILDER", "INTENSITY SCRIPT", "MIDFIELD BATTLE"} for p in player_picks)
assert "TACKLES COMMITTED" in styles
assert "TACKLES RECEIVED" in styles

bot = Path("btts_bot.py").read_text(encoding="utf-8")
assert 'Range' in bot and 'Content-Range' in bot
assert 'shots_on_target,sot,fouls_committed' in bot
assert 'is_team_market' in bot
assert 'match_goals' in bot and 'btts_ht' in bot
assert 'National teams must match exactly' in bot
print(f"OK England-Argentina team builders: {len(team_picks)}")
print(f"OK England-Argentina mixed/player builders: {len(player_picks)}")
print("Styles:", sorted(styles))


# V30 Source/Identity Hub regression tests
from netrattler_identity_hub import teams_match, normalize_team_name, explain_match
from netrattler_source_hub import parse_openfootball_json, source_health_snapshot, FEATURE_RECIPES
from netrattler_feature_hub import feature_plan_for_market, source_priority_for_market

assert normalize_team_name("England National Team") == "england"
assert teams_match("England", "England National Team") is True
assert teams_match("England", "New England Revolution II") is False, explain_match("England", "New England Revolution II")
assert teams_match("Argentina", "Argentina Men") is True
assert teams_match("LDU de Quito", "LDU Quito") is True

_payload = {"name": "World Cup", "matches": [{"date": "2026-07-15", "team1": "England", "team2": "Argentina", "score": {"ft": [2, 1], "ht": [1, 0]}}]}
_rows = parse_openfootball_json(_payload, "2026-07-15", source="unit_openfootball", league="FIFA World Cup")
assert len(_rows) == 1
assert _rows[0]["home_team"] == "England" and _rows[0]["away_score"] == 1
assert any(s["source"] == "soccerdata" for s in source_health_snapshot())
assert "xthreat" in FEATURE_RECIPES
assert "xg" in feature_plan_for_market("shots")
assert source_priority_for_market("tackles_received")[0] == "pinnacle"
print("V30 Source/Identity Hub: OK")
