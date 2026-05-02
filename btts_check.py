"""
═══════════════════════════════════════════════════════════════
  AI TIPP BOT - RESULT CHECKER (Ultimate, Secrets Edition)
  Endstände + ✅/❌ Updates + Tagesbilanz für ALLE Märkte
═══════════════════════════════════════════════════════════════
"""

import os
import requests
import json
import sys
import re
from datetime import datetime, timedelta, timezone, date

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def env(name, default=""):
    return os.getenv(name, default).strip()


def env_list(name):
    value = env(name)
    return [x.strip() for x in value.split(",") if x.strip()]


GEMINI_API_KEYS = env_list("GEMINI_API_KEYS")
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_API_KEYS = env_list("GROQ_API_KEYS")
GROQ_MODEL = "llama-3.3-70b-versatile"

FOOTBALL_DATA_API_KEY = env("FOOTBALL_DATA_API_KEY")
API_FOOTBALL_KEY = env("API_FOOTBALL_KEY")

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

TELEGRAM_GROUPS = {
    "btts": env("TELEGRAM_GROUP_BTTS", TELEGRAM_CHAT_ID),
    "over25": env("TELEGRAM_GROUP_OVER25", TELEGRAM_CHAT_ID),
    "combo": env("TELEGRAM_GROUP_COMBO", TELEGRAM_CHAT_ID),
    "1x2": env("TELEGRAM_GROUP_1X2", TELEGRAM_CHAT_ID),
    "stats": env("TELEGRAM_GROUP_STATS", TELEGRAM_CHAT_ID),
}

SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def get_pending_tips():
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"status": "eq.pending", "select": "*"},
            timeout=15
        )
        if r.ok:
            return r.json()
    except Exception as e:
        log(f"Supabase: {e}", "ERROR")
    return []


def update_tip(tip_id, status, result):
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{tip_id}"},
            json={"status": status, "result": result, "checked_at": datetime.now(timezone.utc).isoformat()},
            timeout=10
        )
        return r.ok
    except:
        return False


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
        return r.ok
    except:
        return False


def get_score_from_football_data(home, away, match_date):
    try:
        from_date = match_date
        to_date = (datetime.fromisoformat(match_date) + timedelta(days=1)).date().isoformat()
        r = requests.get(
            "https://api.football-data.org/v4/matches",
            params={"dateFrom": from_date, "dateTo": to_date, "status": "FINISHED"},
            headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY},
            timeout=15
        )
        if not r.ok:
            return None
        for m in r.json().get("matches", []):
            h = m.get("homeTeam", {}).get("name", "").lower()
            a = m.get("awayTeam", {}).get("name", "").lower()
            home_l, away_l = home.lower(), away.lower()
            if (h in home_l or home_l in h or any(w in h for w in home_l.split() if len(w) > 3)) and \
               (a in away_l or away_l in a or any(w in a for w in away_l.split() if len(w) > 3)):
                ft = m.get("score", {}).get("fullTime", {})
                if ft.get("home") is not None and ft.get("away") is not None:
                    return f"{ft['home']}:{ft['away']}"
    except:
        pass
    return None


def get_score_from_api_football(home, away, match_date):
    try:
        if not API_FOOTBALL_KEY:
            return None
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"},
            params={"date": match_date, "status": "FT"},
            timeout=15
        )
        if not r.ok:
            return None
        for fix in r.json().get("response", []):
            teams = fix.get("teams", {})
            h = teams.get("home", {}).get("name", "").lower()
            a = teams.get("away", {}).get("name", "").lower()
            if (home.lower() in h or h in home.lower()) and (away.lower() in a or a in away.lower()):
                goals = fix.get("goals", {})
                if goals.get("home") is not None and goals.get("away") is not None:
                    return f"{goals['home']}:{goals['away']}"
    except:
        pass
    return None


def get_score_from_ai(home, away, match_date, league, use_gemini=True):
    prompt = f"""Suche im Web den Endstand von:
{home} vs {away}, {match_date}, Liga: {league}

Wenn beendet: HOME:AWAY (z.B. "2:1")
Sonst: PENDING

Nur Zahl oder PENDING."""
    
    keys = GEMINI_API_KEYS if use_gemini else GROQ_API_KEYS
    
    for key in keys:
        try:
            if use_gemini:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "tools": [{"google_search": {}}],
                          "generationConfig": {"temperature": 0.1, "maxOutputTokens": 100}},
                    timeout=60
                )
                data = r.json()
                if "error" in data:
                    continue
                candidates = data.get("candidates", [])
                if not candidates:
                    continue
                text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
            else:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.1, "max_tokens": 100},
                    timeout=60
                )
                data = r.json()
                if "error" in data:
                    continue
                choices = data.get("choices", [])
                if not choices:
                    continue
                text = choices[0].get("message", {}).get("content", "")
            text = text.strip().upper()
            if "PENDING" in text:
                return None
            m = re.search(r'(\d+)[:\-](\d+)', text)
            if m:
                return f"{m.group(1)}:{m.group(2)}"
        except:
            continue
    return None


