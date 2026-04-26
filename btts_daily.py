"""
═══════════════════════════════════════════════════════════════
  AI TIPP BOT - DAILY (Multi-API + Supabase)
═══════════════════════════════════════════════════════════════
  Gemini + Groq + 7x Odds-API + API-Football + Wetter
  Tipps werden in Supabase gespeichert für Auswertung
═══════════════════════════════════════════════════════════════
"""

import requests
import json
import re
import os
import sys
from datetime import date, datetime, timedelta, timezone

# ═══ KONFIGURATION ═══════════════════════════════════════════

GEMINI_API_KEYS = [
    "AIzaSyAhp4Cc-RaycmRWkvMcgBLkOOPSs1sMXgI",
    "AIzaSyAqwbGf-lBX6h6vdp1u1CQ5IrLYC0bL8hw",
    "AIzaSyDcPfgl-eeRKzpODhVqoy3uNYtEiL4r8-U",
    "AIzaSyBDsDmhE8CmHQk0q7ct-dHFydk5nLe_n7c",
    "AIzaSyDFSB5eUdcP_aDidtRs7gEP7uvHF4XZb-M",
    "AIzaSyB-V_ZzMRNnkde_PKUgc45zpOJQQMcyr-M",
    "AIzaSyC6cJlQ2UhAhyfeQH70XV1OYXYCeY-9It8",
    "AIzaSyAV1a7K2pnh9lvmHSgT9y1nl9pn5x_B0fI",
    "AIzaSyC0KefvlyGE7x3ptav9GEAUVTcIYvLLhpw",
    "AIzaSyBIXxe6ngVZpaNpbwVO-8LSI0zpOPnfeO0",
]
GEMINI_MODEL = "gemini-2.5-flash"

GROQ_API_KEYS = [
    "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",
    "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",
    "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",
    "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",
]
GROQ_MODEL = "llama-3.3-70b-versatile"

ODDS_API_KEYS = [
    "4b66fb8339b88da06e6bf49fec19efdf",
    "6e8ca3f1e2b866da469d0c240fda544f",
    "3a74c3b0568e27304018f9e22fa90c6f",
    "a3d647a6a454741a4645dea0a64c362f",
    "aa82164fb332ca1413c0c91a2110b4d7",
    "2d3e697d1268d870bdb1b59f1264ed51",
    "4af53d2e241ee2555c4f47cb577eb792",
]

FOOTBALL_DATA_API_KEY = "bfd46775e9df45e98b5ace754fd6c2b1"
API_FOOTBALL_KEY = "3eb2bd4e228aac07fdbaf1964304b6cf"
WEATHER_API_KEY = "26b0619037f07eea9194d4ef9fea53e1"

TELEGRAM_TOKEN = "8613868656:AAFHN_zpWerWXYjL4o5gb4Jy9aTo_7yITts"
TELEGRAM_CHAT_ID = "558164451"

TELEGRAM_GROUPS = {
    "btts": "-5255652174",
    "over25": "-5113758598",
    "combo": "-5046003943",
}

SUPABASE_URL = "https://sugycqnjncgfheueqaee.supabase.co"
SUPABASE_KEY = "sb_secret_SuIolwQOeMa1mekoyhrnbQ_N36pUi4-"

MIN_PROBABILITY = 65
MIN_ODDS = 1.6

MARKETS_TO_RUN = ["btts", "over25", "combo"]

LEAGUES_TO_RUN = [
    "Champions League", "Europa League", "Conference League",
    "Bundesliga", "2. Bundesliga", "Premier League", "Championship",
    "La Liga", "La Liga 2", "Serie A", "Serie B",
    "Ligue 1", "Ligue 2",
    "Eredivisie", "Primeira Liga", "Pro League Belgien",
    "Süper Lig", "Bundesliga Österreich", "Super League Schweiz",
    "Slovak Super Liga", "Ekstraklasa", "Scottish Premiership",
    "MLS", "Brasileirao Serie A", "Liga Argentinien",
    "J1 League Japan", "Saudi Pro League",
]

# ═════════════════════════════════════════════════════════════

