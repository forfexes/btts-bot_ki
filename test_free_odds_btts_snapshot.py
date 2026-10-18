import json, os, tempfile
import netrattler_free_odds as f

def test_snapshot_ignores_halftime_btts():
    rows = [
        {"home_team": "Brighton", "away_team": "Crystal Palace", "market": "btts", "selection": "yes", "odds": 1.75},
        {"home_team": "Brighton", "away_team": "Crystal Palace", "market": "btts_ht", "selection": "yes", "odds": 7.5},
        {"home_team": "Brighton", "away_team": "Crystal Palace", "market": "btts_2h", "selection": "yes", "odds": 3.0},
    ]
    d = tempfile.mkdtemp(); fn = os.path.join(d, "s.json")
    json.dump(rows, open(fn, "w"))
    os.environ["NETRATTLER_ODDS_SNAPSHOT"] = fn
    f._CACHE.clear() if hasattr(f, "_CACHE") else None
    out = f.get_snapshot("Brighton", "Crystal Palace")
    assert out.get("btts_yes") == 1.75, out
