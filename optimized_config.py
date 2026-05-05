"""
🔧 OPTIMIZED CONFIG - NETRATTLER AI 2.0
=======================================

Alle optimierten Einstellungen für maximale Performance.
Basierend auf Analyse & Best Practices.
"""

# ============================================================
# FILTER SETTINGS (OPTIMIERT)
# ============================================================

# Probability Filter
MIN_PROBABILITY = 67          # 67% (bewährt!)
MAX_PROBABILITY = 95          # Kein 100% (unrealistisch)

# Quoten Filter (OPTIMIERT für Value!)
MIN_ODDS = 1.60              # Minimum Value
MAX_ODDS = 2.80              # Maximum Risiko
OPTIMAL_ODDS_BTTS = (1.70, 2.20)     # Sweet Spot BTTS
OPTIMAL_ODDS_OVER25 = (1.60, 2.00)   # Sweet Spot Over 2.5

# Confidence Filter (STRENGER = BESSER!)
MIN_CONFIDENCE = 4           # 4/5 statt 3/5 (höhere Qualität!)

# Value Rating (nur gute Tipps!)
MIN_VALUE_RATING = "OK"      # HIGH, OK (LOW fliegt raus!)

# ============================================================
# ERWEITERTE FEATURES (AKTIVIERT)
# ============================================================

# xG-Integration (Understat)
ENABLE_XG_DATA = True
XG_WEIGHT = 0.4              # 40% xG, 60% actual goals in analysis

# Verletzungen & Sperren
ENABLE_INJURIES = True
MIN_INJURY_IMPACT = 3.0      # Nur bei Impact > 3/10 erwähnen

# Team Form
ENABLE_FORM_DATA = True
FORM_LOOKBACK_GAMES = 5      # Letzte 5 Spiele

# Head-to-Head
ENABLE_H2H_DATA = True
H2H_LOOKBACK_GAMES = 5       # Letzte 5 H2H-Duelle

# Multi-Combo System
ENABLE_MULTI_COMBO = True
COMBO_TYPES = ["safe", "value"]  # safe, value, risk
COMBO_MIN_TIPS = 3           # Mindestens 3 Tipps für Combo
COMBO_MAX_TIPS = 5           # Maximum 5 Tipps pro Combo

# ============================================================
# API QUOTA MANAGEMENT
# ============================================================

# API-Football (200 req/day mit 2 Keys)
API_FOOTBALL_DAILY_QUOTA = 200
API_FOOTBALL_RESERVE = 20    # Reserve für Settlement/Checks

# Smart Quota Usage:
# - Team-ID Caching (spart ~50 req)
# - Selective enrichment (nur high-confidence matches)
# - Multi-day caching

ENABLE_SMART_CACHING = True
CACHE_DURATION_HOURS = 24

# ============================================================
# ERWEITERTE ANALYSE
# ============================================================

# AI Enhancement
USE_ENHANCED_PROMPTS = True  # Mit Verletzungen, xG, Form, H2H

# Feature Engineering
EXTRACT_ML_FEATURES = True   # Für zukünftiges ML-Training

# ============================================================
# MÄRKTE KONFIGURATION
# ============================================================

MARKETS_CONFIG = {
    "btts": {
        "enabled": True,
        "min_odds": 1.60,
        "max_odds": 2.50,
        "optimal_range": (1.70, 2.20),
        "min_confidence": 4,
        "min_probability": 67
    },
    "over25": {
        "enabled": True,
        "min_odds": 1.50,
        "max_odds": 2.20,
        "optimal_range": (1.60, 2.00),
        "min_confidence": 4,
        "min_probability": 65
    },
    "combo": {
        "enabled": True,
        "min_odds": 1.60,
        "max_odds": 2.50,
        "min_confidence": 4,
        "min_probability": 70
    },
    "btts_ht": {
        "enabled": True,
        "min_odds": 2.00,
        "max_odds": 3.50,
        "min_confidence": 3,
        "min_probability": 60
    }
}

# ============================================================
# SELECTIVE ENRICHMENT (Quota-Saving!)
# ============================================================

