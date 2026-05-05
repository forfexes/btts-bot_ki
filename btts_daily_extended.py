"""
🚀 NETRATTLER AI BOT - EXTENDED VERSION
========================================

NEUE FEATURES:
✅ Verletzungen & Sperren (API-Football)
✅ Team Form (Letzte 5-6 Spiele)
✅ Head-to-Head Analyse
✅ Multi-Combo System (Automatische Kombis)
✅ Enhanced AI-Analyse mit allen Kontext-Daten

Diese Funktionen werden in btts_daily.py integriert.
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple


# ============================================================
# 🆕 API-FOOTBALL INJURIES & SUSPENSIONS
# ============================================================

def get_api_football_injuries(team_id: int, league_id: int, season: int, api_key: str) -> Dict:
    """
    Holt Verletzungen & Sperren für ein Team von API-Football.
    
    Returns:
    {
        "injuries": [...],
        "suspensions": [...],
        "total_out": int,
        "key_players_out": [...],
        "impact_score": float  # 0.0-10.0 (10 = massive Impact)
    }
    """
    try:
        url = "https://v3.football.api-sports.io/injuries"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        params = {
            "team": team_id,
            "league": league_id,
            "season": season
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            return _empty_injuries_data()
        
        data = r.json()
        injuries_list = data.get("response", [])
        
        if not injuries_list:
            return _empty_injuries_data()
        
        # Analysiere Verletzungen
        injuries = []
        suspensions = []
        key_players = []
        
        for entry in injuries_list:
            player = entry.get("player", {})
            injury_type = entry.get("player", {}).get("type", "").lower()
            reason = entry.get("player", {}).get("reason", "").lower()
            
            player_data = {
                "name": player.get("name", "Unknown"),
                "reason": reason,
                "type": injury_type,
            }
            
            # Ist es eine Sperre oder Verletzung?
            if "suspension" in reason or "banned" in reason or "card" in reason:
                suspensions.append(player_data)
            else:
                injuries.append(player_data)
            
            # Key Player? (simplifiziert - könnte durch Statistiken erweitert werden)
            # In echter Implementation würde man hier nach Position, Spielzeit etc. filtern
            key_players.append(player_data)
        
        # Impact Score berechnen (0-10)
        total_out = len(injuries) + len(suspensions)
        impact_score = min(10.0, total_out * 1.5)  # Je mehr fehlen, desto höher
        
        return {
            "injuries": injuries,
            "suspensions": suspensions,
            "total_out": total_out,
            "key_players_out": key_players[:5],  # Top 5
            "impact_score": impact_score,
            "has_data": True
        }
    
    except Exception as e:
        return _empty_injuries_data()


def _empty_injuries_data() -> Dict:
    """Leere Injury-Daten für Fallback"""
    return {
        "injuries": [],
        "suspensions": [],
        "total_out": 0,
        "key_players_out": [],
        "impact_score": 0.0,
        "has_data": False
    }


# ============================================================
# 🆕 TEAM FORM ANALYSIS
# ============================================================

def get_team_form_data(team_id: int, league_id: int, season: int, api_key: str) -> Dict:
    """
    Holt Team-Form (letzte 5-6 Spiele) von API-Football.
    
    Returns:
    {
        "form": "WWDLW",  # W=Win, D=Draw, L=Loss
        "last_5_games": [...],
        "goals_scored_avg": float,
        "goals_conceded_avg": float,
        "btts_rate": float  # % der letzten Spiele mit BTTS
    }
    """
    try:
        url = "https://v3.football.api-sports.io/fixtures"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        params = {
            "team": team_id,
            "league": league_id,
            "season": season,
            "last": 6  # Letzte 6 Spiele
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            return _empty_form_data()
        
        data = r.json()
        fixtures = data.get("response", [])
        
        if not fixtures:
            return _empty_form_data()
        
        # Analysiere letzte Spiele
        form_string = ""
        goals_scored = []
        goals_conceded = []
        btts_count = 0
        games = []
        
        for fixture in fixtures[-5:]:  # Letzte 5 nehmen
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            score = fixture.get("score", {}).get("fulltime", {})
            
            home_id = teams.get("home", {}).get("id")
            away_id = teams.get("away", {}).get("id")
            
            home_goals = score.get("home", 0) or 0
            away_goals = score.get("away", 0) or 0
            
            # Ist unser Team Home oder Away?
            if home_id == team_id:
                our_goals = home_goals
                their_goals = away_goals
            else:
                our_goals = away_goals
                their_goals = home_goals
            
            goals_scored.append(our_goals)
            goals_conceded.append(their_goals)
            
            # BTTS?
            if home_goals > 0 and away_goals > 0:
                btts_count += 1
            
            # Form String
            if our_goals > their_goals:
                form_string += "W"
            elif our_goals < their_goals:
                form_string += "L"
            else:
                form_string += "D"
            
            games.append({
                "opponent": teams.get("away", {}).get("name") if home_id == team_id else teams.get("home", {}).get("name"),
                "score": f"{our_goals}-{their_goals}",
                "result": form_string[-1]
            })
        
        return {
            "form": form_string,
            "last_5_games": games,
            "goals_scored_avg": sum(goals_scored) / len(goals_scored) if goals_scored else 0.0,
            "goals_conceded_avg": sum(goals_conceded) / len(goals_conceded) if goals_conceded else 0.0,
            "btts_rate": (btts_count / len(fixtures[-5:])) * 100 if fixtures else 0.0,
            "has_data": True
        }
    
    except Exception as e:
        return _empty_form_data()


def _empty_form_data() -> Dict:
    """Leere Form-Daten für Fallback"""
    return {
        "form": "",
        "last_5_games": [],
        "goals_scored_avg": 0.0,
        "goals_conceded_avg": 0.0,
        "btts_rate": 0.0,
        "has_data": False
    }


# ============================================================
# 🆕 HEAD-TO-HEAD ANALYSIS
# ============================================================

def get_h2h_history(team1_id: int, team2_id: int, api_key: str, last_n: int = 5) -> Dict:
    """
    Holt Head-to-Head History zwischen zwei Teams.
    
    Returns:
    {
        "h2h_matches": [...],
        "total_matches": int,
        "btts_rate": float,
        "avg_goals": float,
        "team1_wins": int,
        "team2_wins": int,
        "draws": int
    }
    """
    try:
        url = "https://v3.football.api-sports.io/fixtures/headtohead"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        params = {
            "h2h": f"{team1_id}-{team2_id}",
            "last": last_n
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            return _empty_h2h_data()
        
        data = r.json()
        fixtures = data.get("response", [])
        
        if not fixtures:
            return _empty_h2h_data()
        
        # Analysiere H2H
        btts_count = 0
        total_goals = 0
        team1_wins = 0
        team2_wins = 0
        draws = 0
        matches = []
        
        for fixture in fixtures:
            score = fixture.get("score", {}).get("fulltime", {})
            teams = fixture.get("teams", {})
            
            home_goals = score.get("home", 0) or 0
            away_goals = score.get("away", 0) or 0
            
            total_goals += home_goals + away_goals
            
            if home_goals > 0 and away_goals > 0:
                btts_count += 1
            
            # Winner
            home_id = teams.get("home", {}).get("id")
            if home_goals > away_goals:
                if home_id == team1_id:
                    team1_wins += 1
                else:
                    team2_wins += 1
            elif away_goals > home_goals:
                if home_id == team1_id:
                    team2_wins += 1
                else:
                    team1_wins += 1
            else:
                draws += 1
            
            matches.append({
                "date": fixture.get("fixture", {}).get("date", ""),
                "score": f"{home_goals}-{away_goals}",
                "home": teams.get("home", {}).get("name"),
                "away": teams.get("away", {}).get("name")
            })
        
        return {
            "h2h_matches": matches,
            "total_matches": len(fixtures),
            "btts_rate": (btts_count / len(fixtures)) * 100 if fixtures else 0.0,
            "avg_goals": total_goals / len(fixtures) if fixtures else 0.0,
            "team1_wins": team1_wins,
            "team2_wins": team2_wins,
            "draws": draws,
            "has_data": True
        }
    
    except Exception as e:
        return _empty_h2h_data()


def _empty_h2h_data() -> Dict:
    """Leere H2H-Daten für Fallback"""
    return {
        "h2h_matches": [],
        "total_matches": 0,
        "btts_rate": 0.0,
        "avg_goals": 0.0,
        "team1_wins": 0,
        "team2_wins": 0,
        "draws": 0,
        "has_data": False
    }


# ============================================================
# 🆕 ENHANCED AI PROMPT WITH CONTEXT
# ============================================================

def build_enhanced_ai_prompt(
    match_data: Dict,
    injuries_home: Dict,
    injuries_away: Dict,
    form_home: Dict,
    form_away: Dict,
    h2h: Dict,
    market: str = "btts"
) -> str:
    """
    Erstellt einen erweiterten AI-Prompt mit allen Kontext-Daten.
    """
    
    home = match_data.get("home", "Home Team")
    away = match_data.get("away", "Away Team")
    
    prompt = f"""Analysiere dieses Fußballspiel für {market.upper()} Wetten:

🏟️ MATCH: {home} vs {away}
⚽ Liga: {match_data.get('league', 'N/A')}
📅 Datum: {match_data.get('date', 'N/A')}

"""
    
    # Verletzungen & Sperren
    if injuries_home.get("has_data"):
        prompt += f"""
🏥 VERLETZUNGEN & SPERREN - {home}:
   • Gesamt Ausfälle: {injuries_home['total_out']}
   • Verletzte: {len(injuries_home['injuries'])}
   • Gesperrte: {len(injuries_home['suspensions'])}
   • Impact Score: {injuries_home['impact_score']}/10
"""
        if injuries_home['key_players_out']:
            prompt += f"   • Wichtige Spieler fehlen: {', '.join([p['name'] for p in injuries_home['key_players_out'][:3]])}\n"
    
    if injuries_away.get("has_data"):
        prompt += f"""
🏥 VERLETZUNGEN & SPERREN - {away}:
   • Gesamt Ausfälle: {injuries_away['total_out']}
   • Verletzte: {len(injuries_away['injuries'])}
   • Gesperrte: {len(injuries_away['suspensions'])}
   • Impact Score: {injuries_away['impact_score']}/10
"""
        if injuries_away['key_players_out']:
            prompt += f"   • Wichtige Spieler fehlen: {', '.join([p['name'] for p in injuries_away['key_players_out'][:3]])}\n"
    
    # Team Form
    if form_home.get("has_data"):
        prompt += f"""
