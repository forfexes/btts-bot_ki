#!/usr/bin/env python3
"""
NETRATTLER Settlement FINAL V21
===============================

Dateiname bleibt absichtlich stabil: netrattler_settlement_v16_final.py

Wesentliche Fixes:
- stabile Settlement-ID pro Tipp (kein neues Duplikat bei jedem Run)
- wertet eine Combo/Builder als EINEN Tipp aus, Legs nur intern
- lädt echte Builder aus netrattler_builder_picks
- flexible Player-Stats-Auswertung: Shots, SOT, Fouls, Fouls Won,
  Tackles, Karten, Tore, Assists und Corners
- korrekter Profit/ROI auf Basis des Einsatzes
- Reports nur für neu abgeschlossene Tipps, nicht bei jedem Run erneut
- Gruppe für Gruppe: Heute, 7 Tage, Monat, Jahr, All Time
- dedupliziert historische Alt-Settlements nach tip_id
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

try:
    from netrattler_identity_hub import teams_match as _identity_teams_match
except Exception:
    _identity_teams_match = None

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
TG_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
TG_DEFAULT = os.getenv("TELEGRAM_CHAT_ID") or ""
ALLSPORTS_API_KEY = os.getenv("ALLSPORTS_API_KEY") or ""
FOOTBALL_DATA_API_KEYS = [k.strip() for k in (os.getenv("FOOTBALL_DATA_API_KEYS") or os.getenv("FOOTBALL_DATA_API_KEY") or "").split(",") if k.strip()]
FOOTBALLDATA_IO_API_KEY = os.getenv("FOOTBALLDATA_IO_API_KEY") or ""
RESULT_HTTP_TIMEOUT = int(os.getenv("RESULT_HTTP_TIMEOUT", "8"))


def _cffi_get_json(url, timeout=8, params=None):
    """🚀 curl_cffi (TLS-Impersonation) für Ergebnis-Abruf — umgeht SofaScore/ESPN 403.
    Fällt auf normales requests zurück, wenn curl_cffi fehlt."""
    try:
        from curl_cffi import requests as _creq
        r = _creq.get(url, params=params, impersonate="chrome", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    try:
        r = requests.get(url, params=params,
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                        timeout=timeout)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None
RESULT_USE_SOFASCORE = os.getenv("RESULT_USE_SOFASCORE", "false").lower() in {"1", "true", "yes", "on"}
RESULT_USE_ESPN = os.getenv("RESULT_USE_ESPN", "true").lower() not in {"0", "false", "no"}
RESULT_USE_OPENLIGADB = os.getenv("RESULT_USE_OPENLIGADB", "true").lower() not in {"0", "false", "no"}
DAYS = int(os.getenv("SETTLEMENT_DAYS", "7"))
LIMIT = int(os.getenv("SETTLEMENT_LIMIT", "1200"))
UPDATE_SOURCE_TIPS = os.getenv("UPDATE_SOURCE_TIPS", "true").lower() not in {"0", "false", "no"}
SEND_PENDING_SUMMARY = os.getenv("SEND_PENDING_SUMMARY", "false").lower() in {"1", "true", "yes"}
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
TODAY_S = TODAY.isoformat()

GROUPS = {
    "btts": os.getenv("TELEGRAM_GROUP_BTTS") or TG_DEFAULT,
    "over25": os.getenv("TELEGRAM_GROUP_OVER25") or TG_DEFAULT,
    "combo": os.getenv("TELEGRAM_GROUP_COMBO") or os.getenv("TELEGRAM_GROUP_COMBOS") or TG_DEFAULT,
    "btts_ht": os.getenv("TELEGRAM_GROUP_BTTS_HT") or TG_DEFAULT,
    "over15_ht": os.getenv("TELEGRAM_GROUP_OVER15_HT") or os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
    "builder": os.getenv("TELEGRAM_GROUP_BUILDER") or os.getenv("TELEGRAM_GROUP_PLAYER_PROPS") or os.getenv("TELEGRAM_GROUP_PROPS") or TG_DEFAULT,
    "props": os.getenv("TELEGRAM_GROUP_PLAYER_PROPS") or os.getenv("TELEGRAM_GROUP_PROPS") or TG_DEFAULT,
    "corners": os.getenv("TELEGRAM_GROUP_CORNERS") or os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
    "scorer": os.getenv("TELEGRAM_GROUP_LATE_GOALS") or TG_DEFAULT,
    "1x2": os.getenv("TELEGRAM_GROUP_1X2") or os.getenv("TELEGRAM_GROUP_LATE_GOALS") or TG_DEFAULT,
    "stats": os.getenv("TELEGRAM_GROUP_STATS") or TG_DEFAULT,
    "default": TG_DEFAULT,
}

GROUP_ORDER = ["btts", "over25", "combo", "btts_ht", "over15_ht", "1x2", "scorer", "builder", "props", "corners"]

# Nur tatsächlich gesendete Tipps. player_prop_db ist ein Kandidaten-/Datenpool und
# wird absichtlich NICHT komplett als Tipp ausgewertet.
TIP_TABLES = ["tips", "ml_tips", "netrattler_builder_picks"]  # prop_picks entfernt → gehört Prop Hunter (eigene DB)
RESULT_TABLES = {
    "match_results": ["match_date"],  # 🆕 Primär: SofaScore post-match (alle Ligen!)
    "international_results": ["date", "match_date", "Date", "game_date", "event_date"],
    "football_historical_matches": ["match_date", "Date", "game_date", "utc_date", "event_date"],
    "netrattler_data_lake_raw": ["match_date", "Date", "game_date", "event_date", "created_at"],
    "result_candidates": ["match_date", "date", "event_date"],
}
PLAYER_STATS_TABLES = {
    "player_match_stats": ["match_date", "date", "event_date", "created_at"],
    "sofascore_player_match_stats": ["match_date", "date", "event_date", "created_at"],
}


def log(message: str, level: str = "INFO") -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}", flush=True)


def hsh(*parts: Any) -> str:
    return hashlib.sha1("||".join(str(x or "") for x in parts).encode("utf-8")).hexdigest()


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("&", " and ")
    aliases = {"munchen": "munich", "koln": "cologne", "praha": "prague", "wien": "vienna", "moskva": "moscow"}
    for source, target in aliases.items():
        text = re.sub(rf"\b{source}\b", target, text)
    text = re.sub(r"\b(fc|sc|cf|afc|fk|ac|club|de|the|team|women|wfc)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: Any, b: Any) -> float:
    x, y = norm(a), norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if x in y or y in x:
        return 0.88
    sx, sy = set(x.split()), set(y.split())
    return len(sx & sy) / max(1, len(sx | sy))


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def anyv(row: Dict[str, Any], keys: Sequence[str], default: Any = "") -> Any:
    if not isinstance(row, dict):
        return default
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return default


def unpack(row: Dict[str, Any]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    if not isinstance(row, dict):
        return output
    for key in ("tip_payload", "payload", "raw", "data"):
        value = row.get(key)
        if isinstance(value, dict):
            output.update(value)
    output.update(row)
    return output


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def row_date(row: Dict[str, Any]) -> str:
    data = unpack(row)
    for key in (
        "match_date", "date", "Date", "game_date", "event_date", "sent_date",
        "ko", "kickoff", "kickoff_at", "event_time", "commence_time", "created_at",
    ):
        parsed = parse_dt(data.get(key))
        if parsed:
            return parsed.date().isoformat()
    return TODAY_S


def headers(prefer: str = "return=representation") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def sb_get(table: str, params: Dict[str, str], quiet: bool = True) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}", headers=headers(), params=params, timeout=30
        )
        if response.status_code >= 400:
            if not quiet:
                log(f"GET {table} {response.status_code}: {response.text[:180]}", "WARN")
            return []
        return response.json() if response.text else []
    except Exception as exc:
        if not quiet:
            log(f"GET {table}: {exc}", "WARN")
        return []


def sb_upsert(table: str, rows: Sequence[Dict[str, Any]], conflict: str) -> int:
    if not rows:
        return 0
    saved = 0
    for start in range(0, len(rows), 150):
        part = list(rows[start : start + 150])
        try:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers=headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": conflict},
                data=json.dumps(part, ensure_ascii=False, default=str),
                timeout=35,
            )
            if response.status_code in (200, 201, 204):
                saved += len(part)
            else:
                log(f"UPSERT {table} {response.status_code}: {response.text[:220]}", "WARN")
        except Exception as exc:
            log(f"UPSERT {table}: {exc}", "WARN")
    return saved


def sb_patch(table: str, column: str, value: Any, payload: Dict[str, Any]) -> bool:
    if not value:
        return False
    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers("return=minimal"),
            params={column: f"eq.{value}"},
            data=json.dumps(payload, ensure_ascii=False, default=str),
            timeout=20,
        )
        return response.status_code in (200, 204)
    except Exception:
        return False


def telegram(chat_id: str, text: str) -> bool:
    if not TG_TOKEN or not chat_id:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:3900],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if not response.ok:
            log(f"TG {response.status_code}: {response.text[:180]}", "WARN")
        return response.ok
    except Exception as exc:
        log(f"TG: {exc}", "WARN")
        return False



def telegram_edit(chat_id: str, message_id: Any, text: str) -> bool:
    """Original-Tipp direkt bearbeiten."""
    if not TG_TOKEN or not chat_id or not message_id:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": text[:3900],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if not response.ok:
            log(f"TG edit {response.status_code}: {response.text[:180]}", "WARN")
        return response.ok
    except Exception as exc:
        log(f"TG edit: {exc}", "WARN")
        return False


def _strip_old_direct_summary(original: str) -> str:
    if not original:
        return ""
    original = str(original)
    # neue Auswertung: ab der ━━━-Zeile, die von 🏁/✅/❌ ERGEBNIS gefolgt wird
    m = re.search(r"\n?━━━+\n(?:🏁|✅ <b>Tipp|❌ <b>Tipp)", original)
    if m:
        original = original[:m.start()].rstrip()
    # alte Auswertung (⸻⸻ ... Summary) entfernen
    pattern = r"\n?⸻⸻\s*(?:<b>)?(?:Match|Combo|Corner|Builder|Prop) Summary(?:</b>)?\s*⸻⸻[\s\S]*$"
    return re.sub(pattern, "", original).rstrip()


def _direct_summary_title(group: str) -> str:
    if group == "combo":
        return "Combo Summary"
    if group == "corners":
        return "Corner Summary"
    if group == "builder":
        return "Builder Summary"
    if group == "props":
        return "Prop Summary"
    return "Match Summary"


def format_direct_summary(settlement: Dict[str, Any]) -> str:
    """Auswertung direkt im Original-Tipp — Variante B (sauber, kompakt)."""
    status = normalized_status(settlement.get("status"))
    profit = as_float(settlement.get("profit"), 0.0)
    result = settlement.get("match_result") or {}
    raw = result.get("raw") if isinstance(result, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    home_score = result.get("home_score") if isinstance(result, dict) else None
    away_score = result.get("away_score") if isinstance(result, dict) else None
    ht_home = anyv(raw, ["home_score_ht", "ht_home", "home_ht", "HTHG", "intHomeScoreHT"], None)
    ht_away = anyv(raw, ["away_score_ht", "ht_away", "away_ht", "HTAG", "intAwayScoreHT"], None)

    lines = ["━━━━━━━━━━━━━━━━━━"]

    # 🏁 ERGEBNIS: 2:1 (HT 1:0)
    if home_score not in (None, "") and away_score not in (None, ""):
        _res = f"🏁 <b>ERGEBNIS: {home_score}:{away_score}</b>"
        if ht_home not in (None, "") and ht_away not in (None, ""):
            _res += f" (HT {ht_home}:{ht_away})"
        lines.append(_res)

    # ✅ Tipp GEWONNEN / ❌ Tipp VERLOREN
    if status == "win":
        lines.append("✅ <b>Tipp GEWONNEN</b>")
    else:
        lines.append("❌ <b>Tipp VERLOREN</b>")

    # 💰 +0.85 Units
    _icon = "💰" if profit >= 0 else "📉"
    lines.append(f"{_icon} <b>{profit:+.2f} Units</b>")

    # Leg-Auswertung nur bei Combos/Buildern (kompakt)
    legs = settlement.get("legs_payload") or []
    if isinstance(legs, list) and legs and settlement.get("market_group", "") in {"combo", "builder", "props"}:
        lines.append("")
        for item in legs[:8]:
            if not isinstance(item, dict):
                continue
            st = normalized_status(item.get("status"))
            icon = "✅" if st == "win" else "❌" if st == "loss" else "⏳"
            leg = item.get("leg") if isinstance(item.get("leg"), dict) else {}
            label = market_text(leg) if leg else str(item.get("reason") or "Leg")
            lines.append(f"{icon} {label[:60]}")
    return "\n".join(lines)


def edit_original_tip(settlement: Dict[str, Any]) -> bool:
    """Wenn telegram_msg_id + message_text gespeichert sind: Original-Tipp direkt editieren."""
    if normalized_status(settlement.get("status")) not in {"win", "loss"}:
        return False
    payload = settlement.get("tip_payload") or {}
    data = unpack(payload)
    chat_id = anyv(data, ["telegram_chat_id", "chat_id", "tg_chat_id", "channel_id"], "")
    message_id = anyv(data, ["telegram_msg_id", "telegram_message_id", "message_id", "tg_message_id"], "")
    original = str(anyv(data, ["message_text", "text", "tip_text", "message", "caption"], ""))
    if not chat_id or not message_id or not original:
        return False
    edited = _strip_old_direct_summary(original) + "\n\n" + format_direct_summary(settlement)
    return telegram_edit(str(chat_id), message_id, edited)


def market_text(row: Dict[str, Any]) -> str:
    data = unpack(row)
    values: List[str] = []
    for key in ("selection", "pick", "bet", "tip", "market", "type", "bet_type", "category"):
        value = data.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text and text.lower() not in {"none", "null", "nan"}:
                values.append(text)
    return " / ".join(dict.fromkeys(values)).strip() or "Market nicht erkannt"


def group_of(row: Dict[str, Any]) -> str:
    data = unpack(row)
    explicit = str(data.get("market_group") or "").lower().strip()
    if explicit in GROUP_ORDER:
        return explicit
    low = " ".join(
        str(anyv(data, [key], ""))
        for key in ("market", "type", "bet_type", "category", "group", "channel", "selection", "pick", "message", "text", "tip_text", "title", "style")
    ).lower()
    if any(x in low for x in ("builder", "bet_builder", "bet builder", "shot ladder", "sot trio", "foul press", "tackle wall", "corner fusion")):
        return "builder"
    if any(x in low for x in ("combo", "multi", "parlay", "acca", "same game")):
        return "combo"
    if "btts_ht" in low or "btts ht" in low or "both teams to score ht" in low:
        return "btts_ht"
    if "over15_ht" in low or "over 1.5 ht" in low or "over 1.5 first half" in low:
        return "over15_ht"
    if any(x in low for x in ("corner", "corners", "ecken")):
        return "corners"
    if any(x in low for x in ("1x2", "heimsieg", "auswärtssieg", "auswaertssieg", "unentschieden")):
        return "1x2"
    if any(x in low for x in ("scorer", "goalscorer", "to score")):
        return "scorer"
    if any(x in low for x in ("player", "booked", "carded", "shot", "sot", "foul", "tackle")):
        return "props"
    if ("over" in low and "2.5" in low) or "over25" in low:
        return "over25"
    if "btts" in low or "both teams" in low:
        return "btts"
    return "default"


def match_parts(row: Dict[str, Any]) -> Tuple[str, str, str]:
    data = unpack(row)
    home = str(anyv(data, ["home_team", "home", "team_home", "HomeTeam", "strHomeTeam", "home_name", "homeTeamName"], ""))
    away = str(anyv(data, ["away_team", "away", "team_away", "AwayTeam", "strAwayTeam", "away_name", "awayTeamName"], ""))
    if isinstance(data.get("homeTeam"), dict):
        home = home or str(anyv(data["homeTeam"], ["name", "shortName", "displayName"], ""))
    if isinstance(data.get("awayTeam"), dict):
        away = away or str(anyv(data["awayTeam"], ["name", "shortName", "displayName"], ""))
    match = str(anyv(data, ["match", "fixture", "game", "event", "entity_name", "name", "title"], ""))
    if (not home or not away) and re.search(r"\s+v(s)?\.?\s+", match, re.I):
        parts = re.split(r"\s+vs\.?\s+|\s+v\.?\s+", match, flags=re.I)
        if len(parts) >= 2:
            home, away = parts[0].strip(), parts[1].strip()
    if not match and home and away:
        match = f"{home} vs {away}"
    return home, away, match


def tip_id(row: Dict[str, Any]) -> str:
    data = unpack(row)
    for key in ("builder_id", "tip_id", "pick_id", "uuid", "id", "dedup_key"):
        if data.get(key) not in (None, ""):
            return str(data[key])
    home, away, match = match_parts(row)
    legs = legs_of(row)
    leg_signature = json.dumps(legs, ensure_ascii=False, sort_keys=True, default=str) if legs else ""
    return hsh(row_date(row), match, home, away, market_text(row), leg_signature)


def stable_settlement_id(row: Dict[str, Any]) -> str:
    return hsh("netrattler-settlement-v21", row.get("_table", ""), tip_id(row))


def source_key(row: Dict[str, Any]) -> Tuple[str, Any]:
    data = unpack(row)
    for key in ("builder_id", "tip_id", "pick_id", "uuid", "id", "dedup_key"):
        if data.get(key) not in (None, ""):
            return key, data[key]
    return "", ""


def normalized_status(value: Any) -> str:
    status = str(value or "").lower().strip()
    if status in {"win", "won", "green"}:
        return "win"
    if status in {"loss", "lost", "red"}:
        return "loss"
    if status in {"void", "push", "cancelled", "canceled"}:
        return "void"
    return "pending"


def include_tip(row: Dict[str, Any]) -> bool:
    data = unpack(row)
    _st = normalized_status(anyv(data, ["status", "result", "settlement_status"], "pending"))
    # pending UND void erneut versuchen (void entstand meist nur durch fehlendes Ergebnis).
    _reset_void = str(os.getenv("NETRATTLER_RESETTLE_VOID", "true")).lower() in ("1", "true", "yes", "on")
    # 🔧 Auch falsch abgerechnete won/lost der HT/Corner-Märkte neu bewerten:
    # deren Alt-Abrechnung war fehlerhaft (btts_ht 100%, corners 0%). Mit curl_cffi
    # holen wir jetzt HT-Stände + Ecken → korrekt neu bewerten.
    _reset_markets = str(os.getenv("NETRATTLER_RESETTLE_MARKETS", "btts_ht,over15_ht,corners")).lower()
    _mk = str(anyv(data, ["market", "market_group", "type"], "")).lower()
    _is_reset_market = any(m and m in _mk for m in _reset_markets.split(","))
    if _st in ("won", "win", "lost", "loss") and _is_reset_market and \
       str(os.getenv("NETRATTLER_RESETTLE_BROKEN", "false")).lower() in ("1", "true", "yes", "on"):
        pass  # → wird neu bewertet (nicht ausgeschlossen)
    elif _st not in ("pending",) and not (_reset_void and _st == "void"):
        return False
    return row_date(row) >= (TODAY - timedelta(days=DAYS)).isoformat()


def load_tips() -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for table in TIP_TABLES:
        rows = sb_get(table, {"select": "*", "limit": str(LIMIT)}, quiet=True)
        if rows:
            log(f"Tip-Tabelle {table}: {len(rows)} Rows geladen")
        for row in rows:
            if include_tip(row):
                item = dict(row)
                item["_table"] = table
                output.append(item)
    seen = set()
    clean = []
    for row in output:
        key = (row.get("_table"), tip_id(row))
        if key not in seen:
            seen.add(key)
            clean.append(row)
    clean = clean[:LIMIT]
    log(f"Offene Tipps total: {len(clean)}")
    log(f"Offene Tipps nach Gruppen: {dict(Counter(group_of(x) for x in clean))}")
    return clean


def score_row(row: Dict[str, Any]) -> Tuple[str, str, Optional[int], Optional[int]]:
    data = unpack(row)
    home, away, _ = match_parts(data)
    home_score = anyv(data, ["home_score", "home_goals", "FTHG", "intHomeScore", "score_home", "homeScore", "home_goals_ft", "homeGoals"], None)
    away_score = anyv(data, ["away_score", "away_goals", "FTAG", "intAwayScore", "score_away", "awayScore", "away_goals_ft", "awayGoals"], None)
    for key in ("score", "result", "ft_score", "full_time_score"):
        if home_score in (None, "") and isinstance(data.get(key), str):
            nums = re.findall(r"\d+", data[key])
            if len(nums) >= 2:
                home_score, away_score = nums[0], nums[1]
                break
    try:
        home_score = int(float(home_score))
    except (TypeError, ValueError):
        home_score = None
    try:
        away_score = int(float(away_score))
    except (TypeError, ValueError):
        away_score = None
    return home, away, home_score, away_score


def _append_result(output: List[Dict[str, Any]], source: str, day: str, home: Any, away: Any,
                   home_score: Any, away_score: Any, raw: Optional[Dict[str, Any]] = None,
                   ht_home: Any = None, ht_away: Any = None) -> None:
    """Normalisiert ein fertiges Resultat. Ungültige/ungeklärte Scores werden verworfen."""
    if not home or not away or home_score in (None, "") or away_score in (None, ""):
        return
    try:
        hs, aw = int(float(home_score)), int(float(away_score))
    except (TypeError, ValueError):
        return
    row: Dict[str, Any] = {
        "home_team": str(home), "away_team": str(away),
        "home_score": hs, "away_score": aw, "match_date": day,
        "raw": raw or {}, "_result_table": source,
    }
    if ht_home not in (None, "") and ht_away not in (None, ""):
        row["home_score_ht"] = as_int(ht_home, -1)
        row["away_score_ht"] = as_int(ht_away, -1)
    output.append(row)


def _sofascore_results(day: str) -> List[Dict[str, Any]]:
    if not RESULT_USE_SOFASCORE:
        return []
    output: List[Dict[str, Any]] = []
    try:
        data = _cffi_get_json(
            f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{day}",
            timeout=RESULT_HTTP_TIMEOUT,
        )
        if not data:
            log(f"SofaScore {day}: keine Daten (403/blockiert)", "WARN")
            return []
        for event in data.get("events") or []:
            if str((event.get("status") or {}).get("type") or "").lower() != "finished":
                continue
            hs = (event.get("homeScore") or {}).get("current")
            aw = (event.get("awayScore") or {}).get("current")
            _append_result(output, "SofaScore", day,
                (event.get("homeTeam") or {}).get("name"),
                (event.get("awayTeam") or {}).get("name"), hs, aw, event,
                (event.get("homeScore") or {}).get("period1"),
                (event.get("awayScore") or {}).get("period1"))
    except Exception as exc:
        log(f"SofaScore {day}: {str(exc)[:100]}", "WARN")
    return output


def _espn_results(day: str) -> List[Dict[str, Any]]:
    if not RESULT_USE_ESPN:
        return []
    output: List[Dict[str, Any]] = []
    try:
        dates = day.replace("-", "")
        data = _cffi_get_json(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard",
            params={"dates": dates, "limit": "1000"}, timeout=RESULT_HTTP_TIMEOUT,
        )
        if not data:
            log(f"ESPN {day}: keine Daten (403/blockiert)", "WARN")
            return []
        for event in data.get("events") or []:
            comp = ((event.get("competitions") or [{}])[0])
            status = ((comp.get("status") or {}).get("type") or {})
            if not (status.get("completed") or str(status.get("state") or "").lower() == "post"):
                continue
            home = away = None; hs = aw = None
            for c in comp.get("competitors") or []:
                team = (c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name")
                if c.get("homeAway") == "home": home, hs = team, c.get("score")
                elif c.get("homeAway") == "away": away, aw = team, c.get("score")
            _append_result(output, "ESPN", day, home, away, hs, aw, event)
    except Exception as exc:
        log(f"ESPN {day}: {str(exc)[:100]}", "WARN")
    return output


def _openligadb_results(day: str) -> List[Dict[str, Any]]:
    if not RESULT_USE_OPENLIGADB:
        return []
    output: List[Dict[str, Any]] = []
    try:
        r = requests.get(f"https://api.openligadb.de/getmatchdata/{day}", timeout=RESULT_HTTP_TIMEOUT)
        if not r.ok:
            return []
        for match in r.json() if isinstance(r.json(), list) else []:
            if not match.get("matchIsFinished"):
                continue
            results = match.get("matchResults") or []
            final = None
            for item in results:
                if item.get("resultTypeID") == 2 or str(item.get("resultName") or "").lower() in {"endresult", "endergebnis"}:
                    final = item
                    break
            final = final or (results[-1] if results else {})
            _append_result(output, "OpenLigaDB", day,
                (match.get("team1") or {}).get("teamName"),
                (match.get("team2") or {}).get("teamName"),
                final.get("pointsTeam1"), final.get("pointsTeam2"), match)
    except Exception as exc:
        log(f"OpenLigaDB {day}: {str(exc)[:100]}", "WARN")
    return output


def _windrawwin_results(day: str) -> List[Dict[str, Any]]:
    """Windrawwin: HT-Stände + Ergebnisse via einfache HTML-Tabellen (pandas.read_html).
    Kaum Bot-Schutz — laut Recherche die stabilste Ergebnis-Quelle für HT/Ecken."""
    output: List[Dict[str, Any]] = []
    if str(os.getenv("NETRATTLER_USE_WINDRAWWIN", "true")).lower() not in ("1", "true", "yes", "on"):
        return output
    try:
        import pandas as _pd
        # Windrawwin Results-Seite pro Tag
        url = f"https://www.windrawwin.com/results/{day}/"
        html = _cffi_get_json.__wrapped__ if hasattr(_cffi_get_json, "__wrapped__") else None
        # HTML holen (curl_cffi Text)
        try:
            from curl_cffi import requests as _creq
            r = _creq.get(url, impersonate="chrome", timeout=RESULT_HTTP_TIMEOUT)
            raw = r.text if r.status_code == 200 else None
        except Exception:
            raw = None
        if not raw:
            return output
        tables = _pd.read_html(raw)
        for tbl in tables:
            for _, row in tbl.iterrows():
                cells = [str(c) for c in row.values]
                # Suche nach "Home  X-Y  Away" Mustern
                for c in cells:
                    m = re.search(r"(.+?)\s+(\d+)\s*[-:]\s*(\d+)\s+(.+)", c)
                    if m:
                        _append_result(output, "Windrawwin", day,
                                       m.group(1).strip(), m.group(4).strip(),
                                       m.group(2), m.group(3), {})
    except Exception as exc:
        log(f"Windrawwin {day}: {str(exc)[:60]}", "WARN")
    return output


def public_results(day: str) -> List[Dict[str, Any]]:
    """Key-freie + Key-basierte Resultat-Fallbacks. Keine einzelne Quelle darf den Run stoppen."""
    output: List[Dict[str, Any]] = []
    source_counts: Counter = Counter()

    # 🍋 OddsPapi zuerst (API, Endstand + HT, kein Block) — nutzt gecachten Fixtures-Call
    try:
        import netrattler_oddspapi as _op
        for r in _op.get_results(day):
            _append_result(output, "OddsPapi", day, r.get("home"), r.get("away"),
                           r.get("home_score"), r.get("away_score"), r,
                           r.get("ht_home"), r.get("ht_away"))
    except Exception as exc:
        log(f"OddsPapi results {day}: {str(exc)[:80]}", "WARN")

    for getter in (_sofascore_results, _espn_results, _openligadb_results, _windrawwin_results):
        rows = getter(day)
        output.extend(rows)

    # TheSportsDB (curl_cffi gegen Blocks)
    try:
        data = _cffi_get_json("https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
                             params={"d": day, "s": "Soccer"}, timeout=RESULT_HTTP_TIMEOUT)
        if data:
            for event in data.get("events") or []:
                _append_result(output, "TheSportsDB", day, event.get("strHomeTeam"), event.get("strAwayTeam"),
                               event.get("intHomeScore"), event.get("intAwayScore"), event,
                               event.get("intHomeScoreHT"), event.get("intAwayScoreHT"))
    except Exception as exc:
        log(f"TheSportsDB {day}: {str(exc)[:100]}", "WARN")

    # AllSports
    if ALLSPORTS_API_KEY:
        try:
            r = requests.get("https://apiv2.allsportsapi.com/football/",
                params={"met": "Fixtures", "APIkey": ALLSPORTS_API_KEY, "from": day, "to": day},
                timeout=RESULT_HTTP_TIMEOUT)
            if r.ok:
                for m in r.json().get("result") or []:
                    if str(m.get("event_status") or "").lower() not in {"finished", "ft", "after extra time", "after penalties"}:
                        continue
                    score = re.findall(r"\d+", str(m.get("event_final_result") or ""))
                    half = re.findall(r"\d+", str(m.get("event_halftime_result") or ""))
                    if len(score) >= 2:
                        _append_result(output, "AllSports", day, m.get("event_home_team"), m.get("event_away_team"),
                                       score[0], score[1], m, half[0] if len(half)>=2 else None, half[1] if len(half)>=2 else None)
            else:
                log(f"AllSports {day}: HTTP {r.status_code}", "WARN")
        except Exception as exc:
            log(f"AllSports {day}: {str(exc)[:100]}", "WARN")

    # Football-Data.org with key rotation
    for key in FOOTBALL_DATA_API_KEYS:
        try:
            r = requests.get("https://api.football-data.org/v4/matches",
                params={"dateFrom": day, "dateTo": day}, headers={"X-Auth-Token": key}, timeout=RESULT_HTTP_TIMEOUT)
            if r.status_code in (403, 429):
                continue
            if r.ok:
                for m in r.json().get("matches") or []:
                    if m.get("status") != "FINISHED":
                        continue
                    score = m.get("score") or {}; ft = score.get("fullTime") or {}; ht = score.get("halfTime") or {}
                    _append_result(output, "FootballDataOrg", day,
                        (m.get("homeTeam") or {}).get("name"), (m.get("awayTeam") or {}).get("name"),
                        ft.get("home"), ft.get("away"), m, ht.get("home"), ht.get("away"))
                break
        except Exception:
            continue

    # Source Hub V30: OpenFootball worldcup/south-america/europe/champions/internationals + guarded Livescore.
    try:
        from netrattler_source_hub import public_result_fallbacks, rows_to_settlement_results, persist_source_health
        hub_rows = rows_to_settlement_results(public_result_fallbacks(day))
        if hub_rows:
            output.extend(hub_rows)
            log(f"SourceHub V30 {day}: {len(hub_rows)}", "INFO")
        persist_source_health()
    except Exception as exc:
        log(f"SourceHub V30 {day}: {str(exc)[:100]}", "WARN")

    # Optional footballdata.io
    if FOOTBALLDATA_IO_API_KEY:
        try:
            r = requests.get(f"https://footballdata.io/api/v1/matches/date/{day}",
                headers={"Authorization": f"Bearer {FOOTBALLDATA_IO_API_KEY}"}, timeout=RESULT_HTTP_TIMEOUT)
            if r.ok:
                payload = r.json(); matches = payload.get("data") or payload.get("matches") or (payload if isinstance(payload, list) else [])
                for m in matches:
                    if str(m.get("status") or m.get("matchStatus") or "").upper() not in {"FINISHED", "FT", "COMPLETED"}:
                        continue
                    ho=m.get("homeTeam") or m.get("home_team") or {}; ao=m.get("awayTeam") or m.get("away_team") or {}; sc=m.get("score") or {}
                    home=ho.get("name") if isinstance(ho,dict) else ho; away=ao.get("name") if isinstance(ao,dict) else ao
                    _append_result(output, "FootballDataIO", day, home, away,
                        sc.get("home") or sc.get("homeScore"), sc.get("away") or sc.get("awayScore"), m)
        except Exception as exc:
            log(f"FootballDataIO {day}: {str(exc)[:100]}", "WARN")

    for row in output:
        source_counts[row.get("_result_table", "unknown")] += 1
    log(f"Externe Results {day}: {dict(source_counts)}")
    return output


def load_results(dates: Sequence[str]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    min_db_rows = int(os.getenv("RESULT_PUBLIC_FALLBACK_IF_DB_ROWS_LT", "5"))
    for day in dates:
        day_db_rows = 0
        for table, columns in RESULT_TABLES.items():
            for column in columns:
                rows = sb_get(table, {"select": "*", column: f"eq.{day}", "limit": "4000"}, quiet=True)
                if rows:
                    for row in rows:
                        row["_result_table"] = table
                    output.extend(rows)
                    day_db_rows += len(rows)
                    log(f"Results {table} {day} via {column}: {len(rows)}")
                    break
        # 🔧 FALLBACKS IMMER abfragen (ergänzend), nicht nur wenn DB leer ist.
        # Sonst fehlen Ergebnisse für exotische Ligen (Belarus, Usbekistan...),
        # die nicht in match_results stehen → Tipps bleiben ewig pending.
        # Nur überspringen, wenn explizit deaktiviert.
        _always_fallback = str(os.getenv("NETRATTLER_ALWAYS_FALLBACK_RESULTS", "false")).lower() in ("1", "true", "yes", "on")
        if day_db_rows >= min_db_rows and not _always_fallback:
            log(f"Public Result-Fallback {day} übersprungen ({day_db_rows} DB-Results vorhanden)")
            continue
        public = public_results(day)
        if public:
            output.extend(public)
            log(f"Public Results {day}: {len(public)} (ergänzend zu {day_db_rows} DB-Results)")
    seen = set()
    clean = []
    for row in output:
        home, away, hs, aw = score_row(row)
        if hs is None or aw is None:
            continue
        key = (norm(home), norm(away), hs, aw, row_date(row))
        if key not in seen:
            seen.add(key)
            clean.append(row)
    log(f"Result candidates mit Score: {len(clean)}")
    return clean


def load_player_stats(dates: Sequence[str]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for day in dates:
        for table, columns in PLAYER_STATS_TABLES.items():
            for column in columns:
                rows = sb_get(table, {"select": "*", column: f"eq.{day}", "limit": "10000"}, quiet=True)
                if rows:
                    for row in rows:
                        row["_stats_table"] = table
                    output.extend(rows)
                    log(f"Player Stats {table} {day} via {column}: {len(rows)}")
                    break
    # Flexible dedup by date/player/match/source.
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in output:
        data = unpack(row)
        player = norm(anyv(data, ["player_name", "player", "name", "athlete_name"], ""))
        match = norm(anyv(data, ["match", "fixture", "event", "match_name"], ""))
        key = (row_date(row), player, match)
        if player:
            best[key] = row
    clean = list(best.values())
    log(f"Player Stats candidates: {len(clean)}")
    return clean


def find_result(tip: Dict[str, Any], results: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    tip_home, tip_away, tip_match = match_parts(tip)
    tip_day = row_date(tip)
    best, best_score = None, 0.0
    for row in results:
        home, away, hs, aw = score_row(row)
        if hs is None or aw is None:
            continue
        direct = (similarity(tip_home, home) + similarity(tip_away, away)) / 2 if tip_home and tip_away else similarity(tip_match, f"{home} vs {away}")
        reverse = (similarity(tip_home, away) + similarity(tip_away, home)) / 2 if tip_home and tip_away else 0.0
        if _identity_teams_match and tip_home and tip_away:
            if _identity_teams_match(tip_home, home) and _identity_teams_match(tip_away, away):
                direct = max(direct, 0.98)
            if _identity_teams_match(tip_home, away) and _identity_teams_match(tip_away, home):
                reverse = max(reverse, 0.98)
        score = max(direct, reverse)
        if row_date(row) == tip_day:
            score += 0.15
        if score > best_score:
            best_score = score
            best = {"home": home, "away": away, "home_score": hs, "away_score": aw, "raw": row, "match_score": score}
    return best if best and best_score >= 0.66 else None


def player_name(row: Dict[str, Any]) -> str:
    return str(anyv(unpack(row), ["player_name", "player", "name", "athlete", "athlete_name", "selection"], ""))


def player_stats_values(row: Dict[str, Any]) -> Dict[str, float]:
    data = unpack(row)
    return {
        "shots": as_float(anyv(data, ["shots", "total_shots", "shot_total", "shot_attempts"], 0)),
        "sot": as_float(anyv(data, ["sot", "shots_on_target", "shot_on_target", "on_target"], 0)),
        "fouls": as_float(anyv(data, ["fouls_committed", "fouls", "fouls_made", "fc"], 0)),
        "fouls_won": as_float(anyv(data, ["fouls_won", "fouls_drawn", "fouled", "fd"], 0)),
        "tackles": as_float(anyv(data, ["tackles", "tackles_won", "total_tackles", "tackles_committed"], 0)),
        "tackles_committed": as_float(anyv(data, ["tackles_committed", "tackles", "tackles_won", "total_tackles"], 0)),
        "tackles_received": as_float(anyv(data, ["tackles_received", "times_tackled", "tackled"], 0)),
        "yellow_cards": as_float(anyv(data, ["yellow_cards", "cards", "yc", "bookings"], 0)),
        "goals": as_float(anyv(data, ["goals", "goal", "goals_scored"], 0)),
        "assists": as_float(anyv(data, ["assists", "assist"], 0)),
        "corners": as_float(anyv(data, ["corners", "corner_kicks"], 0)),
    }


def find_player_stat(leg: Dict[str, Any], stats: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    data = unpack(leg)
    wanted_player = str(anyv(data, ["player", "player_name", "selection"], ""))
    _, _, wanted_match = match_parts(leg)
    wanted_day = row_date(leg)
    best, best_score = None, 0.0
    for row in stats:
        p_score = similarity(wanted_player, player_name(row))
        if p_score < 0.55:
            continue
        _, _, candidate_match = match_parts(row)
        m_score = similarity(wanted_match, candidate_match) if wanted_match and candidate_match else 0.45
        d_score = 1.0 if row_date(row) == wanted_day else 0.0
        score = p_score * 0.68 + m_score * 0.22 + d_score * 0.10
        if score > best_score:
            best_score, best = score, row
    return best if best and best_score >= 0.66 else None


def market_line(text: str, default: float = 1.0) -> float:
    low_txt = str(text).lower()
    if any(x in low_txt for x in ["over25", "over_25", "over 2.5", "over2.5", "o2.5"]):
        return 2.5
    if any(x in low_txt for x in ["over15_ht", "over 1.5 ht", "over1.5 ht", "o1.5 ht"]):
        return 1.5
    plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", str(text))
    if plus:
        return as_float(plus.group(1), default)
    over = re.search(r"over\s*(\d+(?:\.\d+)?)", str(text), re.I)
    if over:
        return math.floor(as_float(over.group(1), default)) + 1
    return default


def category_of(row: Dict[str, Any]) -> str:
    data = unpack(row)
    explicit = str(data.get("category") or "").lower().strip()
    aliases = {
        "shots_on_target": "sot", "shot_on_target": "sot", "cards": "yellow_cards",
        "booked": "yellow_cards", "fouls_committed": "fouls", "fouls_drawn": "fouls_won",
        "tackles": "tackles_committed", "tackles_made": "tackles_committed",
        "tackled": "tackles_received", "goalscorer": "score", "corners": "corners",
    }
    explicit = aliases.get(explicit, explicit)
    if explicit:
        return explicit
    low = market_text(row).lower()
    if "score or assist" in low:
        return "score_assist"
    if "assist" in low:
        return "assist"
    if "goalscorer" in low or "to score" in low:
        return "score"
    if "shot on target" in low or "shots on target" in low or "sot" in low:
        return "sot"
    if "shot" in low:
        return "shots"
    if "foul won" in low or "to be fouled" in low:
        return "fouls_won"
    if "foul" in low:
        return "fouls"
    if "tackles received" in low or "to be tackled" in low:
        return "tackles_received"
    if "tackle" in low:
        return "tackles_committed"
    if "booked" in low or "carded" in low or "yellow card" in low:
        return "yellow_cards"
    if "corner" in low or "ecken" in low:
        return "corners"
    return ""


def settle_score_market(tip: Dict[str, Any], result: Dict[str, Any]) -> Tuple[str, str]:
    hs, aw = int(result["home_score"]), int(result["away_score"])
    total = hs + aw
    low = (market_text(tip) + " " + str(anyv(unpack(tip), ["message", "text", "tip_text"], ""))).lower()

    # 🏆 1X2 (Sieger): Heimsieg/Unentschieden/Auswärtssieg
    if "1x2" in low or "heimsieg" in low or "auswärtssieg" in low or "auswaertssieg" in low or "unentschieden" in low:
        if "heimsieg" in low or "home win" in low or "1x2 home" in low:
            return ("win" if hs > aw else "loss", f"{hs}:{aw} · Heimsieg {'✓' if hs > aw else '✗'}")
        if "auswärtssieg" in low or "auswaertssieg" in low or "away win" in low or "1x2 away" in low:
            return ("win" if aw > hs else "loss", f"{hs}:{aw} · Auswärtssieg {'✓' if aw > hs else '✗'}")
        if "unentschieden" in low or "draw" in low or "1x2 draw" in low:
            return ("win" if hs == aw else "loss", f"{hs}:{aw} · Remis {'✓' if hs == aw else '✗'}")

    if "btts ht" in low or "btts_ht" in low:
        raw = unpack(result.get("raw") or {})
        hth = as_int(anyv(raw, ["HTHG", "home_score_ht", "halftime_home", "intHomeScoreHT"], -1), -1)
        hta = as_int(anyv(raw, ["HTAG", "away_score_ht", "halftime_away", "intAwayScoreHT"], -1), -1)
        if hth < 0 or hta < 0:
            return "pending", "Halbzeit-Resultat fehlt"
        return ("win" if hth > 0 and hta > 0 else "loss", f"HT {hth}:{hta}")

    if "over 1.5 ht" in low or "over15_ht" in low:
        raw = unpack(result.get("raw") or {})
        hth = as_int(anyv(raw, ["HTHG", "home_score_ht", "halftime_home", "intHomeScoreHT"], -1), -1)
        hta = as_int(anyv(raw, ["HTAG", "away_score_ht", "halftime_away", "intAwayScoreHT"], -1), -1)
        if hth < 0 or hta < 0:
            return "pending", "Halbzeit-Resultat fehlt"
        return ("win" if hth + hta > 1.5 else "loss", f"HT {hth}:{hta}")

    # Combo BTTS + Over 2.5 muss BEIDES treffen.
    if (
        ("btts" in low or "both teams" in low)
        and ("over25" in low or "over 2.5" in low or "over2.5" in low or "total goals" in low)
    ):
        line = 2.5
        return ("win" if (hs > 0 and aw > 0 and total > line) else "loss", f"{hs}:{aw} · BTTS {'YES' if hs > 0 and aw > 0 else 'NO'} · Tore {total} · Over {line}")

    if "btts" in low or "both teams" in low:
        return ("win" if hs > 0 and aw > 0 else "loss", f"{hs}:{aw}")
    if "over25" in low or "over_25" in low or "over 2.5" in low or "over2.5" in low:
        line = 2.5
        return ("win" if total > line else "loss", f"{hs}:{aw} · Tore {total} · Over {line}")
    if "over" in low:
        match = re.search(r"over\s*([0-9]+(?:\.[0-9]+)?)", low)
        line = as_float(match.group(1), 2.5) if match else 2.5
        return ("win" if total > line else "loss", f"{hs}:{aw} · Tore {total} · Over {line}")
    if "under" in low:
        match = re.search(r"under\s*([0-9]+(?:\.[0-9]+)?)", low)
        line = as_float(match.group(1), 2.5) if match else 2.5
        return ("win" if total < line else "loss", f"{hs}:{aw} · Tore {total} · Under {line}")
    return "pending", f"{hs}:{aw} · Markt nicht erkannt"


def team_corner_value(leg: Dict[str, Any], result: Dict[str, Any]) -> Optional[float]:
    raw = unpack(result.get("raw") or {})
    home_corners = anyv(raw, ["home_corners", "corners_home", "HC", "homeCorners"], None)
    away_corners = anyv(raw, ["away_corners", "corners_away", "AC", "awayCorners"], None)
    if home_corners in (None, "") or away_corners in (None, ""):
        return None
    home_corners, away_corners = as_float(home_corners), as_float(away_corners)
    data = unpack(leg)
    team = str(anyv(data, ["team", "selection_team"], ""))
    home, away, _ = match_parts(leg)
    if team and similarity(team, home) >= 0.75:
        return home_corners
    if team and similarity(team, away) >= 0.75:
        return away_corners
    return home_corners + away_corners


def settle_player_market(leg: Dict[str, Any], stats: Sequence[Dict[str, Any]], result: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    category = category_of(leg)
    text = market_text(leg)
    line = as_float(anyv(unpack(leg), ["line"], 0), 0) or market_line(text, 1.0)

    if category in {"corners", "team_corners"}:
        if not result:
            return "pending", "Match-Resultat für Corners fehlt"
        value = team_corner_value(leg, result)
        if value is None:
            return "pending", "Corner-Stats fehlen"
        return ("win" if value >= line else "loss", f"Corners {value:g} · Linie {line:g}")

    row = find_player_stat(leg, stats)
    if not row:
        return "pending", "Player-Stats fehlen"
    values = player_stats_values(row)
    if category == "score_assist":
        value = values["goals"] + values["assists"]
        line = max(1.0, line)
    elif category == "score":
        value = values["goals"]
        line = max(1.0, line)
    elif category == "assist":
        value = values["assists"]
        line = max(1.0, line)
    elif category in values:
        value = values[category]
        line = max(1.0, line)
    else:
        return "pending", f"Player-Markt {category or text} nicht unterstützt"
    status = "win" if value >= line else "loss"
    return status, f"{player_name(row)} · {category} {value:g} · Linie {line:g}"


def legs_of(tip: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = unpack(tip)
    for key in ("legs", "builder_legs", "combo_legs", "selections", "legs_payload"):
        value = data.get(key)
        if isinstance(value, list):
            return [x if isinstance(x, dict) else {"selection": str(x)} for x in value]
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [x if isinstance(x, dict) else {"selection": str(x)} for x in parsed]
            except json.JSONDecodeError:
                pass
    return []


def odds_of(row: Dict[str, Any]) -> Optional[float]:
    value = anyv(unpack(row), ["total_odds", "odds", "quote", "price", "decimal_odds"], None)
    odds = as_float(value, 0)
    return odds if odds > 1 else None


def stake_of(row: Dict[str, Any]) -> float:
    return max(0.01, as_float(anyv(unpack(row), ["stake", "units", "unit", "stake_units"], 1.0), 1.0))


def settle_tip(tip: Dict[str, Any], results: Sequence[Dict[str, Any]], player_stats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    group = group_of(tip)
    tid = tip_id(tip)
    result = find_result(tip, results)
    leg_payload: List[Dict[str, Any]] = []

    if group in {"combo", "builder"}:
        legs = legs_of(tip)
        if not legs:
            legs = [tip]
        wins = losses = pending = 0
        for leg in legs:
            merged = dict(tip)
            merged.update(leg)
            leg_result = find_result(merged, results) or result
            category = category_of(merged)
            if category or group == "builder":
                status, reason = settle_player_market(merged, player_stats, leg_result)
                if status == "pending" and category in {"btts", "over_goals", ""} and leg_result:
                    status, reason = settle_score_market(merged, leg_result)
            elif leg_result:
                status, reason = settle_score_market(merged, leg_result)
            else:
                status, reason = "pending", "kein Result gefunden"
            wins += status == "win"
            losses += status == "loss"
            pending += status == "pending"
            leg_payload.append({"leg": leg, "status": status, "reason": reason})
        status = "loss" if losses else "pending" if pending else "win"
        reason = f"{wins}/{len(legs)} Legs gewonnen · {losses} verloren · {pending} offen"
    else:
        category = category_of(tip)
        if category and group in {"props", "scorer", "corners"}:
            status, reason = settle_player_market(tip, player_stats, result)
        elif result:
            status, reason = settle_score_market(tip, result)
        else:
            status, reason = "pending", "kein Result gefunden"

    odds = odds_of(tip)
    stake = stake_of(tip)
    if status == "win":
        profit = (odds - 1.0) * stake if odds else stake
    elif status == "loss":
        profit = -stake
    else:
        profit = 0.0

    data = unpack(tip)
    return {
        "settlement_id": stable_settlement_id(tip),
        "tip_id": tid,
        "source_table": tip.get("_table", ""),
        "market_group": group,
        "builder_style": str(data.get("style") or data.get("builder_style") or "")[:80],
        "leg_count": len(legs_of(tip)) if group in {"combo", "builder"} else 1,
        "status": status,
        "result_label": "✅ WIN" if status == "win" else "❌ LOST" if status == "loss" else "⏳ PENDING",
        "reason": reason,
        "odds": odds,
        "stake": round(stake, 4),
        "profit": round(profit, 4),
        "tip_date": row_date(tip),
        "tip_payload": tip,
        "legs_payload": leg_payload,
        "match_result": result if isinstance(result, dict) else {},
        "settled_at": NOW.isoformat(),
    }


def existing_settlements() -> List[Dict[str, Any]]:
    return sb_get(
        "netrattler_settlements",
        {"select": "*", "order": "settled_at.desc", "limit": "10000"},
        quiet=True,
    )


def existing_status_map(rows: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for row in rows:
        tid = str(row.get("tip_id") or "")
        if tid and tid not in output:
            output[tid] = normalized_status(row.get("status"))
    return output


def update_source_tip(settlement: Dict[str, Any]) -> None:
    if not UPDATE_SOURCE_TIPS or settlement["status"] not in {"win", "loss"}:
        return
    payload = settlement.get("tip_payload") or {}
    table = settlement.get("source_table") or payload.get("_table") or ""
    column, value = source_key(payload)
    if not table or not column:
        return
    variants = [
        {"status": settlement["status"], "result": settlement["status"], "settled_at": NOW.isoformat(), "profit": settlement["profit"]},
        {"status": settlement["status"], "settled_at": NOW.isoformat()},
        {"result": settlement["status"]},
    ]
    for variant in variants:
        if sb_patch(table, column, value, variant):
            return


def dedup_history(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # One historical bet per tip_id. Newest settlement wins.
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tid = str(row.get("tip_id") or row.get("settlement_id") or "")
        if not tid:
            continue
        current = best.get(tid)
        current_ts = str(current.get("settled_at") or "") if current else ""
        row_ts = str(row.get("settled_at") or "")
        if current is None or row_ts >= current_ts:
            best[tid] = row
    return list(best.values())


def period_start(period: str) -> str:
    if period == "today":
        return TODAY_S
    if period == "week":
        return (TODAY - timedelta(days=6)).isoformat()
    if period == "month":
        return TODAY.replace(day=1).isoformat()
    if period == "year":
        return TODAY.replace(month=1, day=1).isoformat()
    return "1900-01-01"


def summary(rows: Sequence[Dict[str, Any]], group: str, period: str, style: str = "", leg_count: int = 0) -> Dict[str, Any]:
    start = period_start(period)
    selected = []
    for row in dedup_history(rows):
        if group and row.get("market_group") != group:
            continue
        if style and str(row.get("builder_style") or "") != style:
            continue
        if leg_count and as_int(row.get("leg_count")) != leg_count:
            continue
        status = normalized_status(row.get("status"))
        if status not in {"win", "loss"}:
            continue
        if str(row.get("tip_date") or "")[:10] < start:
            continue
        item = dict(row)
        item["status"] = status
        selected.append(item)
    bets = len(selected)
    wins = sum(x["status"] == "win" for x in selected)
    losses = bets - wins
    stake = sum(max(0.01, as_float(x.get("stake"), 1.0)) for x in selected)
    profit = sum(as_float(x.get("profit"), 0.0) for x in selected)
    roi = 100.0 * profit / max(0.01, stake)
    return {
        "bets": bets,
        "wins": wins,
        "losses": losses,
        "stake": round(stake, 2),
        "profit": round(profit, 2),
        "roi": round(roi, 1),
        "winrate": round(100.0 * wins / bets, 1) if bets else 0.0,
    }


def save_group_stats(history: Sequence[Dict[str, Any]]) -> None:
    rows = []
    for group in GROUP_ORDER:
        for period in ("today", "week", "month", "year", "alltime"):
            stats = summary(history, group, period)
            rows.append({
                "stat_id": hsh("group", period, group),
                "period": period,
                "market_group": group,
                **stats,
                "updated_at": NOW.isoformat(),
            })
    log(f"Gruppenstats gespeichert: {sb_upsert('netrattler_group_stats', rows, 'stat_id')}")


def save_dimension_stats(history: Sequence[Dict[str, Any]]) -> None:
    rows: List[Dict[str, Any]] = []
    closed = [x for x in dedup_history(history) if normalized_status(x.get("status")) in {"win", "loss"}]
    styles = sorted({str(x.get("builder_style") or "") for x in closed if x.get("builder_style")})
    leg_counts = sorted({as_int(x.get("leg_count")) for x in closed if as_int(x.get("leg_count")) >= 2})
    for period in ("month", "year", "alltime"):
        for style in styles:
            stats = summary(closed, "builder", period, style=style)
            rows.append({
                "stat_id": hsh("builder_style", period, style),
                "period": period,
                "dimension_type": "builder_style",
                "dimension_value": style,
                **stats,
                "updated_at": NOW.isoformat(),
            })
        for count in leg_counts:
            stats = summary(closed, "", period, leg_count=count)
            rows.append({
                "stat_id": hsh("leg_count", period, count),
                "period": period,
                "dimension_type": "leg_count",
                "dimension_value": str(count),
                **stats,
                "updated_at": NOW.isoformat(),
            })
    if rows:
        log(f"Dimensionstats gespeichert: {sb_upsert('netrattler_performance_stats', rows, 'stat_id')}")


def match_label(settlement: Dict[str, Any]) -> str:
    payload = settlement.get("tip_payload") or {}
    home, away, match = match_parts(payload)
    return match or f"{home} vs {away}".strip(" vs") or "Unbekanntes Spiel"


def format_settlement(settlement: Dict[str, Any]) -> str:
    payload = settlement.get("tip_payload") or {}
    return (
        f"{settlement['result_label']} <b>{settlement['market_group'].upper()}</b>\n"
        f"{match_label(settlement)}\n"
        f"{market_text(payload)}\n"
        f"{settlement.get('reason', '')}\n"
        f"Profit: {as_float(settlement.get('profit')):+.2f}U"
    )


def performance_lines(history: Sequence[Dict[str, Any]], group: str) -> List[str]:
    labels = [("Heute", "today"), ("7 Tage", "week"), ("Monat", "month"), ("Jahr", "year"), ("All Time", "alltime")]
    lines = []
    for label, period in labels:
        stats = summary(history, group, period)
        if stats["bets"]:
            icon = "🟢" if stats["profit"] >= 0 else "🔴"
            lines.append(
                f"{label}: <b>{stats['wins']}-{stats['losses']}</b> / {stats['bets']} · "
                f"ROI <b>{stats['roi']:+.1f}%</b> · {stats['profit']:+.2f}U {icon}"
            )
    return lines


def send_group_reports(newly_closed: Sequence[Dict[str, Any]], current: Sequence[Dict[str, Any]], history: Sequence[Dict[str, Any]]) -> None:
    by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for settlement in newly_closed:
        by_group[settlement.get("market_group", "default")].append(settlement)
    pending_counts = Counter(x.get("market_group", "default") for x in current if x.get("status") == "pending")

    statuses = []
    for group in GROUP_ORDER:
        items = by_group.get(group, [])
        if not items and not (SEND_PENDING_SUMMARY and pending_counts[group]):
            continue
        chat = GROUPS.get(group) or GROUPS.get("default")
        if not chat:
            continue
        lines = [f"📊 <b>NETRATTLER AUSWERTUNG {group.upper()}</b>", TODAY_S, ""]
        lines.extend(performance_lines(history, group))
        if items:
            lines.extend(["", "✅❌ <b>Neu abgeschlossen</b>", ""])
            for item in items[:30]:
                block = format_settlement(item)
                if len("\n".join(lines)) + len(block) > 3650:
                    break
                lines.extend([block, ""])
        if SEND_PENDING_SUMMARY and pending_counts[group]:
            lines.append(f"⏳ Noch offen: {pending_counts[group]}")
        ok = telegram(chat, "\n".join(lines))
        statuses.append(f"{group}:{'OK' if ok else 'FAIL'}")
    log("Gruppenreports: " + (", ".join(statuses) if statuses else "keine neuen Abschlüsse"))


def send_roi_report(history: Sequence[Dict[str, Any]]) -> None:
    chat = GROUPS.get("stats") or GROUPS.get("default")
    if not chat:
        return
    lines = [f"📈 <b>NETRATTLER ROI REPORT</b>", TODAY_S, ""]
    for group in GROUP_ORDER:
        month = summary(history, group, "month")
        year = summary(history, group, "year")
        if not month["bets"] and not year["bets"]:
            continue
        lines.append(
            f"<b>{group.upper()}</b>\n"
            f"Monat: {month['wins']}-{month['losses']} · ROI {month['roi']:+.1f}% · {month['profit']:+.2f}U\n"
            f"Jahr: {year['wins']}-{year['losses']} · ROI {year['roi']:+.1f}% · {year['profit']:+.2f}U"
        )
    if len(lines) > 3:
        telegram(chat, "\n\n".join(lines))


def main() -> None:
    log("⚽ NETRATTLER Settlement FINAL V21 startet")
    log(f"Config: SofaScore={'ON' if RESULT_USE_SOFASCORE else 'OFF'} · Timeout={RESULT_HTTP_TIMEOUT}s · Limit={LIMIT}")
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("SUPABASE_URL oder SUPABASE_KEY fehlt", "ERROR")
        raise SystemExit(2)

    existing = existing_settlements()
    previous = existing_status_map(existing)
    tips = load_tips()
    if not tips:
        log("Keine offenen/neu zu bewertenden Tipps — Result/API/Player-Stats Schritte übersprungen")
        return
    dates = sorted({row_date(tip) for tip in tips})
    log(f"Dates: {dates}")
    results = load_results(dates)
    _tip_groups = {group_of(tip) for tip in tips}
    _needs_player_stats = bool(_tip_groups & {"props", "player_props", "scorer", "builder", "prop_builder"})
    if _needs_player_stats:
        player_stats = load_player_stats(dates)
    else:
        player_stats = []
        log("Player-Stats übersprungen: keine offenen Player-Prop/Builder-Tipps")

    settled = [settle_tip(tip, results, player_stats) for tip in tips]
    log(f"Counts: {dict(Counter(x['status'] for x in settled))}")
    log(f"Nach Gruppen: {dict(Counter(x['market_group'] for x in settled))}")

    newly_closed = [
        row for row in settled
        if row["status"] in {"win", "loss"} and previous.get(str(row["tip_id"])) not in {"win", "loss"}
    ]
    log(f"Neu abgeschlossen: {len(newly_closed)}")

    saved = sb_upsert("netrattler_settlements", settled, "settlement_id")
    log(f"Settlements gespeichert: {saved}")
    edited_count = 0
    for row in newly_closed:
        update_source_tip(row)
        if edit_original_tip(row):
            edited_count += 1
    if newly_closed:
        log(f"Original-Tipps direkt editiert: {edited_count}/{len(newly_closed)}")

    history = dedup_history(existing + settled)
    save_group_stats(history)
    save_dimension_stats(history)
    send_group_reports(newly_closed, settled, history)
    # ROI-Report nur senden, wenn diesem Lauf tatsaechlich neue Abschluesse zugrunde liegen —
    # sonst wurde er 6-9x/Tag mit identischen Zahlen gepostet (Duplikat-Spam).
    if newly_closed:
        send_roi_report(history)
    else:
        log("ROI-Report uebersprungen (keine neuen Abschluesse in diesem Lauf)")
    log("✅ NETRATTLER Settlement FINAL V21 fertig")


if __name__ == "__main__":
    main()