def get_ht_score_from_api_football(home, away, match_date):
    """Holt Halbzeit-Stand für BTTS HT Auswertung"""
    try:
        if not API_FOOTBALL_KEY:
            return None
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"},
            params={"date": match_date, "status": "FT"},
            timeout=15
        )
        if not r.ok:
            return None
        for fix in r.json().get("response", []):
            teams = fix.get("teams", {})
            h = teams.get("home", {}).get("name", "").lower()
            a = teams.get("away", {}).get("name", "").lower()
            if (home.lower() in h or h in home.lower()) and (away.lower() in a or a in away.lower()):
                score = fix.get("score", {})
                ht = score.get("halftime", {})
                if ht.get("home") is not None and ht.get("away") is not None:
                    return f"{ht['home']}:{ht['away']}"
    except:
        pass
    return None


def get_score(home, away, match_date, league=None):
    score = get_score_from_football_data(home, away, match_date)
    if score: return score
    score = get_score_from_api_football(home, away, match_date)
    if score: return score
    score = get_score_from_ai(home, away, match_date, league, True)
    if score: return score
    score = get_score_from_ai(home, away, match_date, league, False)
    return score


def evaluate_tip(tip, score, ht_score=None):
    try:
        h, a = map(int, score.split(":"))
    except:
        return None
    market = tip.get("market", "")
    tip_value = tip.get("tip", "")
    btts_yes = h > 0 and a > 0
    over_25 = (h + a) > 2.5
    if market == "btts":
        return tip_value == ("YES" if btts_yes else "NO")
    elif market == "over25":
        return tip_value == ("YES" if over_25 else "NO")
    elif market == "combo":
        return tip_value == ("YES" if (btts_yes and over_25) else "NO")
    elif market == "btts_ht":
        if ht_score:
            try:
                hh, ha = map(int, ht_score.split(":"))
                btts_ht = hh > 0 and ha > 0
                return tip_value == ("YES" if btts_ht else "NO")
            except:
                pass
        # Fallback: wenn kein HT Score verfügbar → pending lassen
        return None
    return None


def is_likely_finished(tip):
    try:
        time_str = tip.get("time", "")
        date_str = tip.get("date", "")
        if not time_str or not date_str or time_str == "TBD":
            return False
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
        match_date = datetime.fromisoformat(date_str)
        kickoff_local = match_date.replace(hour=hour, minute=minute)
        kickoff_utc = (kickoff_local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        return now_utc > kickoff_utc + timedelta(hours=2)
    except:
        return False


def send_result(tip, score, won):
    chat_id = tip.get("telegram_chat_id") or TELEGRAM_GROUPS.get(tip.get("market"), TELEGRAM_CHAT_ID)
    
    if won:
        msg = f"✅ <b>TIPP GEWONNEN</b> ✅\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>{tip.get('match','?')}</b>\n📍 {tip.get('league','')}\n"
        msg += f"🏁 Endstand: <b>{score}</b>\n\n"
        msg += f"💎 Tipp: {tip.get('tip','?')} ({tip.get('market_name','')})\n"
        msg += f"💰 Quote: {tip.get('odds','-')}\n"
        try:
            odds = float(str(tip.get('odds', '1')).replace(",", "."))
            msg += f"📈 Gewinn: <b>+{round(odds-1, 2)}</b> €"
        except:
            pass
    else:
        msg = f"❌ <b>TIPP VERLOREN</b> ❌\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>{tip.get('match','?')}</b>\n📍 {tip.get('league','')}\n"
        msg += f"🏁 Endstand: <b>{score}</b>\n\n"
        msg += f"💎 Tipp: {tip.get('tip','?')} ({tip.get('market_name','')})\n"
        msg += f"💸 Verlust: <b>-1.00</b> €"
    
    return send_telegram(msg, chat_id)


def get_tips_by_date(target_date):
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"date": f"eq.{target_date}", "select": "*"},
            timeout=15
        )
        if r.ok:
            return r.json()
    except:
        pass
    return []


