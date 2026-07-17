#!/usr/bin/env python3
"""Capture compact opening/current/closing odds and calculate CLV safely.

The source chain is inherited from ``netrattler_odds_harvester``:
Pinnacle -> The Odds API -> OddsHarvester/OddsPortal -> Bet365 best effort ->
Betfair.  Failures never stop the next source.
"""
from __future__ import annotations

import argparse
import json
import requests
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from netrattler_learning_engine import SupabaseRest, log, norm, stable_hash, to_float
from netrattler_odds_harvester import collect_live_all


def event_key(match_date: Any, home: Any, away: Any) -> str:
    return stable_hash(str(match_date or "")[:10], norm(home), norm(away))[:40]


def compact_rows(rows: Sequence[Mapping[str, Any]], snapshot_type: str) -> List[Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    captured_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        odds = to_float(row.get("odds"))
        if odds <= 1:
            continue
        home = str(row.get("home_team") or "")
        away = str(row.get("away_team") or "")
        match_date = str(row.get("match_date") or "")[:10] or None
        market = norm(row.get("market") or "unknown")
        selection = norm(row.get("selection") or "unknown")
        bookmaker = norm(row.get("bookmaker") or row.get("source") or "unknown")
        key = event_key(match_date, home, away)
        snapshot_id = stable_hash(key, market, selection, bookmaker, snapshot_type)[:48]
        compact = {
            "snapshot_id": snapshot_id,
            "event_key": key,
            "match_date": match_date,
            "home_team": home,
            "away_team": away,
            "market": market,
            "selection": selection,
            "line": to_float((row.get("raw") or {}).get("line"), 0) or None,
            "bookmaker": bookmaker,
            "odds": round(odds, 4),
            "snapshot_type": snapshot_type,
            "source": str(row.get("source") or bookmaker),
            "captured_at": captured_at,
            "expires_at": None,
        }
        # Keep the best quote per bookmaker/snapshot key.
        old = output.get(snapshot_id)
        if old is None or compact["odds"] > old["odds"]:
            output[snapshot_id] = compact
    return list(output.values())


def _split_match(value: Any) -> Tuple[str, str]:
    text = str(value or "")
    for sep in (" vs ", " v ", " - ", "–"):
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip(), right.strip()
    return "", ""


def _market_candidates(tip: Mapping[str, Any]) -> List[str]:
    market = norm(tip.get("market") or tip.get("market_name") or "")
    aliases = {
        "btts": ["btts", "both teams to score"],
        "over25": ["totals", "totals 2 5", "over 2 5"],
        "combo": ["btts", "totals"],
        "btts ht": ["btts ht", "1st half btts"],
        "over15 ht": ["1st half totals", "over 1 5 ht"],
    }
    return aliases.get(market, [market])


def _selection_candidates(tip: Mapping[str, Any]) -> List[str]:
    selection = norm(tip.get("tip") or tip.get("selection") or "")
    if selection in {"yes", "btts yes"}:
        return ["yes", "both teams to score"]
    if "over" in selection:
        return [selection, "over", "over 2 5", "over 1 5"]
    return [selection] if selection else []


def calculate_clv(db: SupabaseRest) -> List[Dict[str, Any]]:
    closing = db.get(
        "netrattler_odds_snapshots", filters={"snapshot_type": "eq.closing"},
        order="captured_at.desc", limit_total=50000,
    )
    tips: List[Dict[str, Any]] = []
    for table in ("tips", "prop_picks", "netrattler_builder_picks"):
        tips.extend(db.get(table, limit_total=100000))
    rows: List[Dict[str, Any]] = []
    for tip in tips:
        tip_id = str(tip.get("tip_id") or tip.get("id") or "")
        if not tip_id:
            continue
        home = str(tip.get("home_team") or "")
        away = str(tip.get("away_team") or "")
        if not home or not away:
            home, away = _split_match(tip.get("match"))
        if not home or not away:
            continue
        date_text = str(tip.get("date") or tip.get("tip_date") or "")[:10]
        key = event_key(date_text, home, away)
        markets = _market_candidates(tip)
        selections = _selection_candidates(tip)
        matches = []
        for row in closing:
            if row.get("event_key") != key:
                continue
            row_market = norm(row.get("market"))
            row_selection = norm(row.get("selection"))
            if markets and not any(x in row_market or row_market in x for x in markets):
                continue
            if selections and not any(x in row_selection or row_selection in x for x in selections):
                continue
            matches.append(row)
        if not matches:
            continue
        # Sharp source preferred, then highest available closing quote.
        matches.sort(key=lambda x: ("pinnacle" in norm(x.get("bookmaker")), to_float(x.get("odds"))), reverse=True)
        close = matches[0]
        opening_odds = to_float(tip.get("odds") or tip.get("bet365_quote") or tip.get("oddsYes"))
        closing_odds = to_float(close.get("odds"))
        if opening_odds <= 1 or closing_odds <= 1:
            continue
        rows.append({
            "clv_id": stable_hash(tip_id, close.get("bookmaker"))[:48],
            "tip_id": tip_id,
            "event_key": key,
            "market": norm(tip.get("market")),
            "selection": norm(tip.get("tip") or tip.get("selection")),
            "bookmaker": close.get("bookmaker"),
            "opening_odds": round(opening_odds, 4),
            "closing_odds": round(closing_odds, 4),
            "clv": round((opening_odds / closing_odds) - 1.0, 6),
            "captured_at": close.get("captured_at") or datetime.now(timezone.utc).isoformat(),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-type", choices=["opening", "current", "closing"], default="current")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--clv-only", action="store_true")
    parser.add_argument("--cleanup-days", type=int, default=45)
    args = parser.parse_args()
    db = SupabaseRest()
    if not args.clv_only:
        raw = collect_live_all(args.date)
        compact = compact_rows(raw, args.snapshot_type)
        ok, fail = db.upsert("netrattler_odds_snapshots", compact, "snapshot_id")
        log(
            f"ODDS {args.snapshot_type}: raw={len(raw)} compact={len(compact)} "
            f"saved={ok} failed={fail}"
        )

    run_clv = args.clv_only or args.snapshot_type == "closing"
    if run_clv:
        clv = calculate_clv(db)
        ok, fail = db.upsert("netrattler_clv_events", clv, "clv_id")
        log(f"CLV: calculated={len(clv)} saved={ok} failed={fail}")
    else:
        log(f"CLV deferred until closing snapshot (current={args.snapshot_type})")

    run_cleanup = run_clv and db.enabled and args.cleanup_days > 0
    if run_cleanup:
        try:
            response = requests.post(
                f"{db.url}/rest/v1/rpc/netrattler_cleanup_odds_snapshots",
                headers=db.headers(),
                json={"retention_days": args.cleanup_days},
                timeout=20,
            )
            if response.ok:
                log(f"Odds retention cleanup: {response.text[:120]}")
        except Exception as exc:
            log(f"Odds retention cleanup skipped: {exc}", "WARN")


if __name__ == "__main__":
    main()
