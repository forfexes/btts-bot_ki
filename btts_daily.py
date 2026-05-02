"""
Value-Betting Telegram Bot
==========================
- Holt Fixtures (nächste 24h) von API-Football
- Holt echte Quoten von The Odds API
- Berechnet Wahrscheinlichkeiten via Poisson + empirische Raten (letzte 15 Spiele)
- Postet nur Tipps mit positivem Expected Value (EV)
- Märkte: BTTS, Over 2.5, 1. Halbzeit BTTS, Combo (BTTS + Over 2.5)
- Dedupliziert über 3 Tage, cached Team-Historien 12h

Benötigte Secrets / Env-Vars
----------------------------
API_FOOTBALL_KEY      Pflicht. api-sports.io
ODDS_API_KEY          Empfohlen. the-odds-api.com (sonst nur Modell-Filter)
TELEGRAM_TOKEN        Pflicht.
TELEGRAM_CHAT_ID      Pflicht.
GEMINI_API_KEYS       Optional (komma-separiert).
USE_GEMINI            "1" um Gemini-Sanity-Check zu aktivieren (default: 0)

Filter (Default in Klammern)
----------------------------
MIN_EV                Mindest-EV für Value-Tipps (0.05 = 5%)
MIN_PROBABILITY       Mindestwahrscheinlichkeit (0.55)
MIN_PROB_NO_ODDS      Schwelle wenn keine Quoten verfügbar (0.65)
MIN_HISTORY_GAMES     Mindestens N historische Spiele pro Team (8)
MAX_MATCHES           Maximale Spiele pro Lauf (40)
MARKETS_TO_RUN        Komma-Liste: btts,over25,btts_ht,combo
"""

import os
import json
import time
import math
import html
import difflib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# KONFIGURATION
# ============================================================
def env(name, default=""):
    return os.getenv(name, default).strip()

def env_list(name):
    return [x.strip() for x in env(name).split(",") if x.strip()]

GEMINI_API_KEYS  = env_list("GEMINI_API_KEYS")
API_FOOTBALL_KEY = env("API_FOOTBALL_KEY")
ODDS_API_KEY     = env("ODDS_API_KEY")
TELEGRAM_TOKEN   = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

MIN_EV             = float(env("MIN_EV", "0.05"))
MIN_PROBABILITY    = float(env("MIN_PROBABILITY", "0.55"))
MIN_PROB_NO_ODDS   = float(env("MIN_PROB_NO_ODDS", "0.65"))
MIN_HISTORY_GAMES  = int(env("MIN_HISTORY_GAMES", "8"))
MAX_MATCHES        = int(env("MAX_MATCHES", "40"))
MARKETS_TO_RUN     = env_list("MARKETS_TO_RUN") or ["btts", "over25", "btts_ht", "combo"]
USE_GEMINI         = env("USE_GEMINI", "0") == "1"
GEMINI_MODEL       = env("GEMINI_MODEL", "gemini-2.5-flash")
ODDS_CACHE_HOURS   = float(env("ODDS_CACHE_HOURS", "1.0"))

