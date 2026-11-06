import netrattler_stats_match_cards as c

def test_history_fills_expected_goals(monkeypatch):
    rows = []
    for i in range(6):
        d = f"2026-09-{10+i:02d}"
        rows.append({"match_date": d, "home_team": "Lazio", "away_team": f"X{i}", "home_score": 3, "away_score": 1})
        rows.append({"match_date": d, "home_team": f"Y{i}", "away_team": "Parma", "home_score": 2, "away_score": 0})
    monkeypatch.setattr(c, "_load_results", lambda: rows)
    monkeypatch.setattr(c, "_load_github_matches", lambda log: rows)
    tip = {"match": "Lazio vs Parma", "tip": "x"}
    assert c.attach_history_context({"over25": [tip]}, log=lambda *a: None) == 1
    assert tip["avg_goals_home"] == 3.0 and tip["avg_conceded_home"] == 1.0
    assert tip["avg_conceded_away"] == 2.0
    assert tip["exp_goals_home"] == 2.5 and tip["exp_goals_away"] == 0.5


def test_over25_research_card_requires_consistent_goal_context():
    tip = {"match": "Independiente vs Riestra", "source": "pinnacle", "odds": 2.88,
           "probability": 0.59, "exp_goals_home": 0.9, "exp_goals_away": 0.6}
    assert c.select_cards({"over25": [tip]}) == []
    tip["probability"] = 0.19
    assert len(c.select_cards({"over25": [tip]})) == 1
    tip.pop("exp_goals_home")
    assert c.select_cards({"over25": [tip]}) == []
