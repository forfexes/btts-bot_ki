"""
🎯 ML LOGGER - Für zukünftiges Machine Learning
================================================

Logged alle Tipps mit Features in Supabase für späteres ML-Training.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
import os

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("⚠️ Supabase not available - ML logging disabled")


# Supabase Connection
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase_client: Optional[Client] = None

if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase connection error: {e}")


def log_tip_for_ml(tip: Dict, features: Dict, market: str) -> bool:
    """
    Logged einen Tipp mit Features für ML-Training.
    
    Args:
        tip: Tipp-Dict mit match, odds, confidence, etc.
        features: Feature-Dict (35+ features)
        market: BTTS, Over25, etc.
    
    Returns:
        True wenn erfolgreich, False bei Error
    """
    
    if not supabase_client:
        return False
    
    try:
        # Daten vorbereiten
        ml_data = {
            # Match Info
            "match_id": f"{tip.get('home', '')}_{tip.get('away', '')}_{tip.get('date', '')}",
            "home_team": tip.get("home", ""),
            "away_team": tip.get("away", ""),
            "league": tip.get("league", ""),
            "date": tip.get("date", ""),
            "time": tip.get("time", ""),
            
            # Tipp Info
            "market": market,
            "tip": tip.get("tip", ""),
            "odds": tip.get("odds", 0.0),
            "confidence": tip.get("confidence", 0),
            "probability": tip.get("probability", 0.0),
            "value_rating": tip.get("value_rating", ""),
            
            # Features (als JSON)
            "features": json.dumps(features),
            
            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bot_version": "2.0",
            
            # Result (wird später gefüllt durch settlement)
            "result": None,  # "won", "lost", "void"
            "settled": False,
            "settled_at": None,
        }
        
        # In Supabase speichern
        response = supabase_client.table("ml_tips").insert(ml_data).execute()
        
        return True
    
    except Exception as e:
        print(f"ML Logging Error: {e}")
        return False


def update_tip_result(match_id: str, result: str, actual_score: str = None) -> bool:
    """
    Updated das Ergebnis eines Tipps für ML-Training.
    
    Args:
        match_id: Match-ID
        result: "won", "lost", "void"
        actual_score: Echtes Ergebnis (z.B. "2-1")
    """
    
    if not supabase_client:
        return False
    
    try:
        update_data = {
            "result": result,
            "settled": True,
            "settled_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if actual_score:
            update_data["actual_score"] = actual_score
        
        response = supabase_client.table("ml_tips") \
            .update(update_data) \
            .eq("match_id", match_id) \
            .execute()
        
        return True
    
    except Exception as e:
        print(f"ML Update Error: {e}")
        return False


def get_performance_stats(days: int = 30) -> Dict:
    """
    Holt Performance-Stats der letzten N Tage für Monitoring.
    """
    
    if not supabase_client:
        return {}
    
    try:
        # Letzte N Tage
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Alle settled tips
        response = supabase_client.table("ml_tips") \
            .select("*") \
            .eq("settled", True) \
            .gte("created_at", cutoff_date) \
            .execute()
        
        tips = response.data
        
        if not tips:
            return {}
        
        # Stats berechnen
        total = len(tips)
        won = sum(1 for t in tips if t.get("result") == "won")
        lost = sum(1 for t in tips if t.get("result") == "lost")
        
        # Nach Markt
        by_market = {}
        for tip in tips:
            market = tip.get("market", "unknown")
            if market not in by_market:
                by_market[market] = {"total": 0, "won": 0, "lost": 0}
            
            by_market[market]["total"] += 1
            if tip.get("result") == "won":
                by_market[market]["won"] += 1
            elif tip.get("result") == "lost":
                by_market[market]["lost"] += 1
        
        # Win-Rates berechnen
        for market in by_market:
            total_market = by_market[market]["total"]
            won_market = by_market[market]["won"]
            by_market[market]["win_rate"] = (won_market / total_market * 100) if total_market > 0 else 0
        
        return {
            "total_tips": total,
            "won": won,
            "lost": lost,
            "win_rate": (won / total * 100) if total > 0 else 0,
            "by_market": by_market,
            "period_days": days
        }
    
    except Exception as e:
        print(f"Performance Stats Error: {e}")
        return {}


# ============================================================
# SUPABASE TABLE SCHEMA (für Reference)
# ============================================================

"""
CREATE TABLE ml_tips (
    id BIGSERIAL PRIMARY KEY,
    match_id TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    league TEXT,
    date TEXT,
    time TEXT,
    
    market TEXT,
    tip TEXT,
    odds FLOAT,
    confidence INT,
    probability FLOAT,
    value_rating TEXT,
    
    features JSONB,
    
    created_at TIMESTAMPTZ,
    bot_version TEXT,
    
    result TEXT,  -- won, lost, void
    settled BOOLEAN DEFAULT FALSE,
    settled_at TIMESTAMPTZ,
    actual_score TEXT
);

CREATE INDEX idx_ml_tips_match ON ml_tips(match_id);
CREATE INDEX idx_ml_tips_settled ON ml_tips(settled);
CREATE INDEX idx_ml_tips_created ON ml_tips(created_at);
"""

if __name__ == "__main__":
    print("🤖 ML LOGGER - Test")
    print("=" * 60)
    
    if supabase_client:
        print("✅ Supabase Connected!")
        
        # Test Performance Stats
        stats = get_performance_stats(30)
        if stats:
            print(f"\n📊 Performance (Last 30 Days):")
            print(f"   Total Tips: {stats['total_tips']}")
            print(f"   Won: {stats['won']}")
            print(f"   Win-Rate: {stats['win_rate']:.1f}%")
    else:
        print("❌ Supabase not available")
