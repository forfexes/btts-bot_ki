"""
🆕 FEATURE ENGINEERING
======================

Erstellt ML-Features aus Match-Daten für Predictions.

Features werden in 3 Kategorien erstellt:
1. Basic Features (Form, H2H, etc.)
2. Advanced Features (xG, Injuries Impact)
3. Derived Features (Trends, Patterns)
"""

import numpy as np
from typing import Dict, List, Tuple


# ============================================================
# BASIC FEATURES
# ============================================================

def extract_form_features(match: Dict) -> Dict:
    """
    Extrahiert Form-Features für beide Teams
    """
    features = {}
    
    if match.get("has_form"):
        form_home = match["form_home"]
        form_away = match["form_away"]
        
        # Home Team Form
        features["home_goals_avg"] = form_home.get("goals_avg", 0.0)
        features["home_conceded_avg"] = form_home.get("conceded_avg", 0.0)
        features["home_btts_rate"] = form_home.get("btts_rate", 0.0) / 100.0
        features["home_form_points"] = _form_string_to_points(form_home.get("form", ""))
        
        # Away Team Form
        features["away_goals_avg"] = form_away.get("goals_avg", 0.0)
        features["away_conceded_avg"] = form_away.get("conceded_avg", 0.0)
        features["away_btts_rate"] = form_away.get("btts_rate", 0.0) / 100.0
        features["away_form_points"] = _form_string_to_points(form_away.get("form", ""))
        
        # Combined Features
        features["total_goals_avg"] = features["home_goals_avg"] + features["away_goals_avg"]
        features["total_conceded_avg"] = features["home_conceded_avg"] + features["away_conceded_avg"]
        features["btts_rate_combined"] = (features["home_btts_rate"] + features["away_btts_rate"]) / 2.0
        features["form_differential"] = features["home_form_points"] - features["away_form_points"]
    
    else:
        # Fallback: Zeros
        for key in ["home_goals_avg", "home_conceded_avg", "home_btts_rate", "home_form_points",
                    "away_goals_avg", "away_conceded_avg", "away_btts_rate", "away_form_points",
                    "total_goals_avg", "total_conceded_avg", "btts_rate_combined", "form_differential"]:
            features[key] = 0.0
    
    return features


def _form_string_to_points(form: str) -> float:
    """
    Konvertiert Form-String zu Punkten
    W=3, D=1, L=0
    """
    if not form:
        return 0.0
    
    points = {"W": 3, "D": 1, "L": 0}
    total = sum(points.get(c, 0) for c in form)
    
    # Normalisiert auf 0-1 (max 15 Punkte bei WWWWW)
    return total / 15.0


def extract_h2h_features(match: Dict) -> Dict:
    """
    Extrahiert H2H-Features
    """
    features = {}
    
    if match.get("has_h2h"):
        h2h = match["h2h"]
        
        features["h2h_btts_rate"] = h2h.get("btts_rate", 0.0) / 100.0
        features["h2h_avg_goals"] = h2h.get("avg_goals", 0.0)
        features["h2h_matches"] = min(h2h.get("matches", 0) / 10.0, 1.0)  # Normalize
    
    else:
        features["h2h_btts_rate"] = 0.0
        features["h2h_avg_goals"] = 0.0
        features["h2h_matches"] = 0.0
    
    return features


def extract_injury_features(match: Dict) -> Dict:
    """
    Extrahiert Verletzungs-Impact Features
    """
    features = {}
    
    if match.get("has_injuries"):
        inj_home = match["injuries_home"]
        inj_away = match["injuries_away"]
        
        features["home_injuries_impact"] = inj_home.get("impact_score", 0.0) / 10.0  # Normalize
        features["away_injuries_impact"] = inj_away.get("impact_score", 0.0) / 10.0
        features["total_injuries"] = (inj_home.get("total_out", 0) + inj_away.get("total_out", 0)) / 10.0
        features["injury_differential"] = features["home_injuries_impact"] - features["away_injuries_impact"]
    
    else:
        features["home_injuries_impact"] = 0.0
        features["away_injuries_impact"] = 0.0
        features["total_injuries"] = 0.0
        features["injury_differential"] = 0.0
    
    return features


# ============================================================
# ADVANCED FEATURES (xG)
# ============================================================

