"""
🎯 ML LOGGER - Für zukünftiges Machine Learning
================================================

Logged alle Tipps mit Features in Supabase für späteres ML-Training.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def log_tip_for_ml(tip: Dict, features: Dict, market: str) -> bool:
    """
    Logged einen Tipp mit Features für ML-Training.
    """
    if not REQUESTS_AVAILABLE or not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        ml_data = {
            "match_id": f"{tip.get('home', '')}_{tip.get('away', '')}_{tip.get('date', '')}",
            "home_team": tip.get("home", ""),
            "away_team": tip.get("away", ""),
            "league": tip.get("league", ""),
            "date": tip.get("date", ""),
            "time": tip.get("time", ""),
            "market": market,
            "tip": tip.get("tip", ""),
            "odds": tip.get("odds", 0.0),
            "confidence": tip.get("confidence", 0),
            "probability": tip.get("probability", 0.0),
            "value_rating": tip.get("value_rating", ""),
            "features": json.dumps(features),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bot_version": "3.0",
            "result": None,
            "settled": False,
            "settled_at": None,
        }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/ml_tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=ml_data,
            timeout=10,
        )
        return r.ok

    except Exception as e:
        print(f"ML Logging Error: {e}")
        return False


def update_tip_result(match_id: str, result: str, actual_score: str = None) -> bool:
    """
    Updated das Ergebnis eines Tipps für ML-Training.
    result: 'won', 'lost', 'void'
    """
    if not REQUESTS_AVAILABLE or not SUPABASE_URL or not SUPABASE_KEY:
        return False

    try:
        update_data = {
            "result": result,
            "settled": True,
            "settled_at": datetime.now(timezone.utc).isoformat(),
        }
        if actual_score:
            update_data["actual_score"] = actual_score

        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/ml_tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            params={"match_id": f"eq.{match_id}"},
            json=update_data,
            timeout=10,
        )
        return r.ok

    except Exception as e:
        print(f"ML Update Error: {e}")
        return False


def get_performance_stats(days: int = 30) -> Dict:
    """
    Holt Performance-Stats der letzten N Tage.
    """
    if not REQUESTS_AVAILABLE or not SUPABASE_URL or not SUPABASE_KEY:
        return {}

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/ml_tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "settled": "eq.true",
                "created_at": f"gte.{cutoff}",
                "select": "*",
            },
            timeout=15,
        )

        if not r.ok:
            return {}

        tips = r.json()
        if not tips:
            return {}

        total = len(tips)
        won = sum(1 for t in tips if t.get("result") == "won")
        lost = sum(1 for t in tips if t.get("result") == "lost")

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

        for market in by_market:
            t = by_market[market]["total"]
            w = by_market[market]["won"]
            by_market[market]["win_rate"] = round(w / t * 100, 1) if t > 0 else 0

        return {
            "total_tips": total,
            "won": won,
            "lost": lost,
            "win_rate": round(won / total * 100, 1) if total > 0 else 0,
            "by_market": by_market,
            "period_days": days,
        }

    except Exception as e:
        print(f"Performance Stats Error: {e}")
        return {}


"""
SUPABASE TABLE SCHEMA:

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
    result TEXT,
    settled BOOLEAN DEFAULT FALSE,
    settled_at TIMESTAMPTZ,
    actual_score TEXT
);
"""

if __name__ == "__main__":
    print("🤖 ML LOGGER v3.0")
    stats = get_performance_stats(30)
    if stats:
        print(f"Total: {stats['total_tips']} | Won: {stats['won']} | WR: {stats['win_rate']}%")
    else:
        print("Keine Daten oder Supabase nicht verbunden")
