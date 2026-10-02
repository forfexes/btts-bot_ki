#!/usr/bin/env python3
"""Production runtime fixes for NETRATTLER.

Keeps REAL_ODDS_ONLY intact while:
- routing 1X2 to the main/AI Telegram chat without moving Goal Hunter;
- reading richer Kambi market metadata so non-scorer player props are not lost;
- augmenting missing Pinnacle team-market prices from observed bookmaker sources;
- preventing any missing BTTS/O2.5 price from falling back to synthetic league defaults;
- making the expensive league-loop skip coverage-aware instead of count-only.
"""
from __future__ import annotations

import inspect
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import netrattler_prop_sources as prop_sources

try:
    import netrattler_free_odds as free_odds
except Exception:  # pragma: no cover - optional adapter
    free_odds = None

try:
    import netrattler_oddspapi as oddspapi
except Exception:  # pragma: no cover - optional adapter
    oddspapi = None

_PRE_INSTALLED = False
_TEAM_ODDS_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_TEAM_ODDS_SOURCES: Dict[Tuple[str, str], Dict[str, str]] = {}
_FALLBACK_LOGGED = 0
_SKIP_DIAG_EMITTED = False


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("name") or value.get("label") or value.get("englishLabel")
            or value.get("description") or ""
        )
    return str(value or "")


def _market_text(offer: Dict[str, Any]) -> str:
    criterion = offer.get("criterion") or {}
    bet_type = offer.get("betOfferType") or {}
    parts = [
        criterion.get("label"), criterion.get("englishLabel"), criterion.get("name"),
        offer.get("label"), offer.get("name"), offer.get("description"),
        _text(bet_type),
    ]
    return " | ".join(str(x).strip() for x in parts if str(x or "").strip())


def _participant(outcome: Dict[str, Any]) -> str:
    value = outcome.get("participant")
    if isinstance(value, dict):
        value = value.get("name") or value.get("label") or value.get("participantName")
    if value:
        return str(value).strip()
    label = str(outcome.get("label") or "").strip()
    low = label.lower()
    if low not in {"over", "under", "yes", "no"} and not low.startswith(("over ", "under ")):
        return label
    return ""


def fetch_kambi_player_props_rich(home: str, away: str, brand: str = "ub") -> List[Dict[str, Any]]:
    """Same public Kambi feed as before, but classify from the full market metadata."""
    props: List[Dict[str, Any]] = []
    event_id = None
    host_used = None

    for host in prop_sources._KAMBI_HOSTS:
        list_key = (host, brand)
        if list_key not in prop_sources._KAMBI_LIST_CACHE:
            prop_sources._KAMBI_LIST_CACHE[list_key] = prop_sources._get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"},
            )
        data = prop_sources._KAMBI_LIST_CACHE.get(list_key)
        if not data:
            continue
        for raw_event in data.get("events") or []:
            event = raw_event.get("event") or raw_event
            name = event.get("name") or event.get("englishName") or ""
            home_name = event.get("homeName") or ""
            away_name = event.get("awayName") or ""
            combo = f"{home_name} {away_name}".strip() or str(name).replace(" - ", " ")
            if prop_sources._teams_match(combo, home, away):
                event_id = event.get("id")
                host_used = host
                break
        if event_id:
            break

    if not event_id or not host_used:
        return []

    offer_key = (host_used, brand, str(event_id))
    if offer_key not in prop_sources._KAMBI_OFFER_CACHE:
        prop_sources._KAMBI_OFFER_CACHE[offer_key] = prop_sources._get_json(
            f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
            params={"lang": "en_GB", "market": "GB"},
        )
    offer = prop_sources._KAMBI_OFFER_CACHE.get(offer_key)
    if not offer:
        return []

    match_name = f"{home} vs {away}"
    for bet_offer in offer.get("betOffers") or []:
        market_text = _market_text(bet_offer)
        category = prop_sources.map_category(market_text)
        if category == "other":
            continue
        for outcome in bet_offer.get("outcomes") or []:
            label = str(outcome.get("label") or "")
            if label.lower() in {"under", "no"} or label.lower().startswith("under "):
                continue
            player = _participant(outcome)
            if not player or not prop_sources._valid_player_candidate(player, home, away):
                continue
            try:
                odds = float(outcome.get("odds", 0)) / 1000.0
            except (TypeError, ValueError):
                continue
            if odds <= 1.20:
                continue
            line = outcome.get("line")
            try:
                line = float(line) / 1000.0 if line not in (None, "", 0) else prop_sources._line_from(label, 0.5)
            except (TypeError, ValueError):
                line = prop_sources._line_from(label, 0.5)
            props.append({
                "player": player,
                "team": "",
                "match": match_name,
                "league": "",
                "market": market_text,
                "category": category,
                "line": float(line),
                "odds": odds,
                "source": f"kambi_{brand}",
                "real_observed_line": True,
            })
    return props


