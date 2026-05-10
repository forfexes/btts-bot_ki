"""
🆕 FEATURE ENGINEERING - Für ML Training
=========================================
Erstellt ML-Features aus Match-Daten.
Für späteres Training wenn 500+ Tipps gesammelt.
"""

from typing import Dict, List


def extract_form_features(match: Dict) -> Dict:
    features = {}
    if match.get("has_form"):
        form_home = match["form_home"]
        form_away = match["form_away"]
        features["home_goals_avg"] = form_home.get("goals_avg", 0.0)
        features["home_conceded_avg"] = form_home.get("conceded_avg", 0.0)
        features["home_btts_rate"] = form_home.get("btts_rate", 0.0) / 100.0
        features["home_form_points"] = _form_to_points(form_home.get("form", ""))
        features["away_goals_avg"] = form_away.get("goals_avg", 0.0)
        features["away_conceded_avg"] = form_away.get("conceded_avg", 0.0)
        features["away_btts_rate"] = form_away.get("btts_rate", 0.0) / 100.0
        features["away_form_points"] = _form_to_points(form_away.get("form", ""))
        features["total_goals_avg"] = features["home_goals_avg"] + features["away_goals_avg"]
        features["btts_rate_combined"] = (features["home_btts_rate"] + features["away_btts_rate"]) / 2.0
    else:
        for k in ["home_goals_avg","home_conceded_avg","home_btts_rate","home_form_points",
                  "away_goals_avg","away_conceded_avg","away_btts_rate","away_form_points",
                  "total_goals_avg","btts_rate_combined"]:
            features[k] = 0.0
    return features


def _form_to_points(form: str) -> float:
    points = {"W": 3, "D": 1, "L": 0}
    total = sum(points.get(c, 0) for c in form)
    return total / 15.0


def extract_h2h_features(match: Dict) -> Dict:
    features = {}
    if match.get("has_h2h"):
        h2h = match["h2h"]
        features["h2h_btts_rate"] = h2h.get("btts_rate", 0.0) / 100.0
        features["h2h_avg_goals"] = h2h.get("avg_goals", 0.0)
        features["h2h_matches"] = min(h2h.get("matches", 0) / 10.0, 1.0)
    else:
        features["h2h_btts_rate"] = 0.0
        features["h2h_avg_goals"] = 0.0
        features["h2h_matches"] = 0.0
    return features


def extract_injury_features(match: Dict) -> Dict:
    features = {}
    if match.get("has_injuries"):
        inj_home = match["injuries_home"]
        inj_away = match["injuries_away"]
        features["home_injuries_impact"] = inj_home.get("impact_score", 0.0) / 10.0
        features["away_injuries_impact"] = inj_away.get("impact_score", 0.0) / 10.0
        features["total_injuries"] = (inj_home.get("total_out", 0) + inj_away.get("total_out", 0)) / 10.0
    else:
        features["home_injuries_impact"] = 0.0
        features["away_injuries_impact"] = 0.0
        features["total_injuries"] = 0.0
    return features


def extract_xg_features(match: Dict) -> Dict:
    features = {}
    if match.get("has_xg"):
        xg_home = match["xg_home"]
        xg_away = match["xg_away"]
        features["home_xg_for"] = xg_home.get("xg_for", 0.0)
        features["home_xg_against"] = xg_home.get("xg_against", 0.0)
        features["away_xg_for"] = xg_away.get("xg_for", 0.0)
        features["away_xg_against"] = xg_away.get("xg_against", 0.0)
        features["total_xg"] = features["home_xg_for"] + features["away_xg_for"]
    else:
        for k in ["home_xg_for","home_xg_against","away_xg_for","away_xg_against","total_xg"]:
            features[k] = 0.0
    return features


def extract_all_features(match: Dict) -> Dict:
    """Extrahiert ALLE Features aus einem Match-Object."""
    all_features = {}
    all_features.update(extract_form_features(match))
    all_features.update(extract_h2h_features(match))
    all_features.update(extract_injury_features(match))
    all_features.update(extract_xg_features(match))
    return all_features


if __name__ == "__main__":
    print("✅ Feature Engineering v3.0 - bereit für ML Training")
    print("   Warte auf 500+ Tipps in Supabase...")