def extract_xg_features(match: Dict) -> Dict:
    """
    Extrahiert xG-Features (Expected Goals)
    """
    features = {}
    
    if match.get("has_xg"):
        xg_home = match["xg_home"]
        xg_away = match["xg_away"]
        
        features["home_xg_for"] = xg_home.get("xg_for", 0.0)
        features["home_xg_against"] = xg_home.get("xg_against", 0.0)
        features["home_xg_diff"] = xg_home.get("xg_diff", 0.0)
        
        features["away_xg_for"] = xg_away.get("xg_for", 0.0)
        features["away_xg_against"] = xg_away.get("xg_against", 0.0)
        features["away_xg_diff"] = xg_away.get("xg_diff", 0.0)
        
        # Combined
        features["total_xg"] = features["home_xg_for"] + features["away_xg_for"]
        features["xg_differential"] = features["home_xg_diff"] - features["away_xg_diff"]
        
        # Over/Under Performance (xG vs Actual Goals)
        # Wenn actual_goals vorhanden (aus Form-Daten)
        if match.get("has_form"):
            actual_home = match["form_home"].get("goals_avg", 0)
            actual_away = match["form_away"].get("goals_avg", 0)
            
            features["home_overperforming"] = 1.0 if actual_home > features["home_xg_for"] else 0.0
            features["away_overperforming"] = 1.0 if actual_away > features["away_xg_for"] else 0.0
        else:
            features["home_overperforming"] = 0.0
            features["away_overperforming"] = 0.0
    
    else:
        for key in ["home_xg_for", "home_xg_against", "home_xg_diff",
                    "away_xg_for", "away_xg_against", "away_xg_diff",
                    "total_xg", "xg_differential",
                    "home_overperforming", "away_overperforming"]:
            features[key] = 0.0
    
    return features


# ============================================================
# DERIVED FEATURES
# ============================================================

def extract_derived_features(match: Dict, form_features: Dict, xg_features: Dict) -> Dict:
    """
    Erstellt abgeleitete Features aus Kombination mehrerer Quellen
    """
    features = {}
    
    # Offensive Power (Goals + xG)
    if "home_goals_avg" in form_features and "home_xg_for" in xg_features:
        features["home_offensive_power"] = (
            form_features["home_goals_avg"] * 0.6 + xg_features["home_xg_for"] * 0.4
        )
        features["away_offensive_power"] = (
            form_features["away_goals_avg"] * 0.6 + xg_features["away_xg_for"] * 0.4
        )
    else:
        features["home_offensive_power"] = form_features.get("home_goals_avg", 0.0)
        features["away_offensive_power"] = form_features.get("away_goals_avg", 0.0)
    
    # Defensive Weakness (Conceded + xG Against)
    if "home_conceded_avg" in form_features and "home_xg_against" in xg_features:
        features["home_defensive_weakness"] = (
            form_features["home_conceded_avg"] * 0.6 + xg_features["home_xg_against"] * 0.4
        )
        features["away_defensive_weakness"] = (
            form_features["away_conceded_avg"] * 0.6 + xg_features["away_xg_against"] * 0.4
        )
    else:
        features["home_defensive_weakness"] = form_features.get("home_conceded_avg", 0.0)
        features["away_defensive_weakness"] = form_features.get("away_conceded_avg", 0.0)
    
    # BTTS Likelihood Score
    features["btts_likelihood"] = (
        features["home_offensive_power"] * features["away_defensive_weakness"] +
        features["away_offensive_power"] * features["home_defensive_weakness"]
    ) / 2.0
    
    # Over 2.5 Likelihood Score
    features["over25_likelihood"] = (
        features["home_offensive_power"] + features["away_offensive_power"] +
        features["home_defensive_weakness"] + features["away_defensive_weakness"]
    ) / 4.0
    
    return features


# ============================================================
# MAIN FEATURE EXTRACTOR
# ============================================================

def extract_all_features(match: Dict) -> Dict:
    """
    Extrahiert ALLE Features aus einem Match-Object.
    
    Returns: Dict mit ~30-40 Features ready für ML-Model
    """
    
    all_features = {}
    
    # 1. Form Features
    form_feats = extract_form_features(match)
    all_features.update(form_feats)
    
    # 2. H2H Features
    h2h_feats = extract_h2h_features(match)
    all_features.update(h2h_feats)
    
    # 3. Injury Features
    injury_feats = extract_injury_features(match)
    all_features.update(injury_feats)
    
    # 4. xG Features
    xg_feats = extract_xg_features(match)
    all_features.update(xg_feats)
    
    # 5. Derived Features
    derived_feats = extract_derived_features(match, form_feats, xg_feats)
    all_features.update(derived_feats)
    
    return all_features