📊 FORM - {home}:
   • Letzte 5: {form_home['form']} (W=Win, D=Draw, L=Loss)
   • Tore pro Spiel: {form_home['goals_scored_avg']:.1f}
   • Gegentore: {form_home['goals_conceded_avg']:.1f}
   • BTTS-Rate: {form_home['btts_rate']:.0f}%
"""
    
    if form_away.get("has_data"):
        prompt += f"""
📊 FORM - {away}:
   • Letzte 5: {form_away['form']}
   • Tore pro Spiel: {form_away['goals_scored_avg']:.1f}
   • Gegentore: {form_away['goals_conceded_avg']:.1f}
   • BTTS-Rate: {form_away['btts_rate']:.0f}%
"""
    
    # Head-to-Head
    if h2h.get("has_data") and h2h['total_matches'] > 0:
        prompt += f"""
🔄 HEAD-TO-HEAD (letzte {h2h['total_matches']} Spiele):
   • {home} Siege: {h2h['team1_wins']}
   • {away} Siege: {h2h['team2_wins']}
   • Unentschieden: {h2h['draws']}
   • BTTS-Rate: {h2h['btts_rate']:.0f}%
   • Durchschnittliche Tore: {h2h['avg_goals']:.1f}
"""
        # Zeige letzte 3 H2H Ergebnisse
        if h2h['h2h_matches']:
            prompt += "   • Letzte Ergebnisse:\n"
            for match in h2h['h2h_matches'][:3]:
                prompt += f"     - {match['home']} {match['score']} {match['away']}\n"
    
    # Market-spezifische Anweisungen
    if market == "btts":
        prompt += """
📋 AUFGABE: Bewerte dieses Spiel für BOTH TEAMS TO SCORE (BTTS)

Berücksichtige:
1. Verletzungen von Schlüsselspielern (Stürmer/Verteidiger)
2. Offensive/Defensive Form beider Teams
3. H2H BTTS-Trend
4. Taktische Ausrichtung

Gib zurück: YES oder NO mit Confidence (1-5) und Begründung.
"""
    elif market == "over25":
        prompt += """
📋 AUFGABE: Bewerte dieses Spiel für OVER 2.5 TORE

Berücksichtige:
1. Durchschnittliche Tore beider Teams
2. H2H Tor-Durchschnitt
3. Verletzungen in Defensive/Offensive
4. Spielstil beider Teams

