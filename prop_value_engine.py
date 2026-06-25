import math
import re
from typing import Dict, Any, Optional

def implied_prob(odds: float) -> float:
    try:
        o = float(odds)
        return round(1 / o, 4) if o > 1 else 0.0
    except Exception:
        return 0.0

def fair_odds(prob: float) -> float:
    try:
        p = float(prob)
        return round(1 / p, 2) if p > 0 else 0.0
    except Exception:
        return 0.0

def edge_pct(model_prob: float, odds: float) -> float:
    imp = implied_prob(odds)
    return round((float(model_prob) - imp) * 100, 2)

def classify_market(desc: str, participant: str = "") -> Dict[str, Any]:
    text = f"{desc or ''} {participant or ''}".lower()
    market = desc or ""
    cat = "other"
    line = None
    selection = participant or "Yes"

    if "to score" in text or "goalscorer" in text or "goal scorer" in text:
        cat = "goalscorer"
        market = "Anytime Goalscorer"
    elif "assist" in text:
        cat = "assist"
        market = "Anytime Assist"
    elif "booked" in text or "yellow card" in text or "card" in text:
        cat = "card"
        market = "Player to be Booked"
    elif "shot on target" in text or "sot" in text:
        cat = "sot"
        market = "Shots on Target"
    elif "shot" in text:
        cat = "shots"
        market = "Shots"
    elif "tackle" in text:
        cat = "tackles"
        market = "Tackles"
    elif "foul" in text:
        cat = "fouls"
        market = "Fouls"
    elif "offside" in text:
        cat = "offsides"
        market = "Offsides"

    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", text)
    if m:
        line = float(m.group(1))
    elif cat in {"goalscorer", "assist", "card"}:
        line = 0.5

    return {
        "category": cat,
        "market": market,
        "line": line,
        "selection": selection,
    }

def rough_model_prob(category: str, odds: float, hit_rate: Optional[float] = None) -> float:
    """
    Ohne vollständige Player DB: konservativer Start.
    Später wird hier Supabase-Historie genutzt.
    """
    imp = implied_prob(odds)
    if hit_rate is not None:
        hp = max(0.01, min(0.95, float(hit_rate) / 100))
        return round((hp * 0.65) + (imp * 0.35), 4)

    # Leichter Boost für typische WM-Märkte, aber konservativ.
    boosts = {
        "goalscorer": 0.03,
        "assist": 0.02,
        "card": 0.04,
        "sot": 0.04,
        "shots": 0.04,
        "tackles": 0.03,
        "fouls": 0.03,
        "offsides": 0.02,
    }
    return round(max(0.01, min(0.92, imp + boosts.get(category, 0.0))), 4)

def value_rating(edge: float) -> str:
    if edge >= 10:
        return "HIGH"
    if edge >= 5:
        return "OK"
    if edge >= 2:
        return "SMALL"
    return "LOW"
