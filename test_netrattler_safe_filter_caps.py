import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("NETRATTLER_MATCHUP", "0")
import btts_bot as b

def tip(match, league, odds=2.4):
    return {"match": match, "league": league, "market": "over25", "tip": "YES", "probability": 68,
            "oddsYes": odds, "odds": odds, "time": "20:00", "_source": "pinnacle"}

def test_safe_filter_drops_fringe_and_caps_over25():
    tips = [tip("A vs B", "UEFA - Nations League D"), tip("C vs D", "International - Friendlies"),
            tip("E vs F", "Germany - Bundesliga"), tip("G vs H", "England - Premier League"),
            tip("I vs J", "Spain - La Liga"), tip("K vs L", "Italy - Serie A"), tip("M vs N", "France - Ligue 1")]
    out = b.filter_tips_legacy_safe(tips, market="over25")
    assert len(out) <= 3
    assert all("Nations" not in t["league"] and "Friend" not in t["league"] for t in out)

def test_safe_filter_drops_women():
    out = b.filter_tips_legacy_safe([tip("A vs B", "Germany - Bundesliga Women")], market="over25")
    assert out == []
