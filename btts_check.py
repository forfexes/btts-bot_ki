"""
═══════════════════════════════════════════════════════════════
  AI TIPP BOT - RESULT CHECKER (Supabase + API-Football)
═══════════════════════════════════════════════════════════════
  Holt Endstände, sendet ✅/❌ Updates an Telegram
  Aktualisiert Supabase Datenbank
═══════════════════════════════════════════════════════════════
"""

import requests
import json
import os
import sys
import re
from datetime import datetime, timedelta, timezone

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

FOOTBALL_DATA_API_KEY = "bfd46775e9df45e98b5ace754fd6c2b1"
API_FOOTBALL_KEY = "3eb2bd4e228aac07fdbaf1964304b6cf"

TELEGRAM_TOKEN = "8613868656:AAFHN_zpWerWXYjL4o5gb4Jy9aTo_7yITts"
TELEGRAM_CHAT_ID = "558164451"

TELEGRAM_GROUPS = {
    "btts": "-5255652174",
    "over25": "-5113758598",
    "combo": "-5046003943",
}

SUPABASE_URL = "https://sugycqnjncgfheueqaee.supabase.co"
SUPABASE_KEY = "sb_secret_SuIolwQOeMa1mekoyhrnbQ_N36pUi4-"
# ═════════════════════════════════════════════════════════════


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}")


def get_pending_tips():
    """Holt alle pending Tipps aus Supabase"""
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
        log(f"Supabase Fetch: {e}", "ERROR")
    return []


def update_tip_in_supabase(tip_id, status, result):
    """Updated Status in Supabase"""
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
            json={
                "status": status,
                "result": result,
                "checked_at": datetime.now(timezone.utc).isoformat()
            },
            timeout=10
        )
        return r.ok
    except Exception as e:
        log(f"Update fail: {e}", "WARN")
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
        to_date_obj = datetime.fromisoformat(match_date) + timedelta(days=1)
        to_date = to_date_obj.date().isoformat()
        r = requests.get(
            "https://api.football-data.org/v4/matches",
            params={"dateFrom": from_date, "dateTo": to_date, "status": "FINISHED"},
            headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY},
            timeout=15
        )
        if not r.ok:
            return None
        data = r.json()
        for m in data.get("matches", []):
            h = m.get("homeTeam", {}).get("name", "").lower()
            a = m.get("awayTeam", {}).get("name", "").lower()
            home_l = home.lower()
            away_l = away.lower()
            if (h in home_l or home_l in h or any(w in h for w in home_l.split() if len(w) > 3)) and \
               (a in away_l or away_l in a or any(w in a for w in away_l.split() if len(w) > 3)):
                ft = m.get("score", {}).get("fullTime", {})
                if ft.get("home") is not None and ft.get("away") is not None:
                    return f"{ft['home']}:{ft['away']}"
    except:
        pass
    return None


def get_score_from_api_football(home, away, match_date):
    """Versucht Endstand von API-Football zu holen"""
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"},
            params={"date": match_date, "status": "FT"},
            timeout=15
        )
        if not r.ok:
            return None
        data = r.json()
        for fix in data.get("response", []):
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
{home} vs {away}
Datum: {match_date}
Liga: {league or 'unbekannt'}

Wenn beendet, antworte AUSSCHLIESSLICH mit Endstand im Format:
HOME:AWAY (z.B. "2:1" oder "0:0")

Wenn nicht beendet/abgesagt: PENDING

