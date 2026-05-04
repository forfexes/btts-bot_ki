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
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Odds API Keys (für Resultate)
ODDS_API_KEYS = [k.strip() for k in os.getenv("ODDS_API_KEYS", "").split(",") if k.strip()]

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
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        log("Supabase Config fehlt", "ERROR")
        return []
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
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
    Holt Match-Ergebnis von Odds API.
    Returns: {'home_score': 2, 'away_score': 1} oder None
    """
    if not ODDS_API_KEYS:
        return None
    
    sport_key = LEAGUE_KEYS.get(league)
    if not sport_key:
        return None
    
    # Match muss mindestens 2h in der Vergangenheit sein
    try:
        match_date = datetime.fromisoformat(date_str)
        now = datetime.now(timezone.utc)
        if match_date > now - timedelta(hours=2):
            return None  # Noch zu früh
    except:
        return None
    
    for key in ODDS_API_KEYS:
        try:
            # Scores endpoint
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/",
                params={
                    "apiKey": key,
                    "daysFrom": 3,  # Letzte 3 Tage
                },
                timeout=15,
            )
            
            if r.status_code == 429:
                continue  # Rate limit, nächster Key
            
            if not r.ok:
                continue
            
            games = r.json()
            
            # Match finden
            for g in games:
                home = g.get("home_team", "")
                away = g.get("away_team", "")
                
                # Fuzzy Match
                if match_name.lower() in f"{home} vs {away}".lower():
                    scores = g.get("scores")
                    if scores:
                        return {
                            "home_score": int(scores[0].get("score", 0)),
                            "away_score": int(scores[1].get("score", 0)),
                            "completed": g.get("completed", False),
                        }
            
            return None  # Match nicht gefunden
        
        except Exception as e:
            log(f"Odds API Error: {e}", "WARN")
            continue
    
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
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return False
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/tips"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
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
