#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from supabase_v4 import SupabaseV4
from player_identity import norm_name, looks_like_player, extract_player_from_description
from prop_value_engine import classify_market, implied_prob, fair_odds, edge_pct, rough_model_prob, value_rating

PINNACLE_BASE = os.getenv("PINNACLE_BASE", "https://guest.api.arcadia.pinnacle.com/0.1")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
PROP_CHAT = os.getenv("TELEGRAM_GROUP_STATS") or os.getenv("TELEGRAM_CHAT_ID") or ""
DEBUG = os.getenv("PINNACLE_DEBUG", "false").lower() in ("1", "true", "yes", "on")

MIN_ODDS = float(os.getenv("PROP_BUILDER_MIN_ODDS", "1.40"))
MAX_ODDS = float(os.getenv("PROP_BUILDER_MAX_ODDS", "150"))
LOOKAHEAD_HOURS = int(os.getenv("PROP_BUILDER_LOOKAHEAD_HOURS", "30"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}

PLAYER_KEYWORDS = [
    "player props", "player", "to score", "goalscorer", "goal scorer",
    "to be booked", "booked", "yellow card", "card",
    "shots", "shot on target", "sot", "assist", "tackle", "foul", "offside",
]

TEAM_SKIP = [
    "team props", "to reach", "group ", "winner", "champion", "correct score",
    "first team to score", "either team", "both teams", "total goals",
    "corners", "handicap", "match odds", "draw no bet"
]

def log(msg: str, level: str = "INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)

def get_json(url: str, params: Optional[dict] = None, retries: int = 3):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code in (403, 429, 503):
                wait = 2.5 * attempt
                log(f"Pinnacle {r.status_code}, wait {wait}s", "WARN")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"GET failed {url}: {last}")

def as_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "data", "events", "specials", "leagues"):
            if isinstance(data.get(k), list):
                return data[k]
    return []

def parse_time(obj: Dict[str, Any]) -> Optional[datetime]:
    for key in ("starts", "startTime", "start_time", "cutoffAt", "eventStartTime"):
        val = obj.get(key)
        if not val:
            continue
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            pass
    return None

def participants_to_match(parent: Dict[str, Any], special: Dict[str, Any]) -> Tuple[str, str, str]:
    participants = parent.get("participants") or special.get("participants") or []
    home = away = ""
    for p in participants:
        name = p.get("name") or p.get("participantName") or ""
        align = str(p.get("alignment") or p.get("side") or "").lower()
        if align == "home":
            home = name
        elif align == "away":
            away = name

    parent_name = parent.get("name") or parent.get("description") or special.get("parentName") or ""
    desc = special.get("description") or special.get("name") or ""

    if home and away:
        return home, away, f"{home} vs {away}"

    # Fallback: parent.name oft "Colombia vs DR Congo"
    for text in (parent_name, desc):
        if " vs " in text:
            h, a = text.split(" vs ", 1)
            return h.strip(), a.strip(), f"{h.strip()} vs {a.strip()}"
        if " v " in text:
            h, a = text.split(" v ", 1)
            return h.strip(), a.strip(), f"{h.strip()} vs {a.strip()}"

    return home, away, parent_name or desc or "Unknown Match"

def is_player_special(category: str, desc: str, participants: List[Dict[str, Any]]) -> bool:
    cat = (category or "").lower()
    d = (desc or "").lower()

    if any(skip in cat or skip in d for skip in TEAM_SKIP):
        # Ausnahme: "player props" darf nicht wegen "team props" raus.
        if "player" not in cat and "player" not in d:
            return False

    if any(k in cat or k in d for k in PLAYER_KEYWORDS):
        return True

    # desc="James Rodriguez To Score" ist direkt Spieler-Prop
    if extract_player_from_description(desc):
        return True

    names = [p.get("name") or p.get("participantName") or "" for p in participants]
    playerish = [n for n in names if looks_like_player(n) and norm_name(n) not in ("yes", "no")]
    return len(playerish) >= 1 and any(k in d for k in ["score", "book", "card", "shot", "assist"])