DATA_DIR = Path(env("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)
TEAM_CACHE_FILE = DATA_DIR / "team_cache.json"
ODDS_CACHE_FILE = DATA_DIR / "odds_cache.json"
POSTED_FILE     = DATA_DIR / "posted.json"

API_FOOTBALL_HEADERS = {
    "x-rapidapi-key": API_FOOTBALL_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io",
}

# ============================================================
# UTILS
# ============================================================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def esc(value):
    return html.escape(str(value), quote=False)

def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Cache-Load Fehler {path}: {e}")
    return default

def save_json(path, data):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Cache-Save Fehler {path}: {e}")

def cache_get(cache, key, max_age_hours):
    entry = cache.get(key)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > max_age_hours * 3600:
        return None
    return entry.get("data")

def cache_put(cache, key, data):
    cache[key] = {"ts": time.time(), "data": data}

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM secrets fehlen")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=20,
        )
        if not r.ok:
            log(f"Telegram Fehler: {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as e:
        log(f"Telegram Exception: {e}")
        return False

# ============================================================
# API-FOOTBALL
# ============================================================
def af_get(endpoint, params):
    if not API_FOOTBALL_KEY:
        return None
    try:
        r = requests.get(
            f"https://v3.football.api-sports.io/{endpoint}",
            headers=API_FOOTBALL_HEADERS,
            params=params,
            timeout=25,
        )
        if not r.ok:
            log(f"API-Football {endpoint} Fehler: {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        log(f"API-Football {endpoint} Exception: {e}")
        return None

def fetch_upcoming_fixtures():
    """Spiele in den nächsten 24h, sortiert nach Anstoßzeit."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    fixtures = []
    for date in [today, tomorrow]:
        data = af_get("fixtures", {"date": date})
        if not data:
            continue
        for item in data.get("response", []):
            fixture = item.get("fixture", {})
            if fixture.get("status", {}).get("short", "") not in ["NS", "TBD"]:
                continue
            try:
                kickoff = datetime.fromisoformat(
                    fixture.get("date", "").replace("Z", "+00:00")
                )
            except Exception:
                continue
            if kickoff < now or kickoff > now + timedelta(hours=24):
                continue
            league = item.get("league", {})
            teams = item.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            if not (home.get("name") and away.get("name") and home.get("id") and away.get("id")):
                continue
            fixtures.append({
                "fixture_id": fixture.get("id"),
                "league": league.get("name", ""),
                "country": league.get("country", ""),
                "home": home.get("name"),
                "home_id": home.get("id"),
                "away": away.get("name"),
                "away_id": away.get("id"),
                "kickoff": kickoff,
            })
    fixtures.sort(key=lambda x: x["kickoff"])
    return fixtures[:MAX_MATCHES]

def fetch_team_history(team_id, cache, last=15):
    """Letzte N Spiele eines Teams mit FT- und HT-Score."""
    key = f"hist_{team_id}_{last}"
    cached = cache_get(cache, key, max_age_hours=12)
    if cached is not None:
        return cached
    data = af_get("fixtures", {"team": team_id, "last": last})
    games = []
    if data:
        for item in data.get("response", []):
            score = item.get("score", {})
            ft = score.get("fulltime", {})
            ht = score.get("halftime", {})
            teams = item.get("teams", {})
            is_home = teams.get("home", {}).get("id") == team_id
            h_ft, a_ft = ft.get("home"), ft.get("away")
            h_ht, a_ht = ht.get("home"), ht.get("away")
            if h_ft is None or a_ft is None:
                continue
            scored_ht = (h_ht if is_home else a_ht) if (h_ht is not None and a_ht is not None) else None
            conceded_ht = (a_ht if is_home else h_ht) if (h_ht is not None and a_ht is not None) else None
            games.append({
                "is_home": is_home,
                "scored_ft": h_ft if is_home else a_ft,
                "conceded_ft": a_ft if is_home else h_ft,
                "scored_ht": scored_ht,
                "conceded_ht": conceded_ht,
                "btts": h_ft > 0 and a_ft > 0,
                "btts_ht": (h_ht is not None and a_ht is not None and h_ht > 0 and a_ht > 0),
                "over25": (h_ft + a_ft) > 2,
                "btts_and_over25": h_ft > 0 and a_ft > 0 and (h_ft + a_ft) > 2,
                "has_ht": h_ht is not None and a_ht is not None,
            })
    cache_put(cache, key, games)
    return games

# ============================================================
# WAHRSCHEINLICHKEITS-MODELL (Poisson + Empirie)
# ============================================================
def poisson_pmf(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def prob_over_line(lam_h, lam_a, line=2.5, max_goals=10):
    p_under = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            if i + j <= line:
                p_under += poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
    return 1.0 - p_under

def prob_btts(lam_h, lam_a):
    return (1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a))

def prob_btts_and_over(lam_h, lam_a, line=2.5, max_goals=10):
    p = 0.0
    for i in range(1, max_goals + 1):
        for j in range(1, max_goals + 1):
            if i + j > line:
                p += poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
    return p

def safe_avg(values, fallback=0.0):
    return sum(values) / len(values) if values else fallback

def compute_match_probs(home_hist, away_hist):
    """Liefert Wahrscheinlichkeiten pro Markt oder None bei zu wenig Daten."""
    if len(home_hist) < MIN_HISTORY_GAMES or len(away_hist) < MIN_HISTORY_GAMES:
        return None

    # Tor-Mittelwerte
    h_for  = safe_avg([g["scored_ft"]   for g in home_hist])
    h_ag   = safe_avg([g["conceded_ft"] for g in home_hist])
    a_for  = safe_avg([g["scored_ft"]   for g in away_hist])
    a_ag   = safe_avg([g["conceded_ft"] for g in away_hist])

    # Erwartete Tore (Tore-für-Heim und Gegentore-Auswärts gemittelt)
    lam_h = max(0.10, (h_for + a_ag) / 2.0)
    lam_a = max(0.10, (a_for + h_ag) / 2.0)

    # Halbzeit-Lambdas (nur Spiele mit HT-Daten)
    h_ht_for_list  = [g["scored_ht"]   for g in home_hist if g["has_ht"]]
    h_ht_ag_list   = [g["conceded_ht"] for g in home_hist if g["has_ht"]]
    a_ht_for_list  = [g["scored_ht"]   for g in away_hist if g["has_ht"]]
    a_ht_ag_list   = [g["conceded_ht"] for g in away_hist if g["has_ht"]]

    has_ht_data = (len(h_ht_for_list) >= 5 and len(a_ht_for_list) >= 5)
    if has_ht_data:
        lam_h_ht = max(0.05, (safe_avg(h_ht_for_list) + safe_avg(a_ht_ag_list)) / 2.0)
        lam_a_ht = max(0.05, (safe_avg(a_ht_for_list) + safe_avg(h_ht_ag_list)) / 2.0)
        p_btts_ht_pois = prob_btts(lam_h_ht, lam_a_ht)
    else:
        p_btts_ht_pois = None

    # Empirische Raten
    h_btts_rate    = safe_avg([1 if g["btts"]    else 0 for g in home_hist])
    a_btts_rate    = safe_avg([1 if g["btts"]    else 0 for g in away_hist])
    h_o25_rate     = safe_avg([1 if g["over25"]  else 0 for g in home_hist])
    a_o25_rate     = safe_avg([1 if g["over25"]  else 0 for g in away_hist])
    h_combo_rate   = safe_avg([1 if g["btts_and_over25"] else 0 for g in home_hist])
    a_combo_rate   = safe_avg([1 if g["btts_and_over25"] else 0 for g in away_hist])
    h_btts_ht_rate = safe_avg([1 if g["btts_ht"] else 0 for g in home_hist if g["has_ht"]]) if h_ht_for_list else None
    a_btts_ht_rate = safe_avg([1 if g["btts_ht"] else 0 for g in away_hist if g["has_ht"]]) if a_ht_for_list else None

    # Modell + Empirie 50/50 mischen
    p_btts   = (prob_btts(lam_h, lam_a)            + (h_btts_rate  + a_btts_rate)  / 2) / 2
    p_over25 = (prob_over_line(lam_h, lam_a, 2.5)  + (h_o25_rate   + a_o25_rate)   / 2) / 2
    p_combo  = (prob_btts_and_over(lam_h, lam_a)   + (h_combo_rate + a_combo_rate) / 2) / 2

    if p_btts_ht_pois is not None and h_btts_ht_rate is not None and a_btts_ht_rate is not None:
        p_btts_ht = (p_btts_ht_pois + (h_btts_ht_rate + a_btts_ht_rate) / 2) / 2
    elif h_btts_ht_rate is not None and a_btts_ht_rate is not None:
        p_btts_ht = (h_btts_ht_rate + a_btts_ht_rate) / 2
    else:
        p_btts_ht = None

    return {
        "btts": p_btts,
        "over25": p_over25,
        "btts_ht": p_btts_ht,
        "combo": p_combo,
        "lam_h": lam_h,
        "lam_a": lam_a,
        "n_home": len(home_hist),
        "n_away": len(away_hist),
    }

# ============================================================
# THE ODDS API
# ============================================================
def fetch_odds_index():
    """Liefert Dict 'home_norm|away_norm' -> {market: best_decimal_odds}."""
    if not ODDS_API_KEY:
        return {}

    odds_cache = load_json(ODDS_CACHE_FILE, {})
    cached = cache_get(odds_cache, "all", max_age_hours=ODDS_CACHE_HOURS)
    if cached is not None:
        log(f"Quoten aus Cache ({len(cached)} Spiele)")
        return cached

    # Aktive Soccer-Sport-Keys holen
    sport_keys = []
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports/",
                         params={"apiKey": ODDS_API_KEY}, timeout=20)
        if r.ok:
            for s in r.json():
                k = s.get("key", "")
                if k.startswith("soccer_") and s.get("active"):
                    sport_keys.append(k)
    except Exception as e:
        log(f"Odds API sports Fehler: {e}")
        return {}

    log(f"Aktive Soccer-Märkte: {len(sport_keys)}")
    odds_index = {}
    for sport_key in sport_keys:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "totals,btts",
                    "oddsFormat": "decimal",
                },
                timeout=25,
            )
            if not r.ok:
                continue
            for game in r.json():
                home_n = normalize_team(game.get("home_team", ""))
                away_n = normalize_team(game.get("away_team", ""))
                if not home_n or not away_n:
                    continue
                buckets = {"over25": [], "btts": []}
                for bm in game.get("bookmakers", []):
                    for m in bm.get("markets", []):
                        m_key = m.get("key")
                        if m_key == "totals":
                            for o in m.get("outcomes", []):
                                try:
                                    if o.get("name") == "Over" and float(o.get("point", 0)) == 2.5:
                                        buckets["over25"].append(float(o.get("price", 0)))
                                except (TypeError, ValueError):
                                    pass
                        elif m_key == "btts":
                            for o in m.get("outcomes", []):
                                try:
                                    if o.get("name") == "Yes":
                                        buckets["btts"].append(float(o.get("price", 0)))
                                except (TypeError, ValueError):
                                    pass
                final = {k: max(v) for k, v in buckets.items() if v}
                if final:
                    odds_index[f"{home_n}|{away_n}"] = final
        except Exception as e:
            log(f"Odds API {sport_key} Fehler: {e}")

    cache_put(odds_cache, "all", odds_index)
    save_json(ODDS_CACHE_FILE, odds_cache)
    log(f"Quoten indexiert: {len(odds_index)} Spiele")
    return odds_index

def normalize_team(name):
    if not name:
        return ""
    return (name.lower()
                .replace(".", "")
                .replace("-", " ")
                .replace("fc ", "")
                .replace(" fc", "")
                .replace("  ", " ")
                .strip())

def find_match_odds(odds_index, home, away):
    if not odds_index:
        return None
    h = normalize_team(home)
    a = normalize_team(away)
    direct = odds_index.get(f"{h}|{a}")
    if direct:
        return direct
    # Fuzzy match
    candidates = list(odds_index.keys())
    best_score = 0.0
    best_key = None
    for key in candidates:
        kh, ka = key.split("|")
        sh = difflib.SequenceMatcher(None, h, kh).ratio()
        sa = difflib.SequenceMatcher(None, a, ka).ratio()
        score = (sh + sa) / 2
        if score > best_score:
            best_score = score
            best_key = key
    if best_score >= 0.75:
        return odds_index[best_key]
    return None

# ============================================================
# VALUE-BEWERTUNG
# ============================================================
def fair_odds(p):
    return (1.0 / p) if p and p > 0 else None

def expected_value(p, odds):
    return (p * odds) - 1.0

def evaluate_market(market, probs, odds_for_match):
    p = probs.get(market)
    if p is None or p < MIN_PROBABILITY:
        return None

    odds = None
    if odds_for_match:
        if market in ("btts", "over25"):
            odds = odds_for_match.get(market)
        elif market == "combo":
            b = odds_for_match.get("btts")
            o = odds_for_match.get("over25")
            if b and o:
                odds = b * o  # Parlay-Quote (Bookies geben das Produkt)
        # btts_ht hat selten Quoten -> bleibt None

    if odds:
        ev = expected_value(p, odds)
        if ev < MIN_EV:
            return None
    else:
        # Ohne Quoten: höhere Wahrscheinlichkeitshürde
        if p < MIN_PROB_NO_ODDS:
            return None
        ev = None

    return {"market": market, "prob": p, "odds": odds, "fair": fair_odds(p), "ev": ev}

# ============================================================
# DEDUP
# ============================================================
def cleanup_posted(posted, days=3):
    cutoff = time.time() - days * 86400
    return {k: v for k, v in posted.items() if v > cutoff}

def already_posted(posted, fixture_id, market):
    return f"{fixture_id}_{market}" in posted

def mark_posted(posted, fixture_id, market):
    posted[f"{fixture_id}_{market}"] = time.time()

# ============================================================
# TELEGRAM-FORMATIERUNG
# ============================================================
def market_label(m):
    return {
        "btts":    "BTTS – beide treffen",
        "over25":  "Over 2.5 Tore",
        "btts_ht": "1. Halbzeit BTTS",
        "combo":   "BTTS + Over 2.5 (Combo)",
    }.get(m, m)

def market_emoji(m):
    return {"btts": "⚽", "over25": "🎯", "btts_ht": "⏱️", "combo": "🔥"}.get(m, "📊")

def format_tip(match, tip, probs):
    market = tip["market"]
    kickoff_local = match["kickoff"].astimezone()
    lines = [
        f"<b>{market_emoji(market)} {esc(market_label(market))}</b>",
        "━━━━━━━━━━━━━━━━",
        f"<b>{esc(match['home'])} vs {esc(match['away'])}</b>",
        f"📍 {esc(match['league'])} ({esc(match['country'])})",
        f"🕒 {kickoff_local.strftime('%d.%m %H:%M')}",
        "",
        f"📈 Modell: <b>{tip['prob']*100:.1f}%</b>",
    ]
    if tip["fair"]:
        lines.append(f"🎯 Faire Quote: <b>{tip['fair']:.2f}</b>")
    if tip["odds"]:
        lines.append(f"💰 Beste Quote: <b>{tip['odds']:.2f}</b>")
    if tip["ev"] is not None:
        lines.append(f"💎 Edge: <b>+{tip['ev']*100:.1f}%</b>")
    else:
        lines.append("💎 Edge: <i>(ohne Quote – nur Modell-Filter)</i>")
    lines.append(f"📊 xG: {probs['lam_h']:.2f} – {probs['lam_a']:.2f}")
    lines.append("")
    lines.append("⏳ <b>Status: PENDING</b>")
    return "\n".join(lines)

# ============================================================
# OPTIONAL: GEMINI SANITY CHECK
# ============================================================
def gemini_sanity_check(match, market, prob):
    if not USE_GEMINI or not GEMINI_API_KEYS:
        return True, ""
    prompt = (
        f"Spiel: {match['home']} vs {match['away']} ({match['league']}, {match['country']})\n"
        f"Markt: {market_label(market)}\n"
        f"Modell-Wahrscheinlichkeit: {prob*100:.1f}%\n\n"
        "Gibt es klar BEKANNTE Gründe (z.B. U-/Reserveteam, Pokalrotation, "
        "Saison-Ende-Bedeutungslosigkeit), die diese Wahrscheinlichkeit deutlich SENKEN würden?\n"
        "Antworte NUR mit:\nOK\noder\nSKIP: <kurzer Grund>"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 200,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    for key in GEMINI_API_KEYS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                json=payload, timeout=30,
            )
            data = r.json()
            if "error" in data:
                continue
            text = ""
            for c in data.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    text += p.get("text", "")
            text = text.strip()
            if text.upper().startswith("SKIP"):
                return False, text
            return True, ""
        except Exception:
            continue
    return True, ""

# ============================================================
# MAIN
# ============================================================
def main():
    log("VALUE BOT START")

    if not API_FOOTBALL_KEY:
        send_telegram("❌ <b>API_FOOTBALL_KEY fehlt</b>")
        return

    team_cache = load_json(TEAM_CACHE_FILE, {})
    posted = cleanup_posted(load_json(POSTED_FILE, {}))

    fixtures = fetch_upcoming_fixtures()
    log(f"Fixtures (24h): {len(fixtures)}")
    if not fixtures:
        send_telegram("ℹ️ Keine kommenden Spiele in den nächsten 24h.")
        save_json(TEAM_CACHE_FILE, team_cache)
        save_json(POSTED_FILE, posted)
        return

    odds_index = fetch_odds_index() if ODDS_API_KEY else {}
    if not ODDS_API_KEY:
        log("Kein ODDS_API_KEY – laufe ohne Quoten (Modell-only)")

    send_telegram(
        f"✅ <b>Value-Bot gestartet</b>\n"
        f"{len(fixtures)} Spiele · "
        f"{'mit Odds' if odds_index else 'ohne Odds'} · "
        f"Märkte: {', '.join(MARKETS_TO_RUN)}"
    )

    posted_count = 0
    checked = 0
    skipped_no_data = 0
    skipped_no_value = 0

    for match in fixtures:
        home_hist = fetch_team_history(match["home_id"], team_cache)
        away_hist = fetch_team_history(match["away_id"], team_cache)
        probs = compute_match_probs(home_hist, away_hist)
        if probs is None:
            skipped_no_data += 1
            continue

        match_odds = find_match_odds(odds_index, match["home"], match["away"])

        # Alle Markt-Kandidaten für dieses Spiel sammeln
        candidates = []
        for market in MARKETS_TO_RUN:
            checked += 1
            if already_posted(posted, match["fixture_id"], market):
                continue
            tip = evaluate_market(market, probs, match_odds)
            if not tip:
                skipped_no_value += 1
                continue
            candidates.append(tip)

        if not candidates:
            continue

        # Nur den besten Tipp pro Spiel posten:
        # 1. Tipps mit echtem EV bevorzugen, dann höchster EV
        # 2. Sonst höchste Modell-Wahrscheinlichkeit
        with_ev = [t for t in candidates if t["ev"] is not None]
        if with_ev:
            best = max(with_ev, key=lambda t: t["ev"])
        else:
            best = max(candidates, key=lambda t: t["prob"])

        ok, reason = gemini_sanity_check(match, best["market"], best["prob"])
        if not ok:
            log(f"Gemini SKIP {match['home']} vs {match['away']} {best['market']}: {reason}")
            continue
        if send_telegram(format_tip(match, best, probs)):
            # Alle Märkte des Spiels als gepostet markieren -> kein Reposting in späteren Runs
            for c in candidates:
                mark_posted(posted, match["fixture_id"], c["market"])
            posted_count += 1
            ev_str = f"+{best['ev']*100:.1f}%" if best["ev"] is not None else "n/a"
            log(f"POSTED {best['market']} | {match['home']} vs {match['away']} "
                f"| p={best['prob']:.2f} ev={ev_str}")
            time.sleep(1)

    save_json(TEAM_CACHE_FILE, team_cache)
    save_json(POSTED_FILE, posted)

    send_telegram(
        f"📊 <b>Bot fertig</b>\n"
        f"Geprüft: <b>{checked}</b>\n"
        f"Tipps gepostet: <b>{posted_count}</b>\n"
        f"Kein Value: <b>{skipped_no_value}</b>\n"
        f"Zu wenig Daten: <b>{skipped_no_data}</b>"
    )
    log(f"FERTIG checked={checked} posted={posted_count} "
        f"no_value={skipped_no_value} no_data={skipped_no_data}")


if __name__ == "__main__":
    main()