def features_to_vector(features: Dict, feature_names: List[str] = None) -> np.ndarray:
    """
    Konvertiert Feature-Dict zu numpy array (für ML-Model)
    
    feature_names: Liste der Features in bestimmter Reihenfolge
                   (wichtig für konsistente Model-Inputs!)
    """
    
    if feature_names is None:
        # Standard-Reihenfolge (sollte mit Trainings-Daten übereinstimmen!)
        feature_names = [
            # Form (12)
            "home_goals_avg", "home_conceded_avg", "home_btts_rate", "home_form_points",
            "away_goals_avg", "away_conceded_avg", "away_btts_rate", "away_form_points",
            "total_goals_avg", "total_conceded_avg", "btts_rate_combined", "form_differential",
            
            # H2H (3)
            "h2h_btts_rate", "h2h_avg_goals", "h2h_matches",
            
            # Injuries (4)
            "home_injuries_impact", "away_injuries_impact", "total_injuries", "injury_differential",
            
            # xG (10)
            "home_xg_for", "home_xg_against", "home_xg_diff",
            "away_xg_for", "away_xg_against", "away_xg_diff",
            "total_xg", "xg_differential",
            "home_overperforming", "away_overperforming",
            
            # Derived (6)
            "home_offensive_power", "away_offensive_power",
            "home_defensive_weakness", "away_defensive_weakness",
            "btts_likelihood", "over25_likelihood"
        ]
    
    # Feature-Vektor erstellen
    vector = []
    for name in feature_names:
        vector.append(features.get(name, 0.0))
    
    return np.array(vector, dtype=np.float32)


# ============================================================
# FEATURE IMPORTANCE (für Debugging)
# ============================================================

def get_feature_importance_summary(features: Dict, top_n: int = 10) -> str:
    """
    Gibt eine lesbare Zusammenfassung der wichtigsten Features
    """
    
    # Sortiere Features nach Wert (absolute)
    sorted_features = sorted(features.items(), key=lambda x: abs(x[1]), reverse=True)
    
    summary = "🎯 TOP FEATURES:\n"
    summary += "=" * 50 + "\n"
    
    for i, (name, value) in enumerate(sorted_features[:top_n], 1):
        summary += f"{i:2d}. {name:30s}: {value:6.3f}\n"
    
    return summary


# ============================================================
# USAGE EXAMPLE
# ============================================================

if __name__ == "__main__":
    print("🔧 FEATURE ENGINEERING - Test")
    print("=" * 60)
    
    # Mock Match mit Daten
    match = {
        "home": "Man United",
        "away": "Liverpool",
        "has_form": True,
        "form_home": {
            "form": "WWDLW",
            "goals_avg": 2.2,
            "conceded_avg": 1.0,
            "btts_rate": 60.0
        },
        "form_away": {
            "form": "WWWDL",
            "goals_avg": 2.4,
            "conceded_avg": 0.8,
            "btts_rate": 80.0
        },
        "has_h2h": True,
        "h2h": {
            "btts_rate": 70.0,
            "avg_goals": 3.2,
            "matches": 5
        },
        "has_injuries": True,
        "injuries_home": {
            "total_out": 3,
            "impact_score": 4.5
        },
        "injuries_away": {
            "total_out": 1,
            "impact_score": 1.5
        },
        "has_xg": True,
        "xg_home": {
            "xg_for": 1.8,
            "xg_against": 1.2,
            "xg_diff": 0.6
        },
        "xg_away": {
            "xg_for": 2.1,
            "xg_against": 1.0,
            "xg_diff": 1.1
        }
    }
    
    # Features extrahieren
    features = extract_all_features(match)
    
    print(f"\n✅ Extracted {len(features)} features")
    print("\n" + get_feature_importance_summary(features))
    
    # Zu Vektor konvertieren
    vector = features_to_vector(features)
    print(f"\n📊 Feature Vector Shape: {vector.shape}")
    print(f"   Sample values: {vector[:5]}")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete!")