def build_price_map(markets: List[Dict[str, Any]]) -> Dict[Tuple[str, str], float]:
    """
    Map (specialId, participantId/name) -> price.
    Pinnacle Strukturen variieren, darum defensiv.
    """
    pm = {}
    for m in markets:
        sid = str(m.get("specialId") or m.get("special_id") or m.get("id") or "")
        prices = m.get("prices") or m.get("participants") or m.get("outcomes") or []
        if not isinstance(prices, list):
            continue
        for p in prices:
            pid = str(p.get("participantId") or p.get("participant_id") or p.get("id") or p.get("name") or "")
            price = p.get("price") or p.get("odds") or p.get("decimalPrice")
            try:
                price = float(price)
            except Exception:
                continue
            if sid and pid:
                pm[(sid, pid)] = price
            name = str(p.get("name") or p.get("participantName") or "")
            if sid and name:
                pm[(sid, name)] = price
    return pm

def fetch_pinnacle_specials() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Guest API Endpunkte ändern sich manchmal. Wir probieren mehrere Varianten.
    """
    candidates = [
        f"{PINNACLE_BASE}/sports/29/matchups/special",
        f"{PINNACLE_BASE}/sports/29/specials",
        f"{PINNACLE_BASE}/sports/29/matchups",
    ]
    data = []
    for url in candidates:
        try:
            raw = get_json(url)
            items = as_list(raw)
            if items:
                data = items
                log(f"Pinnacle Specials geladen: {len(data)} via {url}")
                break
        except Exception as e:
            log(f"Pinnacle Specials Endpoint skip: {str(e)[:80]}", "WARN")
    if not data:
        return [], []

    market_candidates = [
        f"{PINNACLE_BASE}/sports/29/markets/special",
        f"{PINNACLE_BASE}/sports/29/markets",
    ]
    markets = []
    for url in market_candidates:
        try:
            raw = get_json(url)
            items = as_list(raw)
            if items:
                markets = items
                log(f"Pinnacle Markets geladen: {len(markets)} via {url}")
                break
        except Exception as e:
            log(f"Pinnacle Markets Endpoint skip: {str(e)[:80]}", "WARN")
    return data, markets

def flatten_specials(specials: List[Dict[str, Any]], markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    price_map = build_price_map(markets)
    rows = []
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=LOOKAHEAD_HOURS)
    no_price = 0
    player_debug = 0

    for item in specials:
        parent = item.get("parent") or item.get("matchup") or item
        children = item.get("specials") or item.get("children") or [item]
        if not isinstance(children, list):
            children = [item]

        for sp in children:
            sid = str(sp.get("id") or sp.get("specialId") or sp.get("special_id") or "")
            cat = sp.get("category") or sp.get("categoryName") or item.get("category") or ""
            desc = sp.get("description") or sp.get("name") or sp.get("specialName") or ""
            league = (
                sp.get("league", {}).get("name") if isinstance(sp.get("league"), dict) else sp.get("league")
            ) or (
                parent.get("league", {}).get("name") if isinstance(parent.get("league"), dict) else parent.get("league")
            ) or parent.get("leagueName") or sp.get("leagueName") or ""

            parts = sp.get("participants") or sp.get("outcomes") or sp.get("prices") or []
            if not isinstance(parts, list):
                parts = []

            if not is_player_special(cat, desc, parts):
                continue

            kickoff = parse_time(parent) or parse_time(sp)
            if kickoff and (kickoff < now - timedelta(hours=2) or kickoff > end):
                continue

            home, away, match = participants_to_match(parent, sp)
            if DEBUG and player_debug < 20:
                log(f"DEBUG special cat='{cat}' desc='{desc}' match='{match}' parts={[p.get('name') or p.get('participantName') for p in parts][:4]}")
                player_debug += 1

            for p in parts:
                pname = p.get("name") or p.get("participantName") or ""
                pid = str(p.get("id") or p.get("participantId") or p.get("participant_id") or pname)
                if norm_name(pname) == "no":
                    continue

                # Bei Yes/No Specials kommt Spieler aus desc.
                player = pname
                if norm_name(pname) == "yes" or not looks_like_player(pname):
                    extracted = extract_player_from_description(desc)
                    if extracted:
                        player = extracted

                if not looks_like_player(player):
                    continue

                price = None
                for key in [(sid, pid), (sid, pname), (sid, "Yes"), (sid, "yes")]:
                    if key in price_map:
                        price = price_map[key]
                        break
                if price is None:
                    raw_price = p.get("price") or p.get("odds") or p.get("decimalPrice")
                    try:
                        price = float(raw_price)
                    except Exception:
                        price = None

                if price is None:
                    no_price += 1
                    if DEBUG and no_price <= 20:
                        log(f"NoPrice: [{cat}] {desc} | {match} | part={pname}", "WARN")
                    continue

                if price < MIN_ODDS or price > MAX_ODDS:
                    continue

                rows.append({
                    "source": "Pinnacle",
                    "source_event_id": str(parent.get("id") or parent.get("matchupId") or ""),
                    "source_special_id": sid,
                    "source_market_id": sid,
                    "kickoff_at": kickoff.isoformat() if kickoff else None,
                    "league": league,
                    "match": match,
                    "home_team": home,
                    "away_team": away,
                    "category": cat,
                    "description": desc,
                    "participant": player,
                    "price": price,
                    "raw": {"special": sp, "participant": p, "parent": parent},
                })

    log(f"Pinnacle Player Props normalisiert: {len(rows)} | ohne Preis: {no_price}")
    return rows

def normalize_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    today = datetime.now(timezone.utc).date().isoformat()
    for r in raw_rows:
        info = classify_market(r.get("description", ""), r.get("participant", ""))
        cat = info["category"]
        if cat == "other":
            continue

        player = r["participant"]
        odds = float(r["price"])
        imp = implied_prob(odds)
        mp = rough_model_prob(cat, odds)
        edge = edge_pct(mp, odds)
        rating = value_rating(edge)
        conf = 5 if rating == "HIGH" else 4 if rating == "OK" else 3 if rating == "SMALL" else 2

        kickoff = r.get("kickoff_at")
        date = today
        if kickoff:
            try:
                date = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).date().isoformat()
            except Exception:
                pass

        out.append({
            "date": date,
            "kickoff_at": kickoff,
            "source": r["source"],
            "league": r.get("league"),
            "match": r.get("match"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "player": player,
            "normalized_player": norm_name(player),
            "team": None,
            "market": info["market"],
            "category": cat,
            "line": info["line"],
            "selection": info["selection"],
            "odds": odds,
            "implied_prob": imp,
            "model_prob": mp,
            "hit_rate": None,
            "fair_odds": fair_odds(mp),
            "edge_pct": edge,
            "confidence": conf,
            "value_rating": rating,
            "status": "candidate",
        })
    return out

CAT_ICON = {
    "goalscorer": "⚽",
    "assist": "🎯",
    "card": "🟨",
    "sot": "🥅",
    "shots": "🎯",
    "tackles": "🧱",
    "fouls": "🟥",
    "offsides": "🚩",
}

def build_cards(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Gute Legs zuerst, max 6 Builder.
    valid = [
        p for p in props
        if p["odds"] >= MIN_ODDS and p["odds"] <= MAX_ODDS and p["category"] in CAT_ICON
    ]
    valid.sort(key=lambda p: (p.get("edge_pct") or 0, p.get("model_prob") or 0), reverse=True)

    # Duplikate Spieler/Märkte begrenzen.
    seen = set()
    unique = []
    for p in valid:
        key = (p["match"], p["player"], p["category"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    cards = []

    # 2-3 Leg Safe Builder
    for size in (2, 3, 4, 5, 6):
        legs = []
        used_matches = {}
        used_players = set()
        for p in unique:
            if p["player"] in used_players:
                continue
            # nicht mehr als 2 aus gleichem Match für breite Builder
            if used_matches.get(p["match"], 0) >= (2 if size >= 4 else 3):
                continue
            legs.append(p)
            used_players.add(p["player"])
            used_matches[p["match"]] = used_matches.get(p["match"], 0) + 1
            if len(legs) == size:
                break
        if len(legs) < size:
            continue
        total = 1.0
        for l in legs:
            total *= float(l["odds"])
        total = round(total, 2)
        if total < 2.0:
            continue
        title = "PLAYER BUILDER" if size <= 3 else "HIGH ROLLER BUILDER"
        stake = 0.5 if total < 50 else 0.25
        bid_src = "|".join(f"{l['match']}:{l['player']}:{l['market']}:{l['odds']}" for l in legs)
        builder_id = hashlib.sha1(bid_src.encode()).hexdigest()[:16]
        cards.append({
            "builder_id": f"pbv4_{datetime.now(timezone.utc).date()}_{builder_id}",
            "title": title,
            "total_odds": total,
            "stake": stake,
            "confidence": max(2, min(5, round(sum(l["confidence"] for l in legs) / len(legs)))),
            "legs": legs,
        })
        if len(cards) >= 6:
            break

    return cards

def format_builder(card: Dict[str, Any]) -> str:
    nl = "\n"
    legs = card["legs"]
    total = card["total_odds"]
    title = card["title"]
    emoji = "🏗️" if total < 50 else "👑"
    msg = f"{emoji} <b>{title}</b>  <b>{total:.2f}</b>{nl}"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"

    by_match = {}
    for l in legs:
        by_match.setdefault(l["match"] or "Unknown Match", []).append(l)

    for match, mlegs in by_match.items():
        msg += f"⚽ <b>{match}</b>{nl}"
        for l in mlegs:
            icon = CAT_ICON.get(l["category"], "🎯")
            prob = int(round((l.get("model_prob") or 0) * 100))
            edge = l.get("edge_pct")
            msg += f"   {icon} <b>{l['player']}</b> — {l['market']} @ {l['odds']:.2f}{nl}"
            msg += f"      <i>{prob}% · Edge {edge:+.1f}% · {l['value_rating']}</i>{nl}"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"💰 @ <b>{total:.2f}</b> · {card['stake']}u\n"
    msg += "<i>NETRATTLER Prop Builder V4</i>"
    return msg

def send_telegram(text: str) -> Optional[int]:
    if not TELEGRAM_TOKEN or not PROP_CHAT:
        log("Telegram fehlt, nur Dry-Run", "WARN")
        print(text)
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": PROP_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=20)
    if not r.ok:
        log(f"Telegram Error {r.status_code}: {r.text[:200]}", "WARN")
        return None
    try:
        return r.json().get("result", {}).get("message_id")
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.debug:
        globals()["DEBUG"] = True

    log("NETRATTLER Prop Builder V4 startet")
    specials, markets = fetch_pinnacle_specials()
    if not specials:
        log("Keine Pinnacle Specials gefunden", "WARN")
        return

    raw_rows = flatten_specials(specials, markets)
    props = normalize_rows(raw_rows)
    log(f"Normalized Props: {len(props)}")
    cats = {}
    for p in props:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    log(f"Kategorien: {cats}")

    if not args.dry_run:
        supa = SupabaseV4()
        try:
            saved_raw = supa.upsert("prop_raw_events", raw_rows, on_conflict="source,source_special_id,participant", batch_size=300)
            log(f"Supabase raw gespeichert: {saved_raw}")
        except Exception as e:
            log(f"Supabase raw Fehler: {e}", "WARN")
        try:
            saved_norm = supa.upsert("prop_normalized", props, on_conflict="source,match,player,market,selection,odds", batch_size=300)
            log(f"Supabase normalized gespeichert: {saved_norm}")
        except Exception as e:
            log(f"Supabase norm Fehler: {e}", "WARN")

    cards = build_cards(props)
    log(f"Builder gebaut: {len(cards)}")

    if not cards:
        log("Keine Builder. Debug einschalten mit PINNACLE_DEBUG=true", "WARN")
        return

    for card in cards:
        msg = format_builder(card)
        mid = None if args.dry_run else send_telegram(msg)
        print(msg)
        if not args.dry_run:
            try:
                supa = SupabaseV4()
                row = {
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "builder_id": card["builder_id"],
                    "title": card["title"],
                    "total_odds": card["total_odds"],
                    "stake": card["stake"],
                    "confidence": card["confidence"],
                    "legs": card["legs"],
                    "message_text": msg,
                    "telegram_chat_id": str(PROP_CHAT),
                    "telegram_msg_id": mid,
                }
                supa.upsert("prop_builder_cards", [row], on_conflict="builder_id")
            except Exception as e:
                log(f"Builder Save Fehler: {e}", "WARN")
        time.sleep(1)

    log("Fertig")

if __name__ == "__main__":
    main()
