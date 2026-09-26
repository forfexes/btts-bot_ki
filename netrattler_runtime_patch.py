#!/usr/bin/env python3
"""Small production runtime fixes that do not change NETRATTLER's core model policy.

Keeps REAL_ODDS_ONLY intact while:
- routing 1X2 to the main/AI Telegram chat without moving Goal Hunter;
- reading richer Kambi market metadata so non-scorer player props are not lost.
"""
from __future__ import annotations

from typing import Any, Dict, List

import netrattler_prop_sources as prop_sources

_PRE_INSTALLED = False


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
    # Some Kambi feeds put the player in outcome label and the threshold in line.
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


def install_bot(bot) -> None:
    """Route only 1X2 to the AI/main chat; Goal Hunter remains Late Goals."""
    if hasattr(bot, "TELEGRAM_GROUPS"):
        bot.TELEGRAM_GROUPS["1x2"] = getattr(bot, "TELEGRAM_CHAT_ID", "")