Gib zurück: YES oder NO mit Confidence (1-5) und Begründung.
"""
    
    prompt += """
Antworte im JSON-Format:
{
  "tip": "YES" oder "NO",
  "confidence": 1-5,
  "reasoning": "Begründung",
  "key_factors": ["Faktor 1", "Faktor 2", ...]
}
"""
    
    return prompt


# ============================================================
# 🆕 MULTI-COMBO GENERATOR
# ============================================================

def generate_multi_combo_bets(
    all_tips: List[Dict],
    combo_type: str = "safe"
) -> Optional[Dict]:
    """
    Generiert automatisch eine Multi-Combo aus den besten Tipps.
    
    combo_type:
    - "safe": 3-4 Tipps, Quote 3.0-5.0, High Confidence
    - "value": 4-5 Tipps, Quote 6.0-12.0, Medium-High Confidence
    - "risk": 5-6 Tipps, Quote 15.0+, Mixed Confidence
    
    Returns:
    {
        "combo_type": str,
        "tips": [...],
        "total_odds": float,
        "expected_confidence": float,
        "stake_suggestion": float (1-10 units)
    }
    """
    
    if not all_tips:
        return None
    
    # Filter: Nur Tipps mit Odds >= 1.50
    valid_tips = [t for t in all_tips if t.get("odds", 0) >= 1.50]
    
    if not valid_tips:
        return None
    
    # Sortiere nach Confidence & Value
    sorted_tips = sorted(
        valid_tips,
        key=lambda x: (x.get("confidence", 0), x.get("value_rating", 0)),
        reverse=True
    )
    
    # Combo-Logik nach Typ
    if combo_type == "safe":
        # 3-4 beste Tipps, hohe Confidence (4-5)
        selected = [t for t in sorted_tips if t.get("confidence", 0) >= 4][:4]
        target_odds_min = 3.0
        target_odds_max = 6.0
        
    elif combo_type == "value":
        # 4-5 Tipps, Medium-High Confidence (3-5)
        selected = [t for t in sorted_tips if t.get("confidence", 0) >= 3][:5]
        target_odds_min = 6.0
        target_odds_max = 15.0
        
    else:  # risk
        # 5-6 Tipps, Mixed
        selected = sorted_tips[:6]
        target_odds_min = 15.0
        target_odds_max = 100.0
    
    if len(selected) < 3:
        return None
    
    # Berechne Gesamt-Quote
    total_odds = 1.0
    for tip in selected:
        total_odds *= tip.get("odds", 1.0)
    
    # Prüfe ob Quote im Target-Bereich
    if total_odds < target_odds_min:
        # Zu niedrig, füge noch einen Tipp hinzu
        if len(selected) < len(sorted_tips):
            selected.append(sorted_tips[len(selected)])
            total_odds *= sorted_tips[len(selected) - 1].get("odds", 1.0)
    
    # Average Confidence
    avg_confidence = sum(t.get("confidence", 0) for t in selected) / len(selected)
    
    # Stake Suggestion (1-10 units)
    if combo_type == "safe":
        stake = min(10, max(3, int(avg_confidence * 2)))
    elif combo_type == "value":
        stake = min(7, max(2, int(avg_confidence * 1.5)))
    else:  # risk
        stake = min(5, max(1, int(avg_confidence)))
    
    return {
        "combo_type": combo_type,
        "tips": selected,
        "total_odds": round(total_odds, 2),
        "expected_confidence": round(avg_confidence, 1),
        "stake_suggestion": stake,
        "num_tips": len(selected)
    }


def format_combo_telegram_message(combo: Dict) -> str:
    """Formatiert Combo für Telegram"""
    if not combo:
        return ""
    
    type_emoji = {
        "safe": "🛡️ SAFE COMBO",
        "value": "💎 VALUE COMBO",
        "risk": "🚀 RISK COMBO"
    }
    
    msg = f"""
<b>{type_emoji.get(combo['combo_type'], '🎲 COMBO')}</b>

🎯 <b>Gesamt-Quote: {combo['total_odds']}</b>
⚡ Confidence: {combo['expected_confidence']}/5.0
💰 Stake: {combo['stake_suggestion']} Units
📋 Anzahl Tipps: {combo['num_tips']}

