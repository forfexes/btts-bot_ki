"""
🧪 FBREF + UNDERSTAT TEST SCRIPT
=================================

Testet FBref Stats & Understat xG-Daten.
Zeigt welche Daten verfügbar sind und wie man sie nutzt.
"""

import sys

print("🔄 Versuche soccerdata zu importieren...")

try:
    import soccerdata as sd
    print("✅ soccerdata erfolgreich importiert!")
except ImportError:
    print("❌ soccerdata nicht gefunden!")
    print("\n📥 Installation:")
    print("   pip install soccerdata")
    sys.exit(1)

print("\n" + "=" * 60)
print("🧪 FBREF + UNDERSTAT TEST")
print("=" * 60)

# ============================================================
# TEST 1: UNDERSTAT (xG-DATEN)
# ============================================================

print("\n📊 TEST 1: UNDERSTAT xG-DATEN")
print("-" * 60)

try:
    # Premier League 2024/25
    print("\n🔄 Lade Understat Daten (Premier League 2024)...")
    understat = sd.Understat("ENG-Premier League", "2425")
    
    # Team Match Stats holen
    team_stats = understat.read_team_match_stats()
    
    print(f"✅ Daten geladen: {len(team_stats)} Einträge")
    
    # Beispiel: Manchester United
    print("\n🔍 Beispiel: Manchester United")
    man_utd = team_stats[team_stats['team'].str.contains('Manchester United', case=False, na=False)]
    
    if not man_utd.empty:
        recent = man_utd.tail(5)  # Letzte 5 Spiele
        
        print(f"   📈 Letzte 5 Spiele:")
        print(f"   • xG (Expected Goals): {recent['xG'].mean():.2f}")
        print(f"   • xGA (xG Against): {recent['xGA'].mean():.2f}")
        print(f"   • xG Diff: {(recent['xG'] - recent['xGA']).mean():.2f}")
        print(f"   • Actual Goals: {recent['scored'].mean():.2f}")
        
        # Over/Under Performance
        over_perf = recent['scored'].mean() > recent['xG'].mean()
        print(f"   • Performance: {'🔥 Overperforming' if over_perf else '❄️ Underperforming'}")
    else:
        print("   ⚠️ Keine Daten für Manchester United gefunden")

except Exception as e:
    print(f"❌ Understat Error: {e}")
    print("   Mögliche Gründe:")
    print("   - Keine Internet-Verbindung")
    print("   - Understat-Website down")
    print("   - Saison noch nicht verfügbar")

# ============================================================
# TEST 2: FBREF (TEAM-STATS)
# ============================================================

print("\n\n📊 TEST 2: FBREF TEAM-STATS")
print("-" * 60)

try:
    print("\n🔄 Lade FBref Daten (Premier League 2024)...")
    fbref = sd.FBref("ENG-Premier League", "2425")
    
    # Team Season Stats
    team_stats = fbref.read_team_season_stats()
    
    print(f"✅ Daten geladen: {len(team_stats)} Teams")
    
    # Zeige Top 5 Teams (nach xG)
    print("\n🏆 Top 5 Teams (nach xG):")
    
    # Stats die verfügbar sind
    if 'xG' in team_stats.columns:
        top_xg = team_stats.nlargest(5, 'xG')[['xG', 'xGA', 'Goals', 'Goals Against']]
        print(top_xg.to_string())
    else:
        # Alternative: Zeige einfach erste paar Spalten
        print(team_stats.head().to_string())
        print(f"\n📋 Verfügbare Spalten:")
        print(f"   {', '.join(team_stats.columns[:10])}")

except Exception as e:
    print(f"❌ FBref Error: {e}")
    print("   Mögliche Gründe:")
    print("   - Keine Internet-Verbindung")
    print("   - FBref-Website down")
    print("   - Rate Limiting (zu viele Requests)")

# ============================================================
# TEST 3: VERFÜGBARE LIGEN
# ============================================================

print("\n\n🌍 TEST 3: VERFÜGBARE LIGEN")
print("-" * 60)

print("\n✅ Understat Ligen:")
understat_leagues = [
    "ENG-Premier League",
    "ESP-La Liga", 
    "GER-Bundesliga",
    "ITA-Serie A",
    "FRA-Ligue 1"
]
for league in understat_leagues:
    print(f"   • {league}")

print("\n✅ FBref Ligen (mehr!):")
fbref_leagues = [
    "ENG-Premier League",
    "ESP-La Liga",
    "GER-Bundesliga", 
    "ITA-Serie A",
    "FRA-Ligue 1",
    "ENG-Championship",
    "GER-2. Bundesliga",
    "ESP-La Liga 2",
    # ... und viele mehr!
]
for league in fbref_leagues:
    print(f"   • {league}")

# ============================================================
# INTEGRATION-BEISPIEL
# ============================================================

print("\n\n💡 INTEGRATION-BEISPIEL")
print("-" * 60)
print("""
# In deinem Bot:

from soccerdata import Understat, FBref

def get_xg_data(team, league="ENG-Premier League", season="2425"):
    try:
        understat = Understat(league, season)
        team_stats = understat.read_team_match_stats()
        
        team_data = team_stats[team_stats['team'].str.contains(team, case=False)]
        recent = team_data.tail(5)
        
        return {
            'xg_for': recent['xG'].mean(),
            'xg_against': recent['xGA'].mean(),
            'xg_diff': (recent['xG'] - recent['xGA']).mean()
        }
    except:
        return None

def get_team_stats(team, league="ENG-Premier League", season="2425"):
    try:
        fbref = FBref(league, season)
        stats = fbref.read_team_season_stats()
        
        team_stats = stats[stats.index.str.contains(team, case=False)]
        
        return {
            'goals_avg': team_stats['Goals'].values[0],
            'goals_against': team_stats['Goals Against'].values[0],
            # ... mehr Stats
        }
    except:
        return None

# Usage:
xg = get_xg_data("Manchester United")
print(f"xG: {xg['xg_for']:.2f}")
""")

# ============================================================
# ZUSAMMENFASSUNG
# ============================================================

print("\n\n" + "=" * 60)
print("✅ TEST ABGESCHLOSSEN")
print("=" * 60)

print("\n📋 WAS DU BEKOMMEN HAST:")
print("   ✅ Understat: xG-Daten (Expected Goals)")
print("   ✅ FBref: Detaillierte Team-Stats")
print("   ✅ Beide: Kostenlos & einfach zu nutzen!")

print("\n💎 WAS DU DAMIT MACHEN KANNST:")
print("   • xG vs Actual Goals vergleichen")
print("   • Over/Under Performance erkennen")
print("   • Bessere AI-Prompts (mit xG-Kontext)")
print("   • Value-Bets finden (Team underperforming → wird besser)")

print("\n🚀 NÄCHSTE SCHRITTE:")
print("   1. pip install soccerdata")
print("   2. python test_fbref_understat.py")
print("   3. Integration in Bot (ich mache das!)")

print("\n" + "=" * 60)
