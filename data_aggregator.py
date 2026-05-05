"""
🆕 DATA AGGREGATOR - Zentrale Datenquelle
==========================================

Vereint ALLE Datenquellen in einem Interface:
- API-Football (Fixtures, Verletzungen, Form, H2H)
- Understat (xG-Daten)
- FBref (Team-Stats)
- Odds API (Quoten)

Returns: Unified Match Object mit allen Daten
"""

import os
import requests
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import json

# ============================================================
# CONFIG
# ============================================================

def get_env_list(name: str) -> List[str]:
    """Holt komma-separierte Liste aus Environment"""
    value = os.getenv(name, "").strip()
    return [x.strip() for x in value.split(",") if x.strip()]


API_FOOTBALL_KEYS = get_env_list("API_FOOTBALL_KEYS")
ODDS_API_KEYS = get_env_list("ODDS_API_KEYS")

# API Rate Limiting
_API_FOOTBALL_LAST_CALL = {}
_API_FOOTBALL_KEY_INDEX = 0


# ============================================================
# API-FOOTBALL CLIENT
# ============================================================

def _get_next_api_football_key() -> Optional[str]:
    """Round-Robin Key Selection"""
    global _API_FOOTBALL_KEY_INDEX
    
    if not API_FOOTBALL_KEYS:
        return None
    
    key = API_FOOTBALL_KEYS[_API_FOOTBALL_KEY_INDEX]
    _API_FOOTBALL_KEY_INDEX = (_API_FOOTBALL_KEY_INDEX + 1) % len(API_FOOTBALL_KEYS)
    
    return key


def _api_football_request(endpoint: str, params: Dict) -> Optional[Dict]:
    """
    Macht Request an API-Football mit Rate Limiting & Retry
    """
    global _API_FOOTBALL_LAST_CALL
    
    key = _get_next_api_football_key()
    if not key:
        return None
    
    # Rate Limiting: 1 Request pro Sekunde pro Key
    last_call = _API_FOOTBALL_LAST_CALL.get(key, 0)
    time_since = time.time() - last_call
    if time_since < 1.0:
        time.sleep(1.0 - time_since)
    
    try:
        url = f"https://v3.football.api-sports.io/{endpoint}"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": key
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        _API_FOOTBALL_LAST_CALL[key] = time.time()
        
        if r.status_code == 429:
            # Rate Limited - versuche anderen Key
            if len(API_FOOTBALL_KEYS) > 1:
                return _api_football_request(endpoint, params)
            return None
        
        if not r.ok:
            return None
        
        return r.json()
    
    except Exception as e:
        print(f"API-Football Error: {e}")
        return None


# ============================================================
# TEAM ID CACHE (Wichtig für Quota-Saving!)
# ============================================================

_TEAM_ID_CACHE = {}  # {(team_name, league_id): team_id}


def get_team_id(team_name: str, league_id: int, season: int) -> Optional[int]:
    """
    Holt Team-ID mit Caching (spart Quota!)
    """
    cache_key = (team_name.lower(), league_id, season)
    
    if cache_key in _TEAM_ID_CACHE:
        return _TEAM_ID_CACHE[cache_key]
    
    # API Call
    data = _api_football_request("teams", {
        "league": league_id,
        "season": season,
        "search": team_name[:10]
    })
    
    if not data or not data.get("response"):
        return None
    
    teams = data["response"]
    if not teams:
        return None
    
    # Erste Übereinstimmung nehmen
    team_id = teams[0]["team"]["id"]
    
    # Cache speichern
    _TEAM_ID_CACHE[cache_key] = team_id
    
    return team_id


# ============================================================
# UNIFIED MATCH OBJECT
# ============================================================

def create_match_object(
    home: str,
    away: str,
    league: str,
    league_id: int,
    date: str,
    odds: Dict = None
) -> Dict:
    """
    Erstellt Unified Match Object mit allen Basis-Daten
    """
    return {
        "home": home,
        "away": away,
        "league": league,
        "league_id": league_id,
        "date": date,
        "odds": odds or {},
        
        # Erweiterte Daten (werden gefüllt)
        "injuries_home": None,
        "injuries_away": None,
        "form_home": None,
        "form_away": None,
        "h2h": None,
        "xg_home": None,
        "xg_away": None,
        "stats_home": None,
        "stats_away": None,
        
        # Flags
        "has_injuries": False,
        "has_form": False,
        "has_h2h": False,
        "has_xg": False,
        "has_stats": False,
    }


# ============================================================
# DATA FETCHERS
# ============================================================