LEAGUE_KEYS = {
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
    "Bundesliga": "soccer_germany_bundesliga",
    "2. Bundesliga": "soccer_germany_bundesliga2",
    "Premier League": "soccer_epl",
    "Championship": "soccer_efl_champ",
    "La Liga": "soccer_spain_la_liga",
    "La Liga 2": "soccer_spain_segunda_division",
    "Serie A": "soccer_italy_serie_a",
    "Serie B": "soccer_italy_serie_b",
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Pro League Belgien": "soccer_belgium_first_div",
    "Süper Lig": "soccer_turkey_super_league",
    "Bundesliga Österreich": "soccer_austria_bundesliga",
    "Super League Schweiz": "soccer_switzerland_superleague",
    "Slovak Super Liga": "soccer_slovakia_super_liga",
    "Ekstraklasa": "soccer_poland_ekstraklasa",
    "Scottish Premiership": "soccer_spl",
    "MLS": "soccer_usa_mls",
    "Brasileirao Serie A": "soccer_brazil_campeonato",
    "Liga Argentinien": "soccer_argentina_primera_division",
    "J1 League Japan": "soccer_japan_j_league",
    "Saudi Pro League": "soccer_saudi_arabia_league",
}

FOOTBALL_DATA_CODES = {
    "Champions League": "CL",
    "Bundesliga": "BL1",
    "2. Bundesliga": "BL2",
    "Premier League": "PL",
    "Championship": "ELC",
    "La Liga": "PD",
    "Serie A": "SA",
    "Ligue 1": "FL1",
    "Eredivisie": "DED",
    "Primeira Liga": "PPL",
    "Brasileirao Serie A": "BSA",
}

MARKET_INFO = {
    "btts": {"name": "⚽ BTTS", "instr": "Analysiere BTTS (Both Teams To Score - beide Teams treffen)."},
    "over25": {"name": "🎯 Over 2.5", "instr": "Analysiere Over 2.5 Tore."},
    "combo": {"name": "🔥 BTTS + Over 2.5", "instr": "Analysiere BTTS & Over 2.5 KOMBO."}
}


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def get_local_time(utc_iso_str):
    try:
        dt_utc = datetime.fromisoformat(utc_iso_str.replace("Z", "+00:00"))
        year = dt_utc.year
        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)
        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)
        offset = 2 if march_last <= dt_utc < oct_last else 1
        return (dt_utc + timedelta(hours=offset)).strftime("%H:%M")
    except:
        return "TBD"


def fetch_odds(league_name, target_date):
    """Holt Odds - probiert alle Keys"""
    sport_key = LEAGUE_KEYS.get(league_name)
    if not sport_key:
        return []
    for key in ODDS_API_KEYS:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
                params={"apiKey": key, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"},
                timeout=15
            )
            if r.status_code == 401 or r.status_code == 429:
                continue  # Try next key
            if not r.ok:
                continue
            games = r.json()
            target = target_date.isoformat()
            now_utc = datetime.now(timezone.utc)
            filtered = []
            for g in games:
                commence = g.get("commence_time", "")
                if not commence.startswith(target):
                    continue
                try:
                    game_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                    if game_time > now_utc:
                        filtered.append(g)
                except:
                    continue
            return filtered
        except:
            continue
    return []


def fetch_football_data_fixtures(league_name, target_date):
    code = FOOTBALL_DATA_CODES.get(league_name)
    if not code:
        return []
    try:
        r = requests.get(
            f"https://api.football-data.org/v4/competitions/{code}/matches",
            params={"dateFrom": target_date.isoformat(), "dateTo": target_date.isoformat()},
            headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY},
            timeout=15
        )
        if not r.ok:
            return []
        data = r.json()
        now_utc = datetime.now(timezone.utc)
        fixtures = []
        for m in data.get("matches", []):
            try:
                kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                if kickoff > now_utc:
                    fixtures.append({
                        "home": m["homeTeam"]["name"],
                        "away": m["awayTeam"]["name"],
                        "match_id": m.get("id"),
                        "time_utc": m["utcDate"],
                        "time_local": get_local_time(m["utcDate"]),
                        "venue": m.get("venue"),
                    })
            except:
                continue
        return fixtures
    except:
        return []