# Nur Matches mit diesen Kriterien werden mit erweiterten Daten angereichert
ENRICHMENT_CRITERIA = {
    "min_base_confidence": 3,        # Mindestens 3/5 Basis-Confidence
    "min_base_probability": 60,      # Mindestens 60% Basis-Probability
    "top_n_per_league": 5,           # Max 5 beste Matches pro Liga
}

# Reduziert API-Calls von ~100 auf ~30 pro Run! 🎯

# ============================================================
# LEAGUE PRIORITIZATION
# ============================================================

# Top-Ligen (immer volle Analyse)
TOP_TIER_LEAGUES = [
    "Premier League",
    "Bundesliga", 
    "La Liga",
    "Serie A",
    "Ligue 1",
    "Champions League",
    "Europa League"
]

# Mid-Tier (Basis-Analyse)
MID_TIER_LEAGUES = [
    "Championship",
    "Eredivisie",
    "Primeira Liga",
    "2. Bundesliga",
    "La Liga 2"
]

# Low-Tier (Selective)
# Rest der Ligen

# ============================================================
# PERFORMANCE TRACKING
# ============================================================

# Supabase Logging
LOG_TO_SUPABASE = True
LOG_FEATURES_FOR_ML = True   # Features für späteres ML-Training loggen

# Performance Metriken
TRACK_PERFORMANCE = True
PERFORMANCE_WINDOW_DAYS = 30  # Letzte 30 Tage tracken

# ============================================================
# TELEGRAM FORMATTING
# ============================================================

# Erweiterte Nachrichten mit Context
TELEGRAM_SHOW_INJURIES = True
TELEGRAM_SHOW_FORM = True
TELEGRAM_SHOW_XG = True
TELEGRAM_SHOW_H2H = True

# Nachricht-Template
TELEGRAM_MESSAGE_TEMPLATE = """
🎯 <b>{home} vs {away}</b>

📊 {league}
🕐 {time}
⚽ {market}: <b>{tip}</b>
💰 Quote: <b>{odds}</b>
⭐ Confidence: <b>{confidence}/5</b>
📈 Probability: <b>{probability}%</b>

{context}

💡 {reasoning}
"""

# ============================================================
# EXPORTS
# ============================================================

def get_market_config(market: str) -> dict:
    """Holt Konfiguration für einen Markt"""
    return MARKETS_CONFIG.get(market, MARKETS_CONFIG["btts"])


def should_enrich_match(base_confidence: int, base_probability: int) -> bool:
    """
    Entscheidet ob ein Match mit erweiterten Daten angereichert werden soll.
    Spart API-Quota!
    """
    return (
        base_confidence >= ENRICHMENT_CRITERIA["min_base_confidence"] and
        base_probability >= ENRICHMENT_CRITERIA["min_base_probability"]
    )


def is_top_tier_league(league: str) -> bool:
    """Prüft ob Top-Tier Liga"""
    return league in TOP_TIER_LEAGUES


# ============================================================
# USAGE
# ============================================================

if __name__ == "__main__":
    print("🔧 OPTIMIZED CONFIG")
    print("=" * 60)
    print(f"Min Probability: {MIN_PROBABILITY}%")
    print(f"Min Confidence: {MIN_CONFIDENCE}/5")
    print(f"Odds Range: {MIN_ODDS} - {MAX_ODDS}")
    print(f"xG Integration: {'✅' if ENABLE_XG_DATA else '❌'}")
    print(f"Injuries: {'✅' if ENABLE_INJURIES else '❌'}")
    print(f"Form Data: {'✅' if ENABLE_FORM_DATA else '❌'}")
    print(f"H2H Data: {'✅' if ENABLE_H2H_DATA else '❌'}")
    print(f"Multi-Combo: {'✅' if ENABLE_MULTI_COMBO else '❌'}")
    print("=" * 60)
    
    # Test Market Config
    btts_config = get_market_config("btts")
    print(f"\nBTTS Config:")
    print(f"  Odds: {btts_config['min_odds']} - {btts_config['max_odds']}")
    print(f"  Optimal: {btts_config['optimal_range']}")
    print(f"  Min Confidence: {btts_config['min_confidence']}/5")
