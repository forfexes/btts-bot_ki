#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTTS Settlement Bot - Prüft pending Tipps und markiert sie als won/lost
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Odds API Keys (für Resultate)
ODDS_API_KEYS = [k.strip() for k in os.getenv("ODDS_API_KEYS", "").split(",") if k.strip()]

# 🆕 BSD Config
BSD_API_URL = "https://sports.bzzoiro.com/api"

# 🆕 Sportmonks Config
SPORTMONKS_API_KEY = os.getenv("SPORTMONKS_API_KEY", "")

# League Keys für Odds API
LEAGUE_KEYS = {
    "Premier League": "soccer_epl",
    "Bundesliga": "soccer_germany_bundesliga",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Ligue 1": "soccer_france_ligue_one",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Championship": "soccer_england_championship",
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    # Weitere nach Bedarf
}


def log(msg, level="INFO"):
    """Simple Logger"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def send_telegram(text):
    """Sendet Nachricht an Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram Error: {e}", "WARN")


def get_pending_tips():
    """Holt alle pending Tipps aus Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Supabase Config fehlt", "ERROR")
        return []
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        params = {
            "status": "eq.pending",
            "select": "*",
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            log(f"Supabase Error: {r.status_code}", "ERROR")
            return []
        
        tips = r.json()
        log(f"📥 {len(tips)} pending Tipps gefunden")
        return tips
    
    except Exception as e:
        log(f"Error getting pending tips: {e}", "ERROR")
        return []


def get_match_result(match_name, league, date_str):
    """
    Holt Match-Ergebnis von mehreren Quellen.
    Versucht der Reihe nach: Odds API → BSD → Sportmonks
    Returns: {'home_score': 2, 'away_score': 1, 'completed': True} oder None
    """
    if not match_name or not league:
        return None
    
    # Spiel muss mindestens 2h vorbei sein
    try:
        match_date = datetime.fromisoformat(date_str)
        now = datetime.now(timezone.utc)
        if match_date > now - timedelta(hours=2):
            return None
    except:
        return None
    
    # 1️⃣ Versuche Odds API (primäre Quelle)
    result = get_result_from_odds_api(match_name, league, date_str)
    if result:
        log(f"   ✅ Ergebnis von Odds API: {match_name} {result['home_score']}-{result['away_score']}")
        return result
    
    # 2️⃣ Versuche BSD (Fallback für 8 Top-Ligen)
    result = get_result_from_bsd(match_name, league, date_str)
    if result:
        log(f"   ✅ Ergebnis von BSD: {match_name} {result['home_score']}-{result['away_score']}")
        return result
    
    # 3️⃣ Versuche Sportmonks (Fallback für DK/SCO)
    result = get_result_from_sportmonks(match_name, league, date_str)
    if result:
        log(f"   ✅ Ergebnis von Sportmonks: {match_name} {result['home_score']}-{result['away_score']}")
        return result
    
    return None


def get_result_from_odds_api(match_name, league, date_str):
    """Odds API Scores Endpoint"""
    if not ODDS_API_KEYS:
        return None
    
    sport_key = LEAGUE_KEYS.get(league)
    if not sport_key:
        return None
    
    for key in ODDS_API_KEYS:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/",
                params={"apiKey": key, "daysFrom": 3},
                timeout=15,
            )
            
            if r.status_code == 429:
                continue
            if not r.ok:
                continue
            
            games = r.json()
            
            # Fuzzy Match Team Names
            for g in games:
                home = g.get("home_team", "").lower()
                away = g.get("away_team", "").lower()
                match_lower = match_name.lower()
                
                if (home in match_lower or away in match_lower or
                    f"{home} vs {away}" in match_lower):
                    
                    scores = g.get("scores")
                    if scores and len(scores) >= 2:
                        return {
                            "home_score": int(scores[0].get("score", 0)),
                            "away_score": int(scores[1].get("score", 0)),
                            "completed": g.get("completed", False),
                        }
            
            return None
        except Exception:
            continue
    
    return None


def get_result_from_bsd(match_name, league, date_str):
    """BSD API für 8 Top-Ligen (Premier, La Liga, Serie A, etc.)"""
    # BSD deckt nur diese 8 Ligen ab
    bsd_leagues = [
        "Premier League", "La Liga", "Serie A", "Bundesliga",
        "Ligue 1", "Championship", "Primeira Liga", "Eredivisie"
    ]
    
    if league not in bsd_leagues:
        return None
    
    try:
        r = requests.get(
            f"{BSD_API_URL}/matches",
            params={
                "league": league,
                "date": date_str.split("T")[0],  # YYYY-MM-DD
                "status": "finished",
            },
            timeout=12,
        )
        
        if not r.ok:
            return None
        
        data = r.json()
        match_lower = match_name.lower()
        
        for match in data.get("matches", []):
            home = match.get("home_team", {}).get("name", "").lower()
            away = match.get("away_team", {}).get("name", "").lower()
            
            if (home in match_lower or away in match_lower or
                f"{home} vs {away}" in match_lower):
                
                return {
                    "home_score": int(match.get("score", {}).get("home", 0)),
                    "away_score": int(match.get("score", {}).get("away", 0)),
                    "completed": True,
                }
        
        return None
    except Exception:
        return None


def get_result_from_sportmonks(match_name, league, date_str):
    """Sportmonks API für Dänemark + Schottland"""
    if not SPORTMONKS_API_KEY:
        return None
    
    sportmonks_leagues = ["Danish Superligaen", "Scottish Premiership"]
    if league not in sportmonks_leagues:
        return None
    
    try:
        r = requests.get(
            f"https://api.sportmonks.com/v2.0/fixtures",
            params={
                "api_token": SPORTMONKS_API_KEY,
                "filters": f"statusId:3",  # 3 = Finished
                "include": "teams,scores",
            },
            timeout=12,
        )
        
        if not r.ok:
            return None
        
        data = r.json()
        match_lower = match_name.lower()
        
        for match in data.get("data", []):
            # Check date
            match_date = match.get("date", "").split("T")[0]
            if match_date != date_str.split("T")[0]:
                continue
            
            teams = match.get("teams", {}).get("data", [])
            if len(teams) < 2:
                continue
            
            home = teams[0].get("name", "").lower()
            away = teams[1].get("name", "").lower()
            
            if (home in match_lower or away in match_lower or
                f"{home} vs {away}" in match_lower):
                
                scores = match.get("scores", {}).get("data", [])
                if len(scores) >= 2:
                    return {
                        "home_score": int(scores[0].get("score", 0)),
                        "away_score": int(scores[1].get("score", 0)),
                        "completed": True,
                    }
        
        return None
    except Exception:
        return None


def check_btts_result(home_score, away_score, tip):
    """
    Prüft ob BTTS-Tipp gewonnen/verloren hat.
    tip: "YES" oder "NO"
    """
    btts_happened = (home_score > 0 and away_score > 0)
    
    if tip == "YES":
        return "won" if btts_happened else "lost"
    elif tip == "NO":
        return "won" if not btts_happened else "lost"
    
    return None


def update_tip_status(tip_id, new_status, result_info=None):
    """Updated Tipp-Status in Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        
        payload = {"status": new_status}
        if result_info:
            payload["result_info"] = json.dumps(result_info)
        
        r = requests.patch(
            url,
            headers=headers,
            params={"id": f"eq.{tip_id}"},
            json=payload,
            timeout=10,
        )
        
        return r.ok
    
    except Exception as e:
        log(f"Update Error: {e}", "ERROR")
        return False