def fetch_weather(city):
    """Holt Wetter für Spielort"""
    if not city or not WEATHER_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=10
        )
        if not r.ok:
            return None
        data = r.json()
        return {
            "temp": data.get("main", {}).get("temp"),
            "weather": data.get("weather", [{}])[0].get("main", ""),
            "wind": data.get("wind", {}).get("speed", 0),
        }
    except:
        return None


def build_context(odds_data, fixtures, league):
    ctx = ""
    if fixtures:
        ctx += f"\n📅 SPIELPLAN für {league} (lokale Zeit MESZ):\n"
        for f in fixtures:
            line = f"• {f['home']} vs {f['away']} · {f['time_local']} Uhr"
            # Wetter hinzufügen wenn Venue verfügbar
            if f.get("venue"):
                weather = fetch_weather(f["venue"])
                if weather:
                    line += f" [{weather['weather']}, {weather['temp']}°C, Wind {weather['wind']}m/s]"
            ctx += line + "\n"
    if odds_data:
        ctx += f"\n💰 LIVE-QUOTEN:\n"
        for g in odds_data[:10]:
            try:
                t = get_local_time(g["commence_time"])
                ctx += f"\n• {g['home_team']} vs {g['away_team']} · {t}\n"
                for bm in g.get("bookmakers", [])[:3]:
                    for m in bm.get("markets", []):
                        if m["key"] == "totals":
                            ov = next((o["price"] for o in m["outcomes"] if o["name"] == "Over" and o.get("point") == 2.5), None)
                            un = next((o["price"] for o in m["outcomes"] if o["name"] == "Under" and o.get("point") == 2.5), None)
                            if ov:
                                ctx += f"  [{bm['title']}] O2.5: {ov} / U2.5: {un}\n"
            except:
                continue
    return ctx


def extract_json_array(text):
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        s = cleaned.find("[")
        e = cleaned.rfind("]")
        if s != -1 and e > s:
            return json.loads(cleaned[s:e+1])
    except:
        pass
    objects = []
    depth = 0
    start_idx = -1
    for i, c in enumerate(cleaned):
        if c == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    obj = json.loads(cleaned[start_idx:i+1])
                    if "match" in obj:
                        objects.append(obj)
                except:
                    pass
                start_idx = -1
    return objects


def build_prompt(market, league, target_date, context):
    info = MARKET_INFO[market]
    return f"""Du bist Fußball-Wettanalyst. {info['instr']}

Liga "{league}", Datum {target_date}.
{context}

WICHTIG:
- Nur Spiele die NOCH NICHT angefangen haben
- Anstoßzeiten ("time") in MESZ (NICHT UTC!)
- Berücksichtige Wetter wenn angegeben (Regen/Wind = weniger Tore)

Antworte AUSSCHLIESSLICH mit JSON-Array:

[{{"match":"A vs B","league":"{league}","time":"HH:MM","tip":"YES","probability":72,"confidence":4,"fairOdds":"1.65","oddsYes":"1.72","oddsNo":"2.10","bookie":"Bet365","homeForm":"WWDLW","awayForm":"LWWDD","valueRating":"HIGH","keyFactor":"Faktor","reasoning":"2 Sätze."}}]

Falls keine Spiele: []"""


def call_gemini(prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 32000}
    }
    for idx, key in enumerate(GEMINI_API_KEYS):
        if not key:
            continue
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload, timeout=240
            )
            data = r.json()
            if "error" in data:
                continue
            candidates = data.get("candidates", [])
            if not candidates:
                continue
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
            results = extract_json_array(text)
            if results:
                return results, f"Gemini Key {idx+1}"
        except:
            continue
    return None, "Gemini erschöpft"


def call_groq(prompt):
    for idx, key in enumerate(GROQ_API_KEYS):
        if not key:
            continue
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.3, "max_tokens": 8000},
                timeout=120
            )
            data = r.json()
            if "error" in data:
                continue
            choices = data.get("choices", [])
            if not choices:
                continue
            text = choices[0].get("message", {}).get("content", "")
            results = extract_json_array(text)
            if results:
                return results, f"Groq Key {idx+1}"
        except:
            continue
    return None, "Groq erschöpft"