def fetch_injuries(team_id: int, league_id: int, season: int) -> Dict:
    """
    Holt Verletzungen & Sperren für ein Team
    """
    data = _api_football_request("injuries", {
        "team": team_id,
        "league": league_id,
        "season": season
    })
    
    if not data or not data.get("response"):
        return {"injuries": [], "suspensions": [], "total_out": 0, "impact_score": 0.0}
    
    injuries_list = data["response"]
    
    injuries = []
    suspensions = []
    
    for entry in injuries_list:
        player = entry.get("player", {})
        reason = entry.get("player", {}).get("reason", "").lower()
        
        player_data = {
            "name": player.get("name", "Unknown"),
            "reason": reason,
        }
        
        if "suspension" in reason or "banned" in reason or "card" in reason:
            suspensions.append(player_data)
        else:
            injuries.append(player_data)
    
    total_out = len(injuries) + len(suspensions)
    impact_score = min(10.0, total_out * 1.5)
    
    return {
        "injuries": injuries,
        "suspensions": suspensions,
        "total_out": total_out,
        "impact_score": impact_score,
        "key_players": injuries[:3] + suspensions[:3]  # Top 3
    }


def fetch_form(team_id: int, league_id: int, season: int) -> Dict:
    """
    Holt Team-Form (Letzte 5-6 Spiele)
    """
    data = _api_football_request("fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": 6
    })
    
    if not data or not data.get("response"):
        return {"form": "", "games": [], "goals_avg": 0.0, "conceded_avg": 0.0, "btts_rate": 0.0}
    
    fixtures = data["response"]
    
    form_string = ""
    goals = []
    conceded = []
    btts_count = 0
    
    for fixture in fixtures[-5:]:  # Letzte 5
        teams = fixture.get("teams", {})
        score = fixture.get("score", {}).get("fulltime", {})
        
        home_id = teams.get("home", {}).get("id")
        home_goals = score.get("home", 0) or 0
        away_goals = score.get("away", 0) or 0
        
        # BTTS?
        if home_goals > 0 and away_goals > 0:
            btts_count += 1
        
        # Form & Goals
        if home_id == team_id:
            our_goals = home_goals
            their_goals = away_goals
        else:
            our_goals = away_goals
            their_goals = home_goals
        
        goals.append(our_goals)
        conceded.append(their_goals)
        
        if our_goals > their_goals:
            form_string += "W"
        elif our_goals < their_goals:
            form_string += "L"
        else:
            form_string += "D"
    
    return {
        "form": form_string,
        "games": len(fixtures),
        "goals_avg": sum(goals) / len(goals) if goals else 0.0,
        "conceded_avg": sum(conceded) / len(conceded) if conceded else 0.0,
        "btts_rate": (btts_count / len(fixtures[-5:])) * 100 if fixtures else 0.0
    }


def fetch_h2h(team1_id: int, team2_id: int, last_n: int = 5) -> Dict:
    """
    Holt Head-to-Head History
    """
    data = _api_football_request("fixtures/headtohead", {
        "h2h": f"{team1_id}-{team2_id}",
        "last": last_n
    })
    
    if not data or not data.get("response"):
        return {"matches": 0, "btts_rate": 0.0, "avg_goals": 0.0}
    
    fixtures = data["response"]
    
    btts_count = 0
    total_goals = 0
    
    for fixture in fixtures:
        score = fixture.get("score", {}).get("fulltime", {})
        home_goals = score.get("home", 0) or 0
        away_goals = score.get("away", 0) or 0
        
        total_goals += home_goals + away_goals
        
        if home_goals > 0 and away_goals > 0:
            btts_count += 1
    
    return {
        "matches": len(fixtures),
        "btts_rate": (btts_count / len(fixtures)) * 100 if fixtures else 0.0,
        "avg_goals": total_goals / len(fixtures) if fixtures else 0.0
    }


# ============================================================
# XG DATA (Understat via soccerdata)
# ============================================================

def fetch_xg_data(team_name: str, league_name: str, season: int) -> Dict:
    """
    Holt xG-Daten von Understat via soccerdata Library
    
    Requires: pip install soccerdata
    """
    try:
        import soccerdata as sd
        
        # League-Mapping für soccerdata
        league_map = {
            "Premier League": "ENG-Premier League",
            "La Liga": "ESP-La Liga",
            "Bundesliga": "GER-Bundesliga",
            "Serie A": "ITA-Serie A",
            "Ligue 1": "FRA-Ligue 1",
        }
        
        sd_league = league_map.get(league_name)
        if not sd_league:
            return {"xg_for": 0.0, "xg_against": 0.0, "xg_diff": 0.0, "available": False}
        
        # Understat Data laden
        understat = sd.Understat(sd_league, str(season))
        team_stats = understat.read_team_match_stats()
        
        # Team-Daten filtern (Fuzzy-Match für Team-Namen)
        team_data = team_stats[team_stats['team'].str.contains(team_name[:8], case=False, na=False)]
        
        if team_data.empty:
            return {"xg_for": 0.0, "xg_against": 0.0, "xg_diff": 0.0, "available": False}
        
        # Durchschnitt berechnen (letzte 5 Spiele)
        recent = team_data.tail(5)
        
        xg_for = recent['xG'].mean() if 'xG' in recent.columns else 0.0
        xg_against = recent['xGA'].mean() if 'xGA' in recent.columns else 0.0
        
        return {
            "xg_for": float(xg_for),
            "xg_against": float(xg_against),
            "xg_diff": float(xg_for - xg_against),
            "available": True
        }
    
    except Exception as e:
        print(f"xG Fetch Error: {e}")
        return {"xg_for": 0.0, "xg_against": 0.0, "xg_diff": 0.0, "available": False}