Keine Erklärung, nur die Zahl oder PENDING."""
    
    keys = GEMINI_API_KEYS if use_gemini else GROQ_API_KEYS
    
    for key in keys:
        if not key:
            continue
        try:
            if use_gemini:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "tools": [{"google_search": {}}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 100}
                    },
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
            match = re.search(r'(\d+)[:\-](\d+)', text)
            if match:
                return f"{match.group(1)}:{match.group(2)}"
        except:
            continue
    return None


def get_finished_score(home, away, match_date, league=None):
    """Smart Fallback durch alle APIs"""
    score = get_score_from_football_data(home, away, match_date)
    if score: return score
    score = get_score_from_api_football(home, away, match_date)
    if score: return score
    score = get_score_from_ai(home, away, match_date, league, use_gemini=True)
    if score: return score
    score = get_score_from_ai(home, away, match_date, league, use_gemini=False)
    return score


def evaluate_tip(tip, score):
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
    return None


def is_match_likely_finished(tip):
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


def send_result_update(tip, score, won):
    chat_id = tip.get("telegram_chat_id") or TELEGRAM_GROUPS.get(tip.get("market"), TELEGRAM_CHAT_ID)
    
    if won:
        msg = f"✅ <b>TIPP GEWONNEN</b> ✅\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>{tip.get('match','?')}</b>\n📍 {tip.get('league','')}\n"
        msg += f"🏁 Endstand: <b>{score}</b>\n\n"
        msg += f"💎 Tipp: {tip.get('tip','?')} ({tip.get('market_name','')})\n"
        msg += f"💰 Quote: {tip.get('odds','-')}\n"
        try:
            odds_val = float(str(tip.get('odds', '1')).replace(",", "."))
            profit = round(odds_val - 1, 2)
            msg += f"📈 Gewinn: <b>+{profit}</b> €"
        except:
            pass
    else:
        msg = f"❌ <b>TIPP VERLOREN</b> ❌\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>{tip.get('match','?')}</b>\n📍 {tip.get('league','')}\n"
        msg += f"🏁 Endstand: <b>{score}</b>\n\n"
        msg += f"💎 Tipp: {tip.get('tip','?')} ({tip.get('market_name','')})\n"
        msg += f"💸 Verlust: <b>-1.00</b> €"
    
    return send_telegram(msg, chat_id)


def get_today_tips_stats(target_date):
    """Holt Statistik für ein Datum"""
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
    tips = get_today_tips_stats(target_date)
    if not tips:
        return
    
    won = [t for t in tips if t.get("status") == "won"]
    lost = [t for t in tips if t.get("status") == "lost"]
    pending = [t for t in tips if t.get("status") == "pending"]
    
    if not won and not lost:
        return
    if pending:
        # Wenn noch offene Tipps → Tagesbilanz später
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
    
    by_market = {"btts": [], "over25": [], "combo": []}
    for t in won + lost:
        m = t.get("market", "")
        if m in by_market:
            by_market[m].append(t)
    
    msg = f"📊 <b>TAGESBILANZ {target_date}</b>\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"✅ Treffer: <b>{len(won)}</b>\n"
    msg += f"❌ Verluste: <b>{len(lost)}</b>\n"
    msg += f"🎯 Quote: <b>{quote_pct}%</b>\n"
    msg += f"💰 ROI: <b>{'+' if roi >= 0 else ''}{round(roi, 2)}</b> €\n\n"
    
    market_names = {"btts": "⚽ BTTS", "over25": "🎯 Over 2.5", "combo": "🔥 Combo"}
    for m, m_tips in by_market.items():
        if not m_tips:
            continue
        m_won = sum(1 for t in m_tips if t.get("status") == "won")
        m_total = len(m_tips)
        m_pct = round(m_won / m_total * 100) if m_total else 0
        emoji = "🟢" if m_pct >= 60 else "🟡" if m_pct >= 40 else "🔴"
        msg += f"{market_names[m]}: {m_won}/{m_total} ({m_pct}%) {emoji}\n"
    
    send_telegram(msg, TELEGRAM_CHAT_ID)


def main():
    log("=" * 60)
    log("AI TIPP BOT - Result Checker (Supabase Edition)")
    log("=" * 60)
    
    pending = get_pending_tips()
    log(f"⏳ {len(pending)} pending Tipps in Supabase")
    
    to_check = [t for t in pending if is_match_likely_finished(t)]
    log(f"🔍 {len(to_check)} wahrscheinlich beendet")
    
    if not to_check:
        log("Nichts zu prüfen.")
        return
    
    updated_today = []
    today_str = str(datetime.now().date())
    
    for tip in to_check:
        match_str = tip.get("match", "")
        log(f" → {match_str} ({tip.get('league','')})")
        try:
            if " vs " not in match_str:
                continue
            home, away = match_str.split(" vs ", 1)
            score = get_finished_score(home.strip(), away.strip(), tip.get("date"), tip.get("league"))
            
            if not score:
                log(f"   ⏳ Endstand noch nicht gefunden")
                continue
            
            won = evaluate_tip(tip, score)
            if won is None:
                continue
            
            status = "won" if won else "lost"
            
            if update_tip_in_supabase(tip["id"], status, score):
                if send_result_update(tip, score, won):
                    log(f"   {'✅' if won else '❌'} {score}")
                    if tip.get("date") == today_str:
                        updated_today.append(tip)
        except Exception as e:
            log(f"   ✗ {e}", "ERROR")
            continue
    
    if updated_today:
        log("📊 Sende Tagesbilanz wenn alle fertig...")
        send_daily_summary(today_str)
    
    log(f"✓ {len(updated_today)} Tipps ausgewertet")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        import traceback
        log(traceback.format_exc(), "FATAL")
        sys.exit(1)