def analyze_market(market, league, target_date):
    odds = fetch_odds(league, target_date)
    fixtures = fetch_football_data_fixtures(league, target_date)
    ctx = build_context(odds, fixtures, league)
    prompt = build_prompt(market, league, target_date, ctx)
    
    results, source = call_gemini(prompt)
    if results:
        return results, source, fixtures
    log("   Gemini erschöpft, Groq...", "WARN")
    results, source = call_groq(prompt)
    if results:
        return results, source, fixtures
    return [], "Beide APIs erschöpft", fixtures


def parse_odds(val):
    try:
        return float(str(val).replace(",", "."))
    except:
        return 0.0


def is_future_game(time_str, target_date):
    try:
        if not time_str or time_str == "TBD":
            return True
        hour, minute = map(int, time_str.split(":")[:2])
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year
        march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while march_last.weekday() != 6:
            march_last -= timedelta(days=1)
        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)
        offset = 2 if march_last <= now_utc < oct_last else 1
        game_local = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        game_utc = (game_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        return game_utc > now_utc - timedelta(minutes=15)
    except:
        return True


def filter_top_tips(results, target_date):
    top = []
    for r in results:
        if not is_future_game(r.get("time", ""), target_date):
            continue
        if r.get("tip") != "YES":
            continue
        if r.get("probability", 0) < MIN_PROBABILITY:
            continue
        if parse_odds(r.get("oddsYes", 0)) < MIN_ODDS:
            continue
        top.append(r)
    top.sort(key=lambda r: (0 if r.get("valueRating") == "HIGH" else 1, -r.get("probability", 0)))
    return top


def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
        if not r.ok:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": re.sub(r'<[^>]+>', '', text)},
                timeout=15
            )
        if r.ok:
            return r.json().get("result", {}).get("message_id")
    except:
        pass
    return None


def save_to_supabase(tip):
    """Speichert Tipp in Supabase"""
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=tip,
            timeout=10
        )
        return r.ok
    except Exception as e:
        log(f"   ⚠ Supabase: {e}", "WARN")
        return False


