#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================
NEUE DATENQUELLEN FÜR btts_daily.py
=======================================================

ANLEITUNG:
1. Alle 5 Blöcke irgendwo nach den bestehenden fetch_* Funktionen einfügen
   (z.B. direkt vor def build_context)

2. In build_context() die Integration (ganz unten) einfügen –
   nach dem bestehenden hist = get_historical_btts_rate(...) Block

3. Neuen .env Key hinzufügen (nur BetFair braucht einen Key):
   BETFAIR_APP_KEY=dein_key   ← https://developer.betfair.com (kostenlos)
   BETFAIR_SESSION=           ← wird automatisch per Login geholt

=======================================================
"""

import requests
import json
import re
import time
from datetime import datetime, timezone, timedelta


# ==============================================================
# BLOCK 1: OPEN-METEO WETTER  (kein Key, kein Limit)
# ==============================================================
WEATHER_CACHE = {}

# Stadion-Koordinaten der Top-Ligen
STADIUM_COORDS = {
    # Premier League
    "Arsenal": (51.5549, -0.1084),
    "Aston Villa": (52.5092, -1.8847),
    "Chelsea": (51.4816, -0.1910),
    "Everton": (53.4388, -2.9661),
    "Liverpool": (53.4308, -2.9608),
    "Manchester City": (53.4831, -2.2004),
    "Manchester United": (53.4631, -2.2913),
    "Newcastle": (54.9756, -1.6218),
    "Tottenham": (51.6043, -0.0665),
    "West Ham": (51.5386, -0.0164),
    # Bundesliga
    "Bayern München": (48.2188, 11.6247),
    "Borussia Dortmund": (51.4926, 7.4516),
    "Bayer Leverkusen": (51.0384, 7.0022),
    "RB Leipzig": (51.3457, 12.3488),
    "Borussia Mönchengladbach": (51.1742, 6.3855),
    "Eintracht Frankfurt": (50.0687, 8.6454),
    "VfB Stuttgart": (48.7924, 9.2324),
    "Hamburger SV": (53.5873, 9.8987),
    # La Liga
    "Real Madrid": (40.4531, -3.6883),
    "Barcelona": (41.3809, 2.1228),
    "Atletico Madrid": (40.4361, -3.5995),
    "Sevilla": (37.3840, -5.9705),
    "Valencia": (39.4745, -0.3583),
    "Athletic Bilbao": (43.2641, -2.9494),
    "Real Sociedad": (43.3016, -1.9734),
    # Serie A
    "Inter": (45.4781, 9.1240),
    "AC Milan": (45.4781, 9.1240),
    "Juventus": (45.1096, 7.6413),
    "Napoli": (40.8279, 14.1933),
    "Roma": (41.9340, 12.4548),
    "Lazio": (41.9340, 12.4548),
    # Ligue 1
    "Paris Saint-Germain": (48.8414, 2.2530),
    "Marseille": (43.2696, 5.3957),
    "Lyon": (45.7651, 4.9822),
    # Champions League häufig genutzte Städte → Fallback über Liga
}

# Fallback-Koordinaten wenn Stadion nicht bekannt (Liga-Hauptstädte)
LEAGUE_COORDS = {
    "Premier League": (51.5074, -0.1278),     # London
    "Bundesliga": (52.5200, 13.4050),          # Berlin
    "La Liga": (40.4168, -3.7038),             # Madrid
    "Serie A": (41.9028, 12.4964),             # Rom
    "Ligue 1": (48.8566, 2.3522),              # Paris
    "Eredivisie": (52.3676, 4.9041),           # Amsterdam
    "Primeira Liga": (38.7223, -9.1393),       # Lissabon
    "Champions League": (47.3769, 8.5417),     # Zürich (UEFA)
}


def fetch_weather(home_team: str, league: str, target_date) -> dict | None:
    """
    Holt Wetterdaten von Open-Meteo für das Heimstadion.
    Kein API-Key nötig, komplett gratis, keine Rate-Limits.
    Returns: dict mit temp, rain, wind, description oder None
    """
    cache_key = f"{home_team}_{target_date}"
    if cache_key in WEATHER_CACHE:
        return WEATHER_CACHE[cache_key]

    # Koordinaten bestimmen
    coords = None
    for name, coord in STADIUM_COORDS.items():
        if name.lower() in home_team.lower() or home_team.lower() in name.lower():
            coords = coord
            break

    if not coords:
        coords = LEAGUE_COORDS.get(league)

    if not coords:
        WEATHER_CACHE[cache_key] = None
        return None

    lat, lon = coords

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "precipitation_sum,windspeed_10m_max,temperature_2m_max",
                "start_date": str(target_date),
                "end_date": str(target_date),
                "timezone": "Europe/Berlin",
            },
            timeout=10,
        )

        if not r.ok:
            WEATHER_CACHE[cache_key] = None
            return None

        data = r.json()
        daily = data.get("daily", {})

        temp  = (daily.get("temperature_2m_max") or [None])[0]
        rain  = (daily.get("precipitation_sum")  or [None])[0]
        wind  = (daily.get("windspeed_10m_max")  or [None])[0]

        if temp is None:
            WEATHER_CACHE[cache_key] = None
            return None

        # Bewertung für Betting-Kontext
        rain_f  = float(rain or 0)
        wind_f  = float(wind or 0)
        temp_f  = float(temp)

        notes = []
        if rain_f > 5:
            notes.append(f"🌧️ Regen {rain_f}mm → Under-Tendenz")
        elif rain_f > 2:
            notes.append(f"🌦️ Leichter Regen {rain_f}mm")

        if wind_f > 40:
            notes.append(f"💨 Starker Wind {wind_f}km/h → Under-Tendenz")
        elif wind_f > 25:
            notes.append(f"💨 Wind {wind_f}km/h")

        if temp_f < 2:
            notes.append(f"🥶 Kalt {temp_f}°C → schwere Bälle, weniger Tore")
        elif temp_f > 32:
            notes.append(f"☀️ Hitze {temp_f}°C → langsameres Spiel")

        result = {
            "temp": temp_f,
            "rain": rain_f,
            "wind": wind_f,
            "notes": notes,
            "summary": f"{temp_f}°C, Regen {rain_f}mm, Wind {wind_f}km/h",
        }

        WEATHER_CACHE[cache_key] = result
        return result

    except Exception:
        WEATHER_CACHE[cache_key] = None
        return None


# ==============================================================
# BLOCK 2: FOOTYSTATS SCRAPING  (BTTS-Rate fertig berechnet)
# ==============================================================
FOOTYSTATS_CACHE = {}

FOOTYSTATS_LEAGUE_URLS = {
    "Premier League":  "https://footystats.org/england/premier-league",
    "Bundesliga":      "https://footystats.org/germany/bundesliga",
    "La Liga":         "https://footystats.org/spain/la-liga",
    "Serie A":         "https://footystats.org/italy/serie-a",
    "Ligue 1":         "https://footystats.org/france/ligue-1",
    "Eredivisie":      "https://footystats.org/netherlands/eredivisie",
    "Primeira Liga":   "https://footystats.org/portugal/primeira-liga",
    "Championship":    "https://footystats.org/england/championship",
    "Champions League":"https://footystats.org/europe/uefa-champions-league",
    "Europa League":   "https://footystats.org/europe/uefa-europa-league",
    "Bundesliga Österreich": "https://footystats.org/austria/bundesliga",
    "Super League Schweiz":  "https://footystats.org/switzerland/super-league",
    "Pro League Belgien":    "https://footystats.org/belgium/pro-league",
    "Scottish Premiership":  "https://footystats.org/scotland/premiership",
    "Süper Lig":             "https://footystats.org/turkey/super-lig",
    "MLS":                   "https://footystats.org/usa/mls",
    "Brasileirao Serie A":   "https://footystats.org/brazil/serie-a",
}


def fetch_footystats_team(team_name: str, league: str) -> dict | None:
    """
    Scraped BTTS%, Over 2.5%, Goals/Game direkt von FootyStats.
    Kein API-Key nötig. Cached pro Liga-Run.
    Returns: dict mit btts_pct, over25_pct, goals_avg, games oder None
    """
    cache_key = f"{league}_{team_name}"
    if cache_key in FOOTYSTATS_CACHE:
        return FOOTYSTATS_CACHE[cache_key]

    league_url = FOOTYSTATS_LEAGUE_URLS.get(league)
    if not league_url:
        FOOTYSTATS_CACHE[cache_key] = None
        return None

    # Team-URL aufbauen
    team_slug = team_name.lower()
    team_slug = re.sub(r"[^a-z0-9]+", "-", team_slug).strip("-")
    team_url  = f"https://footystats.org/clubs/{team_slug}-football-stats"

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        }

        r = requests.get(team_url, headers=headers, timeout=12)
        if not r.ok:
            FOOTYSTATS_CACHE[cache_key] = None
            return None

        html = r.text

        # BTTS % extrahieren
        btts_match = re.search(
            r"BTTS.*?(\d{1,3}(?:\.\d{1,2})?)\s*%", html, re.IGNORECASE
        )
        # Over 2.5 % extrahieren
        over25_match = re.search(
            r"Over 2\.5.*?(\d{1,3}(?:\.\d{1,2})?)\s*%", html, re.IGNORECASE
        )
        # Goals per game
        goals_match = re.search(
            r"Goals\s+Per\s+Game.*?(\d{1,2}\.\d{2})", html, re.IGNORECASE
        )

        if not btts_match and not over25_match:
            FOOTYSTATS_CACHE[cache_key] = None
            return None

        result = {}
        if btts_match:
            result["btts_pct"] = float(btts_match.group(1))
        if over25_match:
            result["over25_pct"] = float(over25_match.group(1))
        if goals_match:
            result["goals_avg"] = float(goals_match.group(1))

        FOOTYSTATS_CACHE[cache_key] = result
        return result

    except Exception:
        FOOTYSTATS_CACHE[cache_key] = None
        return None


# ==============================================================
# BLOCK 3: BETFAIR EXCHANGE ODDS  (gratis mit Account)
# ==============================================================
# .env Keys benötigt:
#   BETFAIR_APP_KEY=...   ← https://developer.betfair.com → API Access → Create App Key
#   BETFAIR_USERNAME=...
#   BETFAIR_PASSWORD=...

import os
BETFAIR_APP_KEY  = os.getenv("BETFAIR_APP_KEY", "")
BETFAIR_USERNAME = os.getenv("BETFAIR_USERNAME", "")
BETFAIR_PASSWORD = os.getenv("BETFAIR_PASSWORD", "")
_BETFAIR_SESSION = {"token": None, "expires": 0}

BETFAIR_CACHE = {}


def _betfair_login() -> str | None:
    """Holt Betfair Session-Token (cached bis Ablauf)."""
    now = time.time()
    if _BETFAIR_SESSION["token"] and now < _BETFAIR_SESSION["expires"]:
        return _BETFAIR_SESSION["token"]

    if not BETFAIR_APP_KEY or not BETFAIR_USERNAME or not BETFAIR_PASSWORD:
        return None

    try:
        r = requests.post(
            "https://identitysso.betfair.com/api/login",
            data={"username": BETFAIR_USERNAME, "password": BETFAIR_PASSWORD},
            headers={
                "X-Application": BETFAIR_APP_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=10,
        )
        data = r.json()
        token = data.get("token")
        if token:
            _BETFAIR_SESSION["token"] = token
            _BETFAIR_SESSION["expires"] = now + 7200  # 2h gültig
            return token
    except Exception:
        pass
    return None


def fetch_betfair_exchange(home_team: str, away_team: str) -> dict | None:
    """
    Holt echte Exchange-Odds von Betfair für BTTS und Over/Under 2.5.
    Exchange = kein Bookmaker-Margin, zeigt echtes Sharp Money.
    Returns: dict mit btts_yes, btts_no, over25, under25 oder None
    """
    cache_key = f"{home_team}_{away_team}"
    if cache_key in BETFAIR_CACHE:
        return BETFAIR_CACHE[cache_key]

    session = _betfair_login()
    if not session:
        return None

    headers = {
        "X-Application":    BETFAIR_APP_KEY,
        "X-Authentication": session,
        "Content-Type":     "application/json",
        "Accept":           "application/json",
    }

    try:
        # 1. Event suchen
        search_payload = {
            "filter": {
                "eventTypeIds": ["1"],  # Soccer
                "textQuery": f"{home_team} {away_team}",
            },
            "maxResults": 3,
        }
        r = requests.post(
            "https://api.betfair.com/exchange/betting/json-rpc/v1",
            json=[{
                "jsonrpc": "2.0",
                "method": "SportsAPING/v1.0/listEvents",
                "params": search_payload,
                "id": 1,
            }],
            headers=headers,
            timeout=10,
        )

        events = r.json()[0].get("result", [])
        if not events:
            BETFAIR_CACHE[cache_key] = None
            return None

        event_id = events[0]["event"]["id"]

        # 2. Märkte holen (BTTS + Goals Over/Under)
        markets_r = requests.post(
            "https://api.betfair.com/exchange/betting/json-rpc/v1",
            json=[{
                "jsonrpc": "2.0",
                "method": "SportsAPING/v1.0/listMarketCatalogue",
                "params": {
                    "filter": {
                        "eventIds": [event_id],
                        "marketTypeCodes": ["BOTH_TEAMS_TO_SCORE", "OVER_UNDER_25"],
                    },
                    "marketProjection": ["RUNNER_DESCRIPTION"],
                    "maxResults": 5,
                },
                "id": 2,
            }],
            headers=headers,
            timeout=10,
        )

        markets = markets_r.json()[0].get("result", [])
        if not markets:
            BETFAIR_CACHE[cache_key] = None
            return None

        market_ids = [m["marketId"] for m in markets]

        # 3. Beste verfügbare Quoten holen
        prices_r = requests.post(
            "https://api.betfair.com/exchange/betting/json-rpc/v1",
            json=[{
                "jsonrpc": "2.0",
                "method": "SportsAPING/v1.0/listMarketBook",
                "params": {
                    "marketIds": market_ids,
                    "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
                },
                "id": 3,
            }],
            headers=headers,
            timeout=10,
        )

        books = prices_r.json()[0].get("result", [])
        result = {}

        for book in books:
            market_id = book["marketId"]
            market_name = next(
                (m["marketName"] for m in markets if m["marketId"] == market_id), ""
            )
            runners = book.get("runners", [])

            if "BOTH_TEAMS" in market_name.upper() or "BTTS" in market_name.upper():
                for runner in runners:
                    name_lower = str(runner.get("selectionId", "")).lower()
                    ex = runner.get("ex", {})
                    best_back = ex.get("availableToBack", [{}])[0].get("price")
                    if best_back:
                        # Runner 0 = Yes, Runner 1 = No (Betfair Konvention)
                        if len(result.get("_btts_runners", [])) == 0:
                            result["btts_yes"] = round(float(best_back), 2)
                            result.setdefault("_btts_runners", []).append("yes")
                        else:
                            result["btts_no"] = round(float(best_back), 2)

            elif "OVER_UNDER_2.5" in market_name.upper() or "OVER/UNDER 2.5" in market_name.upper():
                for i, runner in enumerate(runners):
                    ex = runner.get("ex", {})
                    best_back = ex.get("availableToBack", [{}])[0].get("price")
                    if best_back:
                        if i == 0:
                            result["over25_exchange"] = round(float(best_back), 2)
                        else:
                            result["under25_exchange"] = round(float(best_back), 2)

        # Cleanup interne Keys
        result.pop("_btts_runners", None)

        if not result:
            BETFAIR_CACHE[cache_key] = None
            return None

        BETFAIR_CACHE[cache_key] = result
        return result

    except Exception:
        BETFAIR_CACHE[cache_key] = None
        return None


# ==============================================================
# BLOCK 4: ODDSPORTAL SCRAPING  (historische Opening/Closing Odds)
# ==============================================================
ODDSPORTAL_CACHE = {}

ODDSPORTAL_LEAGUE_URLS = {
    "Premier League":  "soccer/england/premier-league",
    "Bundesliga":      "soccer/germany/bundesliga",
    "La Liga":         "soccer/spain/laliga",
    "Serie A":         "soccer/italy/serie-a",
    "Ligue 1":         "soccer/france/ligue-1",
    "Eredivisie":      "soccer/netherlands/eredivisie",
    "Primeira Liga":   "soccer/portugal/liga-nos",
    "Championship":    "soccer/england/championship",
    "Champions League":"soccer/europe/champions-league",
    "Europa League":   "soccer/europe/europa-league",
    "Super League Schweiz": "soccer/switzerland/super-league",
    "Bundesliga Österreich": "soccer/austria/bundesliga",
    "Scottish Premiership":  "soccer/scotland/premiership",
    "Süper Lig":             "soccer/turkey/super-lig",
}


def fetch_oddsportal_h2h(home_team: str, away_team: str, league: str) -> dict | None:
    """
    Scraped historische H2H Opening/Closing Odds von OddsPortal.
    Gibt Durchschnitt der letzten Direktbegegnungen zurück.
    Returns: dict mit avg_over25_open, avg_over25_close, matches oder None
    """
    cache_key = f"{home_team}_vs_{away_team}"
    if cache_key in ODDSPORTAL_CACHE:
        return ODDSPORTAL_CACHE[cache_key]

    league_slug = ODDSPORTAL_LEAGUE_URLS.get(league)
    if not league_slug:
        ODDSPORTAL_CACHE[cache_key] = None
        return None

    # Team-Slugs für URL
    def slugify(name):
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    h_slug = slugify(home_team)
    a_slug = slugify(away_team)

    url = f"https://www.oddsportal.com/{league_slug}/results/"

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.oddsportal.com/",
        }

        r = requests.get(url, headers=headers, timeout=15)
        if not r.ok:
            ODDSPORTAL_CACHE[cache_key] = None
            return None

        html = r.text

        # Suche nach Begegnungen dieser Teams in Ergebnisliste
        # OddsPortal zeigt Quoten als data-Attribute
        pattern = re.compile(
            rf"{re.escape(home_team[:6])}.*?{re.escape(away_team[:6])}.*?"
            r"(\d\.\d{2,3})\s*/\s*(\d\.\d{2,3})",
            re.IGNORECASE | re.DOTALL,
        )

        matches_found = pattern.findall(html)

        if not matches_found:
            # Fallback: suche Over 2.5 Quoten allgemein auf der Seite
            over_pattern = re.compile(r"over.*?2\.5.*?(\d\.\d{2})", re.IGNORECASE)
            over_matches = over_pattern.findall(html[:5000])
            if over_matches:
                avg = sum(float(x) for x in over_matches[:5]) / len(over_matches[:5])
                result = {
                    "avg_over25": round(avg, 2),
                    "matches": len(over_matches[:5]),
                    "source": "oddsportal_league",
                }
                ODDSPORTAL_CACHE[cache_key] = result
                return result

            ODDSPORTAL_CACHE[cache_key] = None
            return None

        over_odds = [float(m[0]) for m in matches_found[:5]]
        result = {
            "avg_over25": round(sum(over_odds) / len(over_odds), 2),
            "matches":    len(over_odds),
            "source":     "oddsportal_h2h",
        }

        ODDSPORTAL_CACHE[cache_key] = result
        return result

    except Exception:
        ODDSPORTAL_CACHE[cache_key] = None
        return None


# ==============================================================
# BLOCK 5: SOFASCORE  (Live Lineups, Form, letzte 5 Spiele)
# ==============================================================
SOFASCORE_CACHE = {}


def _sofascore_search_team(team_name: str) -> int | None:
    """Sucht Team-ID bei SofaScore."""
    try:
        r = requests.get(
            "https://api.sofascore.com/api/v1/search/all",
            params={"q": team_name},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=10,
        )
        if not r.ok:
            return None

        results = r.json().get("results", [])
        for item in results:
            if item.get("type") == "team":
                entity = item.get("entity", {})
                name = entity.get("name", "")
                if team_name.lower() in name.lower() or name.lower() in team_name.lower():
                    return entity.get("id")
    except Exception:
        pass
    return None


def fetch_sofascore_form(team_name: str) -> dict | None:
    """
    Holt letzte 5 Spiele + Form von SofaScore (inoffizielle API).
    Returns: dict mit form, btts_last5, over25_last5, avg_goals oder None
    """
    cache_key = f"sofascore_{team_name}"
    if cache_key in SOFASCORE_CACHE:
        return SOFASCORE_CACHE[cache_key]

    team_id = _sofascore_search_team(team_name)
    if not team_id:
        SOFASCORE_CACHE[cache_key] = None
        return None

    try:
        # Letzte Spiele holen
        r = requests.get(
            f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=10,
        )

        if not r.ok:
            SOFASCORE_CACHE[cache_key] = None
            return None

        events = r.json().get("events", [])[:5]
        if not events:
            SOFASCORE_CACHE[cache_key] = None
            return None

        form_chars = []
        btts_count = 0
        over25_count = 0
        total_goals = 0

        for ev in events:
            ht_score = ev.get("homeScore", {})
            at_score = ev.get("awayScore", {})

            h_goals = ht_score.get("current", 0) or 0
            a_goals = at_score.get("current", 0) or 0
            total   = h_goals + a_goals
            total_goals += total

            if h_goals > 0 and a_goals > 0:
                btts_count += 1
            if total > 2:
                over25_count += 1

            # Eigenes Ergebnis ermitteln
            home_team_ev = ev.get("homeTeam", {}).get("name", "")
            is_home = team_name.lower() in home_team_ev.lower()

            if is_home:
                if h_goals > a_goals:
                    form_chars.append("W")
                elif h_goals < a_goals:
                    form_chars.append("L")
                else:
                    form_chars.append("D")
            else:
                if a_goals > h_goals:
                    form_chars.append("W")
                elif a_goals < h_goals:
                    form_chars.append("L")
                else:
                    form_chars.append("D")

        n = len(events)
        result = {
            "form":        "".join(form_chars),
            "btts_last5":  round(btts_count / n * 100),
            "over25_last5":round(over25_count / n * 100),
            "avg_goals":   round(total_goals / n, 2),
            "games":       n,
        }

        SOFASCORE_CACHE[cache_key] = result
        return result

    except Exception:
        SOFASCORE_CACHE[cache_key] = None
        return None


# ==============================================================
# INTEGRATION in build_context()
# ==============================================================
# Diesen Block INNERHALB der for-Schleife über fixtures einfügen,
# nach dem bestehenden hist = get_historical_btts_rate(...) Block.
#
# Einfach ans Ende des "line +=" Abschnitts pro Fixture dranhängen:
#
# ---- KOPIERE DIESE ZEILEN ----

"""
            # ── WETTER (Open-Meteo) ──────────────────────────────────────
            weather = fetch_weather(f["home"], league, target_date)
            if weather:
                line += f"\\n   🌤️ Wetter: {weather['summary']}"
                for note in weather["notes"]:
                    line += f" | {note}"

            # ── FOOTYSTATS BTTS-Rate ─────────────────────────────────────
            home_fs = fetch_footystats_team(f["home"], league)
            away_fs = fetch_footystats_team(f["away"], league)
            if home_fs:
                parts = []
                if "btts_pct"   in home_fs: parts.append(f"BTTS {home_fs['btts_pct']}%")
                if "over25_pct" in home_fs: parts.append(f"O2.5 {home_fs['over25_pct']}%")
                if "goals_avg"  in home_fs: parts.append(f"Ø {home_fs['goals_avg']}T")
                line += f"\\n   📊 {f['home']} [FootyStats]: {', '.join(parts)}"
            if away_fs:
                parts = []
                if "btts_pct"   in away_fs: parts.append(f"BTTS {away_fs['btts_pct']}%")
                if "over25_pct" in away_fs: parts.append(f"O2.5 {away_fs['over25_pct']}%")
                if "goals_avg"  in away_fs: parts.append(f"Ø {away_fs['goals_avg']}T")
                line += f"\\n   📊 {f['away']} [FootyStats]: {', '.join(parts)}"

            # ── BETFAIR EXCHANGE ─────────────────────────────────────────
            bf = fetch_betfair_exchange(f["home"], f["away"])
            if bf:
                bf_parts = []
                if "btts_yes"        in bf: bf_parts.append(f"BTTS Yes: {bf['btts_yes']}")
                if "over25_exchange" in bf: bf_parts.append(f"O2.5: {bf['over25_exchange']}")
                if bf_parts:
                    line += f"\\n   📈 Betfair Exchange: {' | '.join(bf_parts)} (kein Margin!)"

            # ── ODDSPORTAL H2H ───────────────────────────────────────────
            op = fetch_oddsportal_h2h(f["home"], f["away"], league)
            if op:
                line += (
                    f"\\n   📉 OddsPortal H2H Ø O2.5: {op['avg_over25']} "
                    f"({op['matches']} Spiele) [{op['source']}]"
                )

            # ── SOFASCORE FORM ───────────────────────────────────────────
            home_ss = fetch_sofascore_form(f["home"])
            away_ss = fetch_sofascore_form(f["away"])
            if home_ss:
                line += (
                    f"\\n   🔥 {f['home']} Form [{home_ss['form']}] "
                    f"BTTS {home_ss['btts_last5']}% "
                    f"O2.5 {home_ss['over25_last5']}% "
                    f"Ø {home_ss['avg_goals']}T [SofaScore]"
                )
            if away_ss:
                line += (
                    f"\\n   🔥 {f['away']} Form [{away_ss['form']}] "
                    f"BTTS {away_ss['btts_last5']}% "
                    f"O2.5 {away_ss['over25_last5']}% "
                    f"Ø {away_ss['avg_goals']}T [SofaScore]"
                )
"""

# ---- ENDE INTEGRATION ----
