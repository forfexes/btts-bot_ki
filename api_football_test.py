#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API-FOOTBALL TEST SCRIPT
========================
Testet ob API-Football Keys funktionieren und erkannt werden.
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

def log(msg, level="INFO"):
    """Simple Logger"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def env_list(name: str) -> list[str]:
    """Holt komma-separierte Liste aus Environment"""
    value = os.getenv(name, "").strip()
    return [x.strip() for x in value.split(",") if x.strip()]


# API Keys laden (genau wie im Bot)
API_FOOTBALL_KEYS = env_list("API_FOOTBALL_KEYS")
if not API_FOOTBALL_KEYS:
    single_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if single_key:
        API_FOOTBALL_KEYS = [single_key]


def test_api_football_key(api_key, index=1):
    """
    Testet einen einzelnen API-Football Key
    Returns: (success: bool, quota_info: dict)
    """
    log(f"Teste API-Football Key #{index}...")
    log(f"Key: {api_key[:10]}...{api_key[-6:]}")
    
    try:
        # Einfacher Test-Request (Status Endpoint)
        url = "https://v3.football.api-sports.io/status"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        
        log("   📤 Sende Request an API-Football...")
        r = requests.get(url, headers=headers, timeout=15)
        
        log(f"   📥 Status Code: {r.status_code}")
        
        if r.status_code == 401:
            log("   ❌ FEHLER: Key ungültig oder abgelaufen!", "ERROR")
            log(f"   Response: {r.text}", "ERROR")
            return False, {}
        
        if r.status_code == 403:
            log("   ❌ FEHLER: Zugriff verweigert (403)", "ERROR")
            log(f"   Response: {r.text}", "ERROR")
            return False, {}
        
        if r.status_code == 429:
            log("   ⚠️ WARNUNG: Rate Limit erreicht!", "WARN")
            return False, {"rate_limited": True}
        
        if not r.ok:
            log(f"   ❌ FEHLER: HTTP {r.status_code}", "ERROR")
            log(f"   Response: {r.text}", "ERROR")
            return False, {}
        
        # Parse Response
        data = r.json()
        
        if data.get("errors"):
            log(f"   ❌ API Fehler: {data['errors']}", "ERROR")
            return False, {}
        
        # Account Info
        response = data.get("response", {})
        account = response.get("account", {})
        requests_info = response.get("requests", {})
        
        quota_info = {
            "account_name": account.get("firstname", "N/A"),
            "email": account.get("email", "N/A"),
            "requests_current": requests_info.get("current", 0),
            "requests_limit_day": requests_info.get("limit_day", 0),
        }
        
        log("   ✅ Key ist gültig!")
        log(f"   📊 Account: {quota_info['account_name']} ({quota_info['email']})")
        log(f"   📊 Requests heute: {quota_info['requests_current']} / {quota_info['requests_limit_day']}")
        
        return True, quota_info
    
    except requests.exceptions.Timeout:
        log("   ❌ TIMEOUT: API antwortet nicht", "ERROR")
        return False, {}
    
    except requests.exceptions.RequestException as e:
        log(f"   ❌ REQUEST ERROR: {e}", "ERROR")
        return False, {}
    
    except Exception as e:
        log(f"   ❌ FEHLER: {e}", "ERROR")
        return False, {}


def test_injuries_endpoint(api_key):
    """
    Testet den Injuries Endpoint (wichtig für die Erweiterung)
    """
    log("\n🏥 Teste Injuries Endpoint...")
    
    try:
        # Test mit Premier League (league=39, season=2024)
        url = "https://v3.football.api-sports.io/injuries"
        headers = {
            "x-rapidapi-host": "v3.football.api-sports.io",
            "x-rapidapi-key": api_key
        }
        params = {
            "league": "39",  # Premier League
            "season": "2024"
        }
        
        log("   📤 Request: Injuries für Premier League 2024...")
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if not r.ok:
            log(f"   ⚠️ Status: {r.status_code}", "WARN")
            return False
        
        data = r.json()
        injuries = data.get("response", [])
        
        log(f"   ✅ Injuries Endpoint funktioniert!")
        log(f"   📊 Gefunden: {len(injuries)} verletzte/gesperrte Spieler")
        
        if injuries:
            # Zeige ersten Eintrag als Beispiel
            first = injuries[0]
            player = first.get("player", {})
            team = first.get("team", {})
            log(f"   📋 Beispiel: {player.get('name')} ({team.get('name')}) - {first.get('player', {}).get('reason', 'N/A')}")
        
        return True
    
    except Exception as e:
        log(f"   ❌ Injuries Test Fehler: {e}", "ERROR")
        return False


def main():
    log("=" * 70)
    log("🧪 API-FOOTBALL TEST SCRIPT")
    log("=" * 70)
    log("")
    
    # 1. Check ob Keys geladen wurden
    log("📋 SCHRITT 1: Environment Variables prüfen")
    log("-" * 70)
    
    # Alle relevanten Env Vars anzeigen
    env_vars = {
        "API_FOOTBALL_KEYS": os.getenv("API_FOOTBALL_KEYS", ""),
        "API_FOOTBALL_KEY": os.getenv("API_FOOTBALL_KEY", ""),
    }
    
    log("Environment Variables:")
    for key, value in env_vars.items():
        if value:
            # Zeige nur ersten/letzten Teil des Keys
            if len(value) > 20:
                masked = f"{value[:10]}...{value[-6:]}"
            else:
                masked = f"{value[:5]}...{value[-3:]}"
            log(f"   ✅ {key}: {masked}")
        else:
            log(f"   ❌ {key}: NICHT GESETZT")
    
    log("")
    log(f"Geladene Keys (geparst): {len(API_FOOTBALL_KEYS)}")
    
    if not API_FOOTBALL_KEYS:
        log("❌ FEHLER: Keine API-Football Keys gefunden!", "ERROR")
        log("")
        log("LÖSUNG:")
        log("1. GitHub Secrets prüfen:")
        log("   - Gehe zu Repository → Settings → Secrets → Actions")
        log("   - Secret-Name: API_FOOTBALL_KEYS (Plural!)")
        log("   - Format: key1,key2 (komma-separiert, KEINE Leerzeichen)")
        log("")
        log("2. Workflow YML prüfen:")
        log("   env:")
        log("     API_FOOTBALL_KEYS: ${{ secrets.API_FOOTBALL_KEYS }}")
        log("")
        sys.exit(1)
    
    log("")
    log("=" * 70)
    log("📋 SCHRITT 2: Keys testen")
    log("-" * 70)
    log("")
    
    valid_keys = []
    
    for i, key in enumerate(API_FOOTBALL_KEYS, 1):
        success, quota = test_api_football_key(key, i)
        
        if success:
            valid_keys.append((key, quota))
        
        log("")
    
    # Summary
    log("=" * 70)
    log("📊 ZUSAMMENFASSUNG")
    log("-" * 70)
    log(f"✅ Gültige Keys: {len(valid_keys)} / {len(API_FOOTBALL_KEYS)}")
    
    if not valid_keys:
        log("")
        log("❌ KEINE gültigen Keys gefunden!", "ERROR")
        log("")
        log("MÖGLICHE URSACHEN:")
        log("1. Keys sind abgelaufen")
        log("2. Keys sind ungültig (Tippfehler)")
        log("3. API-Football Account wurde deaktiviert")
        log("")
        log("LÖSUNG:")
        log("- Neue Keys erstellen: https://www.api-football.com/register")
        log("- Keys in GitHub Secrets aktualisieren")
        sys.exit(1)
    
    log("")
    
    # Test Injuries Endpoint mit erstem gültigen Key
    if valid_keys:
        first_key = valid_keys[0][0]
        log("")
        log("=" * 70)
        log("📋 SCHRITT 3: Injuries Endpoint testen (für Erweiterung)")
        log("-" * 70)
        test_injuries_endpoint(first_key)
    
    log("")
    log("=" * 70)
    log("✅ TEST ABGESCHLOSSEN!")
    log("=" * 70)
    log("")
    log("NÄCHSTE SCHRITTE:")
    log("1. Wenn alle Tests erfolgreich: Bot kann erweitert werden ✅")
    log("2. Falls Fehler: Siehe Fehlermeldungen oben")
    log("")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n\n⚠️ Test abgebrochen", "WARN")
        sys.exit(1)
    except Exception as e:
        log(f"\n\n❌ FATAL ERROR: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