def install_pre_guard() -> None:
    """Must run before importing netrattler_builder_guard."""
    global _PRE_INSTALLED
    if _PRE_INSTALLED:
        return
    prop_sources.fetch_kambi_player_props = fetch_kambi_player_props_rich
    _PRE_INSTALLED = True


def _norm_team(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _match_key(home: Any, away: Any) -> Tuple[str, str]:
    return (_norm_team(home), _norm_team(away))


_FIELD_ALIASES = {
    "home": "home_win",
    "home_win": "home_win",
    "draw": "draw",
    "away": "away_win",
    "away_win": "away_win",
    "btts_yes": "btts_yes",
    "over_25": "over_25",
    "over25": "over_25",
    "btts_yes_ht": "btts_yes_ht",
    "btts_ht_yes": "btts_yes_ht",
    "over_15_ht": "over_15_ht",
    "over15_ht": "over_15_ht",
    "btts_over25_combo": "btts_over25_yes",
    "btts_over25_yes": "btts_over25_yes",
}

_FIELD_MAX = {
    "home_win": 30.0,
    "draw": 30.0,
    "away_win": 30.0,
    "btts_yes": 15.0,
    "over_25": 15.0,
    "btts_yes_ht": 30.0,
    "over_15_ht": 30.0,
    "btts_over25_yes": 60.0,
}

_CORE_FIELDS = ("btts_yes", "over_25", "home_win", "draw", "away_win")
_SPECIAL_FIELDS = ("btts_yes_ht", "over_15_ht", "btts_over25_yes")


def _safe_price(value: Any, field: str) -> Optional[float]:
    try:
        price = float(str(value).replace(",", "."))
    except Exception:
        return None
    if price <= 1.0001 or price > _FIELD_MAX.get(field, 100.0):
        return None
    return round(price, 4)


def _merge_missing(dst: Dict[str, Any], raw: Optional[Dict[str, Any]], source: str, source_map: Dict[str, str]) -> List[str]:
    """Fill only absent fields. Pinnacle remains authoritative when it has a quote."""
    added: List[str] = []
    if not isinstance(raw, dict):
        return added
    src_name = str(raw.get("_source") or source)
    for raw_key, raw_value in raw.items():
        field = _FIELD_ALIASES.get(str(raw_key))
        if not field:
            continue
        if _safe_price(dst.get(field), field) is not None:
            continue
        price = _safe_price(raw_value, field)
        if price is None:
            continue
        dst[field] = price
        source_map[field] = src_name
        added.append(field)
    return added


def _snapshot_rows() -> List[Dict[str, Any]]:
    """Read both legacy list snapshots and V37 {'rows': [...]} snapshots."""
    candidates = [
        os.getenv("NETRATTLER_ODDS_SNAPSHOT", "netrattler_odds_snapshot.json"),
        "odds_snapshot.json",
    ]
    for filename in candidates:
        try:
            path = Path(filename)
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("rows") or []
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            continue
    return []


def _snapshot_for_match(home: str, away: str) -> Dict[str, Any]:
    """Extract observed 1X2/O2.5/BTTS rows from a persisted bookmaker snapshot."""
    out: Dict[str, Any] = {}
    h = _norm_team(home)
    a = _norm_team(away)
    source_for: Dict[str, str] = {}
    for row in _snapshot_rows():
        rh = _norm_team(row.get("home_team"))
        ra = _norm_team(row.get("away_team"))
        if not rh or not ra:
            continue
        home_ok = h == rh or h in rh or rh in h
        away_ok = a == ra or a in ra or ra in a
        if not (home_ok and away_ok):
            continue
        market = str(row.get("market") or "").lower()
        selection = str(row.get("selection") or "").lower()
        raw_line = (row.get("raw") or {}).get("line") if isinstance(row.get("raw"), dict) else None
        price = row.get("odds")
        field = None
        if market in {"1x2", "h2h", "moneyline"}:
            if selection in {"home", "1"}:
                field = "home_win"
            elif selection in {"draw", "x"}:
                field = "draw"
            elif selection in {"away", "2"}:
                field = "away_win"
        elif "btts" in market and selection in {"yes", "y"}:
            field = "btts_yes"
        else:
            try:
                is_25 = "2.5" in market or abs(float(raw_line) - 2.5) <= 0.01
            except Exception:
                is_25 = "2.5" in market
            if is_25 and "over" in selection and ("total" in market or "over" in market):
                field = "over_25"
        if not field:
            continue
        p = _safe_price(price, field)
        if p is None:
            continue
        if p > float(out.get(field) or 0):
            out[field] = p
            source_for[field] = str(row.get("bookmaker") or row.get("source") or "odds_snapshot")
    if out:
        out["_source"] = "odds_snapshot"
        out["_field_sources"] = source_for
    return out


def _caller_likely_candidate() -> bool:
    """Use already-computed model probabilities when called from the main loop."""
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        for _ in range(5):
            if frame is None:
                break
            loc = frame.f_locals
            values: List[float] = []
            for key in ("prob_b", "prob_o"):
                if key not in loc:
                    continue
                try:
                    values.append(float(loc.get(key) or 0))
                except Exception:
                    pass
            ml = loc.get("_ml")
            if isinstance(ml, dict):
                for key in (
                    "btts_ht_pct", "over15_ht_pct", "btts_over25_combo_pct",
                    "home_win_pct", "draw_pct", "away_win_pct",
                ):
                    try:
                        values.append(float(ml.get(key) or 0))
                    except Exception:
                        pass
            if values:
                return max(values) >= float(os.getenv("NETRATTLER_FALLBACK_CANDIDATE_MIN_PROB", "45"))
            frame = frame.f_back
    finally:
        del frame
    return True


def _collect_observed_fallbacks(home: str, away: str, existing: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Collect only real bookmaker prices from independent fallbacks, with caching."""
    key = _match_key(home, away)
    cached = _TEAM_ODDS_CACHE.get(key)
    if cached is not None:
        return dict(cached), dict(_TEAM_ODDS_SOURCES.get(key, {}))

    out: Dict[str, Any] = {}
    source_map: Dict[str, str] = {}

    snap = _snapshot_for_match(home, away)
    field_sources = snap.pop("_field_sources", {}) if isinstance(snap, dict) else {}
    added = _merge_missing(out, snap, "odds_snapshot", source_map)
    for field in added:
        if field in field_sources:
            source_map[field] = field_sources[field]

    if free_odds is not None:
        for name, fn in (
            ("1xbet", lambda: free_odds.get_1xbet(home, away)),
            ("kambi_unibet", lambda: free_odds.get_kambi(home, away)),
            ("odds_api_net", lambda: free_odds.get_odds_api_net(home, away, None)),
        ):
            try:
                _merge_missing(out, fn() or {}, name, source_map)
            except Exception:
                continue
            if all(_safe_price(out.get(f), f) is not None or _safe_price(existing.get(f), f) is not None for f in _CORE_FIELDS):
                break

    likely = _caller_likely_candidate()

    if likely and any(_safe_price(existing.get(f), f) is None and _safe_price(out.get(f), f) is None for f in _SPECIAL_FIELDS):
        for brand in getattr(prop_sources, "_KAMBI_BRANDS", ["ub", "bs", "888", "nb"]):
            try:
                raw = prop_sources.fetch_kambi_team_specials(home, away, brand=brand) or {}
            except Exception:
                raw = {}
            _merge_missing(out, raw, f"kambi_{brand}", source_map)
            if all(_safe_price(out.get(f), f) is not None or _safe_price(existing.get(f), f) is not None for f in _SPECIAL_FIELDS):
                break

    enable_oddspapi = os.getenv("NETRATTLER_ENABLE_ODDSPAPI_RUNTIME", "false").lower() in {"1", "true", "yes", "on"}
    unresolved = [
        f for f in (_CORE_FIELDS + _SPECIAL_FIELDS)
        if _safe_price(existing.get(f), f) is None and _safe_price(out.get(f), f) is None
    ]
    _oddspapi_configured = bool(
        oddspapi is not None
        and getattr(oddspapi, "_keys", lambda: [])()
    )
    if likely and unresolved and enable_oddspapi and _oddspapi_configured:
        try:
            raw = oddspapi.get_odds_for_match(home, away, None) or {}
            _merge_missing(out, raw, "oddspapi", source_map)
        except Exception:
            pass

    _TEAM_ODDS_CACHE[key] = dict(out)
    _TEAM_ODDS_SOURCES[key] = dict(source_map)
    return dict(out), dict(source_map)


def _install_team_market_quote_guard(bot) -> None:
    """Augment missing Pinnacle prices from real sources, then fail closed."""
    original = getattr(bot, "get_pinnacle_match_odds", None)
    if not callable(original) or getattr(original, "_ntr_team_market_quote_guard", False):
        return

    def guarded_get_pinnacle_match_odds(home: str, away: str, *args, **kwargs):
        global _FALLBACK_LOGGED
        raw_original = original(home, away, *args, **kwargs)
        safe = dict(raw_original) if isinstance(raw_original, dict) else {}

        source_map: Dict[str, str] = {}
        for field in _FIELD_MAX:
            if _safe_price(safe.get(field), field) is not None:
                source_map[field] = "pinnacle"

        try:
            fallback, fallback_sources = _collect_observed_fallbacks(home, away, safe)
        except Exception:
            fallback, fallback_sources = {}, {}

        added = _merge_missing(safe, fallback, "observed_fallback", source_map)
        for field in added:
            if fallback_sources.get(field):
                source_map[field] = fallback_sources[field]

        if safe.get("btts_yes_ht") and source_map.get("btts_yes_ht") not in (None, "pinnacle"):
            safe["_btts_ht_source"] = source_map["btts_yes_ht"]
        if safe.get("over_15_ht") and source_map.get("over_15_ht") not in (None, "pinnacle"):
            safe["_over15_ht_source"] = source_map["over_15_ht"]
        if safe.get("btts_over25_yes") and source_map.get("btts_over25_yes") not in (None, "pinnacle"):
            safe["_combo_source"] = source_map["btts_over25_yes"]

        if _safe_price(safe.get("btts_yes"), "btts_yes") is None:
            safe["btts_yes"] = 1.0
            safe["_btts_quote_missing"] = True
        if _safe_price(safe.get("over_25"), "over_25") is None:
            safe["over_25"] = 1.0
            safe["_over25_quote_missing"] = True

        safe["_ntr_field_sources"] = source_map

        if added and _FALLBACK_LOGGED < int(os.getenv("NETRATTLER_FALLBACK_LOG_LIMIT", "20")):
            try:
                detail = ", ".join(f"{f}={source_map.get(f, '?')}" for f in added)
                bot.log(f"   ♻️ Real-Odds Fallback {home} vs {away}: {detail}")
                _FALLBACK_LOGGED += 1
            except Exception:
                pass
        return safe

    guarded_get_pinnacle_match_odds._ntr_team_market_quote_guard = True
    guarded_get_pinnacle_match_odds._ntr_original = original
    bot.get_pinnacle_match_odds = guarded_get_pinnacle_match_odds


def _install_tip_source_attribution(bot) -> None:
    """Replace hard-coded Pinnacle attribution when a real fallback quote was used."""
    original = getattr(bot, "enrich_pinnacle_tip", None)
    if not callable(original) or getattr(original, "_ntr_source_attribution", False):
        return

    def enriched(tip_dict, home, away, *args, **kwargs):
        result = original(tip_dict, home, away, *args, **kwargs)
        try:
            sources = _TEAM_ODDS_SOURCES.get(_match_key(home, away), {})
            market = str(tip_dict.get("market") or "").lower()
            selection = str(tip_dict.get("tip") or tip_dict.get("selection") or "").strip().lower()
            field = None
            if market == "btts":
                field = "btts_yes"
            elif market in {"over25", "over_25"}:
                field = "over_25"
            elif market == "1x2":
                field = {"1": "home_win", "x": "draw", "2": "away_win"}.get(selection)
            source = sources.get(field or "")
            if source and source != "pinnacle":
                tip_dict["_source"] = source
                reasoning = str(tip_dict.get("reasoning") or "")
                if reasoning.startswith("Pinnacle "):
                    tip_dict["reasoning"] = reasoning.replace("Pinnacle ", f"{source} ", 1)
        except Exception:
            pass
        return result

    enriched._ntr_source_attribution = True
    bot.enrich_pinnacle_tip = enriched


def _coverage_counts_from_caller() -> Tuple[Optional[Dict[str, int]], Optional[int]]:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        for _ in range(6):
            if frame is None:
                break
            tips = frame.f_locals.get("tips_by_market")
            pin_count = frame.f_locals.get("pinnacle_tips_count")
            if isinstance(tips, dict) and pin_count is not None:
                counts = {}
                for key, rows in tips.items():
                    try:
                        counts[str(key)] = len(rows or [])
                    except Exception:
                        counts[str(key)] = 0
                try:
                    return counts, int(pin_count)
                except Exception:
                    return counts, None
            frame = frame.f_back
    finally:
        del frame
    return None, None


def _install_coverage_aware_skip(bot) -> None:
    """Skip league fallback only when every required team market has coverage."""
    original = getattr(bot, "env", None)
    if not callable(original) or getattr(original, "_ntr_coverage_skip", False):
        return

    def guarded_env(name: str, default: str = "") -> str:
        global _SKIP_DIAG_EMITTED
        if name != "FORCE_LEAGUE_LOOP":
            return original(name, default)

        explicit = os.getenv("FORCE_LEAGUE_LOOP", "").strip()
        if explicit.lower() in {"1", "true", "yes", "on"}:
            return explicit

        counts, pin_count = _coverage_counts_from_caller()
        if counts is None:
            return "true"

        required = [
            x.strip() for x in os.getenv(
                "NETRATTLER_SKIP_REQUIRED_MARKETS",
                "btts,over25,combo,btts_ht,over15_ht,1x2",
            ).split(",") if x.strip()
        ]
        min_each = max(1, int(os.getenv("NETRATTLER_SKIP_MIN_PER_MARKET", "1")))
        min_total = max(1, int(os.getenv("NETRATTLER_SKIP_TOTAL_MIN", "10")))
        missing = [m for m in required if int(counts.get(m, 0)) < min_each]
        allow_skip = (pin_count or 0) >= min_total and not missing

        if not _SKIP_DIAG_EMITTED:
            try:
                summary = ", ".join(f"{m}={counts.get(m, 0)}" for m in required)
                if allow_skip:
                    bot.log(f"⚡ Coverage-Skip erlaubt: {summary} · total={pin_count}")
                else:
                    bot.log(
                        f"🔎 Liga-Fallback bleibt AN: {summary} · total={pin_count} · "
                        f"fehlend={','.join(missing) or 'total'}"
                    )
            except Exception:
                pass
            _SKIP_DIAG_EMITTED = True

        return "false" if allow_skip else "true"

    guarded_env._ntr_coverage_skip = True
    guarded_env._ntr_original = original
    bot.env = guarded_env


def install_bot(bot) -> None:
    """Install production guards after importing btts_bot."""
    if hasattr(bot, "TELEGRAM_GROUPS"):
        bot.TELEGRAM_GROUPS["1x2"] = getattr(bot, "TELEGRAM_CHAT_ID", "")
    _install_team_market_quote_guard(bot)
    _install_tip_source_attribution(bot)
    _install_coverage_aware_skip(bot)