def main():
    """Haupt-Settlement-Logik"""
    log("🔍 BTTS Settlement Bot gestartet")
    log("=" * 50)
    
    pending_tips = get_pending_tips()
    
    if not pending_tips:
        log("Keine pending Tipps gefunden oder Supabase nicht konfiguriert")
        return
    
    # Nur Tipps von vor >2h checken (Spiel muss vorbei sein)
    now = datetime.now(timezone.utc)
    checkable = []
    
    for tip in pending_tips:
        try:
            tip_date = datetime.fromisoformat(tip.get("date", ""))
            if tip_date < now - timedelta(hours=2):
                checkable.append(tip)
        except:
            continue
    
    log(f"📋 {len(checkable)} Tipps sind alt genug zum Checken")
    
    if not checkable:
        log("Alle pending Tipps sind zu frisch (Spiele noch nicht vorbei)")
        return
    
    settled = 0
    won = 0
    lost = 0
    not_found = 0
    
    for tip in checkable[:50]:  # Max 50 pro Run (Quota-Schutz)
        match_name = tip.get("match", "")
        league = tip.get("league", "")
        date_str = tip.get("date", "")
        tip_market = tip.get("market", "btts")
        tip_value = tip.get("tip", "YES")
        tip_id = tip.get("id")
        
        log(f"Checking: {match_name} ({league}) - {tip_value}")
        
        # Resultat holen
        result = get_match_result(match_name, league, date_str)
        
        if not result:
            not_found += 1
            continue
        
        if not result.get("completed"):
            continue  # Spiel noch nicht fertig
        
        # BTTS Check (für andere Markets später erweitern)
        if tip_market == "btts":
            new_status = check_btts_result(
                result["home_score"],
                result["away_score"],
                tip_value
            )
            
            if new_status:
                success = update_tip_status(
                    tip_id,
                    new_status,
                    {
                        "home_score": result["home_score"],
                        "away_score": result["away_score"],
                        "settled_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                
                if success:
                    settled += 1
                    if new_status == "won":
                        won += 1
                    else:
                        lost += 1
                    
                    log(f"✅ {match_name}: {new_status.upper()} ({result['home_score']}-{result['away_score']})")
    
    # Summary
    log("=" * 50)
    log(f"📊 Settlement Summary:")
    log(f"   • Settled: {settled}")
    log(f"   • Won: {won}")
    log(f"   • Lost: {lost}")
    log(f"   • Not Found: {not_found}")
    log(f"   • Remaining Pending: {len(pending_tips) - settled}")
    
    # Telegram Notification
    if settled > 0:
        msg = f"🤖 <b>Settlement Update</b>\n\n"
        msg += f"✅ Gewonnen: <b>{won}</b>\n"
        msg += f"❌ Verloren: <b>{lost}</b>\n"
        msg += f"⏳ Noch pending: <b>{len(pending_tips) - settled}</b>"
        send_telegram(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}", "ERROR")
        sys.exit(1)