def send_top_tips_to_telegram(tips_by_market, target_date):
    icons = {"YES": "✅", "NO": "❌", "MAYBE": "⚠️"}
    val_icons = {"HIGH": "🔥", "OK": "🟡", "LOW": "🔴"}
    market_emoji = {"btts": "⚽", "over25": "🎯", "combo": "🔥"}
    
    total_tips = sum(len(tips) for tips in tips_by_market.values())
    
    if total_tips == 0:
        send_telegram(
            f"<b>🤖 AI TIPP BOT</b>\n<i>{target_date}</i>\n\nℹ Heute keine Top-Tipps.",
            chat_id=TELEGRAM_CHAT_ID
        )
        return
    
    saved_count = 0
    
    for market_id, tips in tips_by_market.items():
        if not tips:
            continue
        target_chat = TELEGRAM_GROUPS.get(market_id, TELEGRAM_CHAT_ID)
        market_name = MARKET_INFO[market_id]["name"]
        emoji = market_emoji.get(market_id, "💎")
        
        header = f"<b>{emoji} {market_name} TOP-TIPPS</b>\n"
        header += f"<i>📅 {target_date}</i>\n<i>{len(tips)} Top-Tipps</i>"
        send_telegram(header, target_chat)
        
        for i, r in enumerate(tips, 1):
            msg = f"<b>💎 Tipp {i}/{len(tips)}</b>\n━━━━━━━━━━━━━━━━━━\n"
            msg += f"<b>{r.get('match','?')}</b>\n📍 {r.get('league','')}\n⏰ {r.get('time','TBD')} Uhr\n\n"
            msg += f"{icons.get(r.get('tip','MAYBE'),'')} <b>Tipp: {r.get('tip','?')}</b>\n"
            msg += f"📈 Wahrscheinlichkeit: <b>{r.get('probability',0)}%</b>\n"
            msg += f"⭐ Confidence: {'⭐'*r.get('confidence',0)}\n\n"
            msg += f"💰 <b>Quote: {r.get('oddsYes','-')}</b>\n"
            msg += f"🎯 Fair Odds: {r.get('fairOdds','-')}\n"
            msg += f"{val_icons.get(r.get('valueRating','OK'),'')} Value: <b>{r.get('valueRating','OK')}</b>\n"
            if r.get('bookie'):
                msg += f"🏦 Bookie: {r.get('bookie')}\n"
            msg += f"\n📊 <b>Form</b>\n🏠 Heim: {r.get('homeForm','-')}\n✈️ Auswärts: {r.get('awayForm','-')}\n"
            if r.get('keyFactor'):
                msg += f"\n⚡ <i>{r.get('keyFactor')}</i>\n"
            reasoning = r.get('reasoning', '')[:300]
            if reasoning:
                msg += f"\n💭 <i>{reasoning}</i>"
            
            msg_id = send_telegram(msg, target_chat)
            
            # In Supabase speichern
            tip_id = f"{market_id}_{target_date}_{i}_{abs(hash(r.get('match','')))%100000}"
            tip_data = {
                "tip_id": tip_id,
                "date": str(target_date),
                "market": market_id,
                "market_name": market_name,
                "match": r.get("match", ""),
                "league": r.get("league", ""),
                "time": r.get("time", ""),
                "tip": r.get("tip", ""),
                "probability": r.get("probability", 0),
                "confidence": r.get("confidence", 0),
                "odds": str(r.get("oddsYes", "0")),
                "fair_odds": str(r.get("fairOdds", "0")),
                "bookie": r.get("bookie", ""),
                "value_rating": r.get("valueRating", "OK"),
                "home_form": r.get("homeForm", ""),
                "away_form": r.get("awayForm", ""),
                "reasoning": r.get("reasoning", "")[:500],
                "key_factor": r.get("keyFactor", "")[:200],
                "telegram_chat_id": str(target_chat),
                "telegram_msg_id": msg_id,
                "status": "pending",
            }
            if save_to_supabase(tip_data):
                saved_count += 1
        
        value_count = sum(1 for r in tips if r.get("valueRating") == "HIGH")
        footer = "━━━━━━━━━━━━━━━━━━\n"
        footer += f"📊 <b>Zusammenfassung</b>\n"
        footer += f"• {len(tips)} Tipps\n• 🔥 {value_count} Value-Bets\n"
        footer += f"<i>Viel Erfolg! 🍀</i>"
        send_telegram(footer, target_chat)
    
    log(f"💾 {saved_count} Tipps in Supabase gespeichert")


def main():
    log("=" * 60)
    log("AI TIPP BOT - Daily Run (Multi-API + Supabase)")
    log("=" * 60)
    target_date = date.today()
    log(f"Datum: {target_date}")
    log(f"Märkte: {[MARKET_INFO[m]['name'] for m in MARKETS_TO_RUN]}")
    log(f"Ligen: {len(LEAGUES_TO_RUN)}")
    log(f"APIs: 10 Gemini · 4 Groq · 7 Odds · football-data · API-Football · Wetter")
    log("")
    
    tips_by_market = {m: [] for m in MARKETS_TO_RUN}
    total_analyzed = 0
    
    for market in MARKETS_TO_RUN:
        log(f"╔══ {MARKET_INFO[market]['name']} ══╗")
        for league in LEAGUES_TO_RUN:
            log(f" → {league}")
            try:
                results, source, fixtures = analyze_market(market, league, target_date)
                if results:
                    log(f"   ✓ {len(results)} via {source}")
                    total_analyzed += len(results)
                    top = filter_top_tips(results, target_date)
                    if top:
                        log(f"   💎 {len(top)} Top-Tipp(s)!", "TOP")
                        tips_by_market[market].extend(top)
            except Exception as e:
                log(f"   ✗ {e}", "ERROR")
                continue
    
    total_top = sum(len(t) for t in tips_by_market.values())
    log("")
    log("════════════════════════════════════════")
    log(f"Analyse fertig: {total_analyzed} Spiele · 💎 {total_top} Top-Tipps")
    log("════════════════════════════════════════")
    log("Sende an Telegram + speichere in Supabase...")
    send_top_tips_to_telegram(tips_by_market, target_date)
    log("✓ Fertig!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        import traceback
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