<b>🎫 TIPPS:</b>
"""
    
    for i, tip in enumerate(combo['tips'], 1):
        msg += f"""
{i}. <b>{tip.get('match', 'N/A')}</b>
   • {tip.get('league', 'N/A')}
   • {tip.get('market', 'BTTS').upper()}: {tip.get('tip', 'N/A')}
   • Quote: {tip.get('odds', 0.0)}
   • ⭐ {tip.get('confidence', 0)}/5
"""
    
    msg += f"""
<b>💡 STRATEGIE:</b>
• {combo['combo_type'].upper()}: {"Hohe Sicherheit, moderate Quote" if combo['combo_type'] == 'safe' else "Balance zwischen Risiko & Quote" if combo['combo_type'] == 'value' else "Hohes Risiko, hohe Quote"}
• Empfohlener Einsatz: {combo['stake_suggestion']} Units

<i>⚠️ Wetten auf eigenes Risiko. Verantwortungsvoll spielen!</i>
"""
    
    return msg


# ============================================================
# HELPER: GET TEAM ID FROM API-FOOTBALL
# ============================================================

def get_team_id_by_name(team_name: str, league_id: int, season: int, api_key: str) -> Optional[int]:
    """
    Findet Team-ID für ein Team in einer Liga.
    Simplifiziert - in Produktion würde man Caching nutzen.
    """
    try:
        url = "https://v3.football.api-sports.io/teams"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        params = {
            "league": league_id,
            "season": season,
            "search": team_name[:10]  # Erste 10 Zeichen für Suche
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            return None
        
        data = r.json()
        teams = data.get("response", [])
        
        if not teams:
            return None
        
        # Erste Übereinstimmung nehmen (könnte verfeinert werden)
        return teams[0].get("team", {}).get("id")
    
    except Exception:
        return None


# ============================================================
# 🆕 INTEGRIERTE ANALYSE-FUNKTION
# ============================================================

def analyze_match_with_full_context(
    match_data: Dict,
    league_id: int,
    season: int,
    api_key: str,
    market: str = "btts"
) -> Dict:
    """
    Führt vollständige Analyse eines Matches durch mit allen neuen Features.
    
    Returns erweiterte match_data mit:
    - injuries_home, injuries_away
    - form_home, form_away
    - h2h
    - enhanced_prompt (für AI)
    """
    
    home_team = match_data.get("home", "")
    away_team = match_data.get("away", "")
    
    # Team IDs holen
    home_id = get_team_id_by_name(home_team, league_id, season, api_key)
    away_id = get_team_id_by_name(away_team, league_id, season, api_key)
    
    # Daten sammeln (mit Fallbacks)
    injuries_home = get_api_football_injuries(home_id, league_id, season, api_key) if home_id else _empty_injuries_data()
    injuries_away = get_api_football_injuries(away_id, league_id, season, api_key) if away_id else _empty_injuries_data()
    
    form_home = get_team_form_data(home_id, league_id, season, api_key) if home_id else _empty_form_data()
    form_away = get_team_form_data(away_id, league_id, season, api_key) if away_id else _empty_form_data()
    
    h2h = get_h2h_history(home_id, away_id, api_key) if (home_id and away_id) else _empty_h2h_data()
    
    # Enhanced Prompt erstellen
    enhanced_prompt = build_enhanced_ai_prompt(
        match_data,
        injuries_home,
        injuries_away,
        form_home,
        form_away,
        h2h,
        market
    )
    
    # Alles zusammenpacken
    match_data["injuries_home"] = injuries_home
    match_data["injuries_away"] = injuries_away
    match_data["form_home"] = form_home
    match_data["form_away"] = form_away
    match_data["h2h"] = h2h
    match_data["enhanced_prompt"] = enhanced_prompt
    match_data["has_extended_data"] = True
    
    return match_data


# ============================================================
# EXAMPLE USAGE (für Tests)
# ============================================================

if __name__ == "__main__":
    print("🚀 NETRATTLER AI BOT - Extended Features")
    print("=" * 60)
    print("")
    print("✅ Neue Features verfügbar:")
    print("   • get_api_football_injuries()")
    print("   • get_team_form_data()")
    print("   • get_h2h_history()")
    print("   • build_enhanced_ai_prompt()")
    print("   • generate_multi_combo_bets()")
    print("   • analyze_match_with_full_context()")
    print("")
    print("📝 Diese Funktionen müssen in btts_daily.py integriert werden.")
    print("")