def send_daily_summary(target_date):
    tips = get_tips_by_date(target_date)
    if not tips:
        return
    
    won = [t for t in tips if t.get("status") == "won"]
    lost = [t for t in tips if t.get("status") == "lost"]
    pending = [t for t in tips if t.get("status") == "pending"]
    
    if not won and not lost:
        return
    if pending:
        return
    
    total = len(won) + len(lost)
    quote_pct = round(len(won) / total * 100) if total else 0
    
    roi = 0
    for t in won:
        try:
            odds = float(str(t.get('odds', '1')).replace(",", "."))
            roi += odds - 1
        except:
            pass
    roi -= len(lost)
    
    market_names = {"btts": "⚽ BTTS", "over25": "🎯 Over 2.5", "combo": "🔥 Combo", "1x2": "🏆 1X2"}
    by_market = {k: [] for k in market_names}
    for t in won + lost:
        m = t.get("market", "")
        if m in by_market:
            by_market[m].append(t)
    
    msg = f"📊 <b>TAGESBILANZ {target_date}</b>\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"✅ Treffer: <b>{len(won)}</b>\n"
    msg += f"❌ Verluste: <b>{len(lost)}</b>\n"
    msg += f"🎯 Quote: <b>{quote_pct}%</b>\n"
    msg += f"💰 ROI: <b>{'+' if roi >= 0 else ''}{round(roi, 2)}</b> €\n\n"
    msg += "<b>Pro Markt:</b>\n"
    for m, m_tips in by_market.items():
        if not m_tips:
            continue
        m_won = sum(1 for t in m_tips if t.get("status") == "won")
        m_total = len(m_tips)
        m_pct = round(m_won / m_total * 100) if m_total else 0
        emoji = "🟢" if m_pct >= 60 else "🟡" if m_pct >= 40 else "🔴"
        msg += f"{market_names[m]}: {m_won}/{m_total} ({m_pct}%) {emoji}\n"
    
    send_telegram(msg, TELEGRAM_GROUPS["stats"])


def send_weekly_summary():
    if datetime.now().weekday() != 6:
        return
    
    today = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()
    
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/tips",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"date": f"gte.{week_ago}", "select": "*"},
            timeout=15
        )
        if not r.ok:
            return
        tips = r.json()
    except:
        return
    
    won = [t for t in tips if t.get("status") == "won"]
    lost = [t for t in tips if t.get("status") == "lost"]
    
    if not won and not lost:
        return
    
    total = len(won) + len(lost)
    quote_pct = round(len(won) / total * 100) if total else 0
    
    roi = 0
    for t in won:
        try:
            roi += float(str(t.get('odds', '1')).replace(",", ".")) - 1
        except:
            pass
    roi -= len(lost)
    
    by_league = {}
    for t in won + lost:
        lg = t.get("league", "?")
        if lg not in by_league:
            by_league[lg] = {"w": 0, "l": 0}
        if t.get("status") == "won":
            by_league[lg]["w"] += 1
        else:
            by_league[lg]["l"] += 1
    
    best_leagues = sorted(by_league.items(), 
                          key=lambda x: (x[1]["w"]/(x[1]["w"]+x[1]["l"]) if (x[1]["w"]+x[1]["l"]) else 0),
                          reverse=True)[:3]
    
    msg = f"📊 <b>WOCHENREPORT</b>\n<i>{week_ago} bis {today}</i>\n━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"✅ Treffer: <b>{len(won)}</b>\n"
    msg += f"❌ Verluste: <b>{len(lost)}</b>\n"
    msg += f"🎯 Quote: <b>{quote_pct}%</b>\n"
    msg += f"💰 ROI: <b>{'+' if roi >= 0 else ''}{round(roi, 2)}</b> €\n\n"
    
    if best_leagues:
        msg += "<b>🏆 Top-Ligen diese Woche:</b>\n"
        for lg, stats in best_leagues:
            tot = stats["w"] + stats["l"]
            pct = round(stats["w"] / tot * 100) if tot else 0
            msg += f"• {lg}: {stats['w']}/{tot} ({pct}%)\n"
    
    send_telegram(msg, TELEGRAM_GROUPS["stats"])


def main():
    log("=" * 60)
    log("AI TIPP BOT - Result Checker (Secrets Edition)")
    log("=" * 60)
    
    pending = get_pending_tips()
    log(f"⏳ {len(pending)} pending Tipps")
    
    to_check = [t for t in pending if is_likely_finished(t)]
    log(f"🔍 {len(to_check)} zu prüfen")
    
    updated = []
    today_str = str(date.today())
    
    for tip in to_check:
        match_str = tip.get("match", "")
        log(f" → {match_str}")
        try:
            if " vs " not in match_str:
                continue
            home, away = match_str.split(" vs ", 1)
            score = get_score(home.strip(), away.strip(), tip.get("date"), tip.get("league"))
            
            if not score:
                log(f"   ⏳ Kein Endstand")
                continue
            
            # Für BTTS HT: Halbzeit-Stand holen
            ht_score = None
            if tip.get("market") == "btts_ht":
                ht_score = get_ht_score_from_api_football(home.strip(), away.strip(), tip.get("date"))
                if not ht_score:
                    log(f"   ⏳ Kein HT-Stand für BTTS HT")
                    continue
            
            won = evaluate_tip(tip, score, ht_score)
            if won is None:
                continue
            
            status = "won" if won else "lost"
            if update_tip(tip["id"], status, score):
                if send_result(tip, score, won):
                    log(f"   {'✅' if won else '❌'} {score}")
                    if tip.get("date") == today_str:
                        updated.append(tip)
        except Exception as e:
            log(f"   ✗ {e}", "ERROR")
            continue
    
    if updated:
        log("📊 Tagesbilanz...")
        send_daily_summary(today_str)
    
    send_weekly_summary()
    
    log(f"✓ {len(updated)} ausgewertet")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        import traceback
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