# ============================================================
# MAIN AGGREGATOR
# ============================================================

def enrich_match_with_all_data(
    match: Dict,
    season: int,
    include_xg: bool = True,
    include_injuries: bool = True,
    include_form: bool = True,
    include_h2h: bool = True
) -> Dict:
    """
    Reichert Match-Object mit ALLEN verfügbaren Daten an.
    
    Smart: Nutzt nur APIs wenn nötig (Quota-Saving)
    """
    
    league_id = match["league_id"]
    home = match["home"]
    away = match["away"]
    league = match["league"]
    
    # Team IDs holen (mit Caching!)
    home_id = get_team_id(home, league_id, season)
    away_id = get_team_id(away, league_id, season)
    
    # Verletzungen
    if include_injuries and home_id and away_id:
        match["injuries_home"] = fetch_injuries(home_id, league_id, season)
        match["injuries_away"] = fetch_injuries(away_id, league_id, season)
        match["has_injuries"] = True
    
    # Form
    if include_form and home_id and away_id:
        match["form_home"] = fetch_form(home_id, league_id, season)
        match["form_away"] = fetch_form(away_id, league_id, season)
        match["has_form"] = True
    
    # H2H
    if include_h2h and home_id and away_id:
        match["h2h"] = fetch_h2h(home_id, away_id)
        match["has_h2h"] = True
    
    # xG (Understat)
    if include_xg:
        match["xg_home"] = fetch_xg_data(home, league, season)
        match["xg_away"] = fetch_xg_data(away, league, season)
        match["has_xg"] = match["xg_home"]["available"] and match["xg_away"]["available"]
    
    return match


# ============================================================
# USAGE EXAMPLE
# ============================================================

if __name__ == "__main__":
    print("🔄 DATA AGGREGATOR - Test")
    print("=" * 60)
    
    # Test Match erstellen
    match = create_match_object(
        home="Manchester United",
        away="Liverpool",
        league="Premier League",
        league_id=39,
        date="2025-05-04T15:00:00Z",
        odds={"btts": 1.80, "over25": 1.65}
    )
    
    print(f"\n📋 Test Match: {match['home']} vs {match['away']}")
    print(f"Liga: {match['league']}")
    
    # Daten anreichern
    print("\n🔄 Fetching all data...")
    enriched = enrich_match_with_all_data(match, season=2024)
    
    # Ausgabe
    print("\n" + "=" * 60)
    print("✅ ENRICHED MATCH DATA")
    print("=" * 60)
    
    if enriched["has_injuries"]:
        print(f"\n🏥 Verletzungen:")
        print(f"   {enriched['home']}: {enriched['injuries_home']['total_out']} Ausfälle")
        print(f"   {enriched['away']}: {enriched['injuries_away']['total_out']} Ausfälle")
    
    if enriched["has_form"]:
        print(f"\n📊 Form:")
        print(f"   {enriched['home']}: {enriched['form_home']['form']} (Tore: {enriched['form_home']['goals_avg']:.1f})")
        print(f"   {enriched['away']}: {enriched['form_away']['form']} (Tore: {enriched['form_away']['goals_avg']:.1f})")
    
    if enriched["has_h2h"]:
        print(f"\n🔄 H2H:")
        print(f"   BTTS-Rate: {enriched['h2h']['btts_rate']:.0f}%")
        print(f"   Ø Tore: {enriched['h2h']['avg_goals']:.1f}")
    
    if enriched["has_xg"]:
        print(f"\n⚽ xG:")
        print(f"   {enriched['home']}: xG {enriched['xg_home']['xg_for']:.2f} | xGA {enriched['xg_home']['xg_against']:.2f}")
        print(f"   {enriched['away']}: xG {enriched['xg_away']['xg_for']:.2f} | xGA {enriched['xg_away']['xg_against']:.2f}")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete!")
