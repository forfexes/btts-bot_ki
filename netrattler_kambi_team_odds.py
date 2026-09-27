#!/usr/bin/env python3
"""Multi-brand Kambi observed team-market odds for NETRATTLER.

Uses the same public Kambi offering payload/cache as netrattler_prop_sources.
No market is inferred and no separate-leg prices are multiplied into a combo.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import netrattler_prop_sources as ps

BRANDS = tuple(getattr(ps, "_KAMBI_BRANDS", ["ub", "bs", "888", "nb"]))


def _odds(value: Any) -> Optional[float]:
    try:
        x = float(value or 0)
    except Exception:
        return None
    if x > 100:
        x /= 1000.0
    return round(x, 4) if 1.01 < x <= 100 else None


def _market_text(offer: Dict[str, Any]) -> str:
    crit = offer.get("criterion") or {}
    typ = offer.get("betOfferType") or {}
    parts = [
        crit.get("label"), crit.get("englishLabel"), crit.get("name"),
        offer.get("label"), offer.get("name"), offer.get("description"),
        typ.get("name") if isinstance(typ, dict) else typ,
    ]
    return " | ".join(str(x).strip() for x in parts if str(x or "").strip())


def _line(outcome: Dict[str, Any], text: str) -> Optional[float]:
    raw = outcome.get("line")
    try:
        if raw not in (None, "", 0):
            x = float(raw)
            return x / 1000.0 if abs(x) > 100 else x
    except Exception:
        pass
    m = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)(?!\d)", str(text or ""))
    try:
        return float(m.group(1).replace(",", ".")) if m else None
    except Exception:
        return None


def _offer_for_match(home: str, away: str, brand: str) -> Optional[Dict[str, Any]]:
    event_id = None
    host_used = None
    for host in ps._KAMBI_HOSTS:
        lk = (host, brand)
        if lk not in ps._KAMBI_LIST_CACHE:
            ps._KAMBI_LIST_CACHE[lk] = ps._get_json(
                f"{host}/offering/v2018/{brand}/listView/football/all/all/all/matches.json",
                params={"lang": "en_GB", "market": "GB"},
            )
        data = ps._KAMBI_LIST_CACHE.get(lk)
        if not isinstance(data, dict):
            continue
        for raw in data.get("events") or []:
            event = raw.get("event") or raw
            hn = event.get("homeName") or ""
            an = event.get("awayName") or ""
            name = event.get("name") or event.get("englishName") or ""
            candidate = f"{hn} {an}".strip() or str(name).replace(" - ", " ")
            if ps._teams_match(candidate, home, away):
                event_id = event.get("id")
                host_used = host
                break
        if event_id:
            break
    if not event_id or not host_used:
        return None
    ok = (host_used, brand, str(event_id))
    if ok not in ps._KAMBI_OFFER_CACHE:
        ps._KAMBI_OFFER_CACHE[ok] = ps._get_json(
            f"{host_used}/offering/v2018/{brand}/betoffer/event/{event_id}.json",
            params={"lang": "en_GB", "market": "GB"},
        )
    value = ps._KAMBI_OFFER_CACHE.get(ok)
    return value if isinstance(value, dict) else None


def parse_offer(offer: Dict[str, Any]) -> Dict[str, float]:
    """Parse only explicitly labelled match/team markets."""
    out: Dict[str, float] = {}
    for bet_offer in offer.get("betOffers") or []:
        market = _market_text(bet_offer)
        low = market.lower()
        outcomes = bet_offer.get("outcomes") or []
        first_half = any(t in low for t in ("1st half", "first half", "half time", "halftime", "1h"))
        is_btts = any(t in low for t in ("both teams to score", "both teams score", "both to score", "btts"))
        is_result = any(t in low for t in ("match result", "full time result", "1x2", "3-way", "three way"))
        is_total = any(t in low for t in ("total goals", "goals over/under", "over/under goals", "goal total"))

        # 1X2 full time only.
        if is_result and not first_half:
            for oc in outcomes:
                label = str(oc.get("label") or oc.get("type") or "").strip().lower()
                price = _odds(oc.get("odds"))
                if not price:
                    continue
                if label in {"1", "home", "home win"}:
                    out["home_win"] = max(out.get("home_win", 0), price)
                elif label in {"x", "draw"}:
                    out["draw"] = max(out.get("draw", 0), price)
                elif label in {"2", "away", "away win"}:
                    out["away_win"] = max(out.get("away_win", 0), price)

        # BTTS yes; combo is handled by Kambi's dedicated existing special parser.
        if is_btts:
            combo_context = any(t in low for t in ("over 2.5", "total goals", "and total", "& total"))
            if not combo_context:
                for oc in outcomes:
                    label = str(oc.get("label") or oc.get("type") or "").strip().lower()
                    if label not in {"yes", "ja"} and not label.startswith("yes "):
                        continue
                    price = _odds(oc.get("odds"))
                    if not price:
                        continue
                    key = "btts_yes_ht" if first_half else "btts_yes"
                    out[key] = max(out.get(key, 0), price)

        # O2.5 FT and O1.5 HT, exact observed line only.
        if is_total:
            for oc in outcomes:
                label = str(oc.get("label") or oc.get("type") or "").strip().lower()
                if not (label.startswith("over") or label in {"o", "over"}):
                    continue
                observed_line = _line(oc, f"{market} {label}")
                price = _odds(oc.get("odds"))
                if observed_line is None or not price:
                    continue
                if not first_half and abs(observed_line - 2.5) <= 0.01:
                    out["over_25"] = max(out.get("over_25", 0), price)
                if first_half and abs(observed_line - 1.5) <= 0.01:
                    out["over_15_ht"] = max(out.get("over_15_ht", 0), price)

    # Reuse the mature dedicated special parser for exact combo/HT variants.
    try:
        specials = ps._extract_kambi_team_specials(offer) or {}
        aliases = {
            "btts_yes": "btts_yes",
            "btts_yes_ht": "btts_yes_ht",
            "over_15_ht": "over_15_ht",
            "btts_over25_combo": "btts_over25_yes",
        }
        for src, dst in aliases.items():
            price = _odds(specials.get(src))
            if price:
                out[dst] = max(out.get(dst, 0), price)
    except Exception:
        pass
    return out


def get_multi_brand_team_odds(home: str, away: str) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Merge best explicit price across configured Kambi brands."""
    best: Dict[str, float] = {}
    sources: Dict[str, str] = {}
    for brand in BRANDS:
        try:
            offer = _offer_for_match(home, away, brand)
            parsed = parse_offer(offer or {}) if offer else {}
        except Exception:
            parsed = {}
        for field, price in parsed.items():
            if price > best.get(field, 0):
                best[field] = price
                sources[field] = f"kambi_{brand}"
    return best, sources


__all__ = ["parse_offer", "get_multi_brand_team_odds"]
